"""The pre-specified Falcon reference and paired validation bake-off."""

import json
import os
import random
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from .loaders import fingerprint
from .registry import fetch, registry, sha256

PAPER = "https://proceedings.mlr.press/v235/hans24a.html"
PUBLISHED_AUROC = 0.9933  # Figure 11, CNN with LLaMA-2-13B continuations
FALCON_HASHES = (
    (
        "02ebbe9c76d5f574bbacc8193a21e08246905e05b8e66d21a3149fd0ead3a636",
        "b40ecba13b10a02a867975f8b6d76833e71987a49539d09e9d276ff9ef955a45",
    ),
    (
        "b4515a8e32f81ab4fef65e10891fdb188bc45c4195620d447bc3263e132d9de5",
        "d68a175bf005c2dd7fdd9956227b5691802c8d5a5b03897ed107e591017b33ea",
    ),
)


def pair_info():
    paths = [Path(os.environ["VIBECHECKER_PAIR_" + role]) for role in ("OBSERVER", "PERFORMER")]
    configs = [json.loads((p / "config.json").read_bytes()) for p in paths]
    bits = [
        (c.get("quantization") or c.get("quantization_config") or {}).get("bits") for c in configs
    ]
    if bits[0] != bits[1] or bits[0] not in {None, 4, 6, 8}:
        raise ValueError("Deep evidence needs a pair at one supported precision")
    return paths, configs, bits[0]


def quantization_bits():
    return pair_info()[2]


def peak_bytes(backend):
    import mlx.core as mx

    if backend == "mlx-metal":
        from vibechecker_engine.backends.memory import macos_footprint

        # RSS omits unified-memory allocations charged to the GPU on macOS.
        return max(int(mx.get_peak_memory()), macos_footprint(os.getpid())[1])
    return int(mx.get_peak_memory())


def reference(args):
    from vibechecker_engine.deep import PairExtractor

    from .deep_runner import write_json

    paths, configs, bits = pair_info()
    for path, config, expected in zip(paths, configs, FALCON_HASHES, strict=True):
        hashes = tuple(sha256(p) for p in sorted(path.glob("*.safetensors")))
        if (
            bits is not None
            or config["model_type"] != "falcon"
            or config.get("torch_dtype", config.get("dtype")) != "bfloat16"
            or hashes != expected
        ):
            raise ValueError("Reference requires the pinned bf16 Falcon base and instruct weights")
    import torch

    hardware = torch.cuda.get_device_name() if torch.cuda.is_available() else "CPU"
    source = registry()["binoculars-cnn"]
    data = fetch(source.artifacts[0], args.cache)
    with data.open(encoding="utf8") as stream:
        records = [json.loads(line) for line in stream]
    if args.pairs < 0 or args.pairs > len(records):
        raise ValueError("Requested number of pairs exceeds the available reference cohort")
    if args.pairs:
        records = random.Random(args.seed).sample(records, args.pairs)
    extractor = PairExtractor.from_env()
    scores = []
    for r in records:
        # In the original experiment negating the Binoculars ratio makes generated text positive.
        scores.append(
            [
                -extractor.score(r[key], max_tokens=512)[1]
                for key in ("article", "meta-llama-Llama-2-13b-hf_generated_text_wo_prompt")
            ]
        )
    y = np.tile([0, 1], len(scores))
    p = np.asarray(scores)
    auc = float(roc_auc_score(y, p.ravel()))
    rng = np.random.default_rng(args.seed)
    boot = [roc_auc_score(y, p[rng.integers(len(p), size=len(p))].ravel()) for _ in range(200)]
    report = {
        "experiment": "falcon-reference",
        "paper": PAPER,
        "figure": 11,
        "pairs": len(y) // 2,
        "published_auroc": PUBLISHED_AUROC,
        "auroc": auc,
        "paired_bootstrap95": np.percentile(boot, [2.5, 97.5]).tolist(),
        "weights_sha256": FALCON_HASHES,
        "seed": args.seed,
        "max_tokens": 512,
        "corpus_sha256": source.artifacts[0].sha256,
        "paired_ids_sha256": fingerprint(" ".join(sorted(str(r["id"]) for r in records))),
        "backend": extractor.backend.name,
        "gpu": hardware,
        "precision": "bf16",
        "tolerance": 0.01,
        "pass": bool(
            len(records) >= 64
            and "L40S" in hardware
            and extractor.backend.name == "mlx-cuda"
            and abs(auc - PUBLISHED_AUROC) <= 0.01
        ),
    }
    write_json(report, args.out)
    return report


MEMORY_CAP = 18 * 1024**3
PRECISIONS = (None, 4, 6, 8)


def memory_preflight(args):
    from .deep_runner import write_json

    if args.observed_pid is not None:
        import platform

        from vibechecker_engine.backends.memory import macos_footprint

        if platform.system() != "Darwin":
            raise ValueError("A process footprint requires a running M6 candidate on macOS")
        estimate = macos_footprint(args.observed_pid)[1]
        kind = "measured_process_peak"
    else:
        estimate = args.projected_bytes
        kind = "projected_footprint"
    if estimate <= MEMORY_CAP:
        raise ValueError("An over-cap rejection requires an observation or projection above 18 GiB")
    evidence = {
        "experiment": "pair-memory-preflight",
        "family": args.pair_family,
        "bits": args.bits,
        "backend": "mlx-metal",
        "kind": kind,
        "bytes": estimate,
        "cap_bytes": MEMORY_CAP,
        "basis": args.basis,
    }
    write_json(evidence, args.out)
    return evidence


def _quality(metrics):
    tpr = metrics.get("genre/essay", {}).get("tpr_at_1pct_fpr")
    esl = metrics.get("fairness/ESL-essay", {}).get("fpr_high", {}).get("rate")
    return tpr, esl


def _preflight_by_variant(rejected):
    rows = {}
    for record in rejected:
        key = record.get("family"), record.get("bits")
        if (
            not isinstance(key[0], str)
            or not key[0].strip()
            or type(key[1]) is not int
            or key[1] not in (4, 6, 8)
            or key in rows
            or record.get("experiment") != "pair-memory-preflight"
            or record.get("backend") != "mlx-metal"
            or record.get("kind") not in ("measured_process_peak", "projected_footprint")
            or record.get("cap_bytes") != MEMORY_CAP
            or not isinstance(record.get("basis"), str)
            or not record["basis"].strip()
            or not isinstance(record.get("bytes"), int)
            or record["bytes"] <= MEMORY_CAP
        ):
            raise ValueError("Invalid or duplicate over-cap preflight evidence")
        rows[key] = record
    return rows


def bakeoff(reports, *, partial=False, rank_provisional=False, rejected=()):
    if not reports:
        raise ValueError("Expected at least one scored validation report")
    if not partial and rank_provisional:
        raise ValueError("Provisional ranking requires --partial")
    preflights = _preflight_by_variant(rejected)
    candidates, missing = [], []
    by_family = {family: {} for family, _bits in preflights}
    scope = reports[0]["scope"]
    for r in reports:
        if r["mode"] != "deep" or r["scope"] != scope or scope["cohort"] != "validation":
            raise ValueError("Bake-off requires the same validation cohort for every run")
        bits = r["pair_bits"]
        name = r["pair_family"]
        variants = by_family.setdefault(name, {})
        if bits not in PRECISIONS or bits in variants or (name, bits) in preflights:
            raise ValueError("Unsupported or duplicate precision for the same model family")
        if bits is None and r["precision"] != "bf16":
            raise ValueError("The reference run must use bf16 weights")
        if bits is None and r["backend"] != "mlx-cuda":
            raise ValueError("Run the unquantized baseline on CUDA")
        if bits is not None and r["backend"] != "mlx-metal":
            raise ValueError("Quantized candidates need measured Metal memory")
        variants[bits] = r
    for family, variants in by_family.items():
        absent = [
            bits for bits in PRECISIONS if bits not in variants and (family, bits) not in preflights
        ]
        if absent and not partial:
            labels = ", ".join("bf16" if bits is None else f"{bits}-bit" for bits in absent)
            raise ValueError(f"Missing bake-off evidence for {family}: {labels}")
        missing.extend(
            {
                "family": family,
                "precision": f"{bits}bit" if bits else "bf16",
                "backend": "mlx-metal" if bits else "mlx-cuda",
                "status": "unmeasured",
            }
            for bits in absent
        )
        ref_tpr, ref_esl = _quality(variants.get(None, {}).get("metrics", {}))
        for bits, r in variants.items():
            tpr, esl = _quality(r["metrics"])
            peak = r["peak_bytes"]
            if not isinstance(peak, int) or peak <= 0:
                raise ValueError("Candidate memory has to be measured")
            within_gates = (
                bits is not None
                and peak <= MEMORY_CAP
                and tpr is not None
                and esl is not None
                and esl <= 0.05
            )
            candidates.append(
                {
                    "family": family,
                    "bits": bits,
                    "backend": r["backend"],
                    "peak_bytes": peak,
                    "essay_tpr_at_1pct_fpr": tpr,
                    "esl_high_fpr": esl,
                    "model_sha256": r["model_sha256"],
                    "weights": r["weights"],
                    "metal_cuda_parity": r.get("parity"),
                    "tpr_delta_from_bf16": None
                    if tpr is None or ref_tpr is None
                    else tpr - ref_tpr,
                    "esl_fpr_delta_from_bf16": None
                    if esl is None or ref_esl is None
                    else esl - ref_esl,
                    "meets_memory_and_esl_gates": within_gates,
                    "eligible": not partial
                    and within_gates
                    and ref_tpr is not None
                    and ref_esl is not None,
                }
            )
    ranked = sorted(
        (c for c in candidates if c["meets_memory_and_esl_gates"]),
        key=lambda c: (-c["essay_tpr_at_1pct_fpr"], c["esl_high_fpr"], c["peak_bytes"]),
    )
    selected = next((c for c in ranked if c["eligible"]), None)
    result = {
        "experiment": "quantization-bakeoff",
        "partial": partial,
        "scope": scope,
        "candidates": candidates,
        "missing_measurements": missing,
        "preflight_rejections": list(preflights.values()),
        "selected": selected,
        "pass": selected is not None,
    }
    if rank_provisional:
        result["provisional_ranking"] = [{"family": c["family"], "bits": c["bits"]} for c in ranked]
    return result


def _load_p95(rows, count, *, deep=False):
    if not isinstance(rows, list) or len(rows) != count:
        return None
    times = []
    for row in rows:
        if not isinstance(row, dict) or "error" in row:
            return None
        ms = row.get("ms")
        if type(ms) is not int or ms <= 0:
            return None
        if deep:
            first, chunks = row.get("first_chunk_ms"), row.get("chunks")
            if (
                type(first) is not int
                or not 0 <= first <= ms
                or type(chunks) is not int
                or chunks < 2
            ):
                return None
        times.append(ms)
    # The benchmark uses nearest rank (ceil(0.95 * n)), never interpolated percentiles.
    rank = (95 * count + 99) // 100
    return sorted(times)[rank - 1]


def _m6_load_checks(load, trace, version):
    rounds, concurrency = 20, 5
    quick = _load_p95(load.get("quick"), rounds * concurrency)
    deep = _load_p95(load.get("deep"), rounds, deep=True)
    prefill = load.get("quick_prefill", 64)
    trace_prefill = trace.get("quick_prefill", 64)
    peak = load.get("peak_bytes")
    health = load.get("beat_ad_health")
    job = load.get("beat_ad_job")
    # One health sample before warmup and one after each measured round.
    healthy = (
        isinstance(health, list)
        and len(health) == rounds + 1
        and all(
            isinstance(h, dict)
            and h.get("loaded") is True
            and type(h.get("last_exit")) is int
            and h["last_exit"] == 0
            for h in health
        )
    )
    return {
        "benchmark_passed": load.get("passed") is True,
        "artifact": load.get("backend") == "mlx-metal"
        and load.get("version") == version
        and load.get("model_sha256") == trace["model_sha256"],
        "quick_prefill": type(prefill) is int
        and prefill > 0
        and type(trace_prefill) is int
        and trace_prefill == prefill,
        "workload": load.get("quick_concurrency") == concurrency
        and load.get("quick_words") == 1000
        and load.get("deep_words") == 2000
        and quick is not None
        and deep is not None,
        "quick_p95": quick is not None and quick == load.get("quick_p95_ms") and quick <= 2000,
        "deep_p95": deep is not None and deep == load.get("deep_p95_ms") and deep <= 25000,
        "memory": type(peak) is int and 0 < peak <= MEMORY_CAP,
        "co_tenancy": load.get("beat_ad_healthy") is True
        and isinstance(job, str)
        and bool(job.strip())
        and healthy,
    }


def hardware_evidence(args, trace, pair_bits):
    from .deep_runner import read

    reference, bake, load = (
        read(p) or {} for p in (args.reference_report, args.bakeoff_report, args.load_report)
    )
    winner = bake.get("selected") or {}
    load_checks = _m6_load_checks(load, trace, args.version)
    return {
        "falcon_reference": {
            "pass": reference.get("experiment") == "falcon-reference"
            and reference.get("pass") is True,
            "report": reference or None,
        },
        "quantization": {
            "pass": bake.get("pass") is True
            and winner.get("bits") == pair_bits
            and winner.get("weights") == trace["weights"]
            and winner.get("model_sha256") == trace["model_sha256"],
            "report": bake or None,
        },
        "m6_load": {
            "pass": all(load_checks.values()),
            "checks": load_checks,
            "report": load or None,
        },
    }
