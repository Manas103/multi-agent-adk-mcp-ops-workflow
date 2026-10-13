"""Postgres schema and connection helper for the offboarding ops database.

One schema (`offboard`) holds everything: employees, assets, tickets and
policy documents (the two "legacy database" domains both MCP tool servers
read and write) and pending_actions, the schema-validated proposal queue the
human approval gate is the only writer to resolve.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.extras

from . import config

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS offboard;

CREATE TABLE IF NOT EXISTS offboard.employees (
    employee_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    access_level TEXT NOT NULL,
    access_revoked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS offboard.assets (
    asset_id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES offboard.employees(employee_id),
    description TEXT NOT NULL,
    returned BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS offboard.policy_docs (
    doc_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offboard.tickets (
    ticket_id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES offboard.employees(employee_id),
    ticket_type TEXT NOT NULL,
    asset_id INTEGER REFERENCES offboard.assets(asset_id),
    policy_doc_id TEXT REFERENCES offboard.policy_docs(doc_id),
    status TEXT NOT NULL DEFAULT 'OPEN'
);

CREATE TABLE IF NOT EXISTS offboard.pending_actions (
    action_id SERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    schema_invalid BOOLEAN NOT NULL DEFAULT FALSE,
    self_reflection_attempts INTEGER NOT NULL DEFAULT 0
);
"""

RESET_SQL = """
TRUNCATE offboard.pending_actions, offboard.tickets, offboard.assets,
         offboard.employees, offboard.policy_docs RESTART IDENTITY CASCADE;
"""


def get_connection():
    return psycopg2.connect(
        host=config.PG_HOST,
        port=config.PG_PORT,
        dbname=config.PG_DB,
        user=config.PG_USER,
        password=config.PG_PASSWORD,
    )


@contextmanager
def cursor() -> Iterator[Any]:
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    with cursor() as cur:
        cur.execute(SCHEMA_SQL)


def reset() -> None:
    with cursor() as cur:
        cur.execute(RESET_SQL)


def insert_pending_action(task_id: str, run_id: str, action_type: str, payload: dict,
                           schema_invalid: bool, self_reflection_attempts: int) -> int:
    with cursor() as cur:
        cur.execute(
            """INSERT INTO offboard.pending_actions
               (task_id, run_id, action_type, payload, status, schema_invalid, self_reflection_attempts)
               VALUES (%s, %s, %s, %s, 'PROPOSED', %s, %s) RETURNING action_id""",
            (task_id, run_id, action_type, json.dumps(payload), schema_invalid, self_reflection_attempts),
        )
        return cur.fetchone()["action_id"]
