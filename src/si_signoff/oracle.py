"""Independent oracle for the SI signoff corpus. Given a task's true
stackup segments and interface spec, re-derives from scratch (real
scikit-rf cascading, but its own gamma and margin formulas, never an
import of src/si_signoff/physics.py or src/mcp_servers/
si_physics_server.py) the pass/fail verdict a correctly-routed signoff
should reach, then compares it to whichever report an orchestrator
actually produced. A task is graded on that one verdict match, never an
LLM judge; see tests/test_si_oracle_independence.py, which mechanically
checks this file does not import either module.
"""
from __future__ import annotations

import numpy as np
import skrf

from .task_corpus import Task

_C_LIGHT_M_S = 299_792_458.0
_BASE_BUDGET_DB = {"NRZ": 14.0, "PAM4": 6.0}
_SWING_REF_V = 0.6
_MARGIN_BUDGET_DB = 2.0


def _gamma(dk: float, df: float, freq_hz: float) -> complex:
    beta = 2.0 * np.pi * freq_hz * np.sqrt(dk) / _C_LIGHT_M_S
    alpha = (np.pi * freq_hz * np.sqrt(dk) * df) / _C_LIGHT_M_S
    return alpha + 1j * beta


def _insertion_loss_db(segments: tuple[dict, ...], freq_hz: float, z0: float = 50.0) -> float:
    freq = skrf.Frequency.from_f([freq_hz], unit="hz")
    network = None
    for seg in segments:
        media = skrf.media.DefinedGammaZ0(frequency=freq, z0=z0, gamma=_gamma(seg["dk"], seg["df"], freq_hz))
        line = media.line(seg["length_mm"] * 1e-3, unit="m")
        network = line if network is None else network ** line
    return -20.0 * np.log10(abs(network.s[0, 1, 0]))


def expected_verdict(task: Task) -> str:
    standard = task.interface["standard"]
    freq_hz = task.interface["data_rate_gbps"] * 1e9 / (2.0 if standard == "NRZ" else 4.0)
    insertion_loss_db = _insertion_loss_db(task.segments, freq_hz)
    delta_swing_db = 20.0 * np.log10(task.interface["voltage_swing_v"] / _SWING_REF_V)
    margin = _BASE_BUDGET_DB[standard] + delta_swing_db - insertion_loss_db
    return "PASS" if margin >= _MARGIN_BUDGET_DB else "FAIL"


def grade(task: Task, run_result: dict) -> bool:
    report = run_result.get("report")
    if not report:
        return False
    return report["verdict"] == expected_verdict(task)


def grade_all(tasks: list[Task], run_results: list[dict]) -> list[bool]:
    by_id = {r["task_id"]: r for r in run_results}
    return [grade(task, by_id[task.task_id]) for task in tasks]
