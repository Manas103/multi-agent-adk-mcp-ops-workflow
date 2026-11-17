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


def test_approving_restore_access_resets_access_revoked(seeded_db):
    revoke_id = db.insert_pending_action(
        task_id="t1", run_id="r1", action_type="REVOKE_ACCESS",
        payload={"employee_id": 1, "access_level": "ADMIN", "reason": "offboarding test", "proposed_by": "test"},
        schema_invalid=False, self_reflection_attempts=0,
    )
    gate.approve_action(revoke_id, approved_by="tester")

    restore_id = db.insert_pending_action(
        task_id="t1-compensate", run_id="r1", action_type="RESTORE_ACCESS",
        payload={"employee_id": 1, "reason": "compensating rollback after a transport fault", "proposed_by": "compensator"},
        schema_invalid=False, self_reflection_attempts=0,
    )
    result = gate.approve_action(restore_id, approved_by="compensator")
    assert result["status"] == "APPROVED"
    with db.cursor() as cur:
        cur.execute("SELECT access_revoked FROM offboard.employees WHERE employee_id = 1")
        assert cur.fetchone()["access_revoked"] is False


def test_approving_cancel_ticket_deletes_ticket_and_resets_asset(seeded_db):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO offboard.tickets (employee_id, ticket_type, asset_id, status) VALUES (1, 'ASSET_RETURN', 1, 'OPEN') RETURNING ticket_id"
        )
        ticket_id = cur.fetchone()["ticket_id"]
        cur.execute("UPDATE offboard.assets SET returned = FALSE WHERE asset_id = 1")

    cancel_id = db.insert_pending_action(
        task_id="t1-compensate", run_id="r1", action_type="CANCEL_TICKET",
        payload={"ticket_id": ticket_id, "reason": "compensating rollback after a transport fault", "proposed_by": "compensator"},
        schema_invalid=False, self_reflection_attempts=0,
    )
    result = gate.approve_action(cancel_id, approved_by="compensator")
    assert result["status"] == "APPROVED"
    with db.cursor() as cur:
        cur.execute("SELECT * FROM offboard.tickets WHERE ticket_id = %s", (ticket_id,))
        assert cur.fetchone() is None
        cur.execute("SELECT returned FROM offboard.assets WHERE asset_id = 1")
        assert cur.fetchone()["returned"] is False


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
