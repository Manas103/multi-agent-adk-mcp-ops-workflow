"""The self-reflection retry loop: call a state-changing tool, and if the
tool reports `schema_invalid: True`, rebuild the arguments for the next
attempt and try again, up to `max_attempts` (default from src.config). This
is the one mechanism shared, unmodified, between the multi-agent system and
the ReAct baseline; it does not count against either one's tool-call step
budget, because it is correcting a validation failure on the same logical
step, not choosing a different one.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from .. import config
from .mcp_client import McpServerClient


async def propose_with_self_reflection(
    client: McpServerClient,
    tool_name: str,
    build_args: Callable[[int], dict],
    max_attempts: int = config.MAX_SELF_REFLECTION_ATTEMPTS,
) -> dict:
    """`build_args(attempt)` is 1-indexed and returns the raw kwargs for that
    attempt (task_id and run_id are expected to already be inside them)."""

    attempt = 1
    last_result = None
    while attempt <= max_attempts:
        args = build_args(attempt)
        last_result = await client.call(tool_name, **args)
        if last_result.get("ok"):
            return {**last_result, "attempts": attempt}
        attempt += 1
    return {**(last_result or {}), "attempts": attempt - 1}
