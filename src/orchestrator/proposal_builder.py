"""Builds the raw argument dict for each final write tool call. When
`task.inject_schema_mistake` is set, attempt 1 (1-indexed) is deliberately
malformed in a way specific to that action's validator in src/schemas.py;
every later attempt is the corrected, valid version. Both orchestrators
call these same builders so the self-reflection mechanism is identical for
the multi-agent system and the ReAct baseline; only the step-selection
ambiguity in src/orchestrator/tool_catalog.py differs between them.
"""

from __future__ import annotations

from ..tasks.task_corpus import Task


def revoke_access_args(task: Task, access_level: str, attempt: int, proposed_by: str) -> dict:
    if task.inject_schema_mistake and attempt == 1:
        reason = "no"  # fails ProposedAction.reason's min_length=8
    else:
        reason = f"Offboarding: revoking {access_level} access for employee {task.employee_id} on last working day."
    return {"employee_id": task.employee_id, "access_level": access_level, "reason": reason, "proposed_by": proposed_by}


def return_ticket_args(task: Task, attempt: int, proposed_by: str) -> dict:
    asset_id = None if (task.inject_schema_mistake and attempt == 1) else task.asset_id  # fails CreateTicketAction's asset_required_for_asset_return
    return {"employee_id": task.employee_id, "asset_id": asset_id,
            "reason": f"Offboarding: recovering asset {task.asset_id} from employee {task.employee_id}.",
            "proposed_by": proposed_by}


def policy_ticket_args(task: Task, policy_doc_id: str, attempt: int, proposed_by: str) -> dict:
    doc_id = "" if (task.inject_schema_mistake and attempt == 1) else policy_doc_id  # fails policy_required_for_compliance
    return {"employee_id": task.employee_id, "policy_doc_id": doc_id,
            "reason": f"Offboarding: compliance ticket citing {policy_doc_id} for employee {task.employee_id}.",
            "proposed_by": proposed_by}


def update_ticket_status_args(task: Task, attempt: int, proposed_by: str) -> dict:
    new_status = "DONE" if (task.inject_schema_mistake and attempt == 1) else "CLOSED"  # not a member of TicketStatus
    return {"ticket_id": task.ticket_id, "new_status": new_status,
            "reason": f"Offboarding: closing ticket {task.ticket_id} for employee {task.employee_id}.",
            "proposed_by": proposed_by}
