"""Install the isolated inference tunnel in the authorized user's launchd domain."""

import os
import plistlib
import subprocess
from pathlib import Path

home = Path.home() / "vibechecker"
token = home / "cloudflared.token"
token.chmod(0o600)
label = "io.vibechecker.cloudflared"
domain = f"gui/{os.getuid()}"
agents = Path.home() / "Library/LaunchAgents"
agents.mkdir(parents=True, exist_ok=True)
plist = agents / (label + ".plist")
service = {
    "Label": label,
    "ProgramArguments": [
        "/opt/homebrew/bin/cloudflared",
        "tunnel",
        "--no-autoupdate",
        "run",
        "--token-file",
        str(token),
    ],
    "KeepAlive": True,
    "RunAtLoad": True,
    "ThrottleInterval": 30,
    "StandardErrorPath": str(home / "cloudflared.stderr"),
}
if (
    subprocess.run(["launchctl", "print", domain + "/" + label], capture_output=True, check=False).returncode
    == 0
):
    subprocess.run(["launchctl", "bootout", domain + "/" + label], check=True)
with plist.open("wb") as f:
    plistlib.dump(service, f)
subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
