"""The human approval gate: the only code path that mutates
offboard.employees / offboard.assets / offboard.tickets. Every pending
action is re-validated against src.schemas before it is applied, so a
schema-invalid row (one the self-reflection loop never corrected) can never
be approved, even if some future caller tries to approve it anyway.

For live use this is driven one action at a time through the FastAPI app in
api.py, by an actual reviewer. For the measured benchmark in
scripts/run_benchmark.py, a human is not available in this headless session;
auto_approve_all_valid stands in for one, approving every schema-valid
PROPOSED action and leaving every schema-invalid one untouched, which is
disclosed in the README rather than presented as a live approval.
"""

from __future__ import annotations

from typing import Any

from .. import db
from ..schemas import SchemaValidationError, build_action


class ActionNotFound(Exception):
    pass


class ActionAlreadyResolved(Exception):
    pass


def _fetch_action(action_id: int) -> dict:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM offboard.pending_actions WHERE action_id = %s", (action_id,))
        row = cur.fetchone()
    if row is None:
        raise ActionNotFound(f"no pending action {action_id}")
    return dict(row)


def list_pending(status: str = "PROPOSED") -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT * FROM offboard.pending_actions WHERE status = %s ORDER BY action_id", (status,)
        )
        return [dict(r) for r in cur.fetchall()]


def _apply_revoke_access(payload: dict) -> None:
    with db.cursor() as cur:
        cur.execute(
            "UPDATE offboard.employees SET access_revoked = TRUE WHERE employee_id = %s",
            (payload["employee_id"],),
        )


def _apply_create_ticket(payload: dict) -> None:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO offboard.tickets (employee_id, ticket_type, asset_id, policy_doc_id, status)
               VALUES (%s, %s, %s, %s, 'OPEN')""",
            (payload["employee_id"], payload["ticket_type"], payload.get("asset_id"), payload.get("policy_doc_id")),
        )
        if payload.get("asset_id") is not None:
            cur.execute(
                "UPDATE offboard.assets SET returned = FALSE WHERE asset_id = %s",
                (payload["asset_id"],),
            )


def _apply_update_ticket_status(payload: dict) -> None:
    with db.cursor() as cur:
        cur.execute(
            "UPDATE offboard.tickets SET status = %s WHERE ticket_id = %s",
            (payload["new_status"], payload["ticket_id"]),
        )
        if payload["new_status"] == "CLOSED":
            cur.execute(
                """UPDATE offboard.assets SET returned = TRUE WHERE asset_id = (
                       SELECT asset_id FROM offboard.tickets WHERE ticket_id = %s
                   )""",
                (payload["ticket_id"],),
            )


_APPLIERS = {
    "REVOKE_ACCESS": _apply_revoke_access,
    "CREATE_TICKET": _apply_create_ticket,
    "UPDATE_TICKET_STATUS": _apply_update_ticket_status,
}


def approve_action(action_id: int, approved_by: str) -> dict:
    """Re-validates the stored payload, applies the mutation, and marks the
    row APPROVED. Raises if the row is already resolved or re-validation now
    fails (defense in depth; the row should already be schema_invalid=False
    by the time it reaches here)."""

    row = _fetch_action(action_id)
    if row["status"] != "PROPOSED":
        raise ActionAlreadyResolved(f"action {action_id} is already {row['status']}")

    if row["schema_invalid"]:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE offboard.pending_actions SET status = 'REJECTED' WHERE action_id = %s",
                (action_id,),
            )
        return {"action_id": action_id, "status": "REJECTED", "reason": "schema_invalid"}

    try:
        build_action(row["action_type"], row["payload"])
    except SchemaValidationError as exc:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE offboard.pending_actions SET status = 'REJECTED', schema_invalid = TRUE WHERE action_id = %s",
                (action_id,),
            )
        return {"action_id": action_id, "status": "REJECTED", "reason": str(exc)}

    _APPLIERS[row["action_type"]](row["payload"])
    with db.cursor() as cur:
        cur.execute(
            "UPDATE offboard.pending_actions SET status = 'APPROVED' WHERE action_id = %s",
            (action_id,),
        )
    return {"action_id": action_id, "status": "APPROVED", "approved_by": approved_by}


def auto_approve_all_valid(run_id: str, approved_by: str = "benchmark-auto-approver") -> list[dict]:
    """Stand-in for a human reviewer, used only by scripts/run_benchmark.py.
    Approves every PROPOSED, schema-valid action for this run_id in order and
    leaves schema-invalid ones for the self-reflection loop (or a real human)
    to resolve."""

    with db.cursor() as cur:
        cur.execute(
            """SELECT action_id FROM offboard.pending_actions
               WHERE run_id = %s AND status = 'PROPOSED' AND schema_invalid = FALSE
               ORDER BY action_id""",
            (run_id,),
        )
        action_ids = [r["action_id"] for r in cur.fetchall()]
    return [approve_action(action_id, approved_by) for action_id in action_ids]
