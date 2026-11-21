"""Fit the Deep heads on training sources and evaluate the calibrated runtime on held-out essays."""

from __future__ import annotations

import json
import sys
from collections import Counter
from time import perf_counter

from .deep_cohort import fold, mixed_documents, parity, reliability, sentence_metrics
from .loaders import examples, fingerprint
from .metrics import gates, summarize
from .registry import sha256
from .runner import observation, sample, write_report


def _progress(stage, rows, total=None):
    """Occasional aggregate progress keeps long GPU jobs observable without logging inputs."""
    started = last = perf_counter()
    done = 0
    for done, row in enumerate(rows, 1):
        yield row
        now = perf_counter()
        if now - last >= 60:
            count = str(done) if total is None else f"{done}/{total}"
            print(
                f"{stage}: {count} documents in {now - started:.0f}s", file=sys.stderr, flush=True
            )
            last = now
    print(
        f"{stage} finished: {done} documents in {perf_counter() - started:.0f}s",
        file=sys.stderr,
        flush=True,
    )


def _extract(extractor, selected, skipped, stage):
    from vibechecker_engine.text import Refusal

    for item, n in _progress(stage, selected, len(selected)):
        try:
            yield item, n, extractor.extract(item.text)
        except Refusal as e:
            skipped[f"{item.dataset}/{e.code}"] += 1


def _splices(extractor, items, skipped, seed, stage):
    from vibechecker_engine.text import Refusal

    for mix in _progress(stage, mixed_documents(items, seed)):
        try:
            raw = extractor.extract(mix.text)
        except Refusal as e:
            skipped[f"spliced/{e.code}"] += 1
            continue
        if len(raw.waveforms) != len(mix.labels):
            raise ValueError("Sentence head and mixed-document labels have different offsets")
        yield raw, mix.labels


def fit(extractor, chosen, skipped, args):
    from vibechecker_engine.deep import DeepHeads, DeepModel, DeepStacker

    train = [(r, n) for r, n in chosen if r.split == "train"]
    head_sources = [(r, n) for r, n in train if fold(r, "head") == 0]
    stack_sources = [(r, n) for r, n in train if fold(r, "head") == 1]
    cal_sources = [(r, n) for r, n in chosen if r.split == "calibration"]
    for name, sources in (
        ("head", head_sources),
        ("stacker", stack_sources),
        ("calibration", cal_sources),
    ):
        if {r.label for r, _ in sources} != {0, 1}:
            raise ValueError(f"The {name} partition needs eligible human and generated documents")
    print(f"Fitting Deep heads on {len(head_sources)} documents", file=sys.stderr, flush=True)
    heads_rows = list(_extract(extractor, head_sources, skipped, "Head features"))
    if not heads_rows:
        raise ValueError("No eligible documents for fitting the Deep heads")
    waves, labels = [], []
    for doc, _, raw in heads_rows:
        waves.extend(raw.waveforms)
        labels.extend([doc.label] * len(raw.waveforms))
    mixed_count = 0
    for raw, origins in _splices(
        extractor, [r for r, _, _ in heads_rows], skipped, args.seed, "Mixed training features"
    ):
        waves.extend(raw.waveforms)
        labels.extend(origins)
        mixed_count += 1
    if mixed_count == 0:
        raise ValueError(
            "No eligible mixed documents for the sentence head. Increase the training sample."
        )
    ghost_rows = [(raw.ghost, r.label) for r, _, raw in heads_rows]
    esl = [
        (raw.flag_features, r.ell_label)
        for r, _, raw in heads_rows
        if r.label == 0 and r.ell_label is not None
    ]
    attacks = [
        (raw.flag_features, int(r.attack != "none"))
        for r, _, raw in heads_rows
        if r.dataset in {"raid", "raid-attacks"} and r.attack and r.attack != "unknown"
    ]
    for name, rows in (("E7", ghost_rows), ("ELL", esl), ("laundering", attacks)):
        if {y for _, y in rows} != {0, 1}:
            raise ValueError(
                f"{name} fit requires both labeled classes. Increase eligible training coverage."
            )
    heads = DeepHeads.fit(
        waves, labels, *zip(*ghost_rows), *zip(*esl), *zip(*attacks), seed=args.seed
    )
    print(
        f"Fitting the stacker on {len(stack_sources)} documents and calibrating on {len(cal_sources)}",
        file=sys.stderr,
        flush=True,
    )
    training = list(_extract(extractor, stack_sources, skipped, "Stacker features"))
    calibration = list(_extract(extractor, cal_sources, skipped, "Calibration features"))
    stacker = DeepStacker.fit(
        [heads.features(raw) for _, _, raw in training],
        [r.label for r, _, _ in training],
        [heads.features(raw) for _, _, raw in calibration],
        [r.label for r, _, _ in calibration],
        [n for _, n, _ in calibration],
        seed=args.seed,
    )
    return DeepModel(heads, stacker, extractor.identity), {
        "head_documents": len(heads_rows),
        "mixed_training_documents": mixed_count,
        "sentence_training_labels": dict(Counter(labels)),
        "ELL_labels": dict(Counter(y for _, y in esl)),
        "laundering_labels": dict(Counter(y for _, y in attacks)),
        "stacker": dict(Counter(r.label for r, _, _ in training)),
        "calibration": dict(Counter(r.label for r, _, _ in calibration)),
    }


def write_json(obj, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, allow_nan=False, indent=2) + "\n", encoding="utf8")


def read(path):
    return json.loads(path.read_bytes()) if path else None


def evaluation_training_scope(model, requested):
    scope = getattr(model, "training_scope", None)
    supplements = []
    if scope and "supplements" in scope:
        from .rewrite_sidecar import metadata_hash

        scope = dict(scope)
        supplements = scope.pop("supplements")
        if (
            requested["commercial_only"]
            or not isinstance(supplements, list)
            or not supplements
            or any(
                not isinstance(s, dict) or s.get("commercial_only") is not False
                for s in supplements
            )
            or metadata_hash(supplements)
            != getattr(model, "refit_provenance", {}).get("supplements_sha256")
        ):
            raise ValueError(
                "Supplemental Deep training scope and research licensing could not be verified"
            )
    if (scope is not None and scope != requested) or (
        scope is None and requested["commercial_only"]
    ):
        raise ValueError(
            "Fitted Deep model and selected weights, datasets or commercial-use scope differ"
        )
    return scope == requested, supplements


def run_deep(args, datasets):
    from vibechecker_engine.deep import DeepEngine, DeepExtractor, DeepModel
    from vibechecker_engine.text import Refusal, count_words

    manifest = {
        d.id: {"version": d.version, "sha256": [a.sha256 for a in d.artifacts]} for d in datasets
    }
    audit_plan = getattr(args, "audit_plan", None)
    if args.cohort == "prospective":
        from .prospective import resolve

        if not audit_plan or not args.model_in or sha256(args.model_in) != args.audit_model_sha256:
            raise ValueError(
                "The prospective audit requires its plan and a SHA-pinned frozen model"
            )
        plan = read(audit_plan)
        chosen = resolve(
            plan, args.audit_plan_sha256, datasets, examples(datasets, args.cache), count_words
        )
        skipped = Counter()
    else:
        if (
            audit_plan
            or getattr(args, "audit_plan_sha256", None)
            or getattr(args, "audit_model_sha256", None)
        ):
            raise ValueError("Audit plan arguments require --cohort prospective")
        chosen, skipped = sample(
            examples(datasets, args.cache),
            args.limit_per_class,
            args.seed,
            count_words,
            length_range=(300, 2500),
        )
    extractor = DeepExtractor.from_env()
    weights = extractor.identity
    quick_prefill = extractor.quick.lm.chunk_size
    fitted = args.model_in or args.model_out
    training_scope = {
        "manifest": manifest,
        "dataset_order": [d.id for d in datasets],
        "weights": weights,
        "commercial_only": args.commercial_only,
    }
    fit_counts = {}
    supplements = []
    verified_scope = False
    if args.model_in:
        model = DeepModel.load(fitted)
        model.verify(extractor)
        verified_scope, supplements = evaluation_training_scope(model, training_scope)
        fit_counts = getattr(model, "fit_counts", {})
    else:
        model, fit_counts = fit(extractor, chosen, skipped, args)
        model.training_scope = training_scope
        verified_scope = True
        model.fit_selection = {
            "seed": args.seed,
            "limit_per_class_per_dataset_split": args.limit_per_class,
            "dataset_order": [d.id for d in datasets],
            "quick_prefill": quick_prefill,
        }
        model.fit_counts = fit_counts
        model.save(fitted)
    engine = DeepEngine(extractor, model)
    print(f"Scoring the {args.cohort} cohort", file=sys.stderr, flush=True)
    rows, sentences, test_items = [], {}, []
    head_observations = {"e7": [], "esl": [], "laundering": []}
    evaluation = [
        (item, n)
        for item, n in chosen
        if item.split == "test" and fold(item, "bakeoff") == int(args.cohort != "validation")
    ]
    for item, n in _progress("Document evaluation", evaluation, len(evaluation)):
        start = perf_counter()
        try:
            result = engine.analyze(item.text)
        except Refusal as e:
            skipped[f"{item.dataset}/{e.code}"] += 1
            continue
        entry = observation(item, n, result["index"] / 100, (perf_counter() - start) * 1000)
        rows.append(entry)
        test_items.append(item)
        head_observations["e7"].append(
            (item.label, next(s["value"] for s in result["signals"] if s["id"] == "e7"))
        )
        if item.ell_label is not None and item.label == 0:
            head_observations["esl"].append((item.ell_label, int("esl" in result["flags"])))
        if item.dataset in {"raid", "raid-attacks"} and item.attack and item.attack != "unknown":
            head_observations["laundering"].append(
                (int(item.attack != "none"), int("laundering" in result["flags"]))
            )
        sentences[entry.id] = [[s["start"], s["end"], s["score"]] for s in result["sentences"]]
    if not rows:
        raise ValueError("No eligible Deep documents in the evaluation cohort")

    truth, scores = [], []
    for raw, origins in _splices(
        extractor, test_items, skipped, args.seed, "Mixed evaluation features"
    ):
        truth.extend(origins)
        scores.extend(model.heads.sentence_scores(raw))
    sentence = sentence_metrics(truth, scores)
    scope = {
        "seed": args.seed,
        "limit_per_class_per_dataset_split": None if audit_plan else args.limit_per_class,
        "commercial_only": args.commercial_only,
        "cohort": args.cohort,
        "manifest": manifest,
        "scored_ids_sha256": fingerprint(" ".join(sorted(sentences))),
    }
    if audit_plan:
        scope["audit_plan_sha256"] = args.audit_plan_sha256
        scope["reserved_ids_sha256"] = plan["member_ids_sha256"]
        scope["reserved_documents"] = len(chosen)
    trace = {
        "version": args.version,
        "backend": extractor.backend,
        "quick_prefill": quick_prefill,
        "manifest": manifest,
        "scope": scope,
        "model_sha256": sha256(fitted),
        "weights": weights,
        "scores": {r.id: round(r.score * 100) for r in rows},
        "sentences": sentences,
    }
    if args.trace_out:
        write_json(trace, args.trace_out)
    parallel = parity(trace, read(args.compare_trace)) if args.compare_trace else None
    mixed, high = model.stacker.low_threshold / 100, model.stacker.high_threshold / 100
    summary = summarize(rows, mixed, high)
    previous = read(args.previous)
    if previous and (previous.get("mode") != "deep" or previous.get("scope") != scope):
        raise ValueError("Regression comparison requires identical Deep evaluation cohorts")
    gate = gates(
        summary, quick=False, deep=True, previous=previous["metrics"] if previous else None
    )
    if previous and previous.get("sentence_f1") is not None:
        delta = None if sentence["f1"] is None else previous["sentence_f1"] - sentence["f1"]
        status = "unmeasured" if delta is None else "pass" if delta <= 0.01 else "fail"
        gate["checks"]["sentence_f1_regression"] = {
            "value": delta,
            "target": 0.01,
            "status": status,
        }
        gate["eligible"] &= status == "pass"
    from .experiments import hardware_evidence, pair_info, peak_bytes

    _, configs, pair_bits = pair_info()
    pair_family = args.pair_family or "-".join(
        str(configs[0].get(k)) for k in ("model_type", "hidden_size", "num_hidden_layers")
    )
    dtypes = {c.get("torch_dtype", c.get("dtype")) for c in configs}
    precision = (
        f"{pair_bits}bit" if pair_bits else "bf16" if dtypes == {"bfloat16"} else "unquantized"
    )
    evidence = hardware_evidence(args, trace, pair_bits)
    report = {
        "version": args.version,
        "mode": "deep",
        "prior": 0.5,
        "description": "Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.",
        "backend": extractor.backend,
        "quick_prefill": quick_prefill,
        "model_sha256": trace["model_sha256"],
        "weights": weights,
        "pair_bits": pair_bits,
        "pair_family": pair_family,
        "precision": precision,
        "peak_bytes": peak_bytes(extractor.backend),
        "scope": scope,
        "fit_counts": fit_counts,
        "fit_selection": getattr(model, "fit_selection", None),
        "refit_provenance": getattr(model, "refit_provenance", None),
        **({"training_supplements": supplements} if supplements else {}),
        "regression_reference": {
            "version": previous.get("version"),
            "model_sha256": previous.get("model_sha256"),
            "report_sha256": sha256(args.previous),
        }
        if previous
        else None,
        "skipped": dict(sorted(skipped.items())),
        "thresholds": {"mixed": mixed, "high": high},
        "metrics": summary,
        "reliability_bins": reliability(rows),
        "sentence_f1": sentence["f1"],
        "mixed_sentence_metrics": sentence,
        "head_metrics": {
            name: sentence_metrics(*(zip(*pairs) if pairs else ([], [])))
            for name, pairs in head_observations.items()
        },
        "parity": parallel,
        "evidence": evidence,
        "gates": gate,
        "release_ready": bool(
            args.cohort == "test"
            and verified_scope
            and gate["eligible"]
            and parallel
            and parallel["pass"]
            and sentence["f1"] is not None
            and all(x["pass"] for x in evidence.values())
        ),
    }
    write_report(report, args.reports / args.version)
    return report
