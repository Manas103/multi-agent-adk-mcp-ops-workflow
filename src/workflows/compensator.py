"""Reverses whichever prefix of the compound offboarding saga's mutations
already committed before a fault interrupted it, through the same
schema-validated propose-then-approve path real mutations go through
(propose_restore_access / propose_cancel_ticket), never a direct SQL
rollback. Reversal is always in the opposite order from commit: the ticket
this saga created is cancelled before access is restored, which is what
lets a longer saga's partial-write guarantee compose if a 4th step is ever
added (always undo the most recent commit first).
"""

from __future__ import annotations

from typing import Optional

from .. import db
from ..approval import gate
from ..orchestrator.mcp_client import McpServerClient


def snapshot_employee_state(employee_id: int) -> dict:
    """A full comparable snapshot of everything the compound workflow can
    touch for one employee: the access_revoked flag, every asset's returned
    flag, and every ticket's (type, asset_id, policy_doc_id, status). Two
    snapshots taken immediately before and after a faulted-and-compensated
    run are asserted equal by scripts/run_fault_injection_benchmark.py; that
    equality, not an inspection of which rows a compensator happened to
    touch, is what "0 partial writes" measures."""

    with db.cursor() as cur:
        cur.execute(
            "SELECT access_revoked FROM offboard.employees WHERE employee_id = %s", (employee_id,)
        )
        employee = dict(cur.fetchone())
        cur.execute(
            "SELECT asset_id, returned FROM offboard.assets WHERE employee_id = %s ORDER BY asset_id",
            (employee_id,),
        )
        assets = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """SELECT ticket_type, asset_id, policy_doc_id, status FROM offboard.tickets
               WHERE employee_id = %s ORDER BY ticket_type, asset_id, policy_doc_id""",
            (employee_id,),
        )
        tickets = [dict(r) for r in cur.fetchall()]
    return {"employee": employee, "assets": assets, "tickets": tickets}


def _ticket_id_for_action(action_id: int) -> int:
    """pending_actions stores the CREATE_TICKET proposal's payload, not the
    ticket_id Postgres assigned on approval (the SERIAL id does not exist
    yet when the proposal is queued); look the real ticket up by the same
    (employee_id, asset_id, ticket_type) the proposal committed, taking the
    most recently created match so a pre-existing ticket for the same asset
    (seeded independently of this saga) is never the one cancelled."""
    with db.cursor() as cur:
        cur.execute("SELECT payload FROM offboard.pending_actions WHERE action_id = %s", (action_id,))
        payload = cur.fetchone()["payload"]
        cur.execute(
            """SELECT ticket_id FROM offboard.tickets
               WHERE employee_id = %s AND asset_id = %s AND ticket_type = 'ASSET_RETURN'
               ORDER BY ticket_id DESC LIMIT 1""",
            (payload["employee_id"], payload["asset_id"]),
        )
        return cur.fetchone()["ticket_id"]


async def compensate(
    task_id: str,
    run_id: str,
    employee_id: int,
    revoke_action_id: Optional[int],
    ticket_action_id: Optional[int],
    legacy: McpServerClient,
) -> list[str]:
    """Issues the inverse proposal for each committed step, in reverse
    commit order, through the real, unwrapped MCP client; compensation
    itself is never subject to fault injection in this benchmark (a saga's
    own undo path failing mid-rollback is a different, not-yet-built claim,
    and is named in the README's Limitations)."""

    compensated: list[str] = []

    if ticket_action_id is not None:
        propose = await legacy.call(
            "propose_cancel_ticket", task_id=f"{task_id}-compensate-ticket", run_id=run_id,
            ticket_id=_ticket_id_for_action(ticket_action_id),
            reason="Compensating rollback: saga aborted after a transport fault.",
            proposed_by="compensator",
        )
        gate.approve_action(propose["action_id"], "compensator-auto-approver")
        compensated.append("CANCEL_TICKET:ASSET_RETURN")

    if revoke_action_id is not None:
        propose = await legacy.call(
            "propose_restore_access", task_id=f"{task_id}-compensate-access", run_id=run_id,
            employee_id=employee_id,
            reason="Compensating rollback: saga aborted after a transport fault.",
            proposed_by="compensator",
        )
        gate.approve_action(propose["action_id"], "compensator-auto-approver")
        compensated.append("RESTORE_ACCESS")

    return compensated
