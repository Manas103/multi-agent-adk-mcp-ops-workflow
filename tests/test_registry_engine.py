"""End-to-end registry tests over the real MCP servers and real
Postgres: each declared skill runs correctly, a model is called only at
a declared judgment step (never at a lookup or propose step), and a
step that names a tool outside its skill's scoped_tools is rejected
before any call is made.
"""
from __future__ import annotations

import pytest

from src import db
from src.approval import gate
from src.registry import registry_data
from src.registry.engine import RegistryEngine, run_corpus
from src.registry.judge import DeterministicJudge
from src.registry.models import RegistryScopeError, SkillDecl
from src.tasks.task_corpus import Task


@pytest.mark.asyncio
async def test_revoke_access_skill_makes_no_model_call(seeded_db):
    task = Task(task_id="r1", task_type="revoke_access", employee_id=1)
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-revoke")
    assert results[0]["model_calls"] == 0
    assert results[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_recover_asset_skill_makes_no_model_call(seeded_db):
    asset_id = seeded_db["assets_by_employee"][0][0]["asset_id"]
    task = Task(task_id="r2", task_type="recover_asset", employee_id=1, asset_id=asset_id)
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-recover")
    assert results[0]["model_calls"] == 0


@pytest.mark.asyncio
async def test_policy_gated_ticket_skill_calls_the_model_exactly_once(seeded_db):
    task = Task(task_id="r3", task_type="policy_gated_ticket", employee_id=1,
                policy_query="ALL-level access revocation sign-off required")
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-policy")
    assert results[0]["model_calls"] == 1


@pytest.mark.asyncio
async def test_status_update_skill_calls_the_model_exactly_once(seeded_db):
    ticket = seeded_db["preseeded_tickets"][0]
    task = Task(task_id="r4", task_type="status_update", employee_id=ticket["employee_id"],
                ticket_id=ticket["ticket_id"])
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-status")
    assert results[0]["model_calls"] == 1


@pytest.mark.asyncio
async def test_all_level_signoff_routing_calls_model_once_for_non_all_level(seeded_db):
    employees = seeded_db["employees"]
    non_all = next(e for e in employees if e["access_level"] != "ALL")
    task = Task(task_id="r5a", task_type="all_level_signoff_routing", employee_id=non_all["employee_id"])
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-signoff-a")
    assert results[0]["model_calls"] == 1


@pytest.mark.asyncio
async def test_all_level_signoff_routing_calls_model_twice_for_all_level(seeded_db):
    employees = seeded_db["employees"]
    all_level = next((e for e in employees if e["access_level"] == "ALL"), None)
    if all_level is None:
        pytest.skip("no ALL-level employee in this deterministic seed")
    task = Task(task_id="r5b", task_type="all_level_signoff_routing", employee_id=all_level["employee_id"])
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-signoff-b")
    assert results[0]["model_calls"] == 2


@pytest.mark.asyncio
async def test_every_proposal_is_schema_valid_and_reaches_approval(seeded_db):
    task = Task(task_id="r6", task_type="revoke_access", employee_id=2)
    await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-approval")
    gate.auto_approve_all_valid("t-approval")
    with db.cursor() as cur:
        cur.execute(
            "SELECT status, schema_invalid FROM offboard.pending_actions WHERE run_id = 't-approval'"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "APPROVED"
    assert rows[0]["schema_invalid"] is False


@pytest.mark.asyncio
async def test_badge_vs_asset_routing_files_a_ticket_for_a_real_asset(seeded_db):
    assets_by_employee = seeded_db["assets_by_employee"]
    eid, asset_id = 1, None
    for emp_id, emp_assets in enumerate(assets_by_employee, start=1):
        real = next((a for a in emp_assets if a["description"] != "badge"), None)
        if real is not None:
            eid, asset_id = emp_id, real["asset_id"]
            break
    task = Task(task_id="r8", task_type="badge_vs_asset_routing", employee_id=eid, asset_id=asset_id)
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-badge-real")
    assert results[0]["model_calls"] == 1
    gate.auto_approve_all_valid("t-badge-real")
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = 't-badge-real' "
            "AND action_type = 'CREATE_TICKET' AND status = 'APPROVED'"
        )
        assert cur.fetchone()["n"] == 1


@pytest.mark.asyncio
async def test_badge_vs_asset_routing_declines_a_badge_with_no_mutation(seeded_db):
    assets_by_employee = seeded_db["assets_by_employee"]
    eid, asset_id = None, None
    for emp_id, emp_assets in enumerate(assets_by_employee, start=1):
        badge = next((a for a in emp_assets if a["description"] == "badge"), None)
        if badge is not None:
            eid, asset_id = emp_id, badge["asset_id"]
            break
    if eid is None:
        pytest.skip("no badge asset in this deterministic seed")
    task = Task(task_id="r9", task_type="badge_vs_asset_routing", employee_id=eid, asset_id=asset_id)
    results = await run_corpus(registry_data.SKILLS_BY_NAME, [task], DeterministicJudge(), "t-badge-decline")
    assert results[0]["model_calls"] == 1
    assert results[0]["tool_calls"] == 1  # the lookup only; no propose call at all
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = 't-badge-decline'"
        )
        assert cur.fetchone()["n"] == 0


@pytest.mark.asyncio
async def test_a_step_outside_scoped_tools_is_rejected(seeded_db):
    misdeclared = SkillDecl(
        name="misdeclared",
        description="deliberately declares a tool it is not scoped to call",
        scoped_tools=frozenset({"lookup_employee"}),  # missing propose_revoke_access
        steps=(
            {"kind": "lookup", "server": "legacy", "tool": "lookup_employee",
             "args": {"employee_id": "task.employee_id"}, "store_as": "employee"},
            {"kind": "propose", "tool": "propose_revoke_access", "args_builder": "revoke_access"},
        ),
    )
    task = Task(task_id="r7", task_type="misdeclared", employee_id=1)
    with pytest.raises(RegistryScopeError):
        await run_corpus({"misdeclared": misdeclared}, [task], DeterministicJudge(), "t-scope")
