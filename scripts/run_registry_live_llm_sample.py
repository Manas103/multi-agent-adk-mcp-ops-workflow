"""20 real `claude -p` subprocess calls against the registry's judgment
steps: 5 tasks each from the 4 skills that have a judgment step
(policy_gated_ticket, status_update, all_level_signoff_routing,
badge_vs_asset_routing), run through the real RegistryEngine with
ClaudeCLIJudge in place of DeterministicJudge. Needs the `claude` CLI on
PATH and logged in.

Run: python -m scripts.run_registry_live_llm_sample
"""
from __future__ import annotations

import asyncio

from src import db, seed_data
from src.registry import registry_data, task_corpus
from src.registry.engine import run_corpus
from src.registry.judge import ClaudeCLIJudge, JudgeOutputUnusable

RUN_ID = "registry-live-sample"
SAMPLE_PER_JUDGMENT_SKILL = 5


class _CountingClaudeJudge:
    """Wraps ClaudeCLIJudge to count real subprocess calls made and
    record whether each one produced a usable choice, without changing
    what the engine actually does at each judgment step."""

    def __init__(self) -> None:
        self.inner = ClaudeCLIJudge()
        self.calls_made = 0
        self.failures: list[str] = []

    def decide(self, decision_name, task, ctx):
        self.calls_made += 1
        try:
            return self.inner.decide(decision_name, task, ctx)
        except JudgeOutputUnusable as exc:
            self.failures.append(f"{task.task_id} ({decision_name}): {exc}")
            raise


def main() -> None:
    db.init_schema()
    db.reset()
    seed_scenario = seed_data.seed()
    all_tasks = task_corpus.build_tasks(seed_scenario)

    judgment_skills = [
        "policy_gated_ticket", "status_update", "all_level_signoff_routing",
        "badge_vs_asset_routing",
    ]
    sample = []
    for skill_name in judgment_skills:
        sample.extend([t for t in all_tasks if t.task_type == skill_name][:SAMPLE_PER_JUDGMENT_SKILL])
    assert len(sample) == 20

    judge = _CountingClaudeJudge()
    results = []
    for task in sample:
        try:
            result = asyncio.run(run_corpus(registry_data.SKILLS_BY_NAME, [task], judge, RUN_ID))
            results.append((task, result[0], None))
        except JudgeOutputUnusable as exc:
            results.append((task, None, str(exc)))

    lines = [f"REAL LLM SUBPROCESS CALLS MADE: {judge.calls_made}", ""]
    completed = 0
    for task, result, error in results:
        if result is not None:
            completed += 1
            lines.append(
                f"{task.task_id}: skill={result['skill']} status={result['status']} "
                f"model_calls={result['model_calls']} tool_calls={result['tool_calls']}"
            )
        else:
            lines.append(f"{task.task_id}: FAILED ({error})")
    lines.append("")
    lines.append(f"completed: {completed} / {len(sample)}")

    text = "\n".join(lines)
    print(text)

    with open("docs/registry_live_llm_sample_output.txt", "w") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
