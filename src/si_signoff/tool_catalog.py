"""The shared catalog the free-form baseline reasons over for the SI
signoff domain, mirroring src/orchestrator/tool_catalog.py's pattern for
the offboarding domain: real tool docstrings (copied verbatim from
src/mcp_servers/si_physics_server.py), what each tool needs to be
callable at all, and real keyword-overlap ranking against a natural-
language step intent. The gated Taskmaster flow (src/si_signoff/
taskmaster.py) never calls rank_candidates; it routes the ambiguous
cascade/simulate steps from the task's own structured fields instead of
natural-language intent, which is the entire difference under test.
"""
from __future__ import annotations

import random
import re

TOOL_DOCS = {
    "intake_channel": "Validate a channel's stackup segments and interface spec and assign it a channel id.",
    "cascade_board_only": "Cascade the channel's board-only transmission-line segments, with no package layer, into one two-port network and report insertion loss at the signaling Nyquist frequency.",
    "cascade_package_and_board": "Cascade the channel's package segment together with its board transmission-line segments into one two-port network and report insertion loss at the signaling Nyquist frequency.",
    "simulate_nrz_channel": "Run the SPICE simulation for a two-level NRZ channel: cross-check the cascaded insertion loss against an independent lumped-ladder ngspice run and compute the resulting eye margin.",
    "simulate_pam4_channel": "Run the SPICE simulation for a four-level PAM4 channel: cross-check the cascaded insertion loss against an independent lumped-ladder ngspice run and compute the resulting eye margin, including the PAM4 level-spacing penalty.",
    "generate_report": "Generate the channel compliance report (pass or fail) from a simulated eye margin.",
}

REQUIRED_INPUTS = {
    "intake_channel": set(),
    "cascade_board_only": {"channel_id"},
    "cascade_package_and_board": {"channel_id"},
    "simulate_nrz_channel": {"cascade_id"},
    "simulate_pam4_channel": {"cascade_id"},
    "generate_report": {"sim_id"},
}

CASCADE_CANDIDATES = ("cascade_board_only", "cascade_package_and_board")
SIMULATE_CANDIDATES = ("simulate_nrz_channel", "simulate_pam4_channel")

_STOPWORDS = {"the", "a", "an", "to", "of", "is", "it", "its", "and", "for", "at", "one", "this",
              "into", "report", "with", "including"}

_CASCADE_SPECIFIC = {
    True: ["route this channel's package segment plus its board lines through cascading",
           "cascade the stackup's package layer together with the board transmission lines"],
    False: ["cascade this board-only stackup, no package layer present, into one network",
            "run the cascading step for a board-only channel with no package segment"],
}
_CASCADE_GENERIC = [
    "build the two-port network for this channel ahead of simulation",
    "run the channel cascading step so insertion loss can be reported",
]

_SIMULATE_SPECIFIC = {
    "NRZ": ["simulate this two-level NRZ channel and cross-check its insertion loss",
            "run the binary NRZ simulation step for this cascaded channel"],
    "PAM4": ["simulate this four-level PAM4 channel, applying the level-spacing penalty",
             "run the multi-level PAM4 simulation step for this cascaded channel"],
}
_SIMULATE_GENERIC = [
    "run the simulation step for this cascaded channel ahead of the report",
    "cross-check this channel's cascaded insertion loss and compute its eye margin",
]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z']+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def satisfiable_candidates(known_fields: set[str]) -> list[str]:
    return [name for name, needs in REQUIRED_INPUTS.items() if needs <= known_fields]


def rank_candidates(step_intent: str, candidates: list[str]) -> list[tuple[str, int]]:
    """Real keyword overlap between the step's natural-language intent and
    each candidate tool's real docstring, ties broken alphabetically (the
    same tie rule as the offboarding domain's baseline)."""
    intent_words = _words(step_intent)
    scored = [(name, len(intent_words & _words(TOOL_DOCS[name]))) for name in candidates]
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored


def cascade_intent(rng: random.Random, has_package: bool, generic_rate: float) -> str:
    if rng.random() < generic_rate:
        return rng.choice(_CASCADE_GENERIC)
    return rng.choice(_CASCADE_SPECIFIC[has_package])


def simulate_intent(rng: random.Random, standard: str, generic_rate: float) -> str:
    if rng.random() < generic_rate:
        return rng.choice(_SIMULATE_GENERIC)
    return rng.choice(_SIMULATE_SPECIFIC[standard])
