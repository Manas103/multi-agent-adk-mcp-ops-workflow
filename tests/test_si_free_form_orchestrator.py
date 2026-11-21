"""Routing-only unit tests for the free-form baseline, against the same
fake MCP client as test_si_taskmaster.py: it must call whichever tool
rank_candidates ranks first for the task's own intent text, never the
task's structured has_package/standard fields."""

import asyncio

from src.si_signoff.task_corpus import Task
from src.si_signoff import free_form_orchestrator
from .test_si_taskmaster import FakeClient


def _task(cascade_intent: str, simulate_intent: str) -> Task:
    segments = ({"role": "board", "dk": 4.2, "df": 0.015, "length_mm": 80.0},)
    interface = {"standard": "NRZ", "data_rate_gbps": 16.0, "voltage_swing_v": 0.6}
    return Task(task_id="t", segments=segments, interface=interface, has_package=False,
                cascade_intent=cascade_intent, simulate_intent=simulate_intent)


def test_free_form_follows_a_specific_package_intent_even_though_has_package_is_false():
    task = _task(
        cascade_intent="cascade the package segment together with its board segments for this channel",
        simulate_intent="simulate this two-level NRZ channel and cross-check its insertion loss",
    )
    client = FakeClient()
    result = asyncio.run(free_form_orchestrator.run_task(task, client))
    assert result["cascade_tool_picked"] == "cascade_package_and_board"
    assert result["simulate_tool_picked"] == "simulate_nrz_channel"


def test_free_form_generic_intent_ties_break_alphabetically():
    task = _task(
        cascade_intent="build the two-port network for this channel ahead of simulation",
        simulate_intent="run the simulation step for this cascaded channel ahead of the report",
    )
    client = FakeClient()
    result = asyncio.run(free_form_orchestrator.run_task(task, client))
    assert result["cascade_tool_picked"] == "cascade_board_only"
    assert result["simulate_tool_picked"] == "simulate_nrz_channel"
