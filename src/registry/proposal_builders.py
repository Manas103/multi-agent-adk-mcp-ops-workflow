"""Builds the raw argument dict for each "propose" step's write tool
call, the registry's equivalent of orchestrator/proposal_builder.py.
No schema mistakes are injected here (that mechanism is already proven
at the base benchmark's scale, see README); every registry task is
well-formed on the first attempt, so `self_reflection_attempts` is 0 for
every task here and the self-reflection loop is exercised only through
the base benchmark's own 120-task corpus.
"""
from __future__ import annotations


def _revoke_access(task, ctx: dict, attempt: int) -> dict:
    access_level = ctx["employee"].get("access_level", "STANDARD")
    return {
        "employee_id": task.employee_id, "access_level": access_level,
        "reason": f"Offboarding: revoking {access_level} access for employee "
        f"{task.employee_id} on last working day.",
        "proposed_by": "registry-engine",
    }


def _return_ticket(task, ctx: dict, attempt: int) -> dict:
    return {
        "employee_id": task.employee_id, "asset_id": task.asset_id,
        "reason": f"Offboarding: recovering asset {task.asset_id} from employee "
        f"{task.employee_id}.",
        "proposed_by": "registry-engine",
    }


def _policy_ticket(task, ctx: dict, attempt: int) -> dict:
    doc_id = ctx["doc_choice"]
    return {
        "employee_id": task.employee_id, "policy_doc_id": doc_id,
        "reason": f"Offboarding: compliance ticket citing {doc_id} for employee "
        f"{task.employee_id}.",
        "proposed_by": "registry-engine",
    }


def _ticket_status(task, ctx: dict, attempt: int) -> dict:
    ticket_id = ctx["ticket_choice"]
    return {
        "ticket_id": ticket_id, "new_status": "CLOSED",
        "reason": f"Offboarding: closing ticket {ticket_id} for employee "
        f"{task.employee_id}.",
        "proposed_by": "registry-engine",
    }


BUILDERS = {
    "revoke_access": _revoke_access,
    "return_ticket": _return_ticket,
    "policy_ticket": _policy_ticket,
    "ticket_status": _ticket_status,
}
