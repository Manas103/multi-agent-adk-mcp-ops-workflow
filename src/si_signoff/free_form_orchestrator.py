"""The single-agent free-form-tool-calling baseline for the SI signoff
corpus, mirroring src/orchestrator/baseline_orchestrator.py's role for the
offboarding corpus: the same MCP server and task corpus as
taskmaster.py, but at each of the two genuinely ambiguous steps it ranks
every tool satisfiable from context (tool_catalog.rank_candidates) by
real keyword overlap against that task's own natural-language step
intent and calls whichever ranks first, once, with no access to the
task's structured has_package/standard fields and no retry. Built once
and then run, not iterated on to produce a particular gap; see the
README's Findings for which task families this does and does not cost.
"""
from __future__ import annotations

from ..orchestrator.mcp_client import McpServerClient
from . import tool_catalog
from .task_corpus import Task


async def run_task(task: Task, client: McpServerClient) -> dict:
    intake = await client.call("intake_channel", segments=list(task.segments), interface=task.interface)
    if not intake.get("ok"):
        return {"task_id": task.task_id, "status": "intake_failed", "report": None}
    channel_id = intake["channel_id"]

    cascade_ranked = tool_catalog.rank_candidates(task.cascade_intent, list(tool_catalog.CASCADE_CANDIDATES))
    cascade_tool = cascade_ranked[0][0]
    cascade = await client.call(cascade_tool, channel_id=channel_id)

    simulate_ranked = tool_catalog.rank_candidates(task.simulate_intent, list(tool_catalog.SIMULATE_CANDIDATES))
    simulate_tool = simulate_ranked[0][0]
    sim = await client.call(simulate_tool, cascade_id=cascade["cascade_id"])

    report = await client.call("generate_report", sim_id=sim["sim_id"])
    return {
        "task_id": task.task_id, "status": "completed", "report": report,
        "cascade_tool_picked": cascade_tool, "simulate_tool_picked": simulate_tool,
    }


async def run_corpus(tasks: list[Task]) -> list[dict]:
    async with McpServerClient("src.mcp_servers.si_physics_server") as client:
        return [await run_task(task, client) for task in tasks]
