"""The one script that produces every number in the README's Measured
results table and docs/benchmark_output.txt. Resets and reseeds the
database once per orchestrator (so neither run can see the other's
mutations), runs the full 120-task corpus through each, auto-approves every
schema-valid proposal (the disclosed stand-in for a human reviewer; see
src/approval/gate.py), grades both against the independent oracle, and
reports task success, self-reflection attempts, wasted baseline calls, and
the 0-schema-invalid-approved count.

Run: python -m scripts.run_benchmark
"""

from __future__ import annotations

import asyncio
import json
import time

from src import db, seed_data
from src.approval import gate
from src.tasks import oracle, task_corpus


def _schema_invalid_approved_count(run_id: str) -> int:
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = %s AND status = 'APPROVED' AND schema_invalid = TRUE",
            (run_id,),
        )
        return cur.fetchone()["n"]


def _schema_invalid_attempt_count(run_id: str) -> int:
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = %s AND schema_invalid = TRUE",
            (run_id,),
        )
        return cur.fetchone()["n"]


def _summarize(name: str, orchestrator_results: list[dict], oracle_results: list[oracle.TaskResult], run_id: str) -> dict:
    by_type: dict[str, dict] = {}
    for res, grade in zip(orchestrator_results, oracle_results):
        t = res["task_type"]
        by_type.setdefault(t, {"n": 0, "passed": 0})
        by_type[t]["n"] += 1
        by_type[t]["passed"] += int(grade.passed)

    total = len(oracle_results)
    passed = sum(g.passed for g in oracle_results)
    self_reflection_total = sum(r["self_reflection_attempts"] for r in orchestrator_results)
    wasted_total = sum(r.get("wasted_calls", 0) for r in orchestrator_results)
    statuses = {}
    for r in orchestrator_results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1

    return {
        "name": name,
        "total_tasks": total,
        "passed": passed,
        "pass_rate": round(100.0 * passed / total, 2),
        "by_task_type": {
            t: {"n": v["n"], "passed": v["passed"], "pass_rate": round(100.0 * v["passed"] / v["n"], 2)}
            for t, v in sorted(by_type.items())
        },
        "self_reflection_attempts_total": self_reflection_total,
        "wasted_calls_total": wasted_total,
        "status_breakdown": statuses,
        "schema_invalid_attempts": _schema_invalid_attempt_count(run_id),
        "schema_invalid_approved": _schema_invalid_approved_count(run_id),
    }


def main() -> None:
    db.init_schema()

    db.reset()
    seed_scenario = seed_data.seed()
    tasks = task_corpus.build_tasks(seed_scenario, seed_scenario["preseeded_tickets"])

    from src.orchestrator import supervisor_orchestrator

    t0 = time.perf_counter()
    supervisor_results = asyncio.run(supervisor_orchestrator.run_corpus(tasks, "supervisor-run"))
    supervisor_elapsed = time.perf_counter() - t0
    gate.auto_approve_all_valid("supervisor-run")
    supervisor_grades = oracle.grade_all(tasks)
    supervisor_summary = _summarize("multi_agent_supervisor", supervisor_results, supervisor_grades, "supervisor-run")
    supervisor_summary["elapsed_seconds"] = round(supervisor_elapsed, 2)

    db.reset()
    seed_data.seed()  # identical deterministic seed; SERIAL ids restart at 1 so task references still line up

    from src.orchestrator import baseline_orchestrator

    t0 = time.perf_counter()
    baseline_results = asyncio.run(baseline_orchestrator.run_corpus(tasks, "baseline-run"))
    baseline_elapsed = time.perf_counter() - t0
    gate.auto_approve_all_valid("baseline-run")
    baseline_grades = oracle.grade_all(tasks)
    baseline_summary = _summarize("react_baseline", baseline_results, baseline_grades, "baseline-run")
    baseline_summary["elapsed_seconds"] = round(baseline_elapsed, 2)

    report = {"multi_agent_supervisor": supervisor_summary, "react_baseline": baseline_summary}

    lines = []
    lines.append("=== Multi-agent supervisor vs single-agent ReAct baseline, 120-task offboarding corpus ===\n")
    for key in ("multi_agent_supervisor", "react_baseline"):
        s = report[key]
        lines.append(f"-- {key} --")
        lines.append(f"total tasks: {s['total_tasks']}")
        lines.append(f"passed (independent oracle): {s['passed']}/{s['total_tasks']} ({s['pass_rate']}%)")
        for t, v in s["by_task_type"].items():
            lines.append(f"  {t}: {v['passed']}/{v['n']} ({v['pass_rate']}%)")
        lines.append(f"status breakdown: {s['status_breakdown']}")
        lines.append(f"self-reflection attempts triggered: {s['self_reflection_attempts_total']}")
        lines.append(f"wasted (wrong-tool) calls: {s['wasted_calls_total']}")
        lines.append(f"schema-invalid attempts seen: {s['schema_invalid_attempts']}")
        lines.append(f"schema-invalid actions ever approved: {s['schema_invalid_approved']}")
        lines.append(f"elapsed: {s['elapsed_seconds']}s")
        lines.append("")

    gap = supervisor_summary["pass_rate"] - baseline_summary["pass_rate"]
    lines.append(f"task-success gap (multi-agent - baseline): {gap:.2f} percentage points")

    output_text = "\n".join(lines)
    print(output_text)

    with open("docs/benchmark_output.txt", "w") as f:
        f.write(output_text + "\n")
    with open("docs/benchmark_output.json", "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
