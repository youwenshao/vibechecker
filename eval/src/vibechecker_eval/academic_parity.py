"""Verify a frozen academic selection with single-document serving and optional raw-text replay."""

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from threadpoolctl import threadpool_limits

from .academic_addition import (
    HUMAN_DEV,
    STRESS,
    human_checks,
    machine_checks,
    matrix,
    read_academic,
    read_rewrite_rows,
)
from .academic_intake import projection, study_paths
from .deep_runner import write_json
from .loaders import fingerprint
from .refit import load_rows, validation_quality
from .refit_cache import VALIDATION, digest_strings, runtime_identity, same_numeric_runtime
from .registry import sha256
from .rewrite_diagnostics import academic_groups, published_paraphrases
from .rewrite_refit import stress_metrics
from .rewrite_verification import _parity_scores


def compare_raw(stacker, probe, observed, row):
    expected = stacker.predict(matrix([row], probe)[0], row.words)
    if "esl" in observed["flags"]:
        expected["interval"]["low"] = max(0, expected["interval"]["low"] - 5)
        expected["interval"]["high"] = min(100, expected["interval"]["high"] + 5)
    if (
        observed["wordCount"] != row.words
        or any(observed[k] != expected[k] for k in ("index", "interval", "band"))
        or [s["id"] for s in observed["signals"]] != [s["id"] for s in expected["signals"]]
    ):
        raise ValueError(
            "Production word count, index, interval, band or signal ordering differs from numeric replay"
        )
    left = np.asarray([s["value"] for s in observed["signals"]])
    right = np.asarray([s["value"] for s in expected["signals"]])
    if not np.allclose(left, right, rtol=1e-5, atol=1e-6):
        raise ValueError("Raw production signal features differ from cached features")
    return float(np.max(np.abs(left - right)))


def verify(args):
    from vibechecker_engine.deep import DeepEngine, DeepModel

    paths = study_paths(args.study, args.study_sha256)
    if sha256(args.selection) != args.selection_sha256 or sha256(args.model) != args.model_sha256:
        raise ValueError("Expected the independently frozen selection and model")
    selected = json.loads(args.selection.read_bytes())
    binding = json.loads(args.binding.read_bytes())
    members = json.loads(args.plan.read_bytes())
    v3 = json.loads(paths["v3_selection"].read_bytes())
    if (
        selected["selected_model_sha256"] != args.model_sha256
        or selected["study_sha256"] != args.study_sha256
        or sha256(args.plan) != selected["plan_sha256"]
        or binding["content_sha256"] != selected["numeric_content_sha256"]
    ):
        raise ValueError("Frozen academic lineage or selection differs")
    model = DeepModel.load(args.model)
    parent = DeepModel.load(paths["v1_parent"])
    _, base, names, _, content = load_rows(
        paths["base_features"], parent, sha256(paths["v1_parent"]), False
    )
    if content != v3["protocol"]["base_features_sha256"]:
        raise ValueError("Original Deep cache identity differs")
    for name in ("genre/essay", "fairness/ESL-essay", "dataset/liang/toefl", "writer/native_proxy"):
        names.setdefault(fingerprint(name), name)
    _, human = read_academic(args.sidecar, binding, members)
    primary = base[VALIDATION]
    report = {
        "scheme": "academic-frozen-scoring-parity-v1",
        "selected": selected["selected"],
        "model_sha256": args.model_sha256,
        "selection_sha256": args.selection_sha256,
        "study_sha256": args.study_sha256,
    }
    if args.raw:
        if sha256(Path(os.environ["VIBECHECKER_DEEP_MODEL"])) != args.model_sha256:
            raise ValueError("Serving environment must load the same frozen model file")
        engine = DeepEngine.from_env()
        if (
            engine.extractor.backend != v3["protocol"]["backend"]
            or engine.extractor.quick.lm.chunk_size != v3["protocol"]["quick_prefill"]
            or not same_numeric_runtime(v3["protocol"]["base_runtime"], runtime_identity())
        ):
            raise ValueError("Raw replay requires the original serving extraction profile")
        subset = [r for r in primary if fingerprint("attack/paraphrase") in r.strata]
        samples = [(r, d["generation"]) for r, d in published_paraphrases(subset, args.cache)]
        _, native = projection(paths, "human")
        dev = {r["child"]["id"]: r["child"]["text"] for r in native if r["role"] == HUMAN_DEV}
        if len(samples) != 2 or set(dev) != {r.id for r in human["pooled"]} or len(dev) != 4:
            raise ValueError("Expected the six predeclared development features")
        samples.extend((r, dev[r.id]) for r in human["pooled"])
        errors = [
            compare_raw(model.stacker, model.probe, engine.analyze(text), r) for r, text in samples
        ]
        report["production_replay"] = {
            "documents": len(samples),
            "ordinary_academic_machine": len(subset),
            "independent_native_human": len(dev),
            "exact_index_interval_band": len(samples),
            "serving_backend": engine.extractor.backend,
            "quick_prefill": engine.extractor.quick.lm.chunk_size,
            "input_ids_sha256": digest_strings(sorted(r.id for r, _ in samples)),
            "max_abs_display_signal_delta": max(errors),
        }
    else:
        extra, domains = read_rewrite_rows(paths["rewrite_sidecar"], v3)
        aux, _ = academic_groups(
            SimpleNamespace(
                academic_binding=paths["academic_binding"],
                academic_plan=paths["academic_plan"],
                academic_features=paths["academic_features"],
                selection=paths["v3_selection"],
                supplement=paths["rewrite_supplement"],
                control_keys=paths["band_controls"],
                encoder_fit_keys=[paths["encoder_original"], paths["encoder_expanded"]],
            ),
            base,
            v3,
        )
        if selected["selected"] == "incumbent":
            target = v3["incumbent"]
            expected_stress = target["stress"]
            expected_human = selected["incumbent_academic_human_development"]
            expected_machine = selected["incumbent_independent_academic_machine"]
        else:
            target = selected["candidates"][selected["selected"]]
            if target["artifact_sha256"] != args.model_sha256 or target["admission_reasons"]:
                raise ValueError("The frozen selection names a rejected or different model")
            expected_stress = target["books_news_stress"]
            expected_human = target["academic_human_development"]
            expected_machine = target["independent_academic_machine"]
        xp, _ = _parity_scores(model, primary)
        _, scores = _parity_scores(model, extra[STRESS])
        unique_aux = [*aux["academic/rewrite"], *aux["academic/clean_combined"]]
        _parity_scores(model, unique_aux)
        _parity_scores(model, human["pooled"])
        if (
            validation_quality(model.stacker, xp, primary, names) != target["ordinary"]
            or stress_metrics(scores, extra[STRESS], domains) != expected_stress
            or human_checks(model.stacker, model.probe, human) != expected_human
            or machine_checks(model.stacker, model.probe, aux) != expected_machine
        ):
            raise ValueError("Frozen development metrics differ after single-document model reload")
        report["numeric_parity"] = {
            k: {"documents": len(v), "exact_index_matches": len(v)}
            for k, v in (
                ("original_primary", primary),
                ("matched_books_news_stress", extra[STRESS]),
                ("independent_academic_machine", unique_aux),
                ("independent_native_human", human["pooled"]),
            )
        }
        report["bootstraps"] = {k: len(v.bootstrap) for k, v in model.stacker.calibrators.items()}
    write_json(report, args.out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("study", "plan", "selection", "model", "sidecar", "binding", "out", "cache"):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("study", "selection", "model"):
        p.add_argument("--" + k + "-sha256", required=True)
    p.add_argument(
        "--raw",
        action="store_true",
        help="Run the production DeepEngine on the six predeclared development passages",
    )
    with threadpool_limits(limits=1):
        verify(p.parse_args(argv))


if __name__ == "__main__":
    main()
