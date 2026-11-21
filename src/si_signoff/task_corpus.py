"""The 128-task SI signoff corpus: one task per channel signoff, split
evenly across 4 families (board-only vs. package+board stackup, crossed
with NRZ vs. PAM4 signaling). Each family carries one genuine routing
ambiguity at the cascade step (board-only vs. package+board) and one at
the simulate step (NRZ vs. PAM4), exactly the "2 of 4 task types with
genuine tool-selection ambiguity" pattern this portfolio already uses for
the offboarding corpus (see src/orchestrator/tool_catalog.py). Built once
with a fixed seed and then measured, not iterated on to produce a
particular gap; see the README's Findings for the measured result.
"""
from __future__ import annotations

import dataclasses
import random

GENERIC_INTENT_RATE = 0.5


@dataclasses.dataclass(frozen=True)
class Task:
    task_id: str
    segments: tuple[dict, ...]
    interface: dict
    has_package: bool
    cascade_intent: str
    simulate_intent: str


def _board_segment(rng: random.Random) -> dict:
    return {"role": "board", "dk": rng.uniform(3.8, 4.6), "df": rng.uniform(0.006, 0.022),
            "length_mm": rng.uniform(40.0, 160.0)}


def _package_segment(rng: random.Random) -> dict:
    return {"role": "package", "dk": rng.uniform(3.2, 4.0), "df": rng.uniform(0.003, 0.012),
            "length_mm": rng.uniform(5.0, 25.0)}


def _interface(rng: random.Random, standard: str) -> dict:
    data_rate = rng.uniform(8.0, 32.0) if standard == "NRZ" else rng.uniform(56.0, 112.0)
    return {"standard": standard, "data_rate_gbps": data_rate, "voltage_swing_v": rng.uniform(0.3, 1.0)}


def build_corpus(n_per_family: int = 32) -> list[Task]:
    from . import tool_catalog

    tasks: list[Task] = []
    families = [(has_package, standard)
                for has_package in (False, True)
                for standard in ("NRZ", "PAM4")]
    task_index = 0
    for has_package, standard in families:
        for _ in range(n_per_family):
            rng = random.Random(f"si-task-{task_index}")
            segments = [_package_segment(rng)] if has_package else []
            segments.append(_board_segment(rng))
            interface = _interface(rng, standard)
            cascade_intent = tool_catalog.cascade_intent(rng, has_package, GENERIC_INTENT_RATE)
            simulate_intent = tool_catalog.simulate_intent(rng, standard, GENERIC_INTENT_RATE)
            tasks.append(Task(
                task_id=f"si-{task_index:03d}", segments=tuple(segments), interface=interface,
                has_package=has_package, cascade_intent=cascade_intent, simulate_intent=simulate_intent,
            ))
            task_index += 1
    return tasks
