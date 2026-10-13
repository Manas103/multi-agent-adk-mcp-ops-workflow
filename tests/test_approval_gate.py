import pytest

from src import db
from src.approval import gate


def test_approving_a_valid_action_mutates_state(seeded_db):
    action_id = db.insert_pending_action(
        task_id="t1", run_id="r1", action_type="REVOKE_ACCESS",
        payload={"employee_id": 1, "access_level": "ADMIN", "reason": "offboarding test", "proposed_by": "test"},
        schema_invalid=False, self_reflection_attempts=0,
    )
    result = gate.approve_action(action_id, approved_by="tester")
    assert result["status"] == "APPROVED"
    with db.cursor() as cur:
        cur.execute("SELECT access_revoked FROM offboard.employees WHERE employee_id = 1")
        assert cur.fetchone()["access_revoked"] is True


def test_schema_invalid_action_is_never_approved(seeded_db):
    action_id = db.insert_pending_action(
        task_id="t1", run_id="r1", action_type="REVOKE_ACCESS",
        payload={"employee_id": 1, "access_level": "ADMIN", "reason": "no", "proposed_by": "test"},
        schema_invalid=True, self_reflection_attempts=1,
    )
    result = gate.approve_action(action_id, approved_by="tester")
    assert result["status"] == "REJECTED"
    with db.cursor() as cur:
        cur.execute("SELECT access_revoked FROM offboard.employees WHERE employee_id = 1")
        assert cur.fetchone()["access_revoked"] is False


def test_approving_twice_raises(seeded_db):
    action_id = db.insert_pending_action(
        task_id="t1", run_id="r1", action_type="REVOKE_ACCESS",
        payload={"employee_id": 1, "access_level": "ADMIN", "reason": "offboarding test", "proposed_by": "test"},
        schema_invalid=False, self_reflection_attempts=0,
    )
    gate.approve_action(action_id, approved_by="tester")
    with pytest.raises(gate.ActionAlreadyResolved):
        gate.approve_action(action_id, approved_by="tester")


def test_auto_approve_all_valid_skips_schema_invalid(seeded_db):
    valid_id = db.insert_pending_action(
        task_id="t1", run_id="run-x", action_type="REVOKE_ACCESS",
        payload={"employee_id": 2, "access_level": "STANDARD", "reason": "offboarding test", "proposed_by": "test"},
        schema_invalid=False, self_reflection_attempts=0,
    )
    invalid_id = db.insert_pending_action(
        task_id="t2", run_id="run-x", action_type="REVOKE_ACCESS",
        payload={"employee_id": 3, "access_level": "STANDARD", "reason": "no", "proposed_by": "test"},
        schema_invalid=True, self_reflection_attempts=3,
    )
    results = gate.auto_approve_all_valid("run-x")
    assert len(results) == 1
    assert results[0]["action_id"] == valid_id
    with db.cursor() as cur:
        cur.execute("SELECT status FROM offboard.pending_actions WHERE action_id = %s", (invalid_id,))
        assert cur.fetchone()["status"] == "PROPOSED"
