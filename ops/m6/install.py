"""Run under youwenshao after installing the shared engine and inference packages."""

import argparse
import json
import os
import plistlib
import secrets
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True, help="Exact matching web ENGINE_VERSION")
args = parser.parse_args()
home = Path.home() / "vibechecker"
home.mkdir(exist_ok=True, mode=0o700)
config = home / "service.json"
if not config.exists():
    with os.fdopen(os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(
            {"INFERENCE_HMAC_SECRET": secrets.token_urlsafe(48), "ENGINE_VERSION": args.version}, f
        )
elif json.loads(config.read_text()).get("ENGINE_VERSION") != args.version:
    raise SystemExit("Update ENGINE_VERSION in service.json to match the installed model first.")
label = "io.vibechecker.inference"
domain = "gui/" + str(os.getuid())
directory = Path.home() / "Library/LaunchAgents"
directory.mkdir(parents=True, exist_ok=True)
plist = directory / (label + ".plist")
spec = {
    "Label": label,
    "ProgramArguments": [
        sys.executable,
        str(Path(__file__).with_name("start.py").resolve()),
    ],
    "WorkingDirectory": str(home),
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardErrorPath": str(home / "inference.stderr"),
    "ThrottleInterval": 30,
}
target = domain + "/" + label
if subprocess.run(["launchctl", "print", target], capture_output=True, check=False).returncode == 0:
    if plist.exists() and plistlib.loads(plist.read_bytes()) == spec:
        subprocess.run(["launchctl", "kickstart", "-k", target], check=True)
        raise SystemExit(0)
    subprocess.run(["launchctl", "bootout", target], check=True)
with plist.open("wb") as f:
    plistlib.dump(spec, f)
# bootout can finish before launchd has released the previous registration.
for attempt in range(8):
    result = subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True, check=False)
    if result.returncode == 0:
        break
    if attempt == 7 or result.returncode != 5:
        raise SystemExit(result.stderr.decode().strip())
    time.sleep(0.5)
