"""End-to-end integration test over a small slice of the real corpus,
through the real si_physics_server MCP subprocess and real ngspice, for
both orchestrators, graded by the real independent oracle. Skips cleanly
if ngspice is unreachable, matching this project's Postgres-unreachable
skip convention."""

import asyncio
import shutil

import pytest

from src.si_signoff import free_form_orchestrator, oracle, physics, taskmaster
from src.si_signoff.task_corpus import build_corpus

NGSPICE_AVAILABLE = shutil.which(physics.NGSPICE_BIN) is not None


@pytest.mark.skipif(not NGSPICE_AVAILABLE, reason="ngspice not on PATH")
def test_gated_flow_beats_or_matches_free_form_on_a_corpus_slice():
    tasks = build_corpus()[:8]

    gated_results = asyncio.run(taskmaster.run_corpus(tasks))
    free_form_results = asyncio.run(free_form_orchestrator.run_corpus(tasks))

    assert all(r["status"] == "completed" for r in gated_results)
    assert all(r["report"]["verdict"] in ("PASS", "FAIL") for r in gated_results)

    gated_pass = sum(oracle.grade_all(tasks, gated_results))
    free_form_pass = sum(oracle.grade_all(tasks, free_form_results))
    assert gated_pass >= free_form_pass
    assert gated_pass == len(tasks)
