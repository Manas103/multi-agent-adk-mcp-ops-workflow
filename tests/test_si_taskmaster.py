"""Routing-only unit tests for the gated Taskmaster flow, against a fake
MCP client that just records which tool was called with which arguments,
so the dependency-gate and variant-choice logic is checked without
spawning a real subprocess or running ngspice."""

import asyncio

from src.si_signoff.task_corpus import Task
from src.si_signoff import taskmaster


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool_name: str, **kwargs) -> dict:
        self.calls.append((tool_name, kwargs))
        if tool_name == "intake_channel":
            return {"ok": True, "channel_id": "chan-1"}
        if tool_name.startswith("cascade_"):
            return {"cascade_id": "casc-1", "variant": tool_name}
        if tool_name.startswith("simulate_"):
            return {"sim_id": "sim-1", "variant": tool_name}
        if tool_name == "generate_report":
            return {"report_id": "rep-1", "verdict": "PASS"}
        raise AssertionError(f"unexpected tool {tool_name}")


def _task(has_package: bool, standard: str) -> Task:
    segments = ({"role": "package", "dk": 3.6, "df": 0.006, "length_mm": 10.0},) if has_package else ()
    segments += ({"role": "board", "dk": 4.2, "df": 0.015, "length_mm": 80.0},)
    interface = {"standard": standard, "data_rate_gbps": 16.0, "voltage_swing_v": 0.6}
    return Task(task_id="t", segments=segments, interface=interface, has_package=has_package,
                cascade_intent="x", simulate_intent="y")


def test_gated_flow_calls_stages_in_dependency_order():
    client = FakeClient()
    result = asyncio.run(taskmaster.run_task(_task(False, "NRZ"), client))
    tool_sequence = [name for name, _ in client.calls]
    assert tool_sequence == ["intake_channel", "cascade_board_only", "simulate_nrz_channel", "generate_report"]
    assert result["status"] == "completed"


def test_gated_flow_routes_package_segment_and_pam4_from_task_fields():
    client = FakeClient()
    asyncio.run(taskmaster.run_task(_task(True, "PAM4"), client))
    tool_sequence = [name for name, _ in client.calls]
    assert tool_sequence == [
        "intake_channel", "cascade_package_and_board", "simulate_pam4_channel", "generate_report",
    ]


def test_gated_flow_stops_cleanly_when_intake_rejects_the_task():
    class RejectingClient(FakeClient):
        async def call(self, tool_name, **kwargs):
            if tool_name == "intake_channel":
                return {"ok": False, "error": "bad input"}
            raise AssertionError("should not be called past a failed intake")

    result = asyncio.run(taskmaster.run_task(_task(False, "NRZ"), RejectingClient()))
    assert result["status"] == "intake_failed"
    assert result["report"] is None
