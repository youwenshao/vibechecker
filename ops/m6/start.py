"""Launchd entry point. The local JSON config is readable only by the operator."""

import json
import os
import stat
import sys
from pathlib import Path

home = Path.home() / "vibechecker"
config = home / "service.json"
if config.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
    sys.exit("Set service.json permissions to 0600")
settings = json.loads(config.read_text())
os.environ.update(
    {
        "VIBECHECKER_BACKEND": "mlx-metal",
        "VIBECHECKER_LM": str(home / "artifacts/Qwen2.5-0.5B"),
        "VIBECHECKER_ENCODER": str(home / "artifacts/modernbert-ai-detection-raid-mage"),
        "VIBECHECKER_STACKER": str(home / "artifacts/quick.joblib"),
        "HF_HUB_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        **settings,
    }
)
os.execv(
    sys.executable,
    [
        sys.executable,
        "-m",
        "uvicorn",
        "vibechecker_inference.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8317",
        "--no-access-log",
    ],
)
