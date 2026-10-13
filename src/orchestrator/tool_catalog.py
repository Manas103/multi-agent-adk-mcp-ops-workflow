"""The shared catalog both orchestrators reason over: which tools exist,
what each one's docstring says (verbatim, copied from the real tool
definitions in src/mcp_servers/), what each read tool needs to be callable
at all, and the required (correct) tool sequence per task type. The
single-agent ReAct baseline in baseline_orchestrator.py is the only caller
that uses `rank_candidates`; the four scoped specialists in
supervisor_orchestrator.py never face a choice because each one's own
toolset contains exactly one candidate for its read step, by construction.
"""

from __future__ import annotations

import re

TOOL_DOCS = {
    "lookup_employee": "Look up one employee's name, access level and revocation status.",
    "list_assets_for_employee": "List every asset assigned to an employee and whether it has been returned.",
    "list_tickets_for_employee": "List every ticket open against an employee, with its current status.",
    "search_policies": "Rank policy documents by word overlap with the query. Returns the doc_id, title and overlap score for every document with a nonzero score, most relevant first.",
    "get_policy": "Return one policy document's full title and body by id.",
}

READ_TOOLS = list(TOOL_DOCS.keys())

# What each read tool needs in hand before it is even a sensible candidate.
REQUIRED_INPUTS = {
    "lookup_employee": {"employee_id"},
    "list_assets_for_employee": {"employee_id"},
    "list_tickets_for_employee": {"employee_id"},
    "search_policies": {"policy_query"},
    "get_policy": {"doc_id"},
}

REQUIRED_SEQUENCE = {
    "revoke_access": ["lookup_employee", "propose_revoke_access"],
    "recover_asset": ["list_assets_for_employee", "propose_return_ticket"],
    "policy_gated_ticket": ["search_policies", "get_policy", "propose_policy_ticket"],
    "status_update": ["list_tickets_for_employee", "update_ticket_status"],
}

STEP_INTENTS = {
    ("revoke_access", 0): "Employee is offboarding today; look up their record to confirm current access level before revoking anything.",
    ("recover_asset", 0): "Check what equipment this employee still has outstanding so it can be recovered.",
    ("policy_gated_ticket", 0): "Find which offboarding policy document governs this situation.",
    ("policy_gated_ticket", 1): "Read the matched policy document to confirm its exact requirement before citing it.",
    ("status_update", 0): "List the employee's tickets to find the one that needs to be closed.",
}

_STOPWORDS = {"the", "a", "an", "to", "of", "is", "it", "its", "now", "that", "has", "been", "so",
              "can", "be", "this", "and", "for", "before", "after", "on", "at", "in", "their"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z']+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def satisfiable_candidates(known_fields: set[str]) -> list[str]:
    return [name for name, needs in REQUIRED_INPUTS.items() if needs <= known_fields]


def rank_candidates(step_intent: str, candidates: list[str]) -> list[tuple[str, int]]:
    """Real keyword overlap between the step's natural-language intent and
    each candidate tool's real docstring, ties broken alphabetically. This
    is the entire baseline "reasoning" step; it was built once and then run,
    not iterated on to produce a particular gap (see the README's
    Findings)."""
    intent_words = _words(step_intent)
    scored = [(name, len(intent_words & _words(TOOL_DOCS[name]))) for name in candidates]
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored
