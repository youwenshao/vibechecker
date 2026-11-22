"""Fit lens operating points on human reference writing and measure a disjoint holdout."""

import gzip
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from vibechecker_engine.lenses import document_signals

from .lens_sentences import reserve
from .loaders import examples, fingerprint
from .phase11 import MODEL_SHA, historical_groups
from .registry import registry, select, sha256
from .source_groups import source_key


def threshold(values, target):
    ordered = np.unique(values)
    if not len(ordered):
        raise ValueError("Missing human reference observations")
    thresholds = np.append(ordered, np.nextafter(ordered[-1], np.inf))
    counts = len(values) - np.searchsorted(np.sort(values), thresholds)
    return float(thresholds[np.argmin(abs(counts / len(values) - target))])


def measurement(fit, holdout, cutoff, target):
    if not len(holdout):
        raise ValueError("Missing held-out observations")
    hits = int(np.count_nonzero(np.asarray(holdout) >= cutoff))
    rate = hits / len(holdout)
    return {
        "fit_n": len(fit),
        "held_out_n": len(holdout),
        "high": hits,
        "high_rate": rate,
        "target": target,
        "within_two_points": None if target is None else abs(rate - target) <= 0.02,
    }


def essay_candidate(args, traces, broad, target):
    excluded = set(traces[0]["scores"]) | set(traces[1]["scores"])
    membership = reserve(args.features, excluded)
    fingerprint = hashlib.sha256(json.dumps(membership, sort_keys=True).encode()).hexdigest()
    with gzip.open(args.essay_sentences, "rt", encoding="utf8") as stream:
        reference = json.load(stream)
    if reference["membership_sha256"] != fingerprint or reference["model_sha256"] != MODEL_SHA:
        raise ValueError("Essay sentence reference must match reserved documents and frozen model")
    for name, ids in membership.items():
        fold = reference["folds"][name]
        values = np.asarray(fold["scores"], dtype=float)
        if (
            fold["documents"] != len(ids)
            or len(values) < len(ids)
            or not np.all((values >= 0) & (values <= 1))
        ):
            raise ValueError("Incomplete essay sentence reference")
    fit, holdout = (reference["folds"][fold]["scores"] for fold in ("calibration", "validation"))
    candidate = threshold(fit, target)
    essay = measurement(fit, holdout, candidate, target)
    original = threshold(broad[0], target)
    selected = candidate if essay["within_two_points"] else original
    audit = {
        "membership_sha256": fingerprint,
        "reference_sha256": sha256(args.essay_sentences),
        "documents": {fold: len(ids) for fold, ids in membership.items()},
        "essay_candidate": {"cutoff": candidate, **essay},
        "adopted_essay_candidate": essay["within_two_points"],
        "original_broad_control": {"cutoff": original, **measurement(*broad, original, target)},
        "broad_at_essay_cutoff": {
            name: measurement(fit, values, candidate, target)
            for name, values in zip(("original", "prospective"), broad, strict=True)
        },
        "broad_at_shipped_cutoff": measurement(
            fit if essay["within_two_points"] else broad[0], broad[1], selected, target
        ),
    }
    return (
        selected,
        essay if essay["within_two_points"] else audit["broad_at_shipped_cutoff"],
        audit,
    )


def run(args):
    if args.commercial_only:
        raise ValueError("The frozen v4 model and sentence references use research-only datasets")
    config = yaml.safe_load(args.params.read_text())
    receipts = Path("eval/reports/phase-1")
    expected_cache = json.loads((receipts / "academic-addition-input.json").read_bytes())[
        "file_sha256"
    ]["base_features"]
    expected_traces = json.loads((receipts / "phase-1.1/metrics.json").read_bytes())["trace_sha256"]
    paths = (args.historical, args.prospective)
    if sha256(args.features) != expected_cache or [sha256(p) for p in paths] != expected_traces:
        raise ValueError("Inputs must match the frozen Phase 1.1 feature cache and model")
    traces = [json.loads(p.read_bytes()) for p in paths]
    for trace, folder in zip(traces, ("", "prospective"), strict=True):
        historical_groups(trace, json.loads((receipts / folder / "report.json").read_bytes()))
    groups = [set(), set()]
    db = sqlite3.connect(args.features.resolve().as_uri() + "?mode=ro", uri=True)
    with db:
        strata = json.loads(dict(db.execute("select key,value from meta"))["strata"])
        rows = {
            key: (fold, words, [strata[s] for s in json.loads(tags)], np.frombuffer(blob, "<f8"))
            for key, fold, words, tags, blob in db.execute(
                "select id,role,words,strata,features from documents where role in (1,2) and label=0 and features is not null"
            )
        }
    db.close()
    samples = defaultdict(lambda: ([], []))
    seen = set()
    datasets = select(
        registry(), ["asap", "ellipse", "liang", "raid", "raid-attacks"], args.commercial_only
    )
    for item in examples(datasets, args.cache):
        if item.label:
            continue
        key = fingerprint(item.text)
        if key in seen:
            continue
        seen.add(key)
        for fold, trace in enumerate(traces):
            if key in trace["sentences"]:
                groups[fold].add(source_key(item, document_id=key))
                samples["turnitin"][fold].extend(s[2] for s in trace["sentences"][key])
        if key in rows:
            fold, words, tags, values = rows[key]
            if "genre/essay" not in tags:
                continue
            for name, value in document_signals(values, item.text, words, config).items():
                if name != "gptzero" or "writer/ESL" in tags:
                    samples[name][fold - 1].append(value)
    if groups[0] & groups[1]:
        raise ValueError("Sentence cohorts share a source family")
    report = {
        "model": config["model"],
        "model_sha256": MODEL_SHA,
        "feature_cache_sha256": expected_cache,
        "sentence_trace_sha256": expected_traces,
        "sentence_backend": traces[0]["backend"],
        "lenses": {},
    }
    for name in ("turnitin", "gptzero", "zerogpt", "grammarly", "veriguide"):
        fit, holdout = samples[name]
        settings = config[name]
        target = settings.get("target")
        # Qualitative sources only support descriptive bands. Use human reference tertiles.
        if name == "turnitin":
            high, observed, report["sentence_validation"] = essay_candidate(
                args, traces, (fit, holdout), target
            )
        else:
            high = threshold(fit, target if target is not None else 1 / 3)
            settings["mixed"] = threshold(fit, settings.get("mixed_target", 2 / 3))
            observed = measurement(fit, holdout, high, target)
        settings["high"] = high
        report["lenses"][name] = {"source": settings["source"], **observed}
    # The vendor describes the denominator as highlighted sentences. The plan
    # separately asks for the share of all human sentences that were flagged.
    highlighted = sum(
        s[2] >= config["turnitin"]["high"]
        for spans in traces[1]["sentences"].values()
        for s in spans
    )
    human_highlights = report["sentence_validation"]["broad_at_shipped_cutoff"]["high"]
    report["turnitin_highlights"] = {
        "human": human_highlights,
        "total": highlighted,
        "human_share": human_highlights / highlighted if highlighted else None,
    }
    args.params.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    return int(
        args.enforce and any(row["within_two_points"] is False for row in report["lenses"].values())
    )
