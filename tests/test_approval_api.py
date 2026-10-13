from fastapi.testclient import TestClient

from src import db
from src.approval.api import app


def test_health():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_pending_and_approve_flow(seeded_db):
    action_id = db.insert_pending_action(
        task_id="t1", run_id="r1", action_type="REVOKE_ACCESS",
        payload={"employee_id": 1, "access_level": "ADMIN", "reason": "offboarding test", "proposed_by": "test"},
        schema_invalid=False, self_reflection_attempts=0,
    )
    client = TestClient(app)

    pending = client.get("/pending-actions").json()["actions"]
    assert any(a["action_id"] == action_id for a in pending)

    resp = client.post(f"/approve/{action_id}", params={"approved_by": "reviewer-1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"

    missing = client.post("/approve/999999")
    assert missing.status_code == 404

    twice = client.post(f"/approve/{action_id}")
    assert twice.status_code == 409
