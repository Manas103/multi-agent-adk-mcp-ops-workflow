"""Unit tests for FaultInjectingClient: does it fire at the configured
ordinal and only there, and does STALE_READ genuinely make the real call
before substituting an earlier real response for it?"""

import pytest

from src.faults.transport import FaultInjectingClient, FaultSpec, FaultType, TransportFault


class _FakeMcpClient:
    """Minimal stand-in with the same async .call(name, **kwargs) shape as
    McpServerClient, so this file tests FaultInjectingClient's own counting
    and substitution logic in isolation from any real MCP server."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._responses = {"tool_a": [{"v": 1}, {"v": 2}, {"v": 3}]}

    async def call(self, tool_name: str, **kwargs) -> dict:
        self.calls.append((tool_name, kwargs))
        n = len([c for c in self.calls if c[0] == tool_name])
        return self._responses[tool_name][n - 1]


@pytest.mark.asyncio
async def test_no_fault_passes_every_call_through():
    fake = _FakeMcpClient()
    client = FaultInjectingClient(fake, fault=None)
    assert await client.call("tool_a") == {"v": 1}
    assert await client.call("tool_a") == {"v": 2}
    assert client.call_count == 2
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_timeout_fires_only_at_its_ordinal():
    fake = _FakeMcpClient()
    client = FaultInjectingClient(fake, fault=FaultSpec(call_ordinal=2, fault_type=FaultType.TIMEOUT))
    assert await client.call("tool_a") == {"v": 1}
    with pytest.raises(TransportFault) as exc:
        await client.call("tool_a")
    assert exc.value.fault_type == FaultType.TIMEOUT
    assert exc.value.call_ordinal == 2
    # the 2nd call never reached the real client
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_server_error_5xx_fires_only_at_its_ordinal():
    fake = _FakeMcpClient()
    client = FaultInjectingClient(fake, fault=FaultSpec(call_ordinal=1, fault_type=FaultType.SERVER_ERROR_5XX))
    with pytest.raises(TransportFault) as exc:
        await client.call("tool_a")
    assert exc.value.fault_type == FaultType.SERVER_ERROR_5XX
    assert len(fake.calls) == 0


@pytest.mark.asyncio
async def test_stale_read_makes_the_real_call_then_returns_an_earlier_response():
    fake = _FakeMcpClient()
    client = FaultInjectingClient(fake, fault=FaultSpec(call_ordinal=2, fault_type=FaultType.STALE_READ))
    first = await client.call("tool_a")
    assert first == {"v": 1}
    second = await client.call("tool_a")
    # the real round trip happened (fake.calls has 2 entries, so the 2nd real
    # response {"v": 2} genuinely exists), but the caller is handed back the
    # cached 1st response instead
    assert len(fake.calls) == 2
    assert second == {"v": 1}


@pytest.mark.asyncio
async def test_stale_read_with_no_prior_response_raises():
    fake = _FakeMcpClient()
    client = FaultInjectingClient(fake, fault=FaultSpec(call_ordinal=1, fault_type=FaultType.STALE_READ))
    with pytest.raises(TransportFault) as exc:
        await client.call("tool_a")
    assert exc.value.fault_type == FaultType.STALE_READ
