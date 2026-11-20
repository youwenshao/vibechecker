"""Re-evaluate this checkout against the same fitted artifact and Metal cohort."""

import json
import os
import re
from pathlib import Path

from fallback import app, evaluate

version = os.environ["ENGINE_VERSION"]
if not re.fullmatch(r"[a-zA-Z0-9._-]{1,64}", version):
    raise SystemExit("Set ENGINE_VERSION to the fitted model's release identifier")
report = json.loads(
    (Path(__file__).resolve().parents[1] / "eval/reports/phase-1/report.json").read_bytes()
)
scope = report.get("scope") or {}
if scope.get("cohort") != "test" or report.get("version") != version:
    raise SystemExit("Generate the held-out Deep report for ENGINE_VERSION before release evaluation")
with app.run():
    evaluate.remote(
        [
            "quick",
            "--datasets",
            "raid",
            "liang",
            "ellipse",
            "--seed",
            "42",
            "--limit-per-class",
            "96",
            "--version",
            version,
            "--cache",
            "/weights/eval-cache",
            "--model-in",
            "/weights/quick.joblib",
            "--compare-trace",
            f"/weights/traces/{version}.metal.json",
            "--trace-out",
            f"/weights/traces/{version}.cuda.json",
            "--reports",
            "/weights/cuda-reports",
            "--enforce",
        ]
    )
    # Re-score the reviewed cohort using the same artifact and both sentence and document traces.
    evaluate.remote(
        [
            "deep",
            "--datasets",
            *scope["manifest"],
            "--seed",
            str(scope["seed"]),
            "--limit-per-class",
            str(scope["limit_per_class_per_dataset_split"]),
            "--version",
            version,
            "--model-in",
            "/weights/deep.joblib",
            "--pair-family",
            report["pair_family"],
            "--cache",
            "/weights/eval-cache",
            "--reports",
            "/weights/cuda-reports/deep",
            "--compare-trace",
            f"/weights/traces/{version}.deep.metal.json",
            "--trace-out",
            f"/weights/traces/{version}.deep.cuda.json",
            "--load-report",
            f"/weights/evidence/{version}.m6-load.json",
            "--reference-report",
            "/weights/evidence/falcon-reference.json",
            "--bakeoff-report",
            f"/weights/evidence/{version}.bakeoff.json",
            *(["--commercial-only"] if scope["commercial_only"] else []),
            "--enforce",
        ],
        quick_prefill=report.get("quick_prefill", 64),
    )
