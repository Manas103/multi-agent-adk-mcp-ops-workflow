"""Compound, multi-step offboarding saga: revoke access, confirm with a
second real read that the revocation took, recover the employee's second
asset into an ASSET_RETURN ticket, then file a POL-003 compliance ticket.
Unlike every task type in orchestrator/supervisor_orchestrator.py (each of
which proposes exactly one mutation), this saga commits two to three
mutations in sequence, which is what gives a mid-saga transport fault
something real to leave partially written if nothing compensates for it.

Fixed MCP call sequence (1-indexed, this is the call_ordinal
src.faults.transport.FaultSpec targets):
    1. lookup_employee            (pre-revocation snapshot; also becomes the
                                    stale-read fault's cached response)
    2. propose_revoke_access -> approved                      [commits]
    3. lookup_employee            (confirm step 2 actually took; a
                                    STALE_READ fault here serves back call
                                    #1's pre-revocation snapshot)
    4. list_assets_for_employee
    5. propose_return_ticket -> approved                      [commits]
    6. propose_policy_ticket -> approved                       [commits]
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from ..approval import gate
from ..faults.transport import FaultInjectingClient, FaultSpec, FaultType, TransportFault
from ..orchestrator.mcp_client import McpServerClient
from . import compensator

POLICY_DOC_ID = "POL-003"


@dataclasses.dataclass
class CompoundResult:
    employee_id: int
    task_id: str
    status: str                        # "completed" | "failed_compensated"
    completed_mutations: list[str]
    compensated_mutations: list[str]
    fault: Optional[dict]
    snapshot_before: dict
    snapshot_after: dict
    partial_write: bool                # True iff snapshot_after != snapshot_before


async def run_compound_offboard(
    employee_id: int,
    asset_id: int,
    legacy: McpServerClient,
    run_id: str,
    task_id: str,
    fault: Optional[FaultSpec] = None,
) -> CompoundResult:
    client = FaultInjectingClient(legacy, fault)
    snapshot_before = compensator.snapshot_employee_state(employee_id)

    committed: list[str] = []
    revoke_action_id: Optional[int] = None
    ticket_action_id: Optional[int] = None
    fault_info = None

    try:
        lookup = await client.call("lookup_employee", employee_id=employee_id)
        access_level = lookup.get("access_level", "STANDARD")

        propose = await client.call(
            "propose_revoke_access", task_id=task_id, run_id=run_id, employee_id=employee_id,
            access_level=access_level, reason="Offboarding: compound saga step 1 of 3.",
            proposed_by="directory_ops_agent",
        )
        gate.approve_action(propose["action_id"], "benchmark-auto-approver")
        revoke_action_id = propose["action_id"]
        committed.append("REVOKE_ACCESS")

        confirm = await client.call("lookup_employee", employee_id=employee_id)
        if not confirm.get("access_revoked"):
            raise TransportFault(FaultType.STALE_READ, client.call_count, "lookup_employee")

        await client.call("list_assets_for_employee", employee_id=employee_id)

        propose_ticket = await client.call(
            "propose_return_ticket", task_id=task_id, run_id=run_id, employee_id=employee_id,
            asset_id=asset_id, reason="Offboarding: compound saga step 2 of 3.",
            proposed_by="asset_recovery_agent",
        )
        gate.approve_action(propose_ticket["action_id"], "benchmark-auto-approver")
        ticket_action_id = propose_ticket["action_id"]
        committed.append("CREATE_TICKET:ASSET_RETURN")

        propose_policy = await client.call(
            "propose_policy_ticket", task_id=task_id, run_id=run_id, employee_id=employee_id,
            policy_doc_id=POLICY_DOC_ID, reason="Offboarding: compound saga step 3 of 3.",
            proposed_by="ticketing_agent",
        )
        gate.approve_action(propose_policy["action_id"], "benchmark-auto-approver")
        committed.append("CREATE_TICKET:POLICY_COMPLIANCE")

        snapshot_after = compensator.snapshot_employee_state(employee_id)
        return CompoundResult(
            employee_id, task_id, "completed", committed, [], None,
            snapshot_before, snapshot_after, partial_write=False,
        )

    except TransportFault as exc:
        fault_info = {
            "fault_type": exc.fault_type.value,
            "call_ordinal": exc.call_ordinal,
            "tool_name": exc.tool_name,
        }

    compensated = await compensator.compensate(
        task_id=task_id, run_id=run_id, employee_id=employee_id,
        revoke_action_id=revoke_action_id if "REVOKE_ACCESS" in committed else None,
        ticket_action_id=ticket_action_id if "CREATE_TICKET:ASSET_RETURN" in committed else None,
        legacy=legacy,
    )
    snapshot_after = compensator.snapshot_employee_state(employee_id)
    partial = snapshot_after != snapshot_before
    return CompoundResult(
        employee_id, task_id, "failed_compensated", committed, compensated,
        fault_info, snapshot_before, snapshot_after, partial_write=partial,
    )
