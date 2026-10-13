"""The real Google ADK agent graph: one supervisor LlmAgent delegating to
four specialist sub-agents, each scoped to the subset of the two real MCP
servers its mandate needs, plus a single-agent ReAct baseline with every
tool from both servers unscoped.

This module is genuine ADK: `build_supervisor_agent()` and
`build_baseline_agent()` return real `google.adk.agents.LlmAgent` objects
wired to real `McpToolset` connections that launch the real MCP servers in
`src/mcp_servers/` over stdio (see `tests/test_adk_agent_construction.py`,
which connects every toolset for real and asserts the tool lists). What
these agents cannot do in this session is *run*: an `LlmAgent` needs a
model backend, and this headless machine has no `GOOGLE_API_KEY` and no
`gcloud` credentials (see the README's Honest framing). The measured
benchmark in `scripts/run_benchmark.py` therefore drives a separate,
clearly-disclosed deterministic orchestrator in `src/orchestrator/` against
the same two real MCP servers, the same pattern this portfolio already uses
for `claude_cli_judge.py` in `agent-task-environment-state-benchmark`
(implemented, not run live; a deterministic stand-in measured instead).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters

MODEL = "gemini-2.5-flash"


def _toolset(server_module: str, tool_filter: list[str] | None = None) -> McpToolset:
    params = StdioServerParameters(command=sys.executable, args=["-m", server_module])
    kwargs = {"connection_params": StdioConnectionParams(server_params=params, timeout=15.0)}
    if tool_filter is not None:
        kwargs["tool_filter"] = tool_filter
    return McpToolset(**kwargs)


@dataclass(frozen=True)
class SpecialistSpec:
    name: str
    description: str
    instruction: str
    legacy_tools: list[str]
    policy_tools: list[str]


SPECIALISTS = [
    SpecialistSpec(
        name="directory_ops_agent",
        description="Revokes an employee's access level in the legacy directory.",
        instruction="Given an employee id, look them up and propose revoking "
                    "their access at their current level. Always give a "
                    "specific, non-empty reason.",
        legacy_tools=["lookup_employee", "propose_revoke_access"],
        policy_tools=[],
    ),
    SpecialistSpec(
        name="asset_recovery_agent",
        description="Opens asset-return tickets for an employee's unreturned equipment.",
        instruction="Given an employee id and asset id, list the employee's "
                    "assets and propose a return ticket for the named asset.",
        legacy_tools=["list_assets_for_employee", "propose_return_ticket"],
        policy_tools=[],
    ),
    SpecialistSpec(
        name="policy_research_agent",
        description="Finds the offboarding policy document that governs a scenario.",
        instruction="Given a scenario description, search the policy "
                    "documents and return the single most relevant doc_id.",
        legacy_tools=[],
        policy_tools=["search_policies", "get_policy"],
    ),
    SpecialistSpec(
        name="ticketing_agent",
        description="Creates policy-compliance tickets and updates ticket status.",
        instruction="Given an employee id, a policy doc_id, or a ticket id "
                    "and a target status, propose the corresponding ticket "
                    "action. Always cite the policy_doc_id when creating a "
                    "POLICY_COMPLIANCE ticket.",
        legacy_tools=["propose_policy_ticket", "update_ticket_status", "list_tickets_for_employee"],
        policy_tools=[],
    ),
]

ALL_LEGACY_TOOLS = [
    "lookup_employee", "list_assets_for_employee", "list_tickets_for_employee",
    "propose_revoke_access", "propose_return_ticket", "propose_policy_ticket",
    "update_ticket_status",
]
ALL_POLICY_TOOLS = ["search_policies", "get_policy"]


def build_specialist_agent(spec: SpecialistSpec) -> LlmAgent:
    tools = []
    if spec.legacy_tools:
        tools.append(_toolset("src.mcp_servers.legacy_directory_server", spec.legacy_tools))
    if spec.policy_tools:
        tools.append(_toolset("src.mcp_servers.policy_doc_server", spec.policy_tools))
    return LlmAgent(name=spec.name, model=MODEL, description=spec.description,
                     instruction=spec.instruction, tools=tools)


def build_supervisor_agent() -> LlmAgent:
    """One supervisor delegating to the four specialists above via ADK's
    built-in sub_agents transfer mechanism. The supervisor itself holds no
    tools; every tool call happens inside whichever specialist it transfers
    control to, which is what keeps each specialist's first tool choice
    unambiguous (see the README's Findings for why that is the structural
    reason the multi-agent system beats the single-agent baseline)."""

    sub_agents = [build_specialist_agent(spec) for spec in SPECIALISTS]
    return LlmAgent(
        name="offboarding_supervisor",
        model=MODEL,
        description="Routes an offboarding task to the specialist that owns it.",
        instruction="You coordinate employee offboarding. Read the task and "
                     "transfer to directory_ops_agent for access revocation, "
                     "asset_recovery_agent for equipment return, "
                     "policy_research_agent to find a governing policy, or "
                     "ticketing_agent to open or update a ticket. Delegate; "
                     "do not try to call a tool yourself.",
        sub_agents=sub_agents,
    )


def build_baseline_agent() -> LlmAgent:
    """The single-agent ReAct baseline: one agent, no delegation, every tool
    from both MCP servers unscoped. Used only as the comparison point in
    scripts/run_benchmark.py; see src/orchestrator/baseline_orchestrator.py
    for the deterministic policy that actually drives the measured run."""

    tools = [
        _toolset("src.mcp_servers.legacy_directory_server", ALL_LEGACY_TOOLS),
        _toolset("src.mcp_servers.policy_doc_server", ALL_POLICY_TOOLS),
    ]
    return LlmAgent(
        name="offboarding_react_baseline",
        model=MODEL,
        description="Single ReAct agent handling the full offboarding task list alone.",
        instruction="You alone must complete every offboarding task: revoke "
                     "access, recover assets, research policy, and manage "
                     "tickets. Reason about which tool to call, call it, "
                     "observe the result, and continue until the task is done.",
        tools=tools,
    )
