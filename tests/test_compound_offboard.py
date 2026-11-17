"""End-to-end tests of the compound offboarding saga over the real
legacy_directory_server MCP server and real Postgres: the unfaulted happy
path, each of the three fault types landing after a different number of
already-committed mutations, and the snapshot-equality invariant that 0
partial writes is actually measuring."""

import pytest

from src.faults.transport import FaultSpec, FaultType
from src.orchestrator.mcp_client import McpServerClient
from src.workflows import compensator, compound_offboard


def _asset_id(seeded_db, employee_id: int) -> int:
    return seeded_db["assets_by_employee"][employee_id - 1][1]["asset_id"]


@pytest.mark.asyncio
async def test_unfaulted_saga_completes_all_three_mutations(seeded_db):
    employee_id = 40
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy:
        result = await compound_offboard.run_compound_offboard(
            employee_id, _asset_id(seeded_db, employee_id), legacy, "r-happy", "t-happy", fault=None,
        )
    assert result.status == "completed"
    assert result.completed_mutations == [
        "REVOKE_ACCESS", "CREATE_TICKET:ASSET_RETURN", "CREATE_TICKET:POLICY_COMPLIANCE",
    ]
    assert result.compensated_mutations == []
    assert result.partial_write is False


@pytest.mark.asyncio
async def test_timeout_before_any_mutation_needs_no_compensation(seeded_db):
    employee_id = 41
    fault = FaultSpec(call_ordinal=2, fault_type=FaultType.TIMEOUT)  # the propose_revoke_access call itself
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy:
        result = await compound_offboard.run_compound_offboard(
            employee_id, _asset_id(seeded_db, employee_id), legacy, "r-t1", "t-t1", fault=fault,
        )
    assert result.status == "failed_compensated"
    assert result.completed_mutations == []
    assert result.compensated_mutations == []
    assert result.partial_write is False


@pytest.mark.asyncio
async def test_timeout_after_revoke_compensates_with_restore(seeded_db):
    employee_id = 42
    fault = FaultSpec(call_ordinal=4, fault_type=FaultType.TIMEOUT)  # list_assets_for_employee
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy:
        result = await compound_offboard.run_compound_offboard(
            employee_id, _asset_id(seeded_db, employee_id), legacy, "r-t2", "t-t2", fault=fault,
        )
    assert result.status == "failed_compensated"
    assert result.completed_mutations == ["REVOKE_ACCESS"]
    assert result.compensated_mutations == ["RESTORE_ACCESS"]
    assert result.partial_write is False


@pytest.mark.asyncio
async def test_server_error_after_both_mutations_compensates_both_in_reverse_order(seeded_db):
    employee_id = 43
    fault = FaultSpec(call_ordinal=6, fault_type=FaultType.SERVER_ERROR_5XX)  # propose_policy_ticket
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy:
        result = await compound_offboard.run_compound_offboard(
            employee_id, _asset_id(seeded_db, employee_id), legacy, "r-s1", "t-s1", fault=fault,
        )
    assert result.status == "failed_compensated"
    assert result.completed_mutations == ["REVOKE_ACCESS", "CREATE_TICKET:ASSET_RETURN"]
    assert result.compensated_mutations == ["CANCEL_TICKET:ASSET_RETURN", "RESTORE_ACCESS"]
    assert result.partial_write is False


@pytest.mark.asyncio
async def test_stale_read_detected_and_compensated(seeded_db):
    employee_id = 44
    fault = FaultSpec(call_ordinal=3, fault_type=FaultType.STALE_READ)  # the confirm lookup_employee
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy:
        result = await compound_offboard.run_compound_offboard(
            employee_id, _asset_id(seeded_db, employee_id), legacy, "r-sr", "t-sr", fault=fault,
        )
    assert result.status == "failed_compensated"
    assert result.fault["fault_type"] == "STALE_READ"
    assert result.completed_mutations == ["REVOKE_ACCESS"]
    assert result.compensated_mutations == ["RESTORE_ACCESS"]
    assert result.partial_write is False


@pytest.mark.asyncio
async def test_snapshot_equality_is_the_actual_partial_write_check(seeded_db):
    """A direct test of the invariant the benchmark script relies on: after
    a fault and its compensation, the employee/asset/ticket snapshot must be
    byte-for-byte equal to the snapshot taken before the saga started."""
    employee_id = 45
    before = compensator.snapshot_employee_state(employee_id)
    fault = FaultSpec(call_ordinal=6, fault_type=FaultType.SERVER_ERROR_5XX)
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy:
        result = await compound_offboard.run_compound_offboard(
            employee_id, _asset_id(seeded_db, employee_id), legacy, "r-snap", "t-snap", fault=fault,
        )
    after = compensator.snapshot_employee_state(employee_id)
    assert before == after
    assert result.snapshot_before == before
    assert result.snapshot_after == after
