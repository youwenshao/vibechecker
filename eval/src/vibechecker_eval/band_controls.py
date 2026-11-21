"""Fit one global high-band cutoff on independent, human calibration essays."""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.stats import binom
from threadpoolctl import threadpool_limits

from .deep_runner import _progress
from .loaders import examples, fingerprint
from .refit import append_probe
from .refit_cache import runtime_identity, same_numeric_runtime
from .registry import registry, select, sha256
from .source_groups import human_source_aliases, source_key

CAPS = {"asap": 224, "ellipse": 224, "raid": 96, "persuade": 192}
FIT_SOURCES = ("asap", "ellipse")
SCHEME = "independent-human-calibration-42-v1"


def select_controls(datasets, reference, cache, occupied):
    from vibechecker_engine.text import count_words

    used_ids, used_groups = occupied
    aliases = human_source_aliases(examples(datasets, cache))
    chosen = defaultdict(dict)
    original_ids, outside_cal = set(), set()

    def nominate(row, key, group):
        words = count_words(row.text)
        if 300 <= words <= 2500:
            rank = fingerprint("independent-band-v1/42/" + key)
            previous = chosen[row.dataset].get(group)
            if previous is None or previous[0] > rank:
                chosen[row.dataset][group] = (rank, key, words, row)

    for row in examples(datasets, cache):
        key = fingerprint(row.text)
        identity = source_key(row, document_id=key)
        group = fingerprint(identity)
        original_ids.add(key)
        if row.split != "calibration":
            outside_cal.add(key)
        elif (
            row.dataset in (*FIT_SOURCES, "raid")
            and row.label == 0
            and row.attack == "none"
            and key not in used_ids
            and group not in used_groups
            and identity not in aliases.groups
        ):
            nominate(row, key, group)

    for row in examples([reference], cache):
        key = fingerprint(row.text)
        group = fingerprint(source_key(row, document_id=key))
        if (
            row.split == "calibration"
            and row.label == 0
            and row.attack == "none"
            and key not in original_ids
            and key not in used_ids
            and group not in used_groups
        ):
            nominate(row, key, group)

    plan = []
    for source, cap in CAPS.items():
        pool = sorted(
            (rank, key, group, n, row)
            for group, (rank, key, n, row) in chosen[source].items()
            if key not in outside_cal
        )
        plan.extend((k, g, n, source, r) for _, k, g, n, r in pool[:cap])
    if len({r[0] for r in plan}) != len(plan) or len({r[1] for r in plan}) != len(plan):
        raise ValueError("Independent calibration controls require unique documents and sources")
    manifest = {
        "scheme": SCHEME,
        "caps": CAPS,
        "selection": selection_digest(plan),
        "manifest": {
            d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]}
            for d in [*datasets, reference]
        },
        "source_aliases": aliases.summary(),
        "runtime": runtime_identity(),
        "reserved_reference_only": "persuade",
    }
    return plan, manifest


def selection_digest(rows):
    return fingerprint(" ".join(sorted(k + group + source for k, group, _, source, *_ in rows)))


def collect_controls(args):
    from vibechecker_engine.deep import DeepExtractor, DeepModel
    from vibechecker_engine.text import Refusal

    parent = DeepModel.load(args.model_in)
    scope = parent.training_scope
    catalog = registry()
    datasets = select(catalog, scope["dataset_order"])
    if scope["commercial_only"] or not set(FIT_SOURCES).issubset(scope["manifest"]):
        raise ValueError("Independent essay calibration requires the research dataset profile")
    uri = args.base_features.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as base:
        original = list(base.execute("SELECT id,group_id FROM documents"))
    plan, manifest = select_controls(
        datasets,
        catalog["persuade"],
        args.cache,
        ({r[0] for r in original}, {r[1] for r in original}),
    )
    if {k: manifest["manifest"][k] for k in scope["manifest"]} != scope["manifest"]:
        raise ValueError("Frozen heads and calibration data use different upstream revisions")
    extractor = DeepExtractor.from_env(include_encoder_evidence=True)
    parent.verify(extractor)
    binding = {
        "parent_sha256": sha256(args.model_in),
        "weights": extractor.identity,
        "quick_prefill": extractor.quick.lm.chunk_size,
        "backend": extractor.backend,
        "base_features_sha256": sha256(args.base_features),
        "selected": len(plan),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(args.output, timeout=30)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT)")
        db.execute("""CREATE TABLE IF NOT EXISTS controls(
            id TEXT PRIMARY KEY,grp TEXT UNIQUE,words INT,source TEXT,x BLOB,enc BLOB,refusal TEXT)""")
        meta = dict(db.execute("SELECT k,v FROM meta"))
        for name, record in (("manifest", manifest), ("binding", binding)):
            if name in meta and json.loads(meta[name]) != record:
                raise ValueError("Independent feature selection or extraction profile has changed")
        cached = {
            r[0]: r[1:]
            for r in db.execute("SELECT id,grp,words,source,x,enc,refusal FROM controls")
        }
        if cached.keys() - {r[0] for r in plan}:
            raise ValueError("Unexpected document in independent controls")
        # Older research caches recorded a verified extractor but omitted its weights from SQLite.
        # Replay one accepted row per source before adopting such a cache into this bound format.
        replay = (
            {s for _, _, s, x, _, _ in cached.values() if x is not None}
            if "binding" not in meta
            else set()
        )
        with db:
            db.execute(
                "INSERT OR IGNORE INTO meta VALUES ('manifest',?)",
                (json.dumps(manifest, sort_keys=True),),
            )
        for key, group, n, source, item in _progress("Independent human controls", plan, len(plan)):
            previous = cached.get(key)
            if previous and previous[:3] != (group, n, source):
                raise ValueError("Calibration document metadata differs from its source")
            if previous and (source not in replay or previous[3] is None):
                continue
            x = enc = reason = None
            try:
                raw = extractor.extract(item.text)
                x = np.asarray(parent.heads.features(raw), dtype="<f8").tobytes()
                enc = np.asarray(raw.encoder_vector, dtype="<f4").tobytes()
            except Refusal as exc:
                reason = exc.code
            if previous:
                if previous[3:] != (x, enc, reason):
                    raise ValueError("Replayed features differ from existing calibration controls")
                replay.remove(source)
            else:
                with db:
                    db.execute(
                        "INSERT INTO controls VALUES (?,?,?,?,?,?,?)",
                        (key, group, n, source, x, enc, reason),
                    )
        with db:
            db.execute(
                "INSERT OR REPLACE INTO meta VALUES ('binding',?)",
                (json.dumps(binding, sort_keys=True),),
            )
            db.execute("INSERT OR REPLACE INTO meta VALUES ('complete','1')")
    return {
        "database_sha256": sha256(args.output),
        "selection_sha256": manifest["selection"],
        **binding,
    }


@dataclass(frozen=True)
class ControlRows:
    sources: np.ndarray
    words: np.ndarray
    x: np.ndarray
    enc: np.ndarray
    provenance: dict


def load_band_controls(
    path, *, expected_sha256, expected_runtime, parent, parent_sha256, excluded_ids, excluded_groups
):
    from vibechecker_engine.deep import DEEP_FEATURE_NAMES

    path = Path(path)
    if sha256(path) != expected_sha256:
        raise ValueError("Independent human calibration control digest mismatch")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        meta = dict(db.execute("SELECT k,v FROM meta"))
        manifest = json.loads(meta["manifest"])
        binding = json.loads(meta["binding"])
        if (
            meta.get("complete") != "1"
            or manifest["scheme"] != SCHEME
            or not same_numeric_runtime(expected_runtime, manifest["runtime"])
            or manifest["caps"] != CAPS
            or manifest["source_aliases"] != parent.refit_provenance["source_aliases"]
            or binding["weights"] != parent.identity
            or binding["quick_prefill"] != parent.fit_selection["quick_prefill"]
            or binding["parent_sha256"] != parent_sha256
            or binding["backend"] != parent.probe.training_provenance_["backend"]
            or any(
                manifest["manifest"].get(k) != v
                for k, v in parent.training_scope["manifest"].items()
            )
            or parent.training_scope["commercial_only"]
        ):
            raise ValueError("Independent human calibration control profile differs")
        rows = list(
            db.execute("SELECT id,grp,words,source,x,enc,refusal FROM controls ORDER BY id")
        )
    if len(rows) != binding["selected"] or selection_digest(rows) != manifest["selection"]:
        raise ValueError("Independent human control selection is incomplete")
    counts, refused, overlaps = Counter(), Counter(), Counter()
    sources, words, features, encoders = [], [], [], []
    for key, group, n, source, x, enc, refusal in rows:
        counts[source] += 1
        if source not in CAPS or counts[source] > CAPS[source] or not 300 <= n <= 2500:
            raise ValueError("Independent human control row outside its scope")
        if key in excluded_ids or group in excluded_groups:
            overlaps[source] += 1
            continue
        if refusal is not None:
            if (
                refusal not in ("too_short", "too_long", "not_english")
                or x is not None
                or enc is not None
            ):
                raise ValueError("Invalid refusal in independent controls")
            refused[source] += 1
            continue
        vector, representation = np.frombuffer(x, dtype="<f8"), np.frombuffer(enc, dtype="<f4")
        if (
            vector.shape != (len(DEEP_FEATURE_NAMES),)
            or representation.shape != (769,)
            or not (np.isfinite(vector).all() and np.isfinite(representation).all())
        ):
            raise ValueError("Invalid numeric independent human control")
        sources.append(source)
        words.append(n)
        features.append(vector)
        encoders.append(representation)
    provenance = {
        "scheme": SCHEME,
        "database_sha256": expected_sha256,
        "runtime": manifest["runtime"],
        "selection_sha256": manifest["selection"],
        "parent_sha256": binding["parent_sha256"],
        "selected": dict(counts),
        "excluded_intersections": dict(overlaps),
        "refusals_after_exclusions": dict(refused),
        "accepted": dict(Counter(sources)),
        "source_aliases": manifest["source_aliases"],
        "manifest": manifest["manifest"],
    }
    return ControlRows(
        np.asarray(sources),
        np.asarray(words),
        np.asarray(features),
        np.asarray(encoders),
        provenance,
    )


def high_cutoff(indices, *, previous_high, target=0.02, tail=0.05):
    """Choose the smallest integer cutoff satisfying a one-sided order-statistic bound."""
    scores = np.asarray(indices)
    if (
        scores.ndim != 1
        or not np.isin(scores, np.arange(101)).all()
        or not 0 <= previous_high <= 100
    ):
        raise ValueError("Expected attainable integer index values and a usable high band")
    n = len(scores)
    # If Binom(n,target) <= k occurs with probability <= tail, holding observed
    # exceedances to k upper-bounds the exceedance probability on exchangeable controls.
    allowed = np.flatnonzero(binom.cdf(np.arange(n), n, target) <= tail)
    if not len(allowed):
        raise ValueError("Insufficient independent human controls for the requested tail bound")
    k = int(allowed[-1])
    cutoff = max(int(previous_high), int(np.sort(scores)[n - k - 1]) + 1)
    if cutoff > 100:
        raise ValueError("Independent human controls require an unattainable high cutoff")
    return cutoff, k


def control_indices(stacker, probe, controls, source_names):
    from vibechecker_engine.stacker import length_bin

    selected = np.isin(controls.sources, source_names)
    matrix = controls.x[selected]
    if not len(matrix):
        raise ValueError("No matching human calibration controls")
    with threadpool_limits(limits=1):
        if probe is not None:
            matrix = append_probe(matrix, controls.enc[selected], probe)
        raw = stacker.classifier.predict_proba(matrix)[:, 1]
    indices = []
    for score, n in zip(raw, controls.words[selected], strict=True):
        calibration = stacker.calibrators.get(length_bin(n), stacker.calibrators["pooled"])
        indices.append(int(np.rint(100 * calibration.point(score))))
    return controls.sources[selected], np.asarray(indices)


def calibrate_high_band(stacker, probe, controls):
    sources, scores = control_indices(stacker, probe, controls, FIT_SOURCES)
    previous = stacker.high_threshold
    threshold, k = high_cutoff(scores, previous_high=previous)
    by_source = {}
    for source in FIT_SOURCES:
        group = scores[sources == source]
        by_source[source] = {
            "n": len(group),
            "before": int(np.sum(group >= previous)),
            "after": int(np.sum(group >= threshold)),
        }
    stacker.high_threshold = threshold
    return {
        "method": "one-sided class-zero order statistic on rounded index",
        "target_fpr": 0.02,
        "tail_probability": 0.05,
        "max_exceedances": k,
        "previous_high": previous,
        "high": threshold,
        "mixed": stacker.low_threshold,
        "n": len(scores),
        "fit_by_source": by_source,
        "controls": controls.provenance,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model-in", "base-features", "cache", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    print(json.dumps(collect_controls(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
