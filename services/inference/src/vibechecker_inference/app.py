import asyncio
import json
import os
import re
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from threading import Event

import httpx
from fastapi import FastAPI, Request
from pydantic import ValidationError
from starlette.responses import JSONResponse, Response, StreamingResponse
from vibechecker_engine import QuickEngine, Refusal
from vibechecker_engine.text import prepare

from .auth import Authenticator, signed_headers
from .generated_event import InferenceEvent
from .generated_request import AnalyzeRequest
from .scheduler import Busy, Scheduler

MAX_BODY = 800_128
HEARTBEAT_PATH = "/api/engine/heartbeat"


async def heartbeat(url, version, secret):
    payload = json.dumps({"engineVersion": version}).encode()
    async with httpx.AsyncClient(timeout=8) as client:
        while True:
            headers = signed_headers(secret, "POST", HEARTBEAT_PATH, payload)
            if preview_token := os.getenv("VERCEL_AUTOMATION_BYPASS_SECRET"):
                headers["x-vercel-protection-bypass"] = preview_token
            try:
                await client.post(
                    url, content=payload, headers={**headers, "content-type": "application/json"}
                )
            except httpx.HTTPError:
                # A missed pulse makes the router select Modal. The next pulse restores the primary.
                pass
            await asyncio.sleep(60)


def encode_event(**event):
    validated = InferenceEvent.model_validate(event)
    return (validated.model_dump_json(exclude_none=True) + "\n").encode()


def deep_from_env(quick):
    if not any(
        os.getenv(key)
        for key in (
            "VIBECHECKER_DEEP_MODEL",
            "VIBECHECKER_PAIR_OBSERVER",
            "VIBECHECKER_PAIR_PERFORMER",
        )
    ):
        return None
    from vibechecker_engine.deep import DeepEngine

    return DeepEngine.from_env(quick_extractor=quick.extractor)


def create_app(
    *,
    engine_factory: Callable = QuickEngine.from_env,
    deep_factory: Callable = deep_from_env,
    secret: bytes | None = None,
    version: str | None = None,
    scheduler: Scheduler | None = None,
    heartbeat_url=None,
):
    @asynccontextmanager
    async def lifespan(app):
        key = secret if secret is not None else os.environ["INFERENCE_HMAC_SECRET"].encode()
        app.state.auth = Authenticator(key)
        app.state.version = version or os.environ["ENGINE_VERSION"]
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,64}", app.state.version):
            raise ValueError("Invalid ENGINE_VERSION")
        app.state.engine = await asyncio.to_thread(engine_factory)
        app.state.deep = await asyncio.to_thread(deep_factory, app.state.engine)
        if app.state.deep is not None and app.state.deep.backend != app.state.engine.backend:
            raise ValueError("Quick and Deep must use the same backend")
        app.state.scheduler = scheduler or Scheduler()
        app.state.jobs = set()
        url = os.getenv("HEARTBEAT_URL") if heartbeat_url is None else heartbeat_url
        task = asyncio.create_task(heartbeat(url, app.state.version, key)) if url else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if app.state.jobs:
                await asyncio.gather(*app.state.jobs, return_exceptions=True)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path not in {"/v1/analyze", "/v1/health"}:
            return Response(status_code=404)
        # Cap chunked bodies as well as requests that declare their length.
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY:
                return Response(status_code=413)
            body.extend(chunk)
        if not app.state.auth.verify(request.headers, request.method, request.url.path, body):
            return Response(status_code=403)
        request.state.verified_body = bytes(body)
        return await call_next(request)

    @app.get("/v1/health")
    async def health():
        return {"backend": app.state.engine.backend, "engineVersion": app.state.version}

    @app.post("/v1/analyze")
    async def analyze(request: Request):
        try:
            data = AnalyzeRequest.model_validate_json(request.state.verified_body)
        except ValidationError:
            return JSONResponse({"code": "invalid_request"}, status_code=400)
        deep = data.mode == "deep"
        if deep and app.state.deep is None:
            return JSONResponse({"code": "busy"}, status_code=503)
        try:
            slot = await app.state.scheduler.reserve(data.mode)
        except Busy:
            return JSONResponse({"code": "busy"}, status_code=503, headers={"retry-after": "3"})

        stopped = Event()
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit(**event):
            line = encode_event(**event)
            loop.call_soon_threadsafe(queue.put_nowait, line)

        def score():
            try:
                doc = prepare(data.text) if deep else None
                chunks = max(1, len(doc.chunks)) if deep else 1
                emit(
                    type="accepted",
                    backend=app.state.engine.backend,
                    engineVersion=app.state.version,
                    chunks=chunks,
                )
                emit(type="progress", stage="deep" if deep else "scoring", done=0, total=chunks)
                if deep:
                    for event in app.state.deep.stream(doc):
                        if stopped.is_set():
                            break
                        emit(**event)
                else:
                    emit(type="result", result=app.state.engine.analyze(data.text))
            except Refusal as exc:
                emit(type="error", code=exc.code, retryable=False)
            except Exception:  # noqa: BLE001 -- translate private backend failures at the HTTP boundary.
                # Framework validation and backend exceptions can contain snippets of input.
                emit(type="error", code="internal", retryable=True)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        job = asyncio.create_task(asyncio.to_thread(score))
        app.state.jobs.add(job)
        job.add_done_callback(app.state.jobs.discard)
        # A disconnected client must not release the GPU slot during a running forward pass.
        job.add_done_callback(lambda _: slot.release())

        async def stream():
            try:
                while (line := await queue.get()) is not None:
                    yield line
            finally:
                stopped.set()

        return StreamingResponse(
            stream(), media_type="application/x-ndjson", headers={"cache-control": "no-store"}
        )

    return app


app = create_app()
