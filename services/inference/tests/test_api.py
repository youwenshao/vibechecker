import asyncio
import json
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from vibechecker_engine import Refusal
from vibechecker_inference.app import create_app
from vibechecker_inference.auth import Authenticator, signature, signed_headers
from vibechecker_inference.scheduler import Busy, Scheduler

KEY = b"a" * 32
PATH = "/v1/analyze"


class Engine:
    backend = "mlx-cpu"

    def analyze(self, text):
        if text == "short":
            raise Refusal("too_short")
        return {
            "index": 25,
            "interval": {"low": 12, "high": 42},
            "band": "low",
            "wordCount": 200,
            "signals": [
                {"id": id_, "value": 0.4, "humanReference": 0.2}
                for id_ in ("e1", "e2", "e6", "stylometry")
            ],
            "flags": [],
        }


def client(memory_ok=lambda: True):
    return TestClient(
        create_app(
            engine_factory=Engine,
            secret=KEY,
            version="v0",
            scheduler=Scheduler(memory_ok),
            heartbeat_url="",
        )
    )


def test_health_and_shared_signature():
    assert (
        signature(KEY, "POST", PATH, "1700000000", "65bcd128-7849-487d-abc1-c1bab305f6ad", b"{}")
        == "ddf672268e1ea68c561d1184fbafcc9645cc6f58373096963a52efadf40914f4"
    )
    with client() as c:
        assert c.get("/v1/health").status_code == 403
        assert (
            c.get("/v1/health", headers=signed_headers(KEY, "GET", "/v1/health", b"")).json()[
                "backend"
            ]
            == "mlx-cpu"
        )


def test_signed_time_window_and_endpoint_binding():
    auth = Authenticator(KEY)
    for offset in (-120, 120):
        stamp, nonce = str(int(time.time()) + offset), str(uuid4())
        headers = {
            "x-vibe-time": stamp,
            "x-vibe-id": nonce,
            "x-vibe-signature": signature(KEY, "POST", PATH, stamp, nonce, b"{}"),
        }
        assert not auth.verify(headers, "POST", PATH, b"{}")
    valid = signed_headers(KEY, "GET", "/v1/health", b"")
    assert not auth.verify(valid, "POST", PATH, b"")
    assert auth.verify(valid, "GET", "/v1/health", b"")


def test_contract_stream_replay_and_refusal():
    with client() as c:
        for text, kind in [("sample", "result"), ("short", "error")]:
            body = json.dumps({"text": text, "mode": "quick"}).encode()
            headers = signed_headers(KEY, "POST", PATH, body)
            assert c.post(PATH, content=body + b" ", headers=headers).status_code == 403
            response = c.post(PATH, content=body, headers=headers)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("application/x-ndjson")
            assert [json.loads(line)["type"] for line in response.iter_lines()] == [
                "accepted",
                "progress",
                kind,
            ]
            assert c.post(PATH, content=body, headers=headers).status_code == 403


def test_bad_input_is_private_and_memory_pressure_refuses_before_headers():
    with client(lambda: False) as c:
        for body, status in [
            (b'{"text":"private input"}', 400),
            (b'{"text":"private input","mode":"deep"}', 400),
            (b'{"text":"private input","mode":"quick"}', 503),
        ]:
            response = c.post(PATH, content=body, headers=signed_headers(KEY, "POST", PATH, body))
            assert response.status_code == status
            assert "private input" not in response.text


def test_quick_and_deep_have_separate_capacity():
    async def run():
        scheduler = Scheduler(lambda: True, 0.02)
        quick = [await scheduler.reserve("quick") for _ in range(4)]
        deep = await scheduler.reserve("deep")
        for mode in ("quick", "deep"):
            try:
                await scheduler.reserve(mode)
            except Busy:
                pass
            else:
                raise AssertionError("Expected saturated slot")
        for slot in [*quick, deep]:
            slot.release()
        (await scheduler.reserve("quick")).release()

    asyncio.run(run())
