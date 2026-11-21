"""Real physics shared by the SI MCP server's cascade and simulate tools:
a distributed lossy-line insertion loss via scikit-rf (the "S-parameter
cascading" step) and an independent lumped-ladder ngspice cross-check (the
"SPICE simulation" step). This module is imported by
src/mcp_servers/si_physics_server.py only; src/si_signoff/oracle.py
re-derives the same formulas from scratch rather than importing this file,
matching this portfolio's oracle-independence convention.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import skrf

C_LIGHT_M_S = 299_792_458.0
# Per-standard link budget (already net of an assumed CTLE/DFE boost and
# the PAM4 level-spacing penalty, so PAM4's budget is the smaller one),
# plus a small swing-dependent adjustment around a 0.6V reference swing.
BASE_BUDGET_DB = {"NRZ": 14.0, "PAM4": 6.0}
SWING_REF_V = 0.6
MARGIN_BUDGET_DB = 2.0

NGSPICE_BIN = "ngspice"


def nyquist_hz(interface: dict) -> float:
    """NRZ Nyquist = bit rate / 2; PAM4 carries 2 bits/symbol, so its
    Nyquist (symbol rate / 2) is bit rate / 4."""
    rate_hz = interface["data_rate_gbps"] * 1e9
    return rate_hz / 2.0 if interface["standard"] == "NRZ" else rate_hz / 4.0


def _segment_gamma(dk: float, df: float, freq_hz: float) -> complex:
    """Propagation constant per meter for a uniform dielectric line:
    lossless phase term plus a dielectric-loss term (conductor loss is not
    modeled; disclosed in the README)."""
    beta = 2.0 * np.pi * freq_hz * np.sqrt(dk) / C_LIGHT_M_S
    alpha = (np.pi * freq_hz * np.sqrt(dk) * df) / C_LIGHT_M_S
    return alpha + 1j * beta


def cascade_insertion_loss_db(segments: list[dict], freq_hz: float, z0: float = 50.0) -> float:
    """Cascades each segment as a skrf DefinedGammaZ0 line of its own
    length and gamma, at the one frequency point requested, and returns
    the resulting |S21| in dB. Real scikit-rf network cascading (`**`),
    not a hand-rolled ABCD multiply."""
    freq = skrf.Frequency.from_f([freq_hz], unit="hz")
    network = None
    for seg in segments:
        gamma = _segment_gamma(seg["dk"], seg["df"], freq_hz)
        media = skrf.media.DefinedGammaZ0(frequency=freq, z0=z0, gamma=gamma)
        line = media.line(seg["length_mm"] * 1e-3, unit="m")
        network = line if network is None else network ** line
    s21 = network.s[0, 1, 0]
    return -20.0 * np.log10(abs(s21))


def _ladder_netlist(segments: list[dict], freq_hz: float, sections_per_wavelength: int = 20,
                     z0: float = 50.0) -> str:
    """An N-section lumped RLGC ladder standing in for each segment's
    distributed line, with the shunt dielectric conductance sized for the
    exact frequency this AC point examines (see README: this is not a
    general-frequency model, only valid at the one point it is built for).
    N is picked per segment so each lumped section is a small fraction of
    a wavelength at that frequency in that segment's dielectric; a fixed
    section count that was fine at low GHz produced spurious ladder
    resonances (not real insertion loss) once segments reached several
    wavelengths long, see README Findings."""
    lines = ["SI channel lumped-ladder cross-check, single-frequency AC point"]
    node = "in"
    node_counter = 0
    for seg_idx, seg in enumerate(segments):
        v = C_LIGHT_M_S / float(np.sqrt(seg["dk"]))
        l_per_m = z0 / v
        c_per_m = 1.0 / (z0 * v)
        omega = 2.0 * np.pi * freq_hz
        g_per_m = omega * c_per_m * seg["df"]  # dielectric conductance at this one frequency
        length_m = seg["length_mm"] * 1e-3
        wavelength_m = v / freq_hz
        n_sections = max(8, int(np.ceil(length_m / (wavelength_m / sections_per_wavelength))))
        dl = length_m / n_sections
        for sect in range(n_sections):
            node_counter += 1
            next_node = f"n{node_counter}"
            lines.append(f"Lseg{seg_idx}_{sect} {node} {next_node}_pre {l_per_m * dl!r}")
            lines.append(f"Rseg{seg_idx}_{sect} {next_node}_pre {next_node} 1e-6")
            lines.append(f"Cseg{seg_idx}_{sect} {next_node} 0 {c_per_m * dl!r}")
            if g_per_m > 0:
                lines.append(f"Rleak{seg_idx}_{sect} {next_node} 0 {1.0 / (g_per_m * dl)!r}")
            node = next_node
    lines.append(f"Rload {node} 0 {z0!r}")
    lines.append(f"Vsrc in0 0 AC 1 0")
    lines.append(f"Rsrc in0 in {z0!r}")
    lines.append(f".ac lin 1 {freq_hz!r} {freq_hz!r}")
    lines.append(".control")
    lines.append("run")
    lines.append(f"wrdata __spice_out__.txt real(v({node})) imag(v({node}))")
    lines.append(".endc")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def ngspice_insertion_loss_db(segments: list[dict], freq_hz: float, work_dir: Path, z0: float = 50.0) -> float:
    """Runs the ladder above through real ngspice and returns the
    insertion loss implied by v(load)/ (source drive / 2, the matched
    source's open-circuit halving) in dB."""
    work_dir.mkdir(parents=True, exist_ok=True)
    netlist = _ladder_netlist(segments, freq_hz, z0=z0)
    netlist_path = work_dir / "channel_ac.cir"
    netlist_path.write_text(netlist)
    out_path = work_dir / "__spice_out__.txt"
    if out_path.exists():
        out_path.unlink()

    proc = subprocess.run(
        [NGSPICE_BIN, "-b", netlist_path.name],
        cwd=work_dir, capture_output=True, text=True, timeout=60,
    )
    (work_dir / "ngspice_log.txt").write_text(
        f"returncode={proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    if not out_path.exists():
        raise RuntimeError(f"ngspice produced no output (rc={proc.returncode}): {proc.stderr[-2000:]}")

    data = np.loadtxt(out_path)
    # wrdata gives each of the two complex-vector expressions its own
    # frequency column: [freq, real(v), freq, imag(v)].
    v_complex = complex(data[1], data[3])
    v_in_matched = 0.5  # a 1V AC source into a z0 source resistor splits 0.5V across a matched load
    return -20.0 * np.log10(abs(v_complex) / v_in_matched)


def eye_margin_db(insertion_loss_db: float, interface: dict) -> float:
    standard = interface["standard"]
    delta_swing_db = 20.0 * np.log10(interface["voltage_swing_v"] / SWING_REF_V)
    return BASE_BUDGET_DB[standard] + delta_swing_db - insertion_loss_db
