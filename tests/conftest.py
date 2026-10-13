"""Shared fixtures. Every test that touches Postgres skips cleanly if it is
unreachable, matching this portfolio's convention for a database that is
not installed as an always-on service (model-validation-alerting is the
precedent cited in playbooks/BUILDER.md)."""

import pytest

from src import db, seed_data


@pytest.fixture
def seeded_db():
    try:
        db.init_schema()
        db.reset()
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")
    scenario = seed_data.seed()
    yield scenario
