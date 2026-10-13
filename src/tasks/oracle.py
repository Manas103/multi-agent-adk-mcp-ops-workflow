"""Independent expected-state oracle. Reads real final Postgres rows and
diffs them against an expectation this module computes from the task and
the seeded ground truth, never from anything either orchestrator did. The
one place this module and src/mcp_servers/policy_doc_server.py necessarily
touch the same idea (ranking policy documents by word overlap) is
reimplemented from scratch here (`_rank_policy_docs`) rather than imported,
matching this portfolio's oracle-independence convention; see
tests/test_oracle_independence.py, which mechanically checks this file does
not import the servers, the orchestrators, or the ADK agents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import db
from .task_corpus import Task

_STOPWORDS = {"the", "a", "an", "to", "of", "is", "and", "for", "by"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z']+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def _rank_policy_docs(query: str, docs: list[dict]) -> list[str]:
    """A from-scratch word-overlap ranking, independent of
    policy_doc_server.search_policies, used only to say which doc_id a
    correct search *should* have surfaced."""
    q = _words(query)
    scored = []
    for doc in docs:
        overlap = len(q & _words(doc["title"] + " " + doc["body"]))
        if overlap > 0:
            scored.append((overlap, doc["doc_id"]))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [doc_id for _, doc_id in scored]


@dataclass
class TaskResult:
    task_id: str
    task_type: str
    expected: dict
    actual: dict
    passed: bool
    detail: str


def _actual_employee(employee_id: int) -> dict:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM offboard.employees WHERE employee_id = %s", (employee_id,))
        return dict(cur.fetchone())


def _actual_tickets(employee_id: int) -> list[dict]:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM offboard.tickets WHERE employee_id = %s ORDER BY ticket_id", (employee_id,))
        return [dict(r) for r in cur.fetchall()]


def _actual_ticket(ticket_id: int) -> dict:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM offboard.tickets WHERE ticket_id = %s", (ticket_id,))
        return dict(cur.fetchone())


def _actual_asset(asset_id: int) -> dict:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM offboard.assets WHERE asset_id = %s", (asset_id,))
        return dict(cur.fetchone())


def grade_task(task: Task, policy_docs: list[dict]) -> TaskResult:
    if task.task_type == "revoke_access":
        actual = _actual_employee(task.employee_id)
        passed = actual["access_revoked"] is True
        return TaskResult(task.task_id, task.task_type, {"access_revoked": True}, actual, passed,
                           "employee.access_revoked" if passed else "access was never revoked")

    if task.task_type == "recover_asset":
        tickets = _actual_tickets(task.employee_id)
        match = next((t for t in tickets if t["ticket_type"] == "ASSET_RETURN" and t["asset_id"] == task.asset_id), None)
        passed = match is not None
        return TaskResult(task.task_id, task.task_type,
                           {"ticket_type": "ASSET_RETURN", "asset_id": task.asset_id},
                           {"tickets": tickets}, passed,
                           "found matching ASSET_RETURN ticket" if passed else "no ASSET_RETURN ticket for this asset")

    if task.task_type == "policy_gated_ticket":
        ranked = _rank_policy_docs(task.policy_query, policy_docs)
        expected_doc_id = ranked[0] if ranked else None
        tickets = _actual_tickets(task.employee_id)
        match = next((t for t in tickets if t["ticket_type"] == "POLICY_COMPLIANCE" and t["policy_doc_id"] == expected_doc_id), None)
        passed = match is not None and expected_doc_id is not None
        return TaskResult(task.task_id, task.task_type,
                           {"ticket_type": "POLICY_COMPLIANCE", "policy_doc_id": expected_doc_id},
                           {"tickets": tickets}, passed,
                           f"cited {expected_doc_id}" if passed else f"expected {expected_doc_id}, no matching ticket")

    if task.task_type == "status_update":
        ticket = _actual_ticket(task.ticket_id)
        asset = _actual_asset(ticket["asset_id"]) if ticket.get("asset_id") else None
        passed = ticket["status"] == "CLOSED" and (asset is None or asset["returned"] is True)
        return TaskResult(task.task_id, task.task_type,
                           {"status": "CLOSED", "asset_returned": True},
                           {"ticket": ticket, "asset": asset}, passed,
                           "ticket closed and asset returned" if passed else f"ticket status is {ticket['status']}")

    raise ValueError(f"unknown task_type {task.task_type}")


def grade_all(tasks: list[Task]) -> list[TaskResult]:
    with db.cursor() as cur:
        cur.execute("SELECT doc_id, title, body FROM offboard.policy_docs")
        policy_docs = [dict(r) for r in cur.fetchall()]
    return [grade_task(task, policy_docs) for task in tasks]
