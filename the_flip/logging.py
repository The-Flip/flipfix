"""Custom logging formatters."""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

# Fields that are part of the standard LogRecord, not user-provided extras
RESERVED_LOG_ATTRS = frozenset(
    [
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    ]
)

# Context used by logging filters/middleware to annotate records (e.g., request_id)
_log_context: contextvars.ContextVar[Mapping[str, Any] | None] = contextvars.ContextVar(
    "log_context", default=None
)


def bind_log_context(**context: Any) -> contextvars.Token:
    """Bind contextual fields (e.g., request_id, user_id) for the current task/request."""
    filtered = {k: v for k, v in context.items() if v not in {None, ""}}
    return _log_context.set(filtered)


def reset_log_context(token: contextvars.Token) -> None:
    """Reset contextual fields after a task/request completes."""
    with contextlib.suppress(Exception):
        _log_context.reset(token)


def current_log_context() -> dict[str, Any]:
    """Return a copy of the current contextual fields (safe to pass across tasks)."""
    context = _log_context.get({}) or {}
    return dict(context)


class RequestContextFilter(logging.Filter):
    """Attach contextvar fields (request_id, user_id, path, etc.) to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = _log_context.get(None) or {}
        for key, value in context.items():
            setattr(record, key, value)
        return True


def _get_extra_fields(record: logging.LogRecord) -> dict:
    """Extract extra fields from a log record."""
    extras = {}
    for key, value in record.__dict__.items():
        if key not in RESERVED_LOG_ATTRS and not key.startswith("_"):
            extras[key] = value
    return extras


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for structured logging.

    Includes all extra fields passed to logger calls, making logs
    easy to parse and search in log aggregation systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields passed via logger.info(..., extra={...})
        for key, value in _get_extra_fields(record).items():
            try:
                json.dumps(value)
                log_data[key] = value
            except (TypeError, ValueError):
                log_data[key] = str(value)

        return json.dumps(log_data)


class DevFormatter(logging.Formatter):
    """Human-readable formatter for development that includes extra fields.

    Format: timestamp LEVEL    logger message key=value key2=value2
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with extras appended."""
        # Base format
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        base = f"{timestamp} {record.levelname:8} {record.name} {record.getMessage()}"

        # Append extras
        extras = _get_extra_fields(record)
        if extras:
            extra_str = " ".join(f"{k}={v!r}" for k, v in extras.items())
            base = f"{base} | {extra_str}"

        # Add exception if present
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"

        return base
