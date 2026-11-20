"""Deploy with uv run --package vibechecker-modal modal deploy modal/fallback.py."""

import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("vibechecker")
weights = modal.Volume.from_name("vibechecker-weights", create_if_missing=False)
secrets = modal.Secret.from_name("vibechecker-inference")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("uv==0.13.0")
    .add_local_file(ROOT / "pyproject.toml", "/opt/vibe/pyproject.toml", copy=True)
    .add_local_file(ROOT / "uv.lock", "/opt/vibe/uv.lock", copy=True)
    .add_local_file(ROOT / "modal/pyproject.toml", "/opt/vibe/modal/pyproject.toml", copy=True)
)
for package in ["engine", "services/inference", "eval"]:
    folder = ROOT / package
    dest = "/opt/vibe/" + package
    image = image.add_local_dir(
        folder / "src", dest + "/src", copy=True, ignore=["**/__pycache__/**"]
    )
    image = image.add_local_file(folder / "pyproject.toml", dest + "/pyproject.toml", copy=True)
image = (
    image.add_local_file(ROOT / "eval/registry.yaml", "/opt/vibe/eval/registry.yaml", copy=True)
    .run_commands(
        "cd /opt/vibe && UV_PROJECT_ENVIRONMENT=$(python -c 'import sys; print(sys.prefix)') uv sync --frozen --all-packages --extra cuda --inexact --no-editable --no-dev"
    )
    .env(
        {
            "VIBECHECKER_BACKEND": "mlx-cuda",
            "VIBECHECKER_LM": "/weights/Qwen2.5-0.5B",
            "VIBECHECKER_ENCODER": "/weights/modernbert-ai-detection-raid-mage",
            "VIBECHECKER_STACKER": "/weights/quick.joblib",
            "HF_HUB_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
)


@app.function(
    image=image,
    gpu="L4",
    volumes={"/weights": weights},
    secrets=[secrets],
    timeout=180,
    min_containers=0,
    max_containers=1,
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def inference():
    from vibechecker_inference.app import create_app

    if Path("/weights/deep.joblib").is_file():
        os.environ.setdefault("VIBECHECKER_PAIR_OBSERVER", "/weights/pair/base")
        os.environ.setdefault("VIBECHECKER_PAIR_PERFORMER", "/weights/pair/instruct")
        os.environ.setdefault("VIBECHECKER_DEEP_MODEL", "/weights/deep.joblib")
    # Only Metal is allowed to advertise the primary heartbeat.
    return create_app(heartbeat_url="")


@app.function(image=image, gpu="L4", volumes={"/weights": weights}, timeout=86400, max_containers=1)
def evaluate(args: list[str], quick_prefill: int = 64):
    import subprocess

    # Explicit operator entry point. Do not expose corpus fetch/training over HTTP.
    try:
        if args[0] == "deep":
            os.environ.setdefault("VIBECHECKER_PAIR_OBSERVER", "/weights/pair/base")
            os.environ.setdefault("VIBECHECKER_PAIR_PERFORMER", "/weights/pair/instruct")
            os.environ["VIBECHECKER_QUICK_PREFILL"] = str(quick_prefill)
        subprocess.run(["vibechecker-eval", *args], check=True)
    finally:
        weights.commit()
