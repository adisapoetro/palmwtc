"""Characterization tests for ``palmwtc.qc.breakpoints``.

Functions ported from ``flux_chamber/src/qc_functions.py``:
    - detect_breakpoints_ruptures
    - filter_major_breakpoints
    - check_baseline_drift
    - check_cross_variable_consistency
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from palmwtc.qc.breakpoints import (
    check_baseline_drift,
    check_cross_variable_consistency,
    detect_breakpoints_ruptures,
    filter_major_breakpoints,
)

FLUX_CHAMBER_SRC = Path("/Users/adisapoetro/flux_chamber/src/qc_functions.py")
_HAS_RUPTURES = importlib.util.find_spec("ruptures") is not None
_REQUIRES_RUPTURES = pytest.mark.skipif(not _HAS_RUPTURES, reason="ruptures not installed")


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
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def step_change_series() -> pd.DataFrame:
    """Synthetic series with a single sharp step at midpoint."""
    rng = np.random.default_rng(42)
    n = 600
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    base = np.concatenate(
        [
            rng.normal(400, 2, size=n // 2),
            rng.normal(440, 2, size=n // 2),  # +40 step
        ]
    )
    return pd.DataFrame({"CO2_C1": base}, index=idx)


# ──────────────────────────────────────────────────────────────────────────────
# Standalone tests
# ──────────────────────────────────────────────────────────────────────────────


@_REQUIRES_RUPTURES
def test_detect_breakpoints_ruptures_finds_known_step(step_change_series: pd.DataFrame) -> None:
    result = detect_breakpoints_ruptures(
        step_change_series,
        "CO2_C1",
        algorithm="Binseg",
        n_bkps=1,
        min_segment_size=50,
    )
    assert result is not None
    assert result["n_breakpoints"] == 1
    bp = result["breakpoints"][0]
    midpoint = step_change_series.index[len(step_change_series) // 2]
    # The detected breakpoint should be within 5% of total length of the true midpoint
    tolerance = pd.Timedelta(hours=len(step_change_series) // 20)
    assert abs(bp - midpoint) < tolerance


@_REQUIRES_RUPTURES
def test_detect_breakpoints_returns_none_for_missing_var() -> None:
    df = pd.DataFrame({"X": [1, 2, 3]}, index=pd.date_range("2024-01-01", periods=3, freq="1h"))
    result = detect_breakpoints_ruptures(df, "MISSING")
    assert result is None


@_REQUIRES_RUPTURES
def test_detect_breakpoints_no_change_returns_zero() -> None:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=400, freq="1h")
    df = pd.DataFrame({"X": rng.normal(0, 1, size=400)}, index=idx)
    # Use high penalty so no spurious breakpoints
    result = detect_breakpoints_ruptures(df, "X", penalty=1000, min_segment_size=50)
    assert result is not None
    assert result["n_breakpoints"] == 0
    assert result["segment_means"] == [pytest.approx(df["X"].mean())]


def test_filter_major_breakpoints_filters_low_confidence() -> None:
    bp_result = {
        "n_breakpoints": 2,
        "breakpoints": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")],
        "segment_info": [
            {"mean": 400, "std": 1},
            {"mean": 401, "std": 1},  # diff = 1 < min_mean_shift
            {"mean": 500, "std": 1},
        ],
        "confidence_scores": [0.1, 0.95],  # first below 0.3
    }
    out = filter_major_breakpoints(bp_result, min_confidence=0.3, min_mean_shift=15)
    # Only 2nd bp passes both filters; the 1st fails on confidence and shift.
    assert len(out) == 1
    assert out[0] == pd.Timestamp("2024-02-01")


def test_filter_major_breakpoints_handles_none() -> None:
    assert filter_major_breakpoints(None) == []
    assert filter_major_breakpoints({"n_breakpoints": 0, "breakpoints": []}) == []


def test_check_baseline_drift_returns_daily_stats() -> None:
    idx = pd.date_range("2024-01-01", periods=24 * 5, freq="1h")
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"CO2": 415 + rng.normal(0, 5, size=len(idx))}, index=idx)
    result = check_baseline_drift(df, "CO2", expected_min=415)
    assert "CO2_daily_min" in result.columns
    assert "CO2_daily_max" in result.columns
    assert "CO2_daily_mean" in result.columns
    assert "CO2_daily_range" in result.columns
    assert "CO2_baseline_drift" in result.columns
    # 5 days of data
    assert len(result) == 5


def test_check_baseline_drift_missing_column() -> None:
    df = pd.DataFrame({"X": [1, 2, 3]})
    assert check_baseline_drift(df, "MISSING") is None


def test_check_cross_variable_consistency_flags_invalid_rh() -> None:
    idx = pd.date_range("2024-01-01", periods=10, freq="1h")
    df = pd.DataFrame(
        {
            "RH_Avg": [50, 60, 105, 70, -5, 80, 90, 50, 60, 70],
        },
        index=idx,
    )
    flags = check_cross_variable_consistency(df)
    assert "RH_Avg_invalid" in flags.columns
    assert flags["RH_Avg_invalid"].sum() == 2  # 105 and -5


def test_check_cross_variable_consistency_chamber_mismatch() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="1h")
    df = pd.DataFrame(
        {
            "Temp_1_C1": [25.0, 25.0, 25.0, 25.0, 25.0],
            "Temp_1_C2": [25.5, 26.0, 35.5, 25.5, 26.0],
            "CO2_C1": [410.0, 410.0, 410.0, 410.0, 410.0],
            "CO2_C2": [415.0, 700.0, 415.0, 415.0, 415.0],
        },
        index=idx,
    )
    flags = check_cross_variable_consistency(df)
    # Temp diff > 10 only at idx 2 (35.5 - 25.0 = 10.5)
    assert flags["temp_chamber_mismatch"].sum() == 1
    # CO2 diff > 200 only at idx 1 (700 - 410 = 290)
    assert flags["co2_chamber_mismatch"].sum() == 1


# ──────────────────────────────────────────────────────────────────────────────
# Parity tests against original
# ──────────────────────────────────────────────────────────────────────────────


@_PARITY_SKIP
@_REQUIRES_RUPTURES
def test_parity_detect_breakpoints_ruptures(step_change_series: pd.DataFrame) -> None:
    orig = _load_original()
    expected = orig.detect_breakpoints_ruptures(
        step_change_series,
        "CO2_C1",
        algorithm="Binseg",
        n_bkps=1,
        min_segment_size=50,
    )
    actual = detect_breakpoints_ruptures(
        step_change_series,
        "CO2_C1",
        algorithm="Binseg",
        n_bkps=1,
        min_segment_size=50,
    )
    assert actual["n_breakpoints"] == expected["n_breakpoints"]
    assert actual["breakpoints"] == expected["breakpoints"]
    assert actual["confidence_scores"] == expected["confidence_scores"]


@_PARITY_SKIP
def test_parity_filter_major_breakpoints() -> None:
    orig = _load_original()
    bp_result = {
        "n_breakpoints": 2,
        "breakpoints": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")],
        "segment_info": [
            {"mean": 400, "std": 1},
            {"mean": 401, "std": 1},
            {"mean": 500, "std": 1},
        ],
        "confidence_scores": [0.1, 0.95],
    }
    expected = orig.filter_major_breakpoints(bp_result, min_confidence=0.3, min_mean_shift=15)
    actual = filter_major_breakpoints(bp_result, min_confidence=0.3, min_mean_shift=15)
    assert actual == expected


@_PARITY_SKIP
def test_parity_check_cross_variable_consistency() -> None:
    orig = _load_original()
    idx = pd.date_range("2024-01-01", periods=8, freq="1h")
    df = pd.DataFrame(
        {
            "RH_Avg": [50, 60, 105, 70, -5, 80, 90, 50],
            "Temp_1_C1": [25, 25, 25, 25, 25, 25, 25, 25],
            "Temp_1_C2": [25.5, 26, 35.5, 25.5, 26, 26, 25, 25],
            "CO2_C1": [410, 410, 410, 410, 410, 410, 410, 410],
            "CO2_C2": [415, 700, 415, 415, 415, 415, 415, 415],
        },
        index=idx,
    )
    expected = orig.check_cross_variable_consistency(df)
    actual = check_cross_variable_consistency(df)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)


def test_module_reexports_match_init() -> None:
    """Every public name in breakpoints.py is re-exported from palmwtc.qc."""
    import palmwtc.qc as qc

    for name in [
        "detect_breakpoints_ruptures",
        "filter_major_breakpoints",
        "check_baseline_drift",
        "check_cross_variable_consistency",
    ]:
        assert hasattr(qc, name), f"palmwtc.qc missing re-export: {name}"
