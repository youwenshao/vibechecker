"""Frozen-head refits with independent paired rewrites and out-of-fit high-band controls."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import log_loss, roc_auc_score
from threadpoolctl import threadpool_limits

from .deep_runner import write_json
from .encoder_probe import _calibration_error
from .loaders import fingerprint
from .refit import _copy_model, append_probe, validate_probe, validation_quality
from .refit_cache import CALIBRATION, TRAIN, VALIDATION, digest_strings
from .registry import sha256
from .rewrite_sidecar import DOMAINS, STRESS, collect, inputs, metadata_hash, sidecar_rows


def displayed(stacker, matrix, rows):
    from vibechecker_engine.stacker import length_bin

    with threadpool_limits(limits=1, user_api="openmp"):
        raw = stacker.classifier.predict_proba(matrix)[:, 1]
    return np.asarray(
        [
            int(
                np.rint(
                    100
                    * stacker.calibrators.get(
                        length_bin(r.words), stacker.calibrators["pooled"]
                    ).point(p)
                )
            )
            for p, r in zip(raw, rows, strict=True)
        ]
    )


def sensitivity(indices, labels, threshold):
    machine = np.asarray(indices)[np.asarray(labels) == 1]
    hits = int(np.sum(machine >= threshold))
    return {
        "threshold": int(threshold),
        "hits": hits,
        "total": len(machine),
        "recall": hits / len(machine),
    }


def stress_metrics(indices, rows, domains):
    scores = np.asarray(indices) / 100.0
    groups = defaultdict(dict)
    for r, score in zip(rows, scores, strict=True):
        if r.label in groups[r.group]:
            raise ValueError("Repeated origin in matched stress group")
        groups[r.group][r.label] = score
    if any(set(pair) != {0, 1} for pair in groups.values()):
        raise ValueError("Unpaired stress group")
    parts = {}
    for domain in ("pooled", *DOMAINS):
        pairs = np.asarray(
            [
                [pair[0], pair[1]]
                for g, pair in groups.items()
                if domain == "pooled" or domains[g] == domain
            ]
        )
        if not len(pairs):
            raise ValueError(f"No stress pairs in {domain}")
        y = np.tile([0, 1], len(pairs))
        flat = pairs.reshape(-1)
        lo, hi = pairs.T
        wins = int(np.sum(hi > lo))
        ties = int(np.sum(hi == lo))
        stats = {
            "groups": len(pairs),
            "documents": len(flat),
            "wins": wins,
            "ties": ties,
            "pair_concordance": (wins + ties / 2) / len(pairs),
            "auroc": float(roc_auc_score(y, flat)),
            "log_loss": float(log_loss(y, np.clip(flat, 1e-7, 1 - 1e-7), labels=[0, 1])),
            "brier": float(np.mean((flat - y) ** 2)),
            "ece": _calibration_error(y, flat),
        }
        for label, name in ((0, "human"), (1, "machine")):
            p = flat[y == label]
            stats[name] = {
                "count": len(p),
                "brier": float(np.mean((p - label) ** 2)),
                "ece": _calibration_error(np.full(len(p), label), p),
                "mean_index": float(100 * np.mean(p)),
                "errors_at_50": int(np.sum((p >= 0.5) != label)),
            }
        parts[domain] = stats
    return {
        "document_ids_sha256": fingerprint(" ".join(sorted(r.id for r in rows))),
        "source_ids_sha256": digest_strings(sorted(groups)),
        "strata": parts,
    }


def admissibility(ordinary, stress, before, after, incumbent):
    reasons = []
    primary = incumbent["ordinary"]
    for name, check in primary["gates"]["checks"].items():
        if check["status"] == "pass" and ordinary["gates"]["checks"][name]["status"] != "pass":
            reasons.append(f"lost passing primary gate {name}")
    if ordinary["worst_stratum_ece"] >= primary["worst_stratum_ece"]:
        reasons.append("primary worst-stratum ECE did not improve")
    base = incumbent["stress"]["strata"]["pooled"]
    s = stress["strata"]["pooled"]
    if (
        s["brier"] >= base["brier"]
        or s["pair_concordance"] <= base["pair_concordance"]
        or s["auroc"] < base["auroc"]
    ):
        reasons.append(
            "matched stress requires lower Brier, higher within-source concordance and preserved AUROC"
        )
    if (
        after["threshold"] > 100
        or after["hits"] == 0
        or 10 * after["hits"] < 9 * max(before["hits"], incumbent["sensitivity"]["hits"])
    ):
        reasons.append("independent high band disabled or retained fewer than 90% of machine hits")
    return reasons


def validate_rewrite_probe(probe, info, aliases, supplement):
    p = validate_probe(probe, info, aliases)
    s = p.get("rewrite_supplement", {})
    if (
        s.get("scheme") != "rewrite-origin-paired-paraphrase-v1"
        or s.get("role") != "head"
        or s.get("commercial_only") is not False
        or s.get("cohort") != supplement
        or p.get("selection", {}).get("selected") not in {"mixture", "downward"}
    ):
        raise ValueError("Rewrite probe must bind the same research-only supplement and head role")
    for key in ("supervised_roles", "paired_roles"):
        if set(s.get(key, {})) != {"fit", "calibration", "development"}:
            raise ValueError("Rewrite probe lacks disjoint supervised membership provenance")
        for entry in s[key].values():
            if (
                entry.get("groups", 0) < 1
                or entry.get("documents", 0) < entry["groups"]
                or any(
                    not re.fullmatch(r"[a-f0-9]{64}", str(entry.get(h, "")))
                    for h in ("document_ids_sha256", "group_ids_sha256")
                )
            ):
                raise ValueError("Invalid rewrite probe membership provenance")
        for field in ("document_ids_sha256", "group_ids_sha256"):
            if len({entry[field] for entry in s[key].values()}) != 3:
                raise ValueError("Rewrite probe roles report repeated membership")
    return p


def verified_study(args, artifact_sha, p, incumbent):
    from .rewrite_data import load_rewrite_pairs
    from .rewrite_probe import _qualifies, paired_origin_membership

    if sha256(args.probe_membership) != args.probe_membership_sha256:
        raise ValueError("Independent rewrite probe membership proof SHA differs")
    audit = json.loads(args.probe_membership.read_bytes())
    study_sha = sha256(args.probe_study)
    study = json.loads(args.probe_study.read_bytes())
    supplement = p["rewrite_supplement"]
    kind = p["selection"]["selected"]
    if (
        audit["scheme"] != "independent-rewrite-origin-membership-v1"
        or audit["model_sha256"] != artifact_sha
        or audit["study_report_sha256"] != study_sha
        or audit["authenticated_cohort_db_sha256"] != args.supplement_sha256
        or audit["authenticated_cohort_selection_sha256"]
        != supplement["cohort"]["selection_sha256"]
        or audit["general_report_sha256"] != study["general_report_sha256"]
        or study["provenance"] != p
        or study["model_sha256"] != artifact_sha
        or study["selected"] != kind
        or not _qualifies(kind, study["scores"])
    ):
        raise ValueError("Fixed rewrite probe did not reproduce its audited qualifying study")
    expected_pairs = paired_origin_membership(
        load_rewrite_pairs(args.supplement, role="head"), p["seed"]
    )
    ordinary = incumbent.probe.training_provenance_
    if (
        audit["paired_roles"] != expected_pairs
        or supplement["paired_roles"] != expected_pairs
        or audit["supervised_roles"] != supplement["supervised_roles"]
        or audit["model_fit"]["document_ids_sha256"] != p["fit_document_ids_sha256"]
        or audit["model_fit"]["group_ids_sha256"] != p["fit_group_ids_sha256"]
        or audit["model_fit"]["documents"] != sum(p["fit_counts"].values())
        or audit["original_general"]["document_ids_sha256"] != ordinary["fit_document_ids_sha256"]
        or audit["original_general"]["group_ids_sha256"] != ordinary["fit_group_ids_sha256"]
        or audit["general_excluded_by_supplement"] != supplement["general_excluded_by_supplement"]
        or audit["new_source_conflict_groups"]
        != supplement["additional_cross_source_conflict_groups"]
        or audit["new_source_conflict_groups"] != 0
        or audit["split_seed"] != p["seed"]
        or audit["source_aliases"] != p["source_aliases"]
        or audit["pairwise_role_group_overlap"] != 0
        or audit["general_counts_and_model_fit_counts_verified"] is not True
    ):
        raise ValueError(
            "Rewrite probe fit, calibration or development membership differs from the authenticated projection and ordinary membership proof"
        )
    return {
        "study_sha256": study_sha,
        "membership_sha256": args.probe_membership_sha256,
        "qualified": kind,
        "paired_roles": expected_pairs,
    }


def fit(args):
    from vibechecker_engine.deep import DeepModel, ProbeDeepStacker

    from .band_controls import calibrate_high_band, load_band_controls

    (
        parent,
        incumbent,
        selection,
        info,
        base,
        names,
        protocol,
        members,
        forbidden_ids,
        forbidden_groups,
    ) = inputs(args)
    extra, domains, summary = sidecar_rows(args.sidecar, protocol, members)
    controls = load_band_controls(
        args.band_controls,
        expected_sha256=args.band_controls_sha256,
        parent=incumbent,
        parent_sha256=sha256(args.incumbent),
        expected_runtime=info["runtime"],
        excluded_ids=forbidden_ids,
        excluded_groups=forbidden_groups,
    )
    if controls.provenance["runtime"] != summary["runtime"]:
        raise ValueError("Independent control and rewrite sidecar runtimes differ")
    if sha256(args.band_controls) != args.band_controls_sha256:
        raise ValueError("Independent band-control digest differs")
    aliases = incumbent.refit_provenance["source_aliases"]
    validate_probe(incumbent.probe, info, aliases)
    probes = {"ordinary-control": incumbent.probe}
    probe_info = {
        "ordinary-control": {
            "artifact_sha256": incumbent.refit_provenance["probe_sha256"],
            "training_provenance": incumbent.probe.training_provenance_,
        }
    }
    if len(args.probe) != len(args.probe_sha256):
        raise ValueError("One preregistered --probe-sha256 is required per fixed probe")
    for path, expected_sha in zip(args.probe, args.probe_sha256, strict=True):
        if sha256(path) != expected_sha:
            raise ValueError("Fixed rewrite probe artifact SHA does not match")
        probe = joblib.load(path)
        p = validate_rewrite_probe(probe, info, aliases, protocol["supplement"])
        verified = verified_study(args, expected_sha, p, incumbent)
        kind = p["selection"]["selected"]
        if kind in probes:
            raise ValueError("Duplicate fixed rewrite family")
        probes[kind] = probe
        probe_info[kind] = {
            "artifact_sha256": expected_sha,
            "training_provenance": p,
            "qualification": verified,
        }
    partitions = {
        TRAIN: [*base[TRAIN], *extra[TRAIN]],
        CALIBRATION: [*base[CALIBRATION], *extra[CALIBRATION]],
        VALIDATION: base[VALIDATION],
        STRESS: extra[STRESS],
    }
    plain = {k: np.stack([r.features for r in values]) for k, values in partitions.items()}
    encoder = {k: np.stack([r.encoder for r in values]) for k, values in partitions.items()}
    y = {k: np.asarray([r.label for r in values]) for k, values in partitions.items()}
    cal_words = [r.words for r in partitions[CALIBRATION]]
    candidates = {}
    fitted = {}
    baseline = None

    def ordinary_quality(stacker, x):
        q = validation_quality(stacker, x[VALIDATION], base[VALIDATION], names)
        if q["scored_ids_sha256"] != selection["validation_cohort"]["scored_ids_sha256"]:
            raise ValueError("Primary selection evaluated different validation documents")
        return q

    def paired_quality(stacker, x):
        return stress_metrics(displayed(stacker, x[STRESS], extra[STRESS]), extra[STRESS], domains)

    for tag, probe in probes.items():
        x = {k: append_probe(v, encoder[k], probe) for k, v in plain.items()}

        if tag == "ordinary-control":
            ordinary = ordinary_quality(incumbent.stacker, x)
            reference = selection["candidates"][selection["selected"]]
            if (
                ordinary["metrics"] != reference["metrics"]
                or ordinary["thresholds"] != reference["thresholds"]
            ):
                raise ValueError("Incumbent did not reproduce the original live validation report")
            hits = sensitivity(
                displayed(incumbent.stacker, x[VALIDATION], base[VALIDATION]),
                y[VALIDATION],
                incumbent.stacker.high_threshold,
            )
            baseline = {
                "ordinary": ordinary,
                "stress": paired_quality(incumbent.stacker, x),
                "sensitivity": hits,
            }
        for anchor in (0.5, 0.75):
            name = f"{tag}-anchor{anchor:g}"
            stacker = ProbeDeepStacker.fit(
                x[TRAIN],
                y[TRAIN],
                x[CALIBRATION],
                y[CALIBRATION],
                cal_words,
                seed=info["seed"],
                max_leaf_nodes=7,
                l2_regularization=1.0,
                probe_anchor=anchor,
            )
            settings = {
                "probe": tag,
                "probe_sha256": probe_info[tag]["artifact_sha256"],
                "max_leaf_nodes": 7,
                "l2_regularization": 1.0,
                "probe_anchor": anchor,
            }
            threshold_before = stacker.high_threshold
            try:
                control_report = calibrate_high_band(stacker, probe, controls)
            except ValueError as exc:
                stacker.high_threshold = threshold_before
                indices = displayed(stacker, x[VALIDATION], base[VALIDATION])
                candidates[name] = {
                    "settings": settings,
                    "exclusions": [str(exc)],
                    "band_control": "rejected",
                    "ordinary_band_basis": "pre-control diagnostic",
                    "ordinary": ordinary_quality(stacker, x),
                    "stress": paired_quality(stacker, x),
                    "sensitivity_before": sensitivity(indices, y[VALIDATION], threshold_before),
                    "sensitivity_after": None,
                }
                continue
            # No validation or stress outcome is accessed before fitting this candidate's band.
            indices = displayed(stacker, x[VALIDATION], base[VALIDATION])
            before = sensitivity(indices, y[VALIDATION], threshold_before)
            after = sensitivity(indices, y[VALIDATION], stacker.high_threshold)
            ordinary = ordinary_quality(stacker, x)
            stress = paired_quality(stacker, x)
            reasons = admissibility(ordinary, stress, before, after, baseline)
            checks = ordinary["gates"]["checks"]
            minimax = max(
                ordinary[k] / checks[k]["target"] for k in ("pooled_ece", "worst_stratum_ece")
            )
            candidates[name] = {
                "settings": settings,
                "ordinary": ordinary,
                "stress": stress,
                "minimax": minimax,
                "band_control": control_report,
                "sensitivity_before": before,
                "sensitivity_after": after,
                "exclusions": reasons,
            }
            if not reasons:
                fitted[name] = (stacker, probe)

    def rank(name):
        q = candidates[name]
        return (
            q["minimax"] > 1,
            q["minimax"],
            q["stress"]["strata"]["pooled"]["brier"],
            q["ordinary"]["pooled_ece"],
            name,
        )

    winner = min(fitted, key=rank) if fitted else "incumbent"
    supplement_scope = {
        "scheme": "matched-origin-deep-rewrite-v1",
        "commercial_only": False,
        "supplement_sha256": args.supplement_sha256,
        "source_provenance": protocol["supplement"],
        "roles": {"stacker": "stack", "isotonic": "calibration", "development": "stress"},
    }
    if winner == "incumbent":
        _copy_model(args.incumbent, args.model_out)
    else:
        stacker, probe = fitted[winner]
        model = DeepModel(parent.heads, stacker, parent.identity, probe=probe)
        model.training_scope = {**parent.training_scope, "supplements": [supplement_scope]}
        model.fit_selection = {
            **incumbent.fit_selection,
            "rewrite_sidecar_selection_sha256": protocol["selection_sha256"],
        }
        model.fit_counts = {
            **incumbent.fit_counts,
            "stacker": dict(Counter(map(int, y[TRAIN]))),
            "calibration": dict(Counter(map(int, y[CALIBRATION]))),
            "rewrite_matched_documents": summary["matched_documents"],
        }
        model.refit_provenance = {
            **incumbent.refit_provenance,
            "v2_incumbent_sha256": protocol["incumbent_sha256"],
            "winner": winner,
            "settings": candidates[winner]["settings"],
            "probe_sha256": candidates[winner]["settings"]["probe_sha256"],
            "supplements_sha256": metadata_hash([supplement_scope]),
            "rewrite_sidecar_content_sha256": summary["content_sha256"],
            "rewrite_sidecar_selection_sha256": protocol["selection_sha256"],
            "band_controls_sha256": args.band_controls_sha256,
            "band_control": candidates[winner]["band_control"],
        }
        model.save(args.model_out)
    report = {
        "experiment": "matched-origin-deep-rewrite-v1",
        "selected": winner,
        "selected_model_sha256": sha256(args.model_out),
        "cohort": "validation",
        "incumbent_sha256": protocol["incumbent_sha256"],
        "primary_membership": selection["validation_cohort"],
        "protocol": protocol,
        "sidecar": summary,
        "candidate_training_supplements": [supplement_scope],
        "training_supplements": [] if winner == "incumbent" else [supplement_scope],
        "probe_artifacts": probe_info,
        "band_controls_sha256": args.band_controls_sha256,
        "base_counts": {str(k): len(v) for k, v in base.items()},
        "selection_rule": "Keep passing primary gates, reduce worst primary ECE, reduce matched-pair Brier, increase pair concordance and preserve stress AUROC relative to v2. Retain 90% of baseline and pre-control high-band machine hits. Prefer both calibration gates, then gate-relative minimax, stress Brier, pooled ECE and candidate name.",
        "incumbent": baseline,
        "candidates": candidates,
    }
    write_json(report, args.selection_out)
    return {
        "selected": winner,
        "model_sha256": report["selected_model_sha256"],
        "candidates": len(candidates),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for mode in ("plan", "collect", "fit", "verify"):
        cmd = commands.add_parser(mode)
        for flag in ("parent", "incumbent", "features", "supplement", "sidecar"):
            cmd.add_argument("--" + flag, type=Path, required=True)
        cmd.add_argument("--supplement-sha256", required=True)
        cmd.add_argument("--cache", type=Path, default=Path("eval/.cache"))
        cmd.add_argument(
            "--incumbent-selection",
            type=Path,
            default=Path("eval/reports/phase-1/calibration-selection.json"),
        )
        cmd.add_argument(
            "--prospective-plan",
            type=Path,
            default=Path("eval/reports/phase-1/prospective-audit-reservation.json"),
        )
        cmd.add_argument("--groups-per-domain", type=int, default=48)
        cmd.add_argument("--seed", type=int, default=42)
        if mode == "fit":
            cmd.add_argument(
                "--probe-study",
                type=Path,
                default=Path("eval/reports/phase-1/rewrite-origin-probe.json"),
            )
            cmd.add_argument(
                "--probe-membership",
                type=Path,
                default=Path("eval/reports/phase-1/rewrite-origin-membership.json"),
            )
            cmd.add_argument(
                "--probe-membership-sha256",
                default="733a54f2d199ce8d51fbf4317b57b33fb2b515384b85052be95ca6355e18a384",
            )
            cmd.add_argument(
                "--probe",
                action="append",
                type=Path,
                default=[],
                help="Qualified independent rewrite probe (repeatable); control-only is supported",
            )
            cmd.add_argument(
                "--probe-sha256",
                action="append",
                default=[],
                help="Preregistered SHA-256 in the same order as --probe",
            )
            for flag in ("model-out", "selection-out", "band-controls"):
                cmd.add_argument("--" + flag, type=Path, required=True)
            cmd.add_argument("--band-controls-sha256", required=True)
        if mode == "verify":
            for flag in ("model-in", "selection-in", "band-controls", "out"):
                cmd.add_argument("--" + flag, type=Path, required=True)
            for flag in ("model-sha256", "selection-sha256"):
                cmd.add_argument("--" + flag, required=True)
            cmd.add_argument("--withheld-specificity", action="store_true")
    args = parser.parse_args(argv)
    inputs_ = [
        args.parent,
        args.incumbent,
        args.features,
        args.supplement,
        args.incumbent_selection,
        args.prospective_plan,
    ]
    paths = [args.sidecar, *inputs_]
    if args.command == "fit":
        paths += [args.model_out, args.selection_out, args.band_controls, *args.probe]
    if args.command == "verify":
        paths += [args.model_in, args.selection_in, args.band_controls, args.out]
    if len({p.resolve() for p in paths}) != len(paths):
        parser.error("Use separate paths for each input and output")
    if args.command == "plan":
        protocol = inputs(args)[6]
        print(
            json.dumps(
                {
                    k: protocol[k]
                    for k in (
                        "selection_sha256",
                        "role_counts",
                        "group_shortfalls",
                        "excluded_pairs",
                        "exclusion_document_sha256",
                        "exclusion_source_sha256",
                    )
                }
            )
        )
    elif args.command == "verify":
        from .rewrite_verification import verify_selection

        print(json.dumps(verify_selection(args)))
    else:
        print(json.dumps(collect(args) if args.command == "collect" else fit(args)))


if __name__ == "__main__":
    main()
