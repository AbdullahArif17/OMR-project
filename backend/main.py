from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings
from database import engine
from errors import ApplicationError
from routers import answer_keys, auth, exams, results, scanner


logger = logging.getLogger("omr_api")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MULTIPART_OVERHEAD_ALLOWANCE_BYTES = 10 * 1024 * 1024


class RequestBodyTooLarge(Exception):
    """Raised before an oversized request body reaches endpoint parsing."""


class RequestBodyLimitMiddleware:
    """Enforce a request limit while ASGI body chunks are being received."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        batch_limit_mb: int,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.batch_limit_mb = batch_limit_mb

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            request_id = scope.get("state", {}).get("request_id")
            headers = {"X-Request-ID": request_id} if request_id else None
            response = JSONResponse(
                status_code=413,
                content=_error_content(
                    f"Request body exceeds the {self.batch_limit_mb} MB batch limit"
                ),
                headers=headers,
            )
            await response(scope, receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def _run_maintenance():
        from services.storage_maintenance import run_storage_maintenance
        try:
            report = run_storage_maintenance()
            logger.info(
                "Startup maintenance: deleted %d workspaces, %d orphan uploads, %d idempotency records",
                report.workspaces_deleted,
                report.orphan_uploads_deleted,
                report.idempotency_records_deleted,
            )
        except Exception:
            logger.exception("Storage maintenance failed during startup")
            
    if settings.environment != "test":
        import threading
        threading.Thread(target=_run_maintenance, daemon=True, name="startup-maintenance").start()
    
    yield


app = FastAPI(
    title="OMR System API",
    description="Create exams, detect marked answers, grade sheets, and export results.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_bytes=(
        settings.max_batch_size_bytes + MULTIPART_OVERHEAD_ALLOWANCE_BYTES
    ),
    batch_limit_mb=settings.max_batch_size_mb,
)


@app.middleware("http")
async def request_safety_and_logging(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid.uuid4().hex
    )
    request.state.request_id = request_id
    content_length = request.headers.get("content-length")
    request_limit = (
        settings.max_batch_size_bytes + MULTIPART_OVERHEAD_ALLOWANCE_BYTES
    )
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=_error_content("Invalid Content-Length header"),
                headers={"X-Request-ID": request_id},
            )
        if declared_size < 0 or declared_size > request_limit:
            return JSONResponse(
                status_code=413,
                content=_error_content(
                    f"Request body exceeds the {settings.max_batch_size_mb} MB batch limit"
                ),
                headers={"X-Request-ID": request_id},
            )

    started_at = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = (
        "no-store" if request.url.path != "/health/live" else "no-cache"
    )
    logger.info(
        "%s %s -> %s in %.2fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response


def _error_content(message: str, data: Any = None) -> dict[str, Any]:
    return {"success": False, "data": data, "message": message}


@app.exception_handler(ApplicationError)
async def application_error_handler(
    _: Request, exc: ApplicationError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(_error_content(exc.message, exc.data)),
        headers=exc.headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, str):
        message = detail
        data = None
    elif isinstance(detail, dict):
        message = str(detail.get("message", "Request failed"))
        data = detail.get("data", detail)
    else:
        message = "Request failed"
        data = detail
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(_error_content(message, data)),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    messages: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", []) if part != "body")
        prefix = f"{location}: " if location else ""
        messages.append(prefix + str(error.get("msg", "Invalid value")))
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            _error_content(
                "; ".join(messages) or "Request validation failed",
                {"errors": errors},
            )
        ),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error while processing %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_error_content("An unexpected server error occurred"),
    )


app.include_router(auth.router)
app.include_router(exams.router)
app.include_router(answer_keys.router)
app.include_router(scanner.router)
app.include_router(results.router)


@app.get("/")
def api_root() -> dict[str, object]:
    return {
        "success": True,
        "data": {"service": "OMR System API", "version": app.version},
        "message": "API is running",
    }


@app.get("/health")
def health_check() -> dict[str, object]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "success": True,
        "data": {"database": "healthy"},
        "message": "Service is healthy",
    }


@app.get("/health/live", include_in_schema=False)
def liveness_check() -> dict[str, object]:
    return {
        "success": True,
        "data": {"service": "alive"},
        "message": "Service is alive",
    }


@app.get("/health/ready", include_in_schema=False)
def readiness_check() -> dict[str, object]:
    return health_check()
