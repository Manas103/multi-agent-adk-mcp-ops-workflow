from __future__ import annotations

from src.registry import registry_data, task_corpus


def test_corpus_has_N_PER_SKILL_tasks_per_declared_skill(seeded_db):
    tasks = task_corpus.build_tasks(seeded_db)
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.task_type] = counts.get(t.task_type, 0) + 1
    for name in task_corpus.SKILL_ORDER:
        assert counts[name] == task_corpus.N_PER_SKILL
    assert len(tasks) == len(task_corpus.SKILL_ORDER) * task_corpus.N_PER_SKILL


def test_every_task_type_in_the_corpus_is_a_declared_skill(seeded_db):
    tasks = task_corpus.build_tasks(seeded_db)
    for t in tasks:
        assert t.task_type in registry_data.SKILLS_BY_NAME


def test_status_update_tasks_each_get_a_distinct_fresh_open_ticket(seeded_db):
    tasks = task_corpus.build_tasks(seeded_db)
    status_update_tickets = [t.ticket_id for t in tasks if t.task_type == "status_update"]
    assert len(status_update_tickets) == len(set(status_update_tickets))
