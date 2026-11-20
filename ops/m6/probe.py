"""Signed local health probe for launchd or a deployment rehearsal."""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from vibechecker_inference.auth import signed_headers

settings = json.loads((Path.home() / "vibechecker/service.json").read_text())
path = "/v1/health"
deadline = time.monotonic() + (90 if "--wait" in sys.argv else 0)
while True:
    headers = signed_headers(settings["INFERENCE_HMAC_SECRET"].encode(), "GET", path, b"")
    try:
        with urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:8317" + path, headers=headers), timeout=10
        ) as r:
            health = json.load(r)
        if health != {"engineVersion": settings["ENGINE_VERSION"], "backend": "mlx-metal"}:
            raise SystemExit("Unexpected engine version or backend")
        print(json.dumps(health))
        break
    except urllib.error.URLError:
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
