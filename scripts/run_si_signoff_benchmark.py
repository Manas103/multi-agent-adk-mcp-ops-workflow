"""Produces every number in the README's "Signal-Integrity Signoff Flow
Extension" section and docs/si_signoff_benchmark_output.{txt,json}. Builds
the 128-task corpus once, runs it through the gated Taskmaster flow and
the free-form baseline against the same real si_physics_server MCP
server, grades both against the independent oracle, and reports the
gated-vs-free-form gap plus a per-family breakdown.

Run (inside WSL2, this project's venv, ngspice-36 on PATH):
  PYTHONPATH=. .venv/bin/python -m scripts.run_si_signoff_benchmark
"""
from __future__ import annotations

import asyncio
import json

from src.si_signoff import free_form_orchestrator, oracle, taskmaster
from src.si_signoff.task_corpus import build_corpus


def _family(task) -> str:
    return f"{'pkg_board' if task.has_package else 'board_only'}_{task.interface['standard']}"


def main() -> None:
    tasks = build_corpus()

    gated_results = asyncio.run(taskmaster.run_corpus(tasks))
    free_form_results = asyncio.run(free_form_orchestrator.run_corpus(tasks))

    gated_graded = oracle.grade_all(tasks, gated_results)
    free_form_graded = oracle.grade_all(tasks, free_form_results)

    gated_pass = sum(gated_graded)
    free_form_pass = sum(free_form_graded)

    by_family: dict[str, dict] = {}
    for task, g_ok, f_ok in zip(tasks, gated_graded, free_form_graded):
        fam = by_family.setdefault(_family(task), {"n": 0, "gated_pass": 0, "free_form_pass": 0})
        fam["n"] += 1
        fam["gated_pass"] += int(g_ok)
        fam["free_form_pass"] += int(f_ok)

    cascade_wrong = sum(
        1 for task, r in zip(tasks, free_form_results)
        if r.get("cascade_tool_picked") and
        (r["cascade_tool_picked"] == "cascade_package_and_board") != task.has_package
    )
    simulate_wrong = sum(
        1 for task, r in zip(tasks, free_form_results)
        if r.get("simulate_tool_picked") and
        (r["simulate_tool_picked"] == "simulate_pam4_channel") != (task.interface["standard"] == "PAM4")
    )

    lines = [
        f"=== SI signoff flow: {len(tasks)}-task corpus, one model-free deterministic routing comparison ===\n",
        f"gated Taskmaster flow:  {gated_pass} of {len(tasks)} signoffs finished correctly",
        f"free-form tool calling: {free_form_pass} of {len(tasks)} signoffs finished correctly",
        "",
        "by family (has_package x standard):",
    ]
    for fam, c in sorted(by_family.items()):
        lines.append(f"  {fam}: gated {c['gated_pass']}/{c['n']}, free-form {c['free_form_pass']}/{c['n']}")
    lines.append("")
    lines.append(f"free-form wrong cascade-variant picks: {cascade_wrong} of {len(tasks)}")
    lines.append(f"free-form wrong simulate-variant picks: {simulate_wrong} of {len(tasks)}")

    text = "\n".join(lines)
    print(text)

    with open("docs/si_signoff_benchmark_output.txt", "w") as f:
        f.write(text + "\n")

    report = {
        "n_tasks": len(tasks),
        "gated_pass": gated_pass,
        "free_form_pass": free_form_pass,
        "by_family": by_family,
        "free_form_wrong_cascade_picks": cascade_wrong,
        "free_form_wrong_simulate_picks": simulate_wrong,
    }
    with open("docs/si_signoff_benchmark_output.json", "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
