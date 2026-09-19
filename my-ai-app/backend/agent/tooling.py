"""Shared registry, policy and audit primitives for agent tools."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping
from uuid import uuid4


ToolHandler = Callable[[str, Mapping[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    requires_confirmation: bool = False
    timeout_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "requires_confirmation": self.requires_confirmation,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    ok: bool
    tool_name: str
    status: str
    data: Mapping[str, Any] = field(default_factory=dict)
    message: str = ""
    confirmation_id: str | None = None
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        result = {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "status": self.status,
            "data": dict(self.data),
            "message": self.message,
            "duration_ms": round(self.duration_ms, 1),
        }
        if self.confirmation_id:
            result["confirmation_id"] = self.confirmation_id
        return result


@dataclass(frozen=True, slots=True)
class ToolAuditEntry:
    user_id: str
    tool_name: str
    status: str
    created_at: datetime
    duration_ms: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "duration_ms": round(self.duration_ms, 1),
            "metadata": dict(self.metadata),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if not definition.name or definition.name in self._definitions:
            raise ValueError(f"Tool không hợp lệ hoặc đã tồn tại: {definition.name}")
        self._definitions[definition.name] = definition
        self._handlers[definition.name] = handler

    def get(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def handler(self, name: str) -> ToolHandler | None:
        return self._handlers.get(name)

    def definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())


class ToolExecutor:
    """Execute registered tools with per-user rate limits and confirmations."""

    STATUS_EXECUTED = "executed"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"
    STATUS_CONFIRMATION_REQUIRED = "confirmation_required"
    STATUS_RATE_LIMITED = "rate_limited"

    def __init__(self, registry: ToolRegistry, *, max_calls: int = 3, window_seconds: float = 60, timeout_seconds: float = 15, max_audit_entries: int = 500) -> None:
        self.registry = registry
        self.max_calls = max(1, max_calls)
        self.window_seconds = max(1.0, window_seconds)
        self.timeout_seconds = max(0.1, timeout_seconds)
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._pending: dict[str, tuple[str, str, dict[str, Any]]] = {}
        self._audit: deque[ToolAuditEntry] = deque(maxlen=max_audit_entries)

    def _rate_allowed(self, user_id: str) -> bool:
        now = time.monotonic()
        calls = self._calls[user_id]
        while calls and now - calls[0] > self.window_seconds:
            calls.popleft()
        if len(calls) >= self.max_calls:
            return False
        calls.append(now)
        return True

    def _audit_entry(self, user_id: str, name: str, status: str, started: float, **metadata: Any) -> None:
        self._audit.append(ToolAuditEntry(user_id, name, status, datetime.now(timezone.utc), (time.monotonic() - started) * 1000, metadata))

    async def execute(self, name: str, user_id: str, arguments: Mapping[str, Any] | None = None, *, confirmed: bool = False, confirmation_id: str | None = None) -> ToolExecutionResult:
        started = time.monotonic()
        definition = self.registry.get(name)
        if definition is None:
            self._audit_entry(user_id, name, self.STATUS_FAILED, started, reason="unknown_tool")
            return ToolExecutionResult(False, name, self.STATUS_FAILED, message="tool_not_found")
        if not self._rate_allowed(user_id):
            self._audit_entry(user_id, name, self.STATUS_RATE_LIMITED, started)
            return ToolExecutionResult(False, name, self.STATUS_RATE_LIMITED, message="tool_call_limit_reached")
        if definition.requires_confirmation and not confirmed and not confirmation_id:
            token = uuid4().hex
            self._pending[token] = (name, user_id, dict(arguments or {}))
            self._audit_entry(user_id, name, self.STATUS_CONFIRMATION_REQUIRED, started)
            return ToolExecutionResult(False, name, self.STATUS_CONFIRMATION_REQUIRED, message="user_confirmation_required", confirmation_id=token, duration_ms=(time.monotonic() - started) * 1000)
        if confirmation_id:
            pending = self._pending.pop(confirmation_id, None)
            if pending is None or pending[:2] != (name, user_id):
                return ToolExecutionResult(False, name, self.STATUS_FAILED, message="invalid_confirmation")
            arguments = pending[2]

        handler = self.registry.handler(name)
        try:
            if handler is None:
                raise RuntimeError("tool_handler_missing")
            timeout_seconds = definition.timeout_seconds or self.timeout_seconds
            if inspect.iscoroutinefunction(handler):
                output = await asyncio.wait_for(handler(user_id, dict(arguments or {})), timeout=timeout_seconds)
            else:
                output = await asyncio.wait_for(
                    asyncio.to_thread(handler, user_id, dict(arguments or {})),
                    timeout=timeout_seconds,
                )
            result = ToolExecutionResult(True, name, self.STATUS_EXECUTED, data=dict(output or {}), duration_ms=(time.monotonic() - started) * 1000)
            self._audit_entry(user_id, name, result.status, started)
            return result
        except asyncio.TimeoutError:
            self._audit_entry(user_id, name, self.STATUS_TIMEOUT, started)
            return ToolExecutionResult(False, name, self.STATUS_TIMEOUT, message="tool_timeout", duration_ms=(time.monotonic() - started) * 1000)
        except Exception as exc:
            self._audit_entry(user_id, name, self.STATUS_FAILED, started, error=type(exc).__name__)
            return ToolExecutionResult(False, name, self.STATUS_FAILED, message=str(exc), duration_ms=(time.monotonic() - started) * 1000)

    def get_audit(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        return [entry.as_dict() for entry in list(self._audit)[-safe_limit:] if entry.user_id == user_id]
