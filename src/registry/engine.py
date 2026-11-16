"""The one deterministic orchestrator every declared skill runs through.
Unlike supervisor_orchestrator.py (one hand-written Python function per
task type), this module has exactly one `run_skill` that interprets
whichever SkillDecl it is given. A model (the `judge`) is called only at
a step the skill declares `"kind": "judgment"`; every other step is a
real MCP tool call or a deterministic branch, never a model call.

Adding a 6th skill to registry_data.py needs no change to this file;
see tests/test_sixth_skill_adds_no_engine_code.py and the README for the
diff that proves it.
"""
from __future__ import annotations

from typing import Any

from ..orchestrator.mcp_client import McpServerClient
from ..orchestrator.self_reflection import propose_with_self_reflection
from .judge import Judge
from .models import RegistryScopeError, SkillDecl
from .proposal_builders import BUILDERS


def _resolve(path: str, task: Any, ctx: dict) -> Any:
    if path.startswith("lit:"):
        return path[len("lit:"):]
    if path.startswith("task."):
        return getattr(task, path[len("task."):])
    if path.startswith("ctx."):
        node: Any = ctx
        for part in path[len("ctx."):].split("."):
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node
    raise ValueError(f"unresolvable path: {path!r}")


class RegistryEngine:
    def __init__(self, judge: Judge):
        self.judge = judge

    async def run_skill(
        self, skill: SkillDecl, task: Any, legacy: McpServerClient,
        policy: McpServerClient, run_id: str,
    ) -> dict:
        ctx: dict[str, Any] = {}
        counters = {"tool_calls": 0, "self_reflection_attempts": 0, "model_calls": 0}

        await self._run_steps(skill, skill.steps, task, ctx, legacy, policy, run_id, counters)

        return {
            "task_id": task.task_id, "task_type": skill.name, "status": "completed",
            "tool_calls": counters["tool_calls"],
            "self_reflection_attempts": counters["self_reflection_attempts"],
            "model_calls": counters["model_calls"], "skill": skill.name,
        }

    async def _run_steps(
        self, skill: SkillDecl, steps: tuple, task: Any, ctx: dict,
        legacy: McpServerClient, policy: McpServerClient, run_id: str, counters: dict,
    ) -> None:
        for step in steps:
            kind = step["kind"]

            if kind == "lookup":
                tool = step["tool"]
                self._require_scoped(skill, tool)
                if "skip_if_none" in step and _resolve(step["skip_if_none"], task, ctx) is None:
                    continue
                client = legacy if step["server"] == "legacy" else policy
                args = {k: _resolve(v, task, ctx) for k, v in step["args"].items()}
                result = await client.call(tool, **args)
                counters["tool_calls"] += 1
                ctx[step["store_as"]] = result

            elif kind == "judgment":
                value = self.judge.decide(step["decision"], task, ctx)
                counters["model_calls"] += 1
                ctx[step["store_as"]] = value

            elif kind == "conditional":
                branch_value = ctx[step["on"]]
                branch_steps = tuple(step["branches"].get(branch_value, ()))
                await self._run_steps(skill, branch_steps, task, ctx, legacy, policy, run_id, counters)

            elif kind == "propose":
                tool = step["tool"]
                self._require_scoped(skill, tool)
                builder = BUILDERS[step["args_builder"]]

                def build(attempt: int) -> dict:
                    args = builder(task, ctx, attempt)
                    return {"task_id": task.task_id, "run_id": run_id, **args}

                result = await propose_with_self_reflection(legacy, tool, build)
                counters["tool_calls"] += result["attempts"]
                counters["self_reflection_attempts"] += result["attempts"] - 1
                if step.get("store_as"):
                    ctx[step["store_as"]] = result

            else:
                raise ValueError(f"unknown step kind: {kind!r}")

    @staticmethod
    def _require_scoped(skill: SkillDecl, tool: str) -> None:
        if tool not in skill.scoped_tools:
            raise RegistryScopeError(
                f"skill '{skill.name}' is not scoped to call tool '{tool}' "
                f"(scoped_tools={sorted(skill.scoped_tools)})"
            )


async def run_corpus(skills_by_name: dict[str, SkillDecl], tasks: list, judge: Judge, run_id: str) -> list[dict]:
    engine = RegistryEngine(judge)
    async with McpServerClient("src.mcp_servers.legacy_directory_server") as legacy, \
               McpServerClient("src.mcp_servers.policy_doc_server") as policy:
        results = []
        for task in tasks:
            skill = skills_by_name[task.task_type]
            results.append(await engine.run_skill(skill, task, legacy, policy, run_id))
        return results
