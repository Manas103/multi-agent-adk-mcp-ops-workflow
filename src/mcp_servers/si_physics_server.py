"""MCP server #3: real signal-integrity physics tools for the SI signoff
flow extension (src/si_signoff/). Four stages, each a real tool:
intake_channel validates a channel spec; cascade_board_only and
cascade_package_and_board each cascade real scikit-rf S-parameter
segments (src.si_signoff.physics) into one two-port network; simulate_nrz_
channel and simulate_pam4_channel each run a real ngspice AC cross-check
and compute an eye margin; generate_report turns an eye margin into a
pass/fail verdict. cascade_* and simulate_* are two deliberately
overlapping pairs (same required input, different physics) so that
whichever orchestrator calls this server is the one deciding which
member of each pair is correct for a given channel, not this server.
State lives in this process's own dict, scoped to the lifetime of one
stdio connection (one benchmark run), never a database.

Run standalone: python -m src.mcp_servers.si_physics_server
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from ..si_signoff import physics

server = MCPServer(
    name="si-physics",
    instructions="Tools for a channel signal-integrity signoff: intake_channel validates a "
                 "stackup/interface spec; cascade_board_only and cascade_package_and_board each "
                 "cascade the channel's S-parameter segments; simulate_nrz_channel and "
                 "simulate_pam4_channel each run a SPICE cross-check and compute an eye margin; "
                 "generate_report turns an eye margin into a compliance verdict.",
)

_CHANNELS: dict[str, dict] = {}
_CASCADES: dict[str, dict] = {}
_SIMS: dict[str, dict] = {}
_REPORTS: dict[str, dict] = {}


def _validate(segments: list[dict], interface: dict) -> str | None:
    if not segments:
        return "no segments"
    for seg in segments:
        if seg.get("length_mm", 0) <= 0:
            return f"non-positive length_mm in segment {seg}"
        if seg.get("dk", 0) < 1.0:
            return f"dk below 1.0 in segment {seg}"
        if not (0.0 <= seg.get("df", -1.0) < 1.0):
            return f"df out of [0, 1) in segment {seg}"
    if interface.get("standard") not in ("NRZ", "PAM4"):
        return f"unknown interface standard {interface.get('standard')!r}"
    if interface.get("data_rate_gbps", 0) <= 0:
        return "non-positive data_rate_gbps"
    if interface.get("voltage_swing_v", 0) <= 0:
        return "non-positive voltage_swing_v"
    return None


@server.tool()
def intake_channel(segments: list[dict], interface: dict) -> dict:
    """Validate a channel's stackup segments and interface spec and assign it a channel id."""
    error = _validate(segments, interface)
    if error is not None:
        return {"ok": False, "error": error}
    channel_id = str(uuid.uuid4())
    _CHANNELS[channel_id] = {"segments": segments, "interface": interface}
    return {"ok": True, "channel_id": channel_id}


def _cascade(channel_id: str, segments_used: list[dict], variant: str) -> dict:
    channel = _CHANNELS[channel_id]
    freq_hz = physics.nyquist_hz(channel["interface"])
    insertion_loss_db = physics.cascade_insertion_loss_db(segments_used, freq_hz)
    cascade_id = str(uuid.uuid4())
    _CASCADES[cascade_id] = {
        "channel_id": channel_id, "segments_used": segments_used,
        "insertion_loss_db": insertion_loss_db, "variant": variant,
    }
    return {"cascade_id": cascade_id, "insertion_loss_db_at_nyquist": insertion_loss_db, "variant": variant}


@server.tool()
def cascade_board_only(channel_id: str) -> dict:
    """Cascade the channel's board-only transmission-line segments, with no package layer, into one two-port network and report insertion loss at the signaling Nyquist frequency."""
    channel = _CHANNELS[channel_id]
    board_segments = [s for s in channel["segments"] if s["role"] == "board"]
    return _cascade(channel_id, board_segments, "board_only")


@server.tool()
def cascade_package_and_board(channel_id: str) -> dict:
    """Cascade the channel's package segment together with its board transmission-line segments into one two-port network and report insertion loss at the signaling Nyquist frequency."""
    channel = _CHANNELS[channel_id]
    return _cascade(channel_id, list(channel["segments"]), "package_and_board")


def _simulate(cascade_id: str, forced_standard: str) -> dict:
    cascade = _CASCADES[cascade_id]
    channel = _CHANNELS[cascade["channel_id"]]
    forced_interface = {**channel["interface"], "standard": forced_standard}
    freq_hz = physics.nyquist_hz(forced_interface)
    with tempfile.TemporaryDirectory(prefix="si_signoff_") as tmp:
        spice_il_db = physics.ngspice_insertion_loss_db(cascade["segments_used"], freq_hz, Path(tmp))
    eye_margin = physics.eye_margin_db(spice_il_db, forced_interface)
    sim_id = str(uuid.uuid4())
    _SIMS[sim_id] = {
        "channel_id": cascade["channel_id"], "cascade_id": cascade_id,
        "eye_margin_db": eye_margin, "spice_insertion_loss_db": spice_il_db, "variant": forced_standard,
    }
    return {"sim_id": sim_id, "eye_margin_db": eye_margin, "variant": forced_standard}


@server.tool()
def simulate_nrz_channel(cascade_id: str) -> dict:
    """Run the SPICE simulation for a two-level NRZ channel: cross-check the cascaded insertion loss against an independent lumped-ladder ngspice run and compute the resulting eye margin."""
    return _simulate(cascade_id, "NRZ")


@server.tool()
def simulate_pam4_channel(cascade_id: str) -> dict:
    """Run the SPICE simulation for a four-level PAM4 channel: cross-check the cascaded insertion loss against an independent lumped-ladder ngspice run and compute the resulting eye margin, including the PAM4 level-spacing penalty."""
    return _simulate(cascade_id, "PAM4")


@server.tool()
def generate_report(sim_id: str) -> dict:
    """Generate the channel compliance report (pass or fail) from a simulated eye margin."""
    sim = _SIMS[sim_id]
    cascade = _CASCADES[sim["cascade_id"]]
    verdict = "PASS" if sim["eye_margin_db"] >= physics.MARGIN_BUDGET_DB else "FAIL"
    report_id = str(uuid.uuid4())
    report = {
        "report_id": report_id, "channel_id": sim["channel_id"], "verdict": verdict,
        "eye_margin_db": sim["eye_margin_db"], "margin_budget_db": physics.MARGIN_BUDGET_DB,
        "cascade_variant": cascade["variant"], "simulate_variant": sim["variant"],
    }
    _REPORTS[report_id] = report
    return report


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
