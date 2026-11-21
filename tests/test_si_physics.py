"""Real scikit-rf cascading against a real ngspice cross-check, skipping
cleanly if ngspice is unreachable on this machine (same convention
tests/conftest.py uses for an unreachable Postgres)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.si_signoff import physics

NGSPICE_AVAILABLE = shutil.which(physics.NGSPICE_BIN) is not None


def _segments():
    return [
        {"role": "package", "dk": 3.6, "df": 0.006, "length_mm": 12.0},
        {"role": "board", "dk": 4.2, "df": 0.018, "length_mm": 100.0},
    ]


def test_nyquist_hz_nrz_vs_pam4():
    interface = {"standard": "NRZ", "data_rate_gbps": 16.0, "voltage_swing_v": 0.6}
    nrz_hz = physics.nyquist_hz(interface)
    pam4_hz = physics.nyquist_hz({**interface, "standard": "PAM4"})
    assert nrz_hz == 8e9
    assert pam4_hz == 4e9


def test_cascade_insertion_loss_is_positive_and_monotonic_with_length():
    freq_hz = 8e9
    short = physics.cascade_insertion_loss_db([{"dk": 4.0, "df": 0.015, "length_mm": 20.0}], freq_hz)
    long_ = physics.cascade_insertion_loss_db([{"dk": 4.0, "df": 0.015, "length_mm": 100.0}], freq_hz)
    assert short > 0
    assert long_ > short


@pytest.mark.skipif(not NGSPICE_AVAILABLE, reason="ngspice not on PATH")
def test_ngspice_cross_check_agrees_with_skrf_cascade():
    freq_hz = 8e9
    segments = _segments()
    il_skrf = physics.cascade_insertion_loss_db(segments, freq_hz)
    with tempfile.TemporaryDirectory(prefix="si_signoff_test_") as tmp:
        il_spice = physics.ngspice_insertion_loss_db(segments, freq_hz, Path(tmp))
    assert abs(il_skrf - il_spice) < 0.4


def test_eye_margin_pam4_is_worse_than_nrz_for_the_same_loss():
    interface_common = {"voltage_swing_v": 0.6}
    nrz_margin = physics.eye_margin_db(5.0, {**interface_common, "standard": "NRZ"})
    pam4_margin = physics.eye_margin_db(5.0, {**interface_common, "standard": "PAM4"})
    assert pam4_margin < nrz_margin
