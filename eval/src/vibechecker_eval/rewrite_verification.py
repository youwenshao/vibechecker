"""Replay a frozen development selection or measure reserved human-control specificity."""

import json

import numpy as np

from .band_controls import control_indices, load_band_controls
from .metrics import rate
from .refit import append_probe, validation_quality
from .refit_cache import VALIDATION
from .registry import sha256
from .rewrite_refit import displayed, stress_metrics
from .rewrite_sidecar import STRESS, inputs, sidecar_rows


def reference_specificity(stacker, probe, controls):
    sources, indices = control_indices(stacker, probe, controls, ("raid", "persuade"))
    high = int(stacker.high_threshold)
    groups = {}
    for source in ("raid", "persuade"):
        scores = indices[sources == source]
        groups[source] = rate(int(np.sum(scores >= high)), len(scores))
    return {"high_index": high, "high_fpr": groups}


def _parity_scores(model, rows):
    matrix = append_probe(
        np.stack([r.features for r in rows]), np.stack([r.encoder for r in rows]), model.probe
    )
    expected = displayed(model.stacker, matrix, rows)
    observed = []
    for r in rows:
        vector = append_probe(r.features[None, :], r.encoder[None, :], model.probe)[0]
        observed.append(model.stacker.predict(vector, r.words)["index"])
    if not np.array_equal(expected, observed):
        raise ValueError("Single-document serving indexes differ from the batch selection")
    return matrix, observed


def verify_selection(args):
    from vibechecker_engine.deep import DeepModel

    if (
        sha256(args.model_in) != args.model_sha256
        or sha256(args.selection_in) != args.selection_sha256
    ):
        raise ValueError("Frozen model or selection digest differs")
    selection = json.loads(args.selection_in.read_bytes())
    name = selection["selected"]
    if (
        selection.get("cohort") != "validation"
        or selection["selected_model_sha256"] != args.model_sha256
    ):
        raise ValueError("Expected the exact model frozen by the validation selection")
    _, incumbent, _, info, base, names, protocol, members, ids, groups = inputs(args)
    if protocol != selection["protocol"] or selection["incumbent_sha256"] != sha256(args.incumbent):
        raise ValueError("Selection sources or incumbent differ")
    model = DeepModel.load(args.model_in)
    if name == "incumbent":
        target = selection["incumbent"]
        if args.model_sha256 != selection["incumbent_sha256"]:
            raise ValueError("Incumbent fallback differs from its original bytes")
    else:
        target = selection["candidates"][name]
        if target["exclusions"] or target["settings"] != model.refit_provenance["settings"]:
            raise ValueError("Selected candidate has different settings or failed admission")
    report = {
        "model_sha256": args.model_sha256,
        "selection_sha256": args.selection_sha256,
        "selected": name,
        "backend": protocol["backend"],
        "quick_prefill": protocol["quick_prefill"],
    }
    if args.withheld_specificity:
        controls = load_band_controls(
            args.band_controls,
            expected_sha256=selection["band_controls_sha256"],
            expected_runtime=info["runtime"],
            parent=incumbent,
            parent_sha256=sha256(args.incumbent),
            excluded_ids=ids,
            excluded_groups=groups,
        )
        report["independent_controls"] = controls.provenance
        report["incumbent_specificity"] = reference_specificity(
            incumbent.stacker, incumbent.probe, controls
        )
        report["selected_specificity"] = reference_specificity(model.stacker, model.probe, controls)
    else:
        extra, domains, summary = sidecar_rows(args.sidecar, protocol, members)
        if summary != selection["sidecar"]:
            raise ValueError("Supplemental frozen features differ from the selection")
        primary, stress = base[VALIDATION], extra[STRESS]
        x, _ = _parity_scores(model, primary)
        _, scores = _parity_scores(model, stress)
        if (
            validation_quality(model.stacker, x, primary, names) != target["ordinary"]
            or stress_metrics(scores, stress, domains) != target["stress"]
        ):
            raise ValueError("Reloaded model does not reproduce its development metrics")
        report["scoring"] = {
            role: {"documents": len(rows), "exact_index_matches": len(rows)}
            for role, rows in (("primary_validation", primary), ("matched_stress", stress))
        }
        report["bootstrap_curves"] = {
            k: len(v.bootstrap) for k, v in model.stacker.calibrators.items()
        }
    from .prospective import publish

    publish(report, args.out)
    return report
