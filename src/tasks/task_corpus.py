"""The 120-task offboarding corpus: 30 each of the four task types, cycling
through the 60 seeded employees. One in four tasks of each type (`i % 4 ==
<type index>`) carries a deliberately malformed first attempt at its final
write step, so the self-reflection loop in both orchestrators has something
real to correct. See src/seed_data.py for the employees, assets, policy
documents and pre-seeded open tickets this corpus assumes exist.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

POLICY_QUERIES = [
    "ALL-level access revocation sign-off required",
    "laptop or mobile phone asset return window",
    "badge deactivation handled by security operations",
    "contractor offboarding access revocation window",
]

N_PER_TYPE = 30


@dataclasses.dataclass(frozen=True)
class Task:
    task_id: str
    task_type: str
    employee_id: int
    asset_id: Optional[int] = None
    policy_query: Optional[str] = None
    ticket_id: Optional[int] = None
    inject_schema_mistake: bool = False


def _employee_id_for(type_index: int, i: int) -> int:
    return ((type_index * N_PER_TYPE + i) % 60) + 1


def build_tasks(seed_scenario: dict, preseeded_tickets: list[dict]) -> list[Task]:
    tasks: list[Task] = []
    assets_by_employee = seed_scenario["assets_by_employee"]

    for i in range(N_PER_TYPE):
        eid = _employee_id_for(0, i)
        tasks.append(Task(
            task_id=f"revoke_access-{i:03d}", task_type="revoke_access",
            employee_id=eid, inject_schema_mistake=(i % 4 == 0),
        ))

    for i in range(N_PER_TYPE):
        eid = _employee_id_for(1, i)
        asset_id = assets_by_employee[eid - 1][0]["asset_id"]
        tasks.append(Task(
            task_id=f"recover_asset-{i:03d}", task_type="recover_asset",
            employee_id=eid, asset_id=asset_id, inject_schema_mistake=(i % 4 == 1),
        ))

    for i in range(N_PER_TYPE):
        eid = _employee_id_for(2, i)
        query = POLICY_QUERIES[i % len(POLICY_QUERIES)]
        tasks.append(Task(
            task_id=f"policy_gated_ticket-{i:03d}", task_type="policy_gated_ticket",
            employee_id=eid, policy_query=query, inject_schema_mistake=(i % 4 == 2),
        ))

    for i in range(N_PER_TYPE):
        ticket = preseeded_tickets[i]
        tasks.append(Task(
            task_id=f"status_update-{i:03d}", task_type="status_update",
            employee_id=ticket["employee_id"], ticket_id=ticket["ticket_id"],
            inject_schema_mistake=(i % 4 == 3),
        ))

    return tasks
