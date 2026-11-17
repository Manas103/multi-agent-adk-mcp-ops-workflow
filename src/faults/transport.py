"""Fault-injection transport wrapper around McpServerClient, used only by
the compound offboarding saga (src/workflows/compound_offboard.py) and its
benchmark (scripts/run_fault_injection_benchmark.py). Every fault below
either interrupts a genuine MCP round trip that would otherwise have
succeeded (TIMEOUT, SERVER_ERROR_5XX) or lets the real round trip happen and
then substitutes a genuinely-earlier real response for it (STALE_READ);
nothing here mocks away a call that was never made.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Optional

from ..orchestrator.mcp_client import McpServerClient


class FaultType(str, Enum):
    TIMEOUT = "TIMEOUT"
    SERVER_ERROR_5XX = "SERVER_ERROR_5XX"
    STALE_READ = "STALE_READ"


class TransportFault(Exception):
    """Raised either by FaultInjectingClient itself (TIMEOUT,
    SERVER_ERROR_5XX: the call never completed) or by a workflow's own
    consistency check after receiving a stale-but-successful response
    (STALE_READ: the call completed, but the workflow noticed the data it
    got back was not fresh)."""

    def __init__(self, fault_type: FaultType, call_ordinal: int, tool_name: str):
        self.fault_type = fault_type
        self.call_ordinal = call_ordinal
        self.tool_name = tool_name
        super().__init__(f"{fault_type.value} injected at call #{call_ordinal} ({tool_name})")


@dataclasses.dataclass(frozen=True)
class FaultSpec:
    """call_ordinal is 1-indexed over the sequence of MCP calls the target
    workflow itself makes through the FaultInjectingClient wrapping it, not
    a global counter; see src/workflows/compound_offboard.py's module
    docstring for the saga's own fixed call sequence."""

    call_ordinal: int
    fault_type: FaultType


class FaultInjectingClient:
    """Wraps one already-connected McpServerClient. Counts every call made
    through this wrapper; at the configured call_ordinal, TIMEOUT and
    SERVER_ERROR_5XX raise TransportFault instead of letting the call
    reach the server, and STALE_READ makes the real call (so the server
    genuinely does the work and the database genuinely reflects it) but
    returns whichever real response this same tool_name last produced
    through this wrapper, which may now be out of date. Every other call
    passes through untouched and updates that per-tool cache."""

    def __init__(self, client: McpServerClient, fault: Optional[FaultSpec] = None):
        self._client = client
        self._fault = fault
        self._call_count = 0
        self._last_response_by_tool: dict[str, dict] = {}

    @property
    def call_count(self) -> int:
        return self._call_count

    async def call(self, tool_name: str, **kwargs) -> dict:
        self._call_count += 1
        ordinal = self._call_count

        if self._fault is not None and ordinal == self._fault.call_ordinal:
            if self._fault.fault_type in (FaultType.TIMEOUT, FaultType.SERVER_ERROR_5XX):
                raise TransportFault(self._fault.fault_type, ordinal, tool_name)
            if self._fault.fault_type == FaultType.STALE_READ:
                await self._client.call(tool_name, **kwargs)  # the real round trip still happens
                stale = self._last_response_by_tool.get(tool_name)
                if stale is None:
                    # no earlier real response to this tool exists to serve as
                    # stale data; fail loudly rather than silently returning {}
                    raise TransportFault(FaultType.STALE_READ, ordinal, tool_name)
                return stale

        result = await self._client.call(tool_name, **kwargs)
        self._last_response_by_tool[tool_name] = result
        return result
