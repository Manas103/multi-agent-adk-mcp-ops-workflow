"""The pluggable judgment backend a "judgment" step calls. Mirrors this
portfolio's standard split (see e.g. grounded-reconciliation-assistant's
llm_client.py): `DeterministicJudge` (no network call, measured at the
full 240-task scale) and `ClaudeCLIJudge` (shells out to the real
`claude` CLI, exercised on a smaller live sample; see
scripts/run_registry_live_llm_sample.py and the README).

Three decisions, one per judgment step across the five skills currently
in registry_data.py.
"""
from __future__ import annotations

import abc
import json
import re
import subprocess

CLAUDE_CLI_PATH = "claude"


def _decide_pick_policy_doc(task, ctx) -> str | None:
    """Which policy document, among the search results, the compliance
    ticket should cite. The real judgment call: trusting the top-ranked
    hit rather than, say, the most-recently-filed one."""
    results = ctx["search"].get("results", [])
    return results[0]["doc_id"] if results else None


def _decide_pick_ticket_to_close(task, ctx) -> int | None:
    """Which of the employee's tickets needs closing: the OPEN one,
    lowest ticket_id first if more than one is open."""
    open_ids = sorted(t["ticket_id"] for t in ctx["tickets"]["tickets"] if t["status"] == "OPEN")
    return open_ids[0] if open_ids else None


def _decide_signoff_needed(task, ctx) -> str:
    """Whether this employee's revocation needs the ALL-level sign-off
    ticket (POL-002) or can be revoked directly."""
    return "all_level" if ctx["employee"].get("access_level") == "ALL" else "standard_or_admin"


DECISIONS = {
    "pick_policy_doc": _decide_pick_policy_doc,
    "pick_ticket_to_close": _decide_pick_ticket_to_close,
    "decide_signoff_needed": _decide_signoff_needed,
}

# What each decision's prompt needs to show the model and what counts as
# a valid answer; used only by ClaudeCLIJudge.
_DECISION_PROMPTS = {
    "pick_policy_doc": (
        "Given these ranked policy-search results (doc_id, title, score), "
        "choose the doc_id that should be cited on the compliance ticket. "
        'Respond with exactly one line of JSON: {{"choice": "<doc_id>"}}.\n'
        "Results: {payload}"
    ),
    "pick_ticket_to_close": (
        "Given this employee's tickets (ticket_id, status), choose the "
        "ticket_id of the one ticket that needs to be closed (the OPEN "
        'one). Respond with exactly one line of JSON: {{"choice": <ticket_id>}}.\n'
        "Tickets: {payload}"
    ),
    "decide_signoff_needed": (
        "Given this employee record (access_level), decide whether "
        'revoking access needs the ALL-level sign-off ticket. Respond '
        'with exactly one line of JSON: {{"choice": "all_level"}} or '
        '{{"choice": "standard_or_admin"}}.\n'
        "Employee: {payload}"
    ),
}


class Judge(abc.ABC):
    @abc.abstractmethod
    def decide(self, decision_name: str, task, ctx: dict):
        ...


class DeterministicJudge(Judge):
    """The primary, measured-at-scale path. No network call."""

    def decide(self, decision_name: str, task, ctx: dict):
        return DECISIONS[decision_name](task, ctx)


class JudgeOutputUnusable(Exception):
    pass


class ClaudeCLIJudge(Judge):
    """Real LLM backend: shells out to `claude -p "<prompt>"` as a
    genuine subprocess. Used on a smaller live sample (see README for
    the exact count), not the full 240-task benchmark."""

    def __init__(self, claude_path: str = CLAUDE_CLI_PATH, timeout_seconds: int = 60):
        self.claude_path = claude_path
        self.timeout_seconds = timeout_seconds

    def _call_claude(self, prompt: str) -> str:
        result = subprocess.run(
            [self.claude_path, "-p", prompt],
            capture_output=True, text=True, timeout=self.timeout_seconds, check=False,
        )
        return result.stdout.strip()

    def _payload_for(self, decision_name: str, ctx: dict) -> dict:
        if decision_name == "pick_policy_doc":
            return ctx["search"].get("results", [])
        if decision_name == "pick_ticket_to_close":
            return ctx["tickets"]["tickets"]
        if decision_name == "decide_signoff_needed":
            return ctx["employee"]
        raise KeyError(decision_name)

    def decide(self, decision_name: str, task, ctx: dict):
        payload = self._payload_for(decision_name, ctx)
        prompt = _DECISION_PROMPTS[decision_name].format(payload=json.dumps(payload))
        raw_output = self._call_claude(prompt)
        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if not match:
            raise JudgeOutputUnusable(f"no JSON object in LLM output: {raw_output!r}")
        choice = json.loads(match.group(0)).get("choice")
        if decision_name == "pick_ticket_to_close":
            try:
                return int(choice)
            except (TypeError, ValueError) as exc:
                raise JudgeOutputUnusable(f"non-integer ticket choice: {choice!r}") from exc
        return choice
