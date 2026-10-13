"""End-to-end orchestrator tests over the real MCP servers and real
Postgres: self-reflection correcting a deliberately malformed first attempt,
0 schema-invalid actions ever approved, and the baseline's wasted calls on
the two task types test_tool_catalog.py already pins down."""

import pytest

from src import config, db
from src.approval import gate
from src.orchestrator import baseline_orchestrator, supervisor_orchestrator
from src.tasks.task_corpus import Task
from src.tasks.oracle import grade_all


@pytest.mark.asyncio
async def test_supervisor_self_reflection_recovers_from_malformed_first_attempt(seeded_db):
    task = Task(task_id="revoke-mistake", task_type="revoke_access", employee_id=1, inject_schema_mistake=True)
    results = await supervisor_orchestrator.run_corpus([task], "r-mistake")
    assert results[0]["self_reflection_attempts"] == 1

    gate.auto_approve_all_valid("r-mistake")
    with db.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM offboard.pending_actions WHERE run_id = 'r-mistake' AND status = 'APPROVED' AND schema_invalid = TRUE"
        )
        assert cur.fetchone()["n"] == 0

    grades = grade_all([task])
    assert grades[0].passed is True


@pytest.mark.asyncio
async def test_baseline_exceeds_budget_on_status_update(seeded_db):
    ticket = seeded_db["preseeded_tickets"][0]
    task = Task(task_id="status-ambiguous", task_type="status_update",
                employee_id=ticket["employee_id"], ticket_id=ticket["ticket_id"])
    results = await baseline_orchestrator.run_corpus([task], "r-baseline-status")
    assert results[0]["status"] == "budget_exceeded"
    assert results[0]["wasted_calls"] >= 1
    assert results[0]["tool_calls"] <= config.STEP_BUDGET_BY_TASK_TYPE["status_update"]


@pytest.mark.asyncio
async def test_supervisor_status_update_succeeds_on_the_same_task(seeded_db):
    ticket = seeded_db["preseeded_tickets"][0]
    task = Task(task_id="status-ok", task_type="status_update",
                employee_id=ticket["employee_id"], ticket_id=ticket["ticket_id"])
    results = await supervisor_orchestrator.run_corpus([task], "r-supervisor-status")
    assert results[0]["status"] == "completed"
    gate.auto_approve_all_valid("r-supervisor-status")
    assert grade_all([task])[0].passed is True
