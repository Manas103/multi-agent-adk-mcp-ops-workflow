from src import db
from src.tasks.oracle import grade_all
from src.tasks.task_corpus import Task


def test_revoke_access_fails_until_actually_revoked(seeded_db):
    task = Task(task_id="t1", task_type="revoke_access", employee_id=1)
    assert grade_all([task])[0].passed is False

    with db.cursor() as cur:
        cur.execute("UPDATE offboard.employees SET access_revoked = TRUE WHERE employee_id = 1")
    assert grade_all([task])[0].passed is True


def test_recover_asset_requires_matching_ticket(seeded_db):
    # employee 35 has no pre-seeded ticket (those only exist for employees 1-30; see
    # src/seed_data.py), so this task's "before" state is genuinely untouched.
    asset_id = seeded_db["assets_by_employee"][34][0]["asset_id"]
    task = Task(task_id="t2", task_type="recover_asset", employee_id=35, asset_id=asset_id)
    assert grade_all([task])[0].passed is False

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO offboard.tickets (employee_id, ticket_type, asset_id, status) VALUES (35, 'ASSET_RETURN', %s, 'OPEN')",
            (asset_id,),
        )
    assert grade_all([task])[0].passed is True


def test_policy_gated_ticket_must_cite_the_correct_doc(seeded_db):
    task = Task(task_id="t3", task_type="policy_gated_ticket", employee_id=1,
                policy_query="ALL-level access revocation sign-off required")

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO offboard.tickets (employee_id, ticket_type, policy_doc_id, status) VALUES (1, 'POLICY_COMPLIANCE', 'POL-003', 'OPEN')"
        )
    assert grade_all([task])[0].passed is False, "cited the wrong document"

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO offboard.tickets (employee_id, ticket_type, policy_doc_id, status) VALUES (1, 'POLICY_COMPLIANCE', 'POL-002', 'OPEN')"
        )
    assert grade_all([task])[0].passed is True
