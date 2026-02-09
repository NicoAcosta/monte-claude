"""Structured JSON logging with request context."""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
client_ip_var: ContextVar[str] = ContextVar("client_ip", default="")

_configured = False


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(""),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging() -> None:
    """Set up JSON logging. Idempotent — safe to call multiple times."""
    global _configured
    if _configured:
        return
    _configured = True

    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)

    fmt = JSONFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=50 * 1024 * 1024, backupCount=5,
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Quiet noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        client_ip = request.client.host if request.client else ""

        request_id_var.set(req_id)
        client_ip_var.set(client_ip)

        _log = logging.getLogger("poker.http")
        _log.info("request_start method=%s path=%s", request.method, request.url.path)

        response: Response = await call_next(request)

        response.headers["X-Request-ID"] = req_id
        _log.info(
            "request_end method=%s path=%s status=%d",
            request.method, request.url.path, response.status_code,
        )
        return response
