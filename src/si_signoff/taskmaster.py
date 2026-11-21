"""The gated flow: a small Taskmaster state machine (the name Intel's own
published multi-agent SI system uses) that decides which skill may run
next from the task's own declared stackup and interface fields, a real
dependency gate rather than a guess. intake must complete before cascade;
cascade before simulate; simulate before report. At the two steps with a
genuine routing choice (which cascade variant, which simulate variant)
the state machine reads task.has_package / task.interface["standard"]
directly, the same structured fields a real signoff flow would read off
the job's own stackup and interface spec, never natural-language intent
and never a model call. This is the entire claim under test against
free_form_orchestrator.py: identical tools, identical MCP server,
identical task corpus, routed by declared structure instead of guessed
intent.
"""
from __future__ import annotations

from ..orchestrator.mcp_client import McpServerClient
from .task_corpus import Task


async def run_task(task: Task, client: McpServerClient) -> dict:
    intake = await client.call("intake_channel", segments=list(task.segments), interface=task.interface)
    if not intake.get("ok"):
        return {"task_id": task.task_id, "status": "intake_failed", "report": None}
    channel_id = intake["channel_id"]

    cascade_tool = "cascade_package_and_board" if task.has_package else "cascade_board_only"
    cascade = await client.call(cascade_tool, channel_id=channel_id)

    simulate_tool = "simulate_pam4_channel" if task.interface["standard"] == "PAM4" else "simulate_nrz_channel"
    sim = await client.call(simulate_tool, cascade_id=cascade["cascade_id"])

    report = await client.call("generate_report", sim_id=sim["sim_id"])
    return {"task_id": task.task_id, "status": "completed", "report": report}


async def run_corpus(tasks: list[Task]) -> list[dict]:
    async with McpServerClient("src.mcp_servers.si_physics_server") as client:
        return [await run_task(task, client) for task in tasks]
