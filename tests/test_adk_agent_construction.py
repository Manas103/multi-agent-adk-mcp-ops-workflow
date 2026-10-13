"""Genuine ADK integration tests: construct the real LlmAgent supervisor and
baseline from src/adk_app/agents.py, connect every McpToolset for real (a
real stdio subprocess running one of the two real MCP servers, a real MCP
initialize handshake, a real tools/list call), and assert the delegation
and tool-scoping structure the README claims. These do not call Gemini;
see agents.py's module docstring for why."""

import pytest

from src.adk_app import agents


def test_supervisor_has_four_sub_agents():
    supervisor = agents.build_supervisor_agent()
    assert len(supervisor.sub_agents) == 4
    assert {a.name for a in supervisor.sub_agents} == {
        "directory_ops_agent", "asset_recovery_agent", "policy_research_agent", "ticketing_agent",
    }
    assert supervisor.tools == []


@pytest.mark.asyncio
async def test_each_specialist_toolset_exposes_only_its_scoped_tools(seeded_db):
    supervisor = agents.build_supervisor_agent()
    expected = {
        "directory_ops_agent": {"lookup_employee", "propose_revoke_access"},
        "asset_recovery_agent": {"list_assets_for_employee", "propose_return_ticket"},
        "policy_research_agent": {"search_policies", "get_policy"},
        "ticketing_agent": {"propose_policy_ticket", "update_ticket_status", "list_tickets_for_employee"},
    }
    try:
        for sub_agent in supervisor.sub_agents:
            names = set()
            for toolset in sub_agent.tools:
                tools = await toolset.get_tools()
                names.update(t.name for t in tools)
                await toolset.close()
            assert names == expected[sub_agent.name], sub_agent.name
    finally:
        pass


@pytest.mark.asyncio
async def test_baseline_agent_exposes_every_tool_from_both_servers(seeded_db):
    baseline = agents.build_baseline_agent()
    names = set()
    for toolset in baseline.tools:
        tools = await toolset.get_tools()
        names.update(t.name for t in tools)
        await toolset.close()
    assert names == set(agents.ALL_LEGACY_TOOLS) | set(agents.ALL_POLICY_TOOLS)
