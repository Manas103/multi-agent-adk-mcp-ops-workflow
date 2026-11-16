"""The registry's own task corpus: 40 tasks per skill, reusing
src.tasks.task_corpus.Task and the same seeded employee/asset pool
src.seed_data.seed() already built. No schema mistakes are injected
(see proposal_builders.py); every task is well-formed.
"""
from __future__ import annotations

from ..tasks.task_corpus import POLICY_QUERIES, Task
from . import seed_extra

N_PER_SKILL = 40

SKILL_ORDER = [
    "revoke_access", "recover_asset", "policy_gated_ticket", "status_update",
    "all_level_signoff_routing",
]


def _employee_id_for(skill_index: int, i: int) -> int:
    return ((skill_index * N_PER_SKILL + i) % 60) + 1


def build_tasks(seed_scenario: dict) -> list[Task]:
    tasks: list[Task] = []
    assets_by_employee = seed_scenario["assets_by_employee"]

    for i in range(N_PER_SKILL):
        eid = _employee_id_for(0, i)
        tasks.append(Task(
            task_id=f"revoke_access-{i:03d}", task_type="revoke_access", employee_id=eid,
        ))

    for i in range(N_PER_SKILL):
        eid = _employee_id_for(1, i)
        asset_id = assets_by_employee[eid - 1][0]["asset_id"]
        tasks.append(Task(
            task_id=f"recover_asset-{i:03d}", task_type="recover_asset",
            employee_id=eid, asset_id=asset_id,
        ))

    for i in range(N_PER_SKILL):
        eid = _employee_id_for(2, i)
        query = POLICY_QUERIES[i % len(POLICY_QUERIES)]
        tasks.append(Task(
            task_id=f"policy_gated_ticket-{i:03d}", task_type="policy_gated_ticket",
            employee_id=eid, policy_query=query,
        ))

    for i in range(N_PER_SKILL):
        eid = _employee_id_for(3, i)
        asset_id = assets_by_employee[eid - 1][0]["asset_id"]
        ticket_id = seed_extra.preseed_ticket_for_employee(eid, asset_id)
        tasks.append(Task(
            task_id=f"status_update-{i:03d}", task_type="status_update",
            employee_id=eid, ticket_id=ticket_id,
        ))

    for i in range(N_PER_SKILL):
        eid = _employee_id_for(4, i)
        tasks.append(Task(
            task_id=f"all_level_signoff_routing-{i:03d}",
            task_type="all_level_signoff_routing", employee_id=eid,
        ))

    return tasks
