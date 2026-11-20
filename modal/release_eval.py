"""Re-evaluate this checkout against the same fitted artifact and Metal cohort."""

import os
import re

from fallback import app, evaluate

version = os.environ["ENGINE_VERSION"]
if not re.fullmatch(r"[a-zA-Z0-9._-]{1,64}", version):
    raise SystemExit("Set ENGINE_VERSION to the fitted model's release identifier")
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
