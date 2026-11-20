"""Measure warmed, signed loopback requests and the co-resident beat-ad backup job on macOS."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from time import monotonic

import httpx
from vibechecker_engine.backends.memory import macos_footprint
from vibechecker_engine.text import WORD, count_words
from vibechecker_inference.auth import signed_headers
from vibechecker_inference.generated_event import InferenceEvent


def beat_ad_health(label):
    status = subprocess.run(
        ["launchctl", "print", label], capture_output=True, text=True, check=False
    )
    runs = re.search(r"^\s*runs = (\d+)$", status.stdout, re.MULTILINE)
    last_exit = re.search(r"^\s*last exit code = (-?\d+)$", status.stdout, re.MULTILINE)
    return {
        "loaded": status.returncode == 0,
        "runs": int(runs[1]) if runs else None,
        "last_exit": int(last_exit[1]) if last_exit else None,
    }


def fixture(text, n, offset=0):
    words = count_words(text)
    if words == 0:
        raise ValueError("The benchmark needs a public prose fixture")
    repeated = (text.strip() + "\n") * math.ceil((n + offset) / words)
    matches = list(WORD.finditer(repeated))
    return repeated[matches[offset].start() : matches[offset + n - 1].end()] + "."


async def check(client, secret, version, mode, text):
    try:
        return await read_check(client, secret, version, mode, text)
    except httpx.HTTPError as error:
        return {"error": type(error).__name__}


async def read_check(client, secret, version, mode, text):
    path = "/v1/analyze"
    payload = json.dumps({"mode": mode, "text": text}).encode()
    headers = signed_headers(secret, "POST", path, payload)
    started = monotonic()
    first = None
    chunks = 0
    expected = None
    async with client.stream("POST", path, content=payload, headers=headers) as response:
        if response.status_code != 200:
            return {"error": f"http_{response.status_code}"}
        async for line in response.aiter_lines():
            event = InferenceEvent.model_validate_json(line).model_dump()
            if event["type"] == "accepted":
                if event["backend"] != "mlx-metal" or event["engineVersion"] != version:
                    raise RuntimeError("Unexpected inference service or model version")
                expected = event["chunks"]
            elif event["type"] == "sentences":
                if first is None:
                    first = round((monotonic() - started) * 1000)
                chunks += 1
            elif event["type"] == "result":
                if not expected or (mode == "deep" and (chunks != expected or chunks <= 1)):
                    return {"error": "missing_chunks"}
                if event["result"]["wordCount"] != (2000 if mode == "deep" else 1000):
                    return {"error": "wrong_length"}
                return {
                    "ms": round((monotonic() - started) * 1000),
                    "first_chunk_ms": first,
                    "chunks": chunks,
                }
            elif event["type"] == "error":
                return {"error": event["code"]}
    return {"error": "incomplete"}


def p95(rows):
    values = sorted(row["ms"] for row in rows if "ms" in row)
    return values[math.ceil(0.95 * len(values)) - 1] if values else None


async def run(args):
    config = json.loads(args.config.read_bytes()) if args.config else os.environ
    version = config["ENGINE_VERSION"]
    model_sha256 = hashlib.sha256(Path(config["VIBECHECKER_DEEP_MODEL"]).read_bytes()).hexdigest()
    secret = config["INFERENCE_HMAC_SECRET"].encode()
    source = args.fixture.read_text(encoding="utf8")
    quick = [fixture(source, 1000, offset) for offset in (0, 37, 83, 119, 167)]
    deep = fixture(source, 2000)
    health = [beat_ad_health(args.beat_ad_job)]
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{args.port}", timeout=180) as client:
        warmup = [
            await check(client, secret, version, mode, text)
            for mode, text in (("quick", quick[0]), ("deep", deep))
        ]
        quick_rows, deep_rows = [], []
        if all("ms" in r for r in warmup):
            for _ in range(args.rounds):
                quick_rows.extend(
                    await asyncio.gather(
                        *(check(client, secret, version, "quick", essay) for essay in quick)
                    )
                )
                deep_rows.append(await check(client, secret, version, "deep", deep))
                health.append(beat_ad_health(args.beat_ad_job))
    quick_p95, deep_p95 = p95(quick_rows), p95(deep_rows)
    try:
        _, peak = macos_footprint(args.pid)
    except ProcessLookupError:
        peak = None
    healthy = all(h["loaded"] and h["last_exit"] == 0 for h in health)
    passed = bool(
        quick_p95 is not None
        and quick_p95 <= 2000
        and deep_p95 is not None
        and deep_p95 <= 25000
        and peak is not None
        and peak <= 18 * 1024**3
        and healthy
        and all("ms" in r for r in quick_rows + deep_rows)
    )
    return {
        "version": version,
        "model_sha256": model_sha256,
        "quick_prefill": int(config.get("VIBECHECKER_QUICK_PREFILL", 64)),
        "backend": "mlx-metal",
        "passed": passed,
        "path": "signed loopback HTTP",
        "quick_concurrency": 5,
        "quick_words": 1000,
        "quick_word_offsets": [0, 37, 83, 119, 167],
        "deep_words": 2000,
        "method": "nearest-rank p95, one excluded warm-up per mode",
        "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
        "warmup": warmup,
        "quick": quick_rows,
        "deep": deep_rows,
        "quick_p95_ms": quick_p95,
        "deep_p95_ms": deep_p95,
        "peak_bytes": peak,
        "beat_ad_job": args.beat_ad_job,
        "beat_ad_health": health,
        "beat_ad_healthy": healthy,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--config", type=Path, help="Defaults to the process environment")
    parser.add_argument(
        "--pid", required=True, type=int, help="PID of the loopback inference server"
    )
    parser.add_argument("--port", type=int, default=8317)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--beat-ad-job", default="system/hk.beatad.px-backup")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.rounds < 1 or sys.platform != "darwin":
        parser.error("Run on the M6 with at least one round")
    report = asyncio.run(run(args))
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    sys.exit(0 if report["passed"] else 1)
