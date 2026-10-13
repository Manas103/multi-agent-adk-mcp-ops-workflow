"""Pins down the real keyword-overlap ambiguity the ReAct baseline computes
in src/orchestrator/tool_catalog.py: which task types the baseline picks
correctly on the first try, and which two it does not. See the README's
Findings for the honest explanation of why this is not uniform across task
types."""

from src.orchestrator import tool_catalog


def _first_pick(task_type: str, step: int, known_fields: set[str]) -> str:
    candidates = tool_catalog.satisfiable_candidates(known_fields)
    ranked = tool_catalog.rank_candidates(tool_catalog.STEP_INTENTS[(task_type, step)], candidates)
    return ranked[0][0]


def test_revoke_access_step0_is_unambiguous():
    assert _first_pick("revoke_access", 0, {"employee_id"}) == "lookup_employee"


def test_recover_asset_step0_is_unambiguous():
    assert _first_pick("recover_asset", 0, {"employee_id", "asset_id"}) == "list_assets_for_employee"


def test_policy_gated_ticket_step0_is_unambiguous():
    assert _first_pick("policy_gated_ticket", 0, {"employee_id", "policy_query"}) == "search_policies"


def test_policy_gated_ticket_step1_wrongly_repeats_search():
    """Once doc_id is known, get_policy is satisfiable, but the baseline's
    keyword overlap still favors search_policies over get_policy for this
    step's intent text: a genuine, not engineered, wasted call."""
    picked = _first_pick("policy_gated_ticket", 1, {"employee_id", "policy_query", "doc_id"})
    assert picked == "search_policies"
    required = tool_catalog.REQUIRED_SEQUENCE["policy_gated_ticket"][1]
    assert required == "get_policy"
    assert picked != required


def test_status_update_step0_wrongly_picks_lookup_employee():
    """lookup_employee's docstring shares "one" and "employee's" with this
    step's intent text (an apostrophe-s token match, not a deep one), which
    outscores both list tools even though neither of them is the right
    read either: a genuine, not engineered, double-wasted-call case."""
    picked = _first_pick("status_update", 0, {"employee_id", "ticket_id"})
    assert picked == "lookup_employee"
    required = tool_catalog.REQUIRED_SEQUENCE["status_update"][0]
    assert required == "list_tickets_for_employee"
    assert picked != required

    remaining_candidates = [c for c in tool_catalog.satisfiable_candidates({"employee_id", "ticket_id"}) if c != picked]
    ranked_again = tool_catalog.rank_candidates(tool_catalog.STEP_INTENTS[("status_update", 0)], remaining_candidates)
    second_picked = ranked_again[0][0]
    assert second_picked == "list_assets_for_employee"
    assert second_picked != required
