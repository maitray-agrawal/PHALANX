"""Security middleware, rate limiting, size limits, and RFC 7807 Problem+JSON handlers."""

import json
import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# Max request body size: 64 KB (manual 23 size limits)
MAX_REQUEST_BODY_BYTES = 64 * 1024

# Per-identity rate limit: 120 requests per minute
RATE_LIMIT_MAX_REQUESTS = 120
RATE_LIMIT_WINDOW_SECONDS = 60


class RequestIdAndStructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns X-Request-ID and emits structured JSON access logs with execution latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"

        response: Response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        log_payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": duration_ms,
            "client_ip": client_ip,
        }
        logging.getLogger("phalanx.access").info(json.dumps(log_payload))

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforce strict defensive security headers on all HTTP responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject payloads exceeding MAX_REQUEST_BODY_BYTES to prevent memory exhaustion."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return create_problem_response(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                title="Payload Too Large",
                detail=(
                    f"Request payload size ({content_length} bytes) exceeds limit "
                    f"of {MAX_REQUEST_BODY_BYTES} bytes"
                ),
                instance=str(request.url.path),
            )
        response: Response = await call_next(request)
        return response


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter per client identity."""

    def __init__(self, max_requests: int = 120, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, identity_key: str) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self.window_seconds
        timestamps = [t for t in self._history[identity_key] if t > cutoff]
        self._history[identity_key] = timestamps

        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
            return True, max(1, retry_after)

        self._history[identity_key].append(now)
        return False, 0


_rate_limiter = InMemoryRateLimiter(RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit per IP / authorization token identity."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Exempt health probes
        if request.url.path in ("/healthz", "/readyz", "/health"):
            res: Response = await call_next(request)
            return res

        auth_header = request.headers.get("authorization", "")
        client_ip = request.client.host if request.client else "unknown"
        identity_key = auth_header or client_ip

        is_limited, retry_after = _rate_limiter.is_rate_limited(identity_key)
        if is_limited:
            response = create_problem_response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                title="Too Many Requests",
                detail=f"Rate limit exceeded. Please retry after {retry_after} seconds.",
                instance=str(request.url.path),
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

        final_res: Response = await call_next(request)
        return final_res


def create_problem_response(
    status_code: int,
    title: str,
    detail: str,
    instance: str,
) -> JSONResponse:
    """Format RFC 7807 application/problem+json response without stack traces."""
    problem_body = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
    return JSONResponse(
        status_code=status_code,
        content=problem_body,
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register RFC 7807 Problem+JSON error handlers on FastAPI app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        title_map = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            409: "Conflict",
            413: "Payload Too Large",
            422: "Unprocessable Entity",
            429: "Too Many Requests",
            500: "Internal Server Error",
            503: "Service Unavailable",
        }
        title = title_map.get(exc.status_code, "HTTP Error")
        headers = dict(exc.headers or {})
        response = create_problem_response(
            status_code=exc.status_code,
            title=title,
            detail=str(exc.detail),
            instance=str(request.url.path),
        )
        for k, v in headers.items():
            response.headers[k] = v
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        error_details = []
        for e in errors:
            loc = " -> ".join(str(item) for item in e.get("loc", []))
            msg = e.get("msg", "Validation error")
            error_details.append(f"{loc}: {msg}")

        detail_str = "; ".join(error_details) if error_details else "Invalid request body."
        return create_problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation Error",
            detail=detail_str,
            instance=str(request.url.path),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("phalanx").error("Unhandled exception: %s", exc)
        return create_problem_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="An unexpected internal server error occurred.",
            instance=str(request.url.path),
        )


class LogRedactionFilter(logging.Filter):
    """Redacts secrets and tokens from logging output."""

    SENSITIVE_PATTERNS = [
        re.compile(
            r'(?i)(secret|token|password|authorization|signature|key)\s*[:=]\s*["\']?([^"\'\s]+)'
        ),
        re.compile(r"(?i)(bearer\s+)([A-Za-z0-9_\-\.]+)"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern in self.SENSITIVE_PATTERNS:
                msg = pattern.sub(r"\1 [REDACTED]", msg)
            record.msg = msg
        return True
