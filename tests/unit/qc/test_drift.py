"""Characterization tests for ``palmwtc.qc.drift``.

Functions ported from ``flux_chamber/src/qc_functions.py``:
    - detect_drift_windstats
    - apply_drift_correction
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from palmwtc.qc.drift import apply_drift_correction, detect_drift_windstats

FLUX_CHAMBER_SRC = Path("/Users/adisapoetro/flux_chamber/src/qc_functions.py")


def _load_original() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_flux_chamber_qc_functions_orig", FLUX_CHAMBER_SRC
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PARITY_SKIP = pytest.mark.skipif(
    not FLUX_CHAMBER_SRC.exists(),
    reason="flux_chamber source not available at expected path",
)


# ──────────────────────────────────────────────────────────────────────────────
# Standalone tests
# ──────────────────────────────────────────────────────────────────────────────


def test_detect_drift_windstats_returns_expected_dict_shape() -> None:
    """Smoke test: drift detection returns the documented dict shape.

    NOTE: The original ``flux_chamber/src/qc_functions.py`` constructs the
    output via ``pd.DataFrame(drift_score, columns=[...])`` which silently
    produces an empty frame when the column name does not match the input
    Series' name (a pre-existing bug). Behaviour is preserved verbatim per
    the Phase 2 "don't fix bugs while porting" rule.
    """
    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"X": np.linspace(0, 50, n) + rng.normal(0, 0.5, size=n)}, index=idx)
    result = detect_drift_windstats(df, "X", window=24)
    assert result is not None
    assert set(result.keys()) == {"scores", "metric", "window"}
    assert result["metric"] == "rolling_z_score"
    assert result["window"] == 24
    assert isinstance(result["scores"], pd.DataFrame)
    assert "X_drift_score" in result["scores"].columns


def test_detect_drift_windstats_constant_returns_none(capsys: pytest.CaptureFixture[str]) -> None:
    df = pd.DataFrame({"X": [5.0] * 100}, index=pd.date_range("2024-01-01", periods=100, freq="1h"))
    result = detect_drift_windstats(df, "X", window=24)
    assert result is None


def test_detect_drift_windstats_missing_var_returns_none() -> None:
    df = pd.DataFrame({"X": [1, 2, 3]})
    assert detect_drift_windstats(df, "MISSING") is None


def test_detect_drift_windstats_excludes_flagged() -> None:
    n = 100
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    df = pd.DataFrame({"X": np.linspace(0, 1, n), "X_qc": [0] * n}, index=idx)
    df.iloc[10:20, df.columns.get_loc("X_qc")] = 2  # flag a chunk
    result = detect_drift_windstats(df, "X", qc_flag_col="X_qc", window=12)
    assert result is not None
    assert "X_drift_score" in result["scores"].columns


def test_apply_drift_correction_aligns_segments() -> None:
    idx = pd.date_range("2024-01-01", periods=200, freq="1h")
    # Two segments: first mean ≈ 400, second mean ≈ 440
    vals = np.concatenate([np.full(100, 400.0), np.full(100, 440.0)])
    df = pd.DataFrame({"X": vals}, index=idx)
    breakpoint_ts = idx[100]
    corrected, offsets = apply_drift_correction(df, "X", [breakpoint_ts])
    # First segment is the reference → mean stays 400, offset = 0
    assert corrected.iloc[:100].mean() == pytest.approx(400.0)
    # Second segment shifted by -40
    assert corrected.iloc[100:].mean() == pytest.approx(400.0)
    assert offsets.iloc[100:].mean() == pytest.approx(40.0)


def test_apply_drift_correction_no_breakpoints_returns_original() -> None:
    idx = pd.date_range("2024-01-01", periods=10, freq="1h")
    df = pd.DataFrame({"X": np.arange(10, dtype=float)}, index=idx)
    corrected, offsets = apply_drift_correction(df, "X", [])
    pd.testing.assert_series_equal(corrected, df["X"])
    assert (offsets == 0).all()


def test_apply_drift_correction_missing_var_returns_none_offsets() -> None:
    df = pd.DataFrame({"X": [1.0, 2.0]})
    corrected, offsets = apply_drift_correction(df, "MISSING", [])
    assert corrected is None
    assert offsets is None


def test_apply_drift_correction_with_explicit_baseline() -> None:
    idx = pd.date_range("2024-01-01", periods=200, freq="1h")
    vals = np.concatenate([np.full(100, 400.0), np.full(100, 450.0)])
    df = pd.DataFrame({"X": vals}, index=idx)
    breakpoint_ts = idx[100]
    corrected, _offsets = apply_drift_correction(df, "X", [breakpoint_ts], reference_baseline=420.0)
    # First segment mean is 400, so offset = 400 - 420 = -20 → corrected = 400 - (-20) = 420
    assert corrected.iloc[:100].mean() == pytest.approx(420.0)
    # Second segment mean 450, offset = 450 - 420 = 30 → corrected = 450 - 30 = 420
    assert corrected.iloc[100:].mean() == pytest.approx(420.0)


# ──────────────────────────────────────────────────────────────────────────────
# Parity tests against original
# ──────────────────────────────────────────────────────────────────────────────


@_PARITY_SKIP
def test_parity_detect_drift_windstats() -> None:
    orig = _load_original()
    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"X": np.linspace(0, 50, n) + rng.normal(0, 0.5, size=n)}, index=idx)
    expected = orig.detect_drift_windstats(df, "X", window=24)
    actual = detect_drift_windstats(df, "X", window=24)
    pd.testing.assert_frame_equal(actual["scores"], expected["scores"])
    assert actual["window"] == expected["window"]
    assert actual["metric"] == expected["metric"]


@_PARITY_SKIP
def test_parity_apply_drift_correction() -> None:
    orig = _load_original()
    idx = pd.date_range("2024-01-01", periods=200, freq="1h")
    vals = np.concatenate([np.full(100, 400.0), np.full(100, 440.0)])
    df = pd.DataFrame({"X": vals}, index=idx)
    breakpoint_ts = idx[100]
    expected_corr, expected_off = orig.apply_drift_correction(df, "X", [breakpoint_ts])
    actual_corr, actual_off = apply_drift_correction(df, "X", [breakpoint_ts])
    pd.testing.assert_series_equal(actual_corr, expected_corr)
    pd.testing.assert_series_equal(actual_off, expected_off)


def test_module_reexports_match_init() -> None:
    """Every public name in drift.py is re-exported from palmwtc.qc."""
    import palmwtc.qc as qc

    for name in ["detect_drift_windstats", "apply_drift_correction"]:
        assert hasattr(qc, name), f"palmwtc.qc missing re-export: {name}"
