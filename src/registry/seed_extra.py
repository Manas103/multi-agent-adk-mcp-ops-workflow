"""One extra preseeding helper the registry's own task corpus needs: an
OPEN ticket for a specific employee, built the same way
src.seed_data.seed()'s own 30 preseeded tickets are, but callable one at
a time so the status_update skill's 40 tasks can each get their own
fresh OPEN ticket rather than reusing (and exhausting) the base
benchmark's 30."""
from __future__ import annotations

from .. import db


def preseed_ticket_for_employee(employee_id: int, asset_id: int) -> int:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO offboard.tickets (employee_id, ticket_type, asset_id, status)
               VALUES (%s, 'ASSET_RETURN', %s, 'OPEN') RETURNING ticket_id""",
            (employee_id, asset_id),
        )
        return cur.fetchone()["ticket_id"]
