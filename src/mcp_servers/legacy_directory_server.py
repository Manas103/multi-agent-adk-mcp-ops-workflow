"""MCP server #1: the legacy HR/ITSM database. Five tools, three of them
state-changing (propose_revoke_access, propose_return_ticket,
update_ticket_status), each of which schema-validates its arguments with
src.schemas.build_action before it is allowed anywhere near
offboard.pending_actions. A tool never writes to employees, assets or
tickets directly; that only happens in src/approval/gate.py once a human
(simulated by scripts/run_benchmark.py for measurement; see README) approves
the proposal.

Run standalone: python -m src.mcp_servers.legacy_directory_server
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from mcp.server.mcpserver import MCPServer

from .. import db
from ..schemas import SchemaValidationError, build_action

server = MCPServer(
    name="legacy-directory",
    instructions="Tools over the legacy employee/asset/ticket database. Use "
                 "lookup_employee and list_assets_for_employee to read state; "
                 "propose_revoke_access, propose_return_ticket and "
                 "update_ticket_status write nothing directly, they queue a "
                 "schema-validated proposal for human approval.",
)


@server.tool()
def lookup_employee(employee_id: int) -> dict:
    """Look up one employee's name, access level and revocation status."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT employee_id, name, access_level, access_revoked FROM offboard.employees WHERE employee_id = %s",
            (employee_id,),
        )
        row = cur.fetchone()
    if row is None:
        return {"found": False, "employee_id": employee_id}
    return {"found": True, **dict(row)}


@server.tool()
def list_assets_for_employee(employee_id: int) -> dict:
    """List every asset assigned to an employee and whether it has been returned."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT asset_id, description, returned FROM offboard.assets WHERE employee_id = %s ORDER BY asset_id",
            (employee_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"employee_id": employee_id, "assets": rows}


@server.tool()
def list_tickets_for_employee(employee_id: int) -> dict:
    """List every ticket open against an employee, with its current status."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT ticket_id, ticket_type, asset_id, policy_doc_id, status FROM offboard.tickets WHERE employee_id = %s ORDER BY ticket_id",
            (employee_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return {"employee_id": employee_id, "tickets": rows}


def _queue_proposal(task_id: str, run_id: str, action_type: str, raw_args: dict) -> dict:
    """Shared by every state-changing tool below: validate with
    src.schemas.build_action, record whichever attempt this is, and queue the
    result (valid or not) so the self-reflection loop and the 0-invalid-calls
    count both have one real row to look at, not a mocked return value."""

    try:
        action = build_action(action_type, raw_args)
        action_id = db.insert_pending_action(
            task_id=task_id, run_id=run_id, action_type=action_type,
            payload=action.model_dump(mode="json"), schema_invalid=False,
            self_reflection_attempts=raw_args.get("_attempt", 0),
        )
        return {"ok": True, "action_id": action_id, "schema_invalid": False}
    except SchemaValidationError as exc:
        db.insert_pending_action(
            task_id=task_id, run_id=run_id, action_type=action_type,
            payload=raw_args, schema_invalid=True,
            self_reflection_attempts=raw_args.get("_attempt", 0),
        )
        return {"ok": False, "schema_invalid": True, "error": exc.pydantic_error}


@server.tool()
def propose_revoke_access(task_id: str, run_id: str, employee_id: int, access_level: str,
                           reason: str, proposed_by: str) -> dict:
    """Propose revoking an employee's access at a given level. Schema-validated;
    returns ok=False with the validation error if the arguments do not build a
    valid RevokeAccessAction (missing reason, bad access_level, and so on)."""
    return _queue_proposal(task_id, run_id, "REVOKE_ACCESS", {
        "employee_id": employee_id, "access_level": access_level,
        "reason": reason, "proposed_by": proposed_by,
    })


@server.tool()
def propose_return_ticket(task_id: str, run_id: str, employee_id: int, asset_id: Optional[int],
                           reason: str, proposed_by: str) -> dict:
    """Propose an ASSET_RETURN ticket for one of an employee's assets.
    asset_id is optional at this layer on purpose: an ASSET_RETURN ticket
    without one is exactly the malformed call the self-reflection loop
    exists to catch, one layer down in src.schemas."""
    return _queue_proposal(task_id, run_id, "CREATE_TICKET", {
        "employee_id": employee_id, "ticket_type": "ASSET_RETURN", "asset_id": asset_id,
        "reason": reason, "proposed_by": proposed_by,
    })


@server.tool()
def propose_policy_ticket(task_id: str, run_id: str, employee_id: int, policy_doc_id: str,
                           reason: str, proposed_by: str) -> dict:
    """Propose a POLICY_COMPLIANCE ticket citing the policy document that required it."""
    return _queue_proposal(task_id, run_id, "CREATE_TICKET", {
        "employee_id": employee_id, "ticket_type": "POLICY_COMPLIANCE", "policy_doc_id": policy_doc_id,
        "reason": reason, "proposed_by": proposed_by,
    })


@server.tool()
def update_ticket_status(task_id: str, run_id: str, ticket_id: int, new_status: str,
                          reason: str, proposed_by: str) -> dict:
    """Propose a ticket status transition (OPEN / IN_PROGRESS / CLOSED)."""
    return _queue_proposal(task_id, run_id, "UPDATE_TICKET_STATUS", {
        "ticket_id": ticket_id, "new_status": new_status,
        "reason": reason, "proposed_by": proposed_by,
    })


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
