"""The measured stand-in for the single-agent ReAct baseline: one agent, no
delegation, every tool from both real MCP servers in one unscoped catalog
(see src/adk_app/agents.py's `build_baseline_agent`, which wires the real
counterpart). At each read step this agent must choose among every
currently-satisfiable read tool by real keyword overlap with that step's
intent (tool_catalog.rank_candidates); a wrong choice is a genuine wasted
call against a step budget with no slack (src.config.STEP_BUDGET_BY_TASK_TYPE),
unlike a scoped specialist, which only ever has one candidate. See the
README's Findings for which task types this produces a real gap on, and
which it does not.
"""

from __future__ import annotations

from .. import config
from ..tasks.task_corpus import Task
from . import proposal_builder, tool_catalog
from .mcp_client import McpServerClient
from .self_reflection import propose_with_self_reflection

_WRITE_TOOL_SERVER = {
    "propose_revoke_access": "legacy",
    "propose_return_ticket": "legacy",
    "propose_policy_ticket": "legacy",
    "update_ticket_status": "legacy",
}


async def _call_read_tool(name: str, task: Task, legacy: McpServerClient, policy: McpServerClient, doc_id: str | None) -> dict:
    if name == "lookup_employee":
        return await legacy.call(name, employee_id=task.employee_id)
    if name == "list_assets_for_employee":
        return await legacy.call(name, employee_id=task.employee_id)
    if name == "list_tickets_for_employee":
        return await legacy.call(name, employee_id=task.employee_id)
    if name == "search_policies":
        return await policy.call(name, query=task.policy_query)
    if name == "get_policy":
        return await policy.call(name, doc_id=doc_id)
    raise ValueError(f"unhandled read tool {name}")


async def run_task(task: Task, legacy: McpServerClient, policy: McpServerClient, run_id: str) -> dict:
    budget = config.STEP_BUDGET_BY_TASK_TYPE[task.task_type]
    required_sequence = tool_catalog.REQUIRED_SEQUENCE[task.task_type]
    read_steps = required_sequence[:-1]
    write_tool = required_sequence[-1]

    known: set[str] = {"employee_id"}
    if task.task_type == "recover_asset":
        known.add("asset_id")
    if task.task_type == "policy_gated_ticket":
        known.add("policy_query")
    if task.task_type == "status_update":
        known.add("ticket_id")

    calls_used = 0
    wasted_calls = 0
    doc_id = None
    step_results: dict[str, dict] = {}

    for step_index, required_tool in enumerate(read_steps):
        intent = tool_catalog.STEP_INTENTS[(task.task_type, step_index)]
        excluded: set[str] = set()
        while True:
            candidate_fields = known | ({"doc_id"} if doc_id else set())
            candidates = [c for c in tool_catalog.satisfiable_candidates(candidate_fields) if c not in excluded]
            if not candidates:
                return {"task_id": task.task_id, "task_type": task.task_type, "status": "stuck",
                        "tool_calls": calls_used, "self_reflection_attempts": 0, "wasted_calls": wasted_calls}
            ranked = tool_catalog.rank_candidates(intent, candidates)
            picked = ranked[0][0]
            calls_used += 1
            if calls_used > budget:
                return {"task_id": task.task_id, "task_type": task.task_type, "status": "budget_exceeded",
                        "tool_calls": calls_used - 1, "self_reflection_attempts": 0, "wasted_calls": wasted_calls}
            result = await _call_read_tool(picked, task, legacy, policy, doc_id)
            if picked == "search_policies":
                results = result.get("results", [])
                if results:
                    doc_id = results[0]["doc_id"]
            if picked == required_tool:
                step_results[required_tool] = result
                break
            wasted_calls += 1
            excluded.add(picked)

    calls_used += 1
    if calls_used > budget:
        return {"task_id": task.task_id, "task_type": task.task_type, "status": "budget_exceeded",
                "tool_calls": calls_used - 1, "self_reflection_attempts": 0, "wasted_calls": wasted_calls}

    client = legacy  # every write tool in this corpus lives on the legacy server
    if write_tool == "propose_revoke_access":
        access_level = step_results.get("lookup_employee", {}).get("access_level", "STANDARD")

        def build(attempt: int) -> dict:
            args = proposal_builder.revoke_access_args(task, access_level, attempt, "offboarding_react_baseline")
            return {"task_id": task.task_id, "run_id": run_id, **args}
    elif write_tool == "propose_return_ticket":
        def build(attempt: int) -> dict:
            args = proposal_builder.return_ticket_args(task, attempt, "offboarding_react_baseline")
            return {"task_id": task.task_id, "run_id": run_id, **args}
    elif write_tool == "propose_policy_ticket":
        def build(attempt: int) -> dict:
            args = proposal_builder.policy_ticket_args(task, doc_id or "", attempt, "offboarding_react_baseline")
            return {"task_id": task.task_id, "run_id": run_id, **args}
    elif write_tool == "update_ticket_status":
        def build(attempt: int) -> dict:
            args = proposal_builder.update_ticket_status_args(task, attempt, "offboarding_react_baseline")
            return {"task_id": task.task_id, "run_id": run_id, **args}
    else:
        raise ValueError(f"unhandled write tool {write_tool}")

    result = await propose_with_self_reflection(client, write_tool, build)
    return {
        "task_id": task.task_id, "task_type": task.task_type, "status": "completed",
        "tool_calls": calls_used + result["attempts"],
        "self_reflection_attempts": result["attempts"] - 1, "wasted_calls": wasted_calls,
    }


async def run_corpus(tasks: list[Task], run_id: str) -> list[dict]:
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy, \
               McpServerClient("src.mcp_servers.policy_doc_server") as policy:
        return [await run_task(task, legacy, policy, run_id) for task in tasks]
