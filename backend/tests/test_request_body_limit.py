from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request

from main import RequestBodyLimitMiddleware


ASGIMessage = dict[str, Any]


def _invoke_asgi(
    app: Callable[..., Awaitable[None]],
    *,
    chunks: list[bytes],
    content_type: str,
    request_id: str = "stream-limit-test",
) -> tuple[list[ASGIMessage], int]:
    sent: list[ASGIMessage] = []
    receive_calls = 0

    async def run() -> None:
        nonlocal receive_calls
        pending = list(chunks)

        async def receive() -> ASGIMessage:
            nonlocal receive_calls
            receive_calls += 1
            if pending:
                body = pending.pop(0)
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": bool(pending),
                }
            return {"type": "http.disconnect"}

        async def send(message: ASGIMessage) -> None:
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            # Deliberately omit Content-Length to exercise streamed/chunked input.
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", content_type.encode("ascii")),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "state": {"request_id": request_id},
        }
        await app(scope, receive, send)

    asyncio.run(run())
    return sent, receive_calls


def _response(messages: list[ASGIMessage]) -> tuple[int, dict[str, str], Any]:
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return start["status"], headers, json.loads(body)


def test_chunked_multipart_is_rejected_before_form_parsing_finishes() -> None:
    boundary = "stream-cap-boundary"
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="sheet.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("ascii")
    file_chunk = b"x" * 64
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    parser_completed = False

    test_app = FastAPI()

    @test_app.post("/upload")
    async def upload(request: Request) -> dict[str, bool]:
        nonlocal parser_completed
        await request.form()
        parser_completed = True
        return {"parsed": True}

    test_app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=len(prefix) + len(file_chunk) - 1,
        batch_limit_mb=1,
    )

    messages, receive_calls = _invoke_asgi(
        test_app,
        chunks=[prefix, file_chunk, suffix],
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    status, headers, payload = _response(messages)

    assert status == 413
    assert payload == {
        "success": False,
        "data": None,
        "message": "Request body exceeds the 1 MB batch limit",
    }
    assert headers["x-request-id"] == "stream-limit-test"
    assert receive_calls == 2
    assert parser_completed is False


def test_stream_at_exact_request_limit_reaches_the_endpoint() -> None:
    endpoint_received = 0
    chunks = [b"first", b"second", b"third"]

    test_app = FastAPI()

    @test_app.post("/upload")
    async def upload(request: Request) -> dict[str, int]:
        nonlocal endpoint_received
        endpoint_received = len(await request.body())
        return {"received": endpoint_received}

    test_app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=sum(map(len, chunks)),
        batch_limit_mb=1,
    )

    messages, receive_calls = _invoke_asgi(
        test_app,
        chunks=chunks,
        content_type="application/octet-stream",
    )
    status, _, payload = _response(messages)

    assert status == 200
    assert payload == {"received": sum(map(len, chunks))}
    assert receive_calls == len(chunks)
    assert endpoint_received == sum(map(len, chunks))


def test_declared_oversize_response_keeps_error_envelope_and_request_id(client) -> None:
    response = client.post(
        "/",
        content=b"ignored",
        headers={
            "Content-Length": str(1024 * 1024 * 1024),
            "X-Request-ID": "declared-limit-test",
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "success": False,
        "data": None,
        "message": "Request body exceeds the 100 MB batch limit",
    }
    assert response.headers["X-Request-ID"] == "declared-limit-test"
