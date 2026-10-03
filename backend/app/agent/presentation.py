"""Shape a stored agent run for an admin view. Secrets stay redacted and results stay short."""

import json
import re
from datetime import datetime
from typing import Any

from app.agent.tracking import redact

_SUMMARY_LIMIT = 240
_ARGUMENT_TEXT_LIMIT = 400
_SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
)


def present_arguments(arguments: Any) -> Any:
    return _bound_text(redact(arguments))


def summarize_tool_result(tool_name: str, result: Any) -> str | None:
    """A short description of a tool result. Full passages and customer rows are not included."""
    if result is None:
        return None
    value = redact(result)
    if isinstance(value, dict) and "error" in value:
        return _clip(f"Failed: {value['error']}")
    if tool_name == "calculator" and isinstance(value, dict) and "result" in value:
        return _clip(str(value["result"]))
    if tool_name == "search_knowledge" and isinstance(value, dict):
        return _knowledge_summary(value.get("results"))
    if tool_name == "analytics" and isinstance(value, dict):
        return _analytics_summary(value)
    return _clip(_compact(value))


def present_tool_call(
    *,
    tool_name: str,
    status: str,
    arguments: Any,
    result: Any,
    started_at: datetime,
    completed_at: datetime | None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "status": status,
        "arguments": present_arguments(arguments),
        "result_summary": summarize_tool_result(tool_name, result),
        "started_at": started_at,
        "completed_at": completed_at,
    }


def _knowledge_summary(results: Any) -> str:
    if not isinstance(results, list) or not results:
        return "No matching passages."
    names: list[str] = []
    for hit in results:
        if not isinstance(hit, dict):
            continue
        name = hit.get("document")
        if isinstance(name, str) and name not in names:
            names.append(name)
    count = len(results)
    if not names:
        return f"{_count(count, 'passage', 'passages')}."
    return _clip(f"{_count(count, 'passage', 'passages')} from {', '.join(names)}.")


def _analytics_summary(value: dict[str, Any]) -> str:
    operation = value.get("operation")
    label = operation if isinstance(operation, str) else "analytics"
    if isinstance(value.get("customers"), list):
        return _clip(f"{label}: {_count(len(value['customers']), 'customer', 'customers')}.")
    if isinstance(value.get("currencies"), list):
        return _clip(f"{label}: {_count(len(value['currencies']), 'currency', 'currencies')}.")
    if "refund_count" in value:
        return _clip(f"{label}: {_count(_as_int(value['refund_count']), 'refund', 'refunds')}.")
    if "order_count" in value:
        return _clip(f"{label}: {_count(_as_int(value['order_count']), 'order', 'orders')}.")
    return _clip(label)


def _count(count: int, singular: str, plural: str) -> str:
    noun = singular if count == 1 else plural
    return f"{count} {noun}"


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _compact(value: Any) -> str:
    try:
        return json.dumps(value, default=str, separators=(",", ":"))
    except TypeError:
        return str(value)


def _bound_text(value: Any) -> Any:
    if isinstance(value, str):
        return _clip(value, _ARGUMENT_TEXT_LIMIT)
    if isinstance(value, dict):
        return {key: _bound_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_bound_text(item) for item in value]
    return value


def _clip(text: str, limit: int = _SUMMARY_LIMIT) -> str:
    cleaned = _SECRET_VALUE.sub("[redacted]", text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
