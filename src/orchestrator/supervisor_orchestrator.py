"""The measured stand-in for the multi-agent ADK system: a supervisor that
delegates each task to the scoped specialist(s) that own it, over the same
two real MCP servers src/adk_app/agents.py wires the real LlmAgent sub_agents
to. Every specialist's toolset contains only the tools its mandate needs,
so a specialist never faces a choice at its read step; see
tool_catalog.REQUIRED_SEQUENCE for what "its mandate" means per task type.

This module does not call Gemini; see src/adk_app/agents.py's docstring and
the README's Honest framing for why, and src/orchestrator/mcp_client.py for
what is real here (every MCP call below is a genuine stdio round trip to a
running server process).
"""

from __future__ import annotations

from .. import config
from ..tasks.task_corpus import Task
from . import proposal_builder
from .mcp_client import McpServerClient
from .self_reflection import propose_with_self_reflection


async def run_task(task: Task, legacy: McpServerClient, policy: McpServerClient, run_id: str) -> dict:
    tool_calls = 0
    self_reflection_attempts = 0
    delegated_to: list[str] = []

    if task.task_type == "revoke_access":
        delegated_to.append("directory_ops_agent")
        lookup = await legacy.call("lookup_employee", employee_id=task.employee_id)
        tool_calls += 1
        access_level = lookup.get("access_level", "STANDARD")

        def build(attempt: int) -> dict:
            args = proposal_builder.revoke_access_args(task, access_level, attempt, "directory_ops_agent")
            return {"task_id": task.task_id, "run_id": run_id, **args}

        result = await propose_with_self_reflection(legacy, "propose_revoke_access", build)
        tool_calls += result["attempts"]
        self_reflection_attempts += result["attempts"] - 1

    elif task.task_type == "recover_asset":
        delegated_to.append("asset_recovery_agent")
        await legacy.call("list_assets_for_employee", employee_id=task.employee_id)
        tool_calls += 1

        def build(attempt: int) -> dict:
            args = proposal_builder.return_ticket_args(task, attempt, "asset_recovery_agent")
            return {"task_id": task.task_id, "run_id": run_id, **args}

        result = await propose_with_self_reflection(legacy, "propose_return_ticket", build)
        tool_calls += result["attempts"]
        self_reflection_attempts += result["attempts"] - 1

    elif task.task_type == "policy_gated_ticket":
        delegated_to.extend(["policy_research_agent", "ticketing_agent"])
        search = await policy.call("search_policies", query=task.policy_query)
        tool_calls += 1
        results = search.get("results", [])
        doc_id = results[0]["doc_id"] if results else None

        if doc_id is not None:
            await policy.call("get_policy", doc_id=doc_id)
            tool_calls += 1

        def build(attempt: int) -> dict:
            args = proposal_builder.policy_ticket_args(task, doc_id or "", attempt, "ticketing_agent")
            return {"task_id": task.task_id, "run_id": run_id, **args}

        result = await propose_with_self_reflection(legacy, "propose_policy_ticket", build)
        tool_calls += result["attempts"]
        self_reflection_attempts += result["attempts"] - 1

    elif task.task_type == "status_update":
        delegated_to.append("ticketing_agent")
        await legacy.call("list_tickets_for_employee", employee_id=task.employee_id)
        tool_calls += 1

        def build(attempt: int) -> dict:
            args = proposal_builder.update_ticket_status_args(task, attempt, "ticketing_agent")
            return {"task_id": task.task_id, "run_id": run_id, **args}

        result = await propose_with_self_reflection(legacy, "update_ticket_status", build)
        tool_calls += result["attempts"]
        self_reflection_attempts += result["attempts"] - 1

    else:
        raise ValueError(f"unknown task_type {task.task_type}")

    return {
        "task_id": task.task_id, "task_type": task.task_type, "status": "completed",
        "tool_calls": tool_calls, "self_reflection_attempts": self_reflection_attempts,
        "delegated_to": delegated_to,
    }


async def run_corpus(tasks: list[Task], run_id: str) -> list[dict]:
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy, \
               McpServerClient("src.mcp_servers.policy_doc_server") as policy:
        return [await run_task(task, legacy, policy, run_id) for task in tasks]
