"""Produces every number in the README's "Declarative Skill Registry
Extension" section and docs/registry_benchmark_output.txt. Resets and
reseeds the database, runs the registry's task corpus (40 tasks per
declared skill) through RegistryEngine with the deterministic judge,
auto-approves every valid proposal (same disclosed stand-in
run_benchmark.py already uses), and reports the workflow count, the
proposed/approved mutation counts, and the model-call count against the
number of declared judgment steps.

Run: python -m scripts.run_registry_benchmark
"""
from __future__ import annotations

import asyncio
import json

from src import db, seed_data
from src.approval import gate
from src.registry import registry_data, task_corpus
from src.registry.engine import run_corpus
from src.registry.judge import DeterministicJudge

RUN_ID = "registry-run"


def _pending_action_counts(run_id: str) -> dict:
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = %s", (run_id,),
        )
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = %s AND status = 'APPROVED'",
            (run_id,),
        )
        approved = cur.fetchone()["n"]
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = %s AND status != 'APPROVED'",
            (run_id,),
        )
        unapproved = cur.fetchone()["n"]
    return {"total": total, "approved": approved, "unapproved": unapproved}


def main() -> None:
    db.init_schema()
    db.reset()
    seed_scenario = seed_data.seed()
    tasks = task_corpus.build_tasks(seed_scenario)

    results = asyncio.run(
        run_corpus(registry_data.SKILLS_BY_NAME, tasks, DeterministicJudge(), RUN_ID)
    )
    gate.auto_approve_all_valid(RUN_ID)

    counts = _pending_action_counts(RUN_ID)

    model_calls_total = sum(r["model_calls"] for r in results)
    judgment_steps_declared = sum(
        1 for skill in registry_data.SKILLS_BY_NAME.values()
        for step in skill.steps if step["kind"] == "judgment"
    ) + sum(
        1 for skill in registry_data.SKILLS_BY_NAME.values()
        for step in skill.steps if step["kind"] == "conditional"
        for branch in step["branches"].values() for s in branch if s["kind"] == "judgment"
    )
    by_skill: dict[str, dict] = {}
    for r in results:
        s = by_skill.setdefault(r["skill"], {"n": 0, "model_calls": 0, "tool_calls": 0})
        s["n"] += 1
        s["model_calls"] += r["model_calls"]
        s["tool_calls"] += r["tool_calls"]

    branch_counts: dict[str, int] = {}
    with db.cursor() as cur:
        cur.execute(
            "SELECT action_type, count(*) AS n FROM offboard.pending_actions "
            "WHERE run_id = %s GROUP BY action_type ORDER BY action_type", (RUN_ID,),
        )
        for row in cur.fetchall():
            branch_counts[row["action_type"]] = row["n"]

    n_skills = len(registry_data.SKILLS_BY_NAME)
    lines = []
    lines.append(f"=== Declarative skill registry: {n_skills} skills, {len(tasks)}-task corpus ===\n")
    lines.append(f"skills declared: {n_skills}")
    lines.append(f"real MCP servers: {len(registry_data.REAL_MCP_SERVERS)} "
                 f"({', '.join(registry_data.REAL_MCP_SERVERS)})")
    lines.append("")
    for name in task_corpus.SKILL_ORDER:
        s = by_skill[name]
        lines.append(f"  {name}: {s['n']} tasks, {s['model_calls']} model call(s), "
                      f"{s['tool_calls']} tool call(s)")
    lines.append("")
    lines.append(f"proposed mutations (pending_actions rows, run_id={RUN_ID}): {counts['total']}")
    lines.append(f"approved: {counts['approved']}")
    lines.append(f"reached a record unapproved: {counts['unapproved']}")
    lines.append("")
    lines.append(f"total model calls across the corpus: {model_calls_total}")
    lines.append(f"declared judgment steps (counting both conditional branches once each): "
                 f"{judgment_steps_declared}")
    lines.append("")
    lines.append("action_type breakdown (includes the all_level_signoff_routing branch split):")
    for action_type, n in branch_counts.items():
        lines.append(f"  {action_type}: {n}")

    text = "\n".join(lines)
    print(text)

    with open("docs/registry_benchmark_output.txt", "w") as f:
        f.write(text + "\n")

    report = {
        "skills_declared": len(registry_data.SKILLS_BY_NAME),
        "real_mcp_servers": list(registry_data.REAL_MCP_SERVERS),
        "by_skill": by_skill,
        "pending_action_counts": counts,
        "model_calls_total": model_calls_total,
        "action_type_breakdown": branch_counts,
    }
    with open("docs/registry_benchmark_output.json", "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
