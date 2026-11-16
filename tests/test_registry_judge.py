"""Unit tests for the deterministic judge's decision functions, and for
ClaudeCLIJudge's parsing of a real `claude -p` response (mocked here;
the live sample itself is scripts/run_registry_live_llm_sample.py)."""
from __future__ import annotations

import dataclasses
from unittest.mock import patch

import pytest

from src.registry.judge import ClaudeCLIJudge, DeterministicJudge, JudgeOutputUnusable


@dataclasses.dataclass
class _FakeTask:
    employee_id: int = 1
    asset_id: int | None = None


def test_pick_policy_doc_takes_the_top_ranked_result():
    ctx = {"search": {"results": [{"doc_id": "POL-002", "score": 3}, {"doc_id": "POL-001", "score": 1}]}}
    assert DeterministicJudge().decide("pick_policy_doc", _FakeTask(), ctx) == "POL-002"


def test_pick_policy_doc_returns_none_when_no_results():
    ctx = {"search": {"results": []}}
    assert DeterministicJudge().decide("pick_policy_doc", _FakeTask(), ctx) is None


def test_pick_ticket_to_close_picks_the_open_one():
    ctx = {"tickets": {"tickets": [
        {"ticket_id": 5, "status": "CLOSED"}, {"ticket_id": 3, "status": "OPEN"},
    ]}}
    assert DeterministicJudge().decide("pick_ticket_to_close", _FakeTask(), ctx) == 3


def test_pick_ticket_to_close_picks_lowest_id_when_more_than_one_open():
    ctx = {"tickets": {"tickets": [
        {"ticket_id": 9, "status": "OPEN"}, {"ticket_id": 2, "status": "OPEN"},
    ]}}
    assert DeterministicJudge().decide("pick_ticket_to_close", _FakeTask(), ctx) == 2


def test_decide_signoff_needed_all_level():
    ctx = {"employee": {"access_level": "ALL"}}
    assert DeterministicJudge().decide("decide_signoff_needed", _FakeTask(), ctx) == "all_level"


def test_decide_signoff_needed_standard():
    ctx = {"employee": {"access_level": "STANDARD"}}
    assert DeterministicJudge().decide("decide_signoff_needed", _FakeTask(), ctx) == "standard_or_admin"


def test_claude_cli_judge_parses_a_valid_choice():
    ctx = {"employee": {"access_level": "ALL"}}
    with patch.object(ClaudeCLIJudge, "_call_claude", return_value='{"choice": "all_level"}') as mock_call:
        value = ClaudeCLIJudge().decide("decide_signoff_needed", _FakeTask(), ctx)
    mock_call.assert_called_once()
    assert value == "all_level"


def test_claude_cli_judge_raises_on_unparseable_output():
    ctx = {"employee": {"access_level": "ALL"}}
    with patch.object(ClaudeCLIJudge, "_call_claude", return_value="not json"):
        with pytest.raises(JudgeOutputUnusable):
            ClaudeCLIJudge().decide("decide_signoff_needed", _FakeTask(), ctx)


def test_claude_cli_judge_coerces_ticket_choice_to_int():
    ctx = {"tickets": {"tickets": [{"ticket_id": 7, "status": "OPEN"}]}}
    with patch.object(ClaudeCLIJudge, "_call_claude", return_value='{"choice": "7"}'):
        value = ClaudeCLIJudge().decide("pick_ticket_to_close", _FakeTask(), ctx)
    assert value == 7


def test_decide_badge_or_asset_declines_a_badge():
    ctx = {"assets": {"assets": [{"asset_id": 1, "description": "badge", "returned": False}]}}
    task = _FakeTask(asset_id=1)
    assert DeterministicJudge().decide("decide_badge_or_asset", task, ctx) == "badge_no_ticket"


def test_decide_badge_or_asset_routes_a_real_asset():
    ctx = {"assets": {"assets": [{"asset_id": 2, "description": "laptop", "returned": False}]}}
    task = _FakeTask(asset_id=2)
    assert DeterministicJudge().decide("decide_badge_or_asset", task, ctx) == "real_asset_ticket"
