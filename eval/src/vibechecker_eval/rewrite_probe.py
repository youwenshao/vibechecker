"""Train and compare source-origin probes using only the guarded head-training partition."""

import argparse
import csv
import io
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from contextlib import ExitStack
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from vibechecker_engine.rewrite_probe import RewriteOriginProbe
from vibechecker_engine.signals import ENCODER_VECTOR_VERSION, Encoder
from vibechecker_engine.stacker import save_artifact
from vibechecker_engine.text import count_words

from .encoder_probe import _linear, _source_folds, collect, open_cache, training_sample
from .loaders import Example, examples, fingerprint
from .registry import fetch, registry, select, sha256
from .rewrite_data import load_rewrite_pairs, rewrite_provenance
from .source_groups import human_source_aliases


@dataclass(frozen=True)
class Row:
    id: str
    group: str
    label: int
    domain: str
    attack: str
    generator: str
    vector: np.ndarray
    grade: str | None = None


def _identity_summary(document_ids, source_groups):
    groups = sorted(set(source_groups))
    ids = sorted(set(document_ids))
    return {
        "documents": len(ids),
        "groups": len(groups),
        "document_ids_sha256": fingerprint(" ".join(ids)),
        "group_ids_sha256": fingerprint(" ".join(groups)),
    }


def _members(rows):
    return _identity_summary((r.id for r in rows), (r.group for r in rows))


def _essay_grades(rows, datasets, cache):
    by_id = {}
    for dataset in datasets:
        if dataset.id not in {"asap", "ellipse"}:
            continue
        permitted = {r.id for r in rows if r.domain == dataset.id and r.label == 0}
        with ExitStack() as stack:
            path = fetch(dataset.artifacts[0], cache)
            if dataset.id == "asap":
                archive = stack.enter_context(zipfile.ZipFile(path))
                content = stack.enter_context(archive.open("ASAP_2_Final_github_train.csv"))
                stream = stack.enter_context(io.TextIOWrapper(content, encoding="utf-8-sig"))
                field = "grade_level"
            else:
                stream = stack.enter_context(path.open(encoding="utf-8-sig", newline=""))
                field = "grade"
            for item in csv.DictReader(stream):
                key = fingerprint(item["full_text"])
                if key in permitted:
                    grade = item[field].strip()
                    match = re.fullmatch(
                        r"(?:grade\s*)?(\d{1,2})(?:\.0+)?", grade, flags=re.IGNORECASE
                    )
                    by_id[key] = (
                        str(int(match[1])) if match and 1 <= int(match[1]) <= 12 else "unknown"
                    )
    return [replace(r, grade=by_id[r.id]) if r.id in by_id else r for r in rows]


def _load_general(args, source, profile):
    datasets = select(registry(), source["manifest"], commercial_only=False)
    manifest = {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in datasets
    }
    if manifest != source["manifest"]:
        raise ValueError("Pinned general corpus differs from the probe report")
    aliases = human_source_aliases(examples(datasets, args.cache))
    if aliases.summary() != source["source_aliases"]:
        raise ValueError("General source aliases differ from the guarded report")
    caps = source["sampling_caps"]
    chosen = training_sample(
        examples(datasets, args.cache),
        count_words,
        source_aliases=aliases,
        seed=source["seed"],
        human_cap=caps["human"],
        clean_cap=caps["clean_machine"],
        attack_cap=caps["attacked_machine"],
    )
    db = open_cache(args.general_features, profile, cached_only=True)
    try:
        values = collect(chosen, db, None, cached_only=True)
    finally:
        db.close()
    rows = []
    for doc, group, label, stratum, vector in values:
        dataset, generator, attack = stratum.rsplit("/", 2)
        rows.append(Row(doc, group, label, dataset, attack, generator, vector))
    members = _members(rows)
    if (
        members["group_ids_sha256"] != source["fit_group_ids_sha256"]
        or members["document_ids_sha256"] != source["fit_document_ids_sha256"]
    ):
        raise ValueError("General numeric rows differ from the guarded report")
    return _essay_grades(rows, datasets, args.cache)


def _load_pairs(args, profile, checkpoint):
    pairs = load_rewrite_pairs(args.cohort, role="head", commercial_only=False)
    provenance = rewrite_provenance(args.cohort)
    chosen = []
    for pair in pairs:
        gid = fingerprint(pair.source_group)
        for item, label, attack in (
            (pair.human, 0, "paraphrase"),
            (pair.machine, 1, "paraphrase"),
            (pair.clean_human, 0, "none"),
            (pair.clean_machine, 1, "none"),
        ):
            if fingerprint(item.text) != item.id:
                raise ValueError("Supplement text differs from its verified document identity")
            ex = Example(
                item.text,
                label,
                pair.domain,
                "train",
                pair.domain,
                generator=item.generator,
                attack=attack,
                source_group=pair.source_group,
            )
            chosen.append((item.id, gid, ex))
    if not chosen:
        raise ValueError("The supplement contains no eligible head-training pairs")
    # Bind the cache to this extraction profile. The corpus loader verifies the
    # supplement membership on every invocation, even when all vectors are cached.
    db = open_cache(args.features, profile, cached_only=args.cached_only)

    def encoder():
        model = Encoder.load(checkpoint, profile["backend"])
        model.batch_windows = 1 if profile["quick_prefill"] == 64 else 2
        return model

    try:
        values = collect(chosen, db, encoder, cached_only=args.cached_only)
    finally:
        db.close()
    if len(values) != len(chosen):
        raise ValueError("An admitted release-length supplement document was refused")
    return [
        Row(doc, group, item.label, item.genre, item.attack, item.generator, vector)
        for (doc, group, item), (_, _, _, _, vector) in zip(chosen, values, strict=True)
    ], provenance


def _part(group, seed):
    grouped = np.array(group)
    dev = _source_folds(grouped, seed, "probe-validation", 5) == 0
    calibration = (~dev) & (_source_folds(grouped, seed, "origin-calibration", 4) == 0)
    return np.where(dev, 2, np.where(calibration, 1, 0))


def paired_origin_membership(pairs, seed):
    """Reconstruct the training study's document and source digests from authenticated head pairs."""
    if not pairs or any(pair.role != "head" for pair in pairs):
        raise ValueError("Only authenticated head pairs can define probe membership")
    groups = [fingerprint(pair.source_group) for pair in pairs]
    partitions = _part(groups, seed)
    roles = {}
    for index, name in enumerate(("fit", "calibration", "development")):
        items = [pair for pair, role in zip(pairs, partitions, strict=True) if role == index]
        ids = [
            doc.id
            for pair in items
            for doc in (pair.human, pair.machine, pair.clean_human, pair.clean_machine)
        ]
        members = _identity_summary(ids, (fingerprint(pair.source_group) for pair in items))
        if members["documents"] != 4 * len(items) or members["groups"] != len(items):
            raise ValueError("Authenticated paired probe members must be unique")
        roles[name] = members
    return roles


def _cohorts(general, supplement, seed):
    # A text claimed under conflicting sources or labels cannot inform any role.
    seen = {}
    ambiguous = set()
    for r in [*general, *supplement]:
        prev = seen.setdefault(r.id, (r.group, r.label))
        if prev != (r.group, r.label):
            ambiguous.update((r.group, prev[0]))
    parts = []
    for family in (general, supplement):
        rows = [r for r in family if r.group not in ambiguous]
        roles = _part([r.group for r in rows], seed)
        parts.append(
            [[r for r, role in zip(rows, roles, strict=True) if role == i] for i in range(3)]
        )
    left, right = parts
    sources = [{r.group for r in [*left[i], *right[i]]} for i in range(3)]
    if any(sources[i] & sources[j] for i in range(3) for j in range(i)):
        raise ValueError("Source groups overlap between fitting, calibration and development")
    return left, right, ambiguous


def _matrix(rows):
    return np.stack([r.vector for r in rows])


def _labels(rows):
    return np.asarray([r.label for r in rows])


def _merged(general, supplement):
    # Identical clean parents may already be drawn in the ordinary head corpus.
    return list({r.id: r for r in [*general, *supplement]}.values())


def _sigmoid(margin, labels, seed):
    return make_pipeline(
        StandardScaler(), LogisticRegression(C=2, max_iter=600, random_state=seed)
    ).fit(margin[:, None], labels)


def fit_candidates(general, supplement, seed):
    gen_train, gen_cal, _ = general
    paired_train, paired_cal, _ = supplement
    base = make_pipeline(StandardScaler(), _linear(0.1, seed)).fit(
        _matrix(gen_train), _labels(gen_train)
    )
    rewrites = [r for r in paired_train if r.attack == "paraphrase"]
    projection = make_pipeline(
        StandardScaler(),
        PCA(n_components=min(32, len(rewrites) - 1), whiten=True, random_state=seed),
    )
    reduced = projection.fit_transform(_matrix(rewrites))
    pairs = defaultdict(dict)
    for row, vec in zip(rewrites, reduced, strict=True):
        if row.label in pairs[row.group]:
            raise ValueError("Expected one rewritten document per origin in each source group")
        pairs[row.group][row.label] = vec
    if any(set(pair) != {0, 1} for pair in pairs.values()):
        raise ValueError("A supervised origin contrast requires both source authors")
    # Within-source differences remove the shared prompt/topic from the target.
    difference = np.stack([pair[1] - pair[0] for pair in pairs.values()])
    contrasts = np.vstack((difference, -difference))
    contrast = LogisticRegression(C=0.1, fit_intercept=False, random_state=seed, max_iter=600).fit(
        contrasts, np.repeat([1, 0], len(difference))
    )
    cal_origin = [r for r in paired_cal if r.attack == "paraphrase"]
    margins = contrast.decision_function(projection.transform(_matrix(cal_origin)))
    origin_cal = _sigmoid(margins, _labels(cal_origin), seed)
    tr = _merged(gen_train, paired_train)
    ca = _merged(gen_cal, paired_cal)
    gate = make_pipeline(
        StandardScaler(),
        PCA(n_components=min(32, len(tr) - 1), whiten=True, random_state=seed),
        _linear(0.1, seed),
    )
    gate.fit(_matrix(tr), [int(r.attack == "paraphrase") for r in tr])
    gate_cal = _sigmoid(
        gate.decision_function(_matrix(ca)), [int(r.attack == "paraphrase") for r in ca], seed
    )
    model = RewriteOriginProbe(base, projection, contrast, origin_cal, gate, gate_cal, False)
    return {"general": base, "mixture": model, "downward": replace(model, downward_only=True)}


def _summary(y, p):
    residual = y - p
    bins = np.clip((p * 10).astype(int), 0, 9)
    return {
        "n": len(y),
        "human_n": int(np.sum(y == 0)),
        "machine_n": int(np.sum(y == 1)),
        "false_positives_at_half": int(np.sum((y == 0) & (p >= 0.5))),
        "false_negatives_at_half": int(np.sum((y == 1) & (p < 0.5))),
        "auc": float(roc_auc_score(y, p)) if len(set(y)) == 2 else None,
        "log_loss": float(np.mean(_loss(y, p))),
        "brier": float(np.mean(residual**2)),
        "ece_10_bins": float(
            np.abs(np.bincount(bins, weights=residual, minlength=10)).sum() / len(y)
        ),
    }


def _loss(y, p):
    return -np.log(np.clip(np.where(y == 1, p, 1 - p), 1e-12, 1))


def _paired(y, base, candidate, groups, seed):
    # Resample sources, including both origins and every variant in each draw.
    _, inverse = np.unique(groups, return_inverse=True)
    n = int(inverse.max()) + 1
    loss = _loss(y, candidate) - _loss(y, base)
    error = ((candidate >= 0.5) != y).astype(float) - ((base >= 0.5) != y)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(500):
        w = np.bincount(rng.integers(n, size=n), minlength=n)[inverse]
        draws.append([np.average(loss, weights=w), np.average(error, weights=w)])
    low, high = np.quantile(draws, [0.025, 0.975], axis=0)
    return {
        "log_loss_delta_95": [float(low[0]), float(high[0])],
        "error_rate_delta_95": [float(low[1]), float(high[1])],
    }


def compare(models, general_dev, supplement_dev, seed):
    supplemental = [r for r in supplement_dev if r.attack == "paraphrase"]
    strata = {
        "origin": supplemental,
        "paired_clean": [r for r in supplement_dev if r.attack == "none"],
        "general": general_dev,
        "human": [r for r in general_dev if r.label == 0],
        "clean_machine": [r for r in general_dev if r.label and r.attack == "none"],
        "regular_rewrites": [r for r in general_dev if r.attack in ("synonym", "paraphrase")],
    }
    families = {r.group: r.generator for r in supplemental if r.label}
    for r in supplemental:
        strata.setdefault("origin_family/" + families[r.group], []).append(r)
        strata.setdefault("origin_domain/" + r.domain, []).append(r)
        if r.label:
            strata.setdefault("machine_family/" + r.generator, []).append(r)
    for r in strata["human"]:
        strata.setdefault("human_corpus/" + r.domain, []).append(r)
        if r.grade is not None:
            strata.setdefault(f"human_grade/{r.domain}/{r.grade}", []).append(r)
    report = {}
    for key, items in strata.items():
        if not items:
            raise ValueError(f"Cannot evaluate empty development stratum {key}")
        y = _labels(items)
        x = _matrix(items)
        g = [r.group for r in items]
        probabilities = {name: model.predict_proba(x)[:, 1] for name, model in models.items()}
        report[key] = {
            "sources": len(set(g)),
            "scores": {k: _summary(y, p) for k, p in probabilities.items()},
            "paired": {
                k: _paired(y, probabilities["general"], p, g, seed)
                for k, p in probabilities.items()
                if k != "general"
            },
        }
    return report


def _qualifies(name, scores):
    domains = [s["scores"] for k, s in scores.items() if k.startswith("origin_domain/")]
    humans = [
        s["scores"] for k, s in scores.items() if k == "human" or k.startswith("human_corpus/")
    ]
    return (
        {"origin_domain/books", "origin_domain/news"}.issubset(scores)
        and all(r[name]["log_loss"] < r["general"]["log_loss"] for r in domains)
        and scores["origin"]["paired"][name]["log_loss_delta_95"][1] < 0
        and all(
            r[name]["false_positives_at_half"] <= r["general"]["false_positives_at_half"]
            for r in humans
        )
        and scores["clean_machine"]["paired"][name]["error_rate_delta_95"][1] <= 0.01
    )


def train_study(source, gen, supplement, supplement_info):
    seed = source["seed"]
    if supplement_info["original_source_aliases"] != source["source_aliases"]:
        raise ValueError("Supplement is pinned to a different general source quarantine")
    supplemental_aliases = set(supplement_info["new_human_alias_group_hashes"])
    newly_excluded = [r for r in gen if r.group in supplemental_aliases]
    gen = [r for r in gen if r.group not in supplemental_aliases]
    general, paired, ambiguities = _cohorts(gen, supplement, seed)
    with threadpool_limits(limits=2):
        models = fit_candidates(general, paired, seed)
        scores = compare(models, general[2], paired[2], seed)
    candidates = [k for k in ("mixture", "downward") if _qualifies(k, scores)]
    # Prefer the protective direction if both losses match.
    selected = min(
        candidates,
        key=lambda k: (scores["origin"]["scores"][k]["log_loss"], k != "downward"),
        default=None,
    )
    roles = {
        k: _members(_merged(general[i], paired[i]))
        for i, k in enumerate(("fit", "calibration", "development"))
    }
    used = _merged([*general[0], *general[1]], [*paired[0], *paired[1]])
    members = _members(used)
    supplement_metadata = {
        "scheme": "rewrite-origin-paired-paraphrase-v1",
        "role": "head",
        "commercial_only": False,
        "cohort": json.loads(json.dumps(supplement_info, sort_keys=True)),
        "additional_cross_source_conflict_groups": len(ambiguities),
        "general_excluded_by_supplement": _members(newly_excluded),
        "supervised_roles": roles,
        "paired_roles": {
            k: _members(paired[i]) for i, k in enumerate(("fit", "calibration", "development"))
        },
    }
    provenance = {
        k: source[k]
        for k in (
            "backend",
            "quick_prefill",
            "vector_version",
            "encoder_files",
            "encoder_sha256",
            "manifest",
            "source_aliases",
            "commercial_only",
            "partition",
            "head_fold",
            "seed",
        )
    }
    provenance.update(
        fit_document_ids_sha256=members["document_ids_sha256"],
        fit_group_ids_sha256=members["group_ids_sha256"],
        fit_counts=dict(
            sorted(Counter(f"{r.domain}/{r.generator}/{r.attack}" for r in used).items())
        ),
        rewrite_supplement=supplement_metadata,
        selection={"selected": selected, "compared": ["mixture", "downward"]},
    )
    model = models.get(selected)
    if model is not None:
        model.training_provenance_ = provenance
    return model, {"provenance": provenance, "scores": scores, "selected": selected}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--cohort", required=True, type=Path)
    cli.add_argument("--general-features", required=True, type=Path)
    cli.add_argument("--general-report", required=True, type=Path)
    cli.add_argument("--features", required=True, type=Path)
    cli.add_argument("--cache", type=Path, default=Path("eval/.cache"))
    cli.add_argument("--cached-only", action="store_true")
    cli.add_argument("--report", required=True, type=Path)
    cli.add_argument("--model-out", required=True, type=Path)
    args = cli.parse_args(argv)
    paths = (
        args.cohort,
        args.features,
        args.general_features,
        args.general_report,
        args.report,
        args.model_out,
    )
    if (
        len({p.resolve() for p in paths}) != len(paths)
        or args.model_out.exists()
        or args.report.exists()
    ):
        cli.error("Use distinct input and output paths, and new model and report names")
    source = json.loads(args.general_report.read_text(encoding="utf8"))
    checkpoint = Path(os.environ["VIBECHECKER_ENCODER"])
    profile = {
        k: source[k] for k in ("encoder_files", "backend", "quick_prefill", "vector_version")
    }
    actual = {
        p.name: sha256(p)
        for p in checkpoint.iterdir()
        if p.is_file() and p.suffix in {".json", ".safetensors", ".txt", ".model", ".jinja"}
    }
    if (
        source["partition"] != "train"
        or source["head_fold"] != 0
        or source["commercial_only"] is not False
        or profile["vector_version"] != ENCODER_VECTOR_VERSION
        or actual != profile["encoder_files"]
        or profile["backend"] != os.environ["VIBECHECKER_BACKEND"]
        or profile["quick_prefill"] != int(os.environ["VIBECHECKER_QUICK_PREFILL"])
    ):
        raise ValueError("Encoder profile or licensing scope differs from the guarded reference")
    gen = _load_general(args, source, profile)
    supplement, supplement_info = _load_pairs(args, profile, checkpoint)
    model, report = train_study(source, gen, supplement, supplement_info)
    report["general_report_sha256"] = sha256(args.general_report)
    if model is not None:
        save_artifact(model, args.model_out)
        report["model_sha256"] = sha256(args.model_out)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8")
    print(
        json.dumps({"selected": report["selected"], "model_sha256": report.get("model_sha256")}),
        flush=True,
    )


if __name__ == "__main__":
    main()
