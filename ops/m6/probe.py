"""Signed local health probe for launchd or a deployment rehearsal."""

import json
import urllib.request
from pathlib import Path

from vibechecker_inference.auth import signed_headers

settings = json.loads((Path.home() / "vibechecker/service.json").read_text())
path = "/v1/health"
headers = signed_headers(settings["INFERENCE_HMAC_SECRET"].encode(), "GET", path, b"")
with urllib.request.urlopen(
    urllib.request.Request("http://127.0.0.1:8317" + path, headers=headers), timeout=10
) as r:
    print(r.read().decode())
