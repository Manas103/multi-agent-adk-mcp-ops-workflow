"""Direct tool-level tests against the two real MCP servers over a real
stdio subprocess and a real Postgres connection, no ADK involved. These are
the same servers src/adk_app/agents.py wires MCPToolset to and
src/orchestrator talks to for the benchmark."""

import pytest

from src.orchestrator.mcp_client import McpServerClient


@pytest.mark.asyncio
async def test_legacy_directory_server_lists_its_tools(seeded_db):
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as client:
        names = await client.list_tool_names()
    assert set(names) == {
        "lookup_employee", "list_assets_for_employee", "list_tickets_for_employee",
        "propose_revoke_access", "propose_return_ticket", "propose_policy_ticket",
        "update_ticket_status",
    }


@pytest.mark.asyncio
async def test_policy_doc_server_lists_its_tools(seeded_db):
    async with McpServerClient("src.mcp_servers.policy_doc_server") as client:
        names = await client.list_tool_names()
    assert set(names) == {"search_policies", "get_policy"}


@pytest.mark.asyncio
async def test_lookup_employee_real_row(seeded_db):
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as client:
        result = await client.call("lookup_employee", employee_id=1)
    assert result["found"] is True
    assert result["employee_id"] == 1


@pytest.mark.asyncio
async def test_lookup_employee_missing_row(seeded_db):
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as client:
        result = await client.call("lookup_employee", employee_id=99999)
    assert result["found"] is False


@pytest.mark.asyncio
async def test_propose_revoke_access_valid_queues_a_schema_valid_action(seeded_db):
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as client:
        result = await client.call(
            "propose_revoke_access", task_id="t1", run_id="r1", employee_id=1,
            access_level="ADMIN", reason="offboarding, revoking admin access", proposed_by="test",
        )
    assert result["ok"] is True
    assert result["schema_invalid"] is False


@pytest.mark.asyncio
async def test_propose_revoke_access_short_reason_is_schema_invalid(seeded_db):
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as client:
        result = await client.call(
            "propose_revoke_access", task_id="t1", run_id="r1", employee_id=1,
            access_level="ADMIN", reason="no", proposed_by="test",
        )
    assert result["ok"] is False
    assert result["schema_invalid"] is True


@pytest.mark.asyncio
async def test_search_policies_ranks_by_overlap(seeded_db):
    async with McpServerClient("src.mcp_servers.policy_doc_server") as client:
        result = await client.call("search_policies", query="ALL-level access revocation sign-off")
    assert result["results"], "expected at least one matching policy document"
    assert result["results"][0]["doc_id"] == "POL-002"


@pytest.mark.asyncio
async def test_get_policy_found_and_not_found(seeded_db):
    async with McpServerClient("src.mcp_servers.policy_doc_server") as client:
        found = await client.call("get_policy", doc_id="POL-001")
        missing = await client.call("get_policy", doc_id="POL-999")
    assert found["found"] is True
    assert missing["found"] is False
