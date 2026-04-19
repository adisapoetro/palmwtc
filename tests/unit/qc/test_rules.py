"""Characterization tests for ``palmwtc.qc.rules``.

Functions ported from ``flux_chamber/src/qc_functions.py``:
    - apply_physical_bounds_flags
    - apply_iqr_flags
    - combine_qc_flags
    - generate_qc_summary
    - get_variable_config
    - apply_rate_of_change_flags
    - apply_persistence_flags
    - apply_battery_proxy_flags
    - apply_sensor_exclusion_flags  (bare-bones smoke; no YAML needed)
    - process_variable_qc
    - add_cycle_id

Two layers:
    1. Standalone behaviour tests (always run) — anchor numeric semantics.
    2. Parity tests against the original module (skipped when source is
       absent) — boolean/value parity to 1e-12.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from palmwtc.qc.rules import (
    add_cycle_id,
    apply_battery_proxy_flags,
    apply_iqr_flags,
    apply_physical_bounds_flags,
    apply_rate_of_change_flags,
    apply_sensor_exclusion_flags,
    combine_qc_flags,
    generate_qc_summary,
    get_variable_config,
    process_variable_qc,
)

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
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    """4 s sampled DataFrame with known out-of-bounds values."""
    idx = pd.date_range("2024-01-01", periods=200, freq="4s")
    rng = np.random.default_rng(0)
    base = 25.0 + rng.normal(0, 0.5, size=200)
    # Inject known anomalies at known positions:
    base[10] = 100.0  # hard-bounds violation (Flag 2)
    base[50] = 38.0  # soft-bounds violation only (Flag 1)
    base[100] = -50.0  # hard-bounds violation (Flag 2)
    return pd.DataFrame({"AirTC_Avg": base}, index=idx)


@pytest.fixture
def temp_config() -> dict:
    """Variable-config style dict for AirTC_Avg."""
    return {
        "hard": [-40.0, 60.0],
        "soft": [10.0, 35.0],
        "rate_of_change": {"limit": 5.0},
        "persistence": {"window_hours": 1, "epsilon": 0.001},
        "iqr_factor": 1.5,
    }


@pytest.fixture
def var_config_dict(temp_config: dict) -> dict:
    return {"AirTemp": {**temp_config, "columns": ["AirTC_Avg"]}}


# ──────────────────────────────────────────────────────────────────────────────
# Standalone tests
# ──────────────────────────────────────────────────────────────────────────────


def test_apply_physical_bounds_flags_known_outliers(
    synthetic_df: pd.DataFrame, temp_config: dict
) -> None:
    flags = apply_physical_bounds_flags(synthetic_df, "AirTC_Avg", temp_config)
    # Flag 2 at hard violations
    assert flags.iloc[10] == 2
    assert flags.iloc[100] == 2
    # Flag 1 at soft-only violation
    assert flags.iloc[50] == 1
    # Most points are flag 0
    assert (flags == 0).sum() >= 195


def test_apply_physical_bounds_flags_missing_column_returns_zeros(
    synthetic_df: pd.DataFrame, temp_config: dict
) -> None:
    flags = apply_physical_bounds_flags(synthetic_df, "MISSING", temp_config)
    assert (flags == 0).all()
    assert len(flags) == len(synthetic_df)


def test_apply_iqr_flags_short_series_returns_zeros() -> None:
    df = pd.DataFrame({"X": [1.0, 2.0, 3.0]})
    flags = apply_iqr_flags(df, "X")
    assert (flags == 0).all()


def test_apply_iqr_flags_constant_series_returns_zeros() -> None:
    df = pd.DataFrame({"X": [5.0] * 50})
    flags = apply_iqr_flags(df, "X")
    assert (flags == 0).all()


def test_apply_iqr_flags_flags_extreme_outlier() -> None:
    rng = np.random.default_rng(0)
    vals = list(rng.normal(0, 1, size=100))
    vals.append(50.0)  # extreme outlier
    df = pd.DataFrame({"X": vals})
    flags = apply_iqr_flags(df, "X", iqr_factor=1.5)
    assert flags.iloc[-1] == 1


def test_combine_qc_flags_does_not_demote_flag2() -> None:
    bounds = pd.Series([0, 2, 0, 0])
    iqr = pd.Series([1, 0, 1, 0])
    out = combine_qc_flags(bounds, iqr)
    # idx 0: bounds=0, iqr=1 → 1
    # idx 1: bounds=2 → stays 2 (no demotion)
    # idx 2: bounds=0, iqr=1 → 1
    # idx 3: 0
    assert list(out) == [1, 2, 1, 0]


def test_combine_qc_flags_handles_optional_inputs() -> None:
    bounds = pd.Series([0, 1, 0])
    iqr = pd.Series([0, 0, 1])
    out = combine_qc_flags(bounds, iqr, roc_flags=None, persistence_flags=None)
    assert list(out) == [0, 1, 1]


def test_generate_qc_summary_counts() -> None:
    df = pd.DataFrame({"f": [0, 0, 1, 2, 2, 0]})
    summary = generate_qc_summary(df, "f")
    assert summary["total_points"] == 6
    assert summary["flag_0_count"] == 3
    assert summary["flag_1_count"] == 1
    assert summary["flag_2_count"] == 2
    assert summary["flag_0_percent"] == pytest.approx(50.0)


def test_get_variable_config_direct_match() -> None:
    cfg_dict = {"AirTemp": {"columns": ["AirTC_Avg", "AirTC_Inst"], "hard": [-40, 60]}}
    cfg = get_variable_config("AirTC_Avg", cfg_dict)
    assert cfg is not None
    assert cfg["hard"] == [-40, 60]


def test_get_variable_config_pattern_match() -> None:
    cfg_dict = {"Soil": {"pattern": "Tsol", "hard": [0, 50]}}
    cfg = get_variable_config("Tsol_15_Avg_Soil", cfg_dict)
    assert cfg is not None
    assert cfg["pattern"] == "Tsol"


def test_get_variable_config_no_match() -> None:
    cfg_dict = {"AirTemp": {"columns": ["X"]}}
    cfg = get_variable_config("Y", cfg_dict)
    assert cfg is None


def test_apply_rate_of_change_flags_flags_step() -> None:
    idx = pd.date_range("2024-01-01", periods=10, freq="4s")
    vals = [25.0] * 10
    vals[5] = 100.0  # huge step
    df = pd.DataFrame({"X": vals}, index=idx)
    flags = apply_rate_of_change_flags(df, "X", {"rate_of_change": {"limit": 10.0}})
    # The step at idx 5 (and back at 6) both have diffs > 10
    assert flags.iloc[5] == 1
    assert flags.iloc[6] == 1


def test_apply_rate_of_change_flags_no_config_returns_zeros() -> None:
    df = pd.DataFrame(
        {"X": [1.0, 100.0, 1.0]}, index=pd.date_range("2024-01-01", periods=3, freq="4s")
    )
    flags = apply_rate_of_change_flags(df, "X", {})
    assert (flags == 0).all()


def test_apply_battery_proxy_flags_warn_and_bad() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="4s")
    df = pd.DataFrame(
        {
            "BattV_Avg": [13.0, 11.0, 11.0, 9.0, 13.0],
            "CO2_C1_rule_flag": [0, 0, 0, 0, 0],
            "CO2_C1_qc_flag": [0, 0, 0, 0, 0],
        },
        index=idx,
    )
    cfg = {
        "sensors": {
            "BattV_Avg": {
                "warn_below": 12.0,
                "bad_below": 10.0,
                "targets": ["CO2_C1"],
            }
        }
    }
    summary = apply_battery_proxy_flags(df, cfg)
    assert summary["BattV_Avg"]["warn_count"] == 3  # values 11, 11, 9
    assert summary["BattV_Avg"]["bad_count"] == 1  # value 9
    # Row index 1 was warn (11 < 12) → flag 1
    assert df["CO2_C1_rule_flag"].iloc[1] == 1
    # Row index 3 was bad (9 < 10) → flag 2
    assert df["CO2_C1_rule_flag"].iloc[3] == 2


def test_apply_sensor_exclusion_flags_no_config_returns_zeros(synthetic_df: pd.DataFrame) -> None:
    """When config file is absent, returns a zeros series of the right shape."""
    flags = apply_sensor_exclusion_flags(
        synthetic_df, "AirTC_Avg", config_path="/nonexistent/path.yaml"
    )
    assert (flags == 0).all()
    assert len(flags) == len(synthetic_df)


def test_process_variable_qc_returns_full_dict(
    synthetic_df: pd.DataFrame, var_config_dict: dict
) -> None:
    result = process_variable_qc(synthetic_df, "AirTC_Avg", var_config_dict)
    assert {
        "final_flags",
        "exclusion_flags",
        "bounds_flags",
        "iqr_flags",
        "roc_flags",
        "persistence_flags",
        "summary",
        "config",
    } <= set(result.keys())
    assert len(result["final_flags"]) == len(synthetic_df)
    # Hard violations propagated to final flags
    assert result["final_flags"].iloc[10] == 2
    assert result["final_flags"].iloc[100] == 2


def test_process_variable_qc_no_config_warns_and_returns_zeros(synthetic_df: pd.DataFrame) -> None:
    result = process_variable_qc(synthetic_df, "AirTC_Avg", {})  # empty cfg dict
    assert (result["final_flags"] == 0).all()


def test_add_cycle_id_splits_on_gap() -> None:
    ts = list(pd.date_range("2024-01-01 00:00:00", periods=5, freq="4s")) + list(
        pd.date_range("2024-01-01 01:00:00", periods=5, freq="4s")
    )
    df = pd.DataFrame({"TIMESTAMP": ts, "x": range(10)})
    out = add_cycle_id(df, time_col="TIMESTAMP", gap_threshold_sec=300)
    assert out["cycle_id"].nunique() == 2
    # First 5 rows form cycle 1, next 5 form cycle 2
    assert (out["cycle_id"].iloc[:5] == 1).all()
    assert (out["cycle_id"].iloc[5:] == 2).all()


def test_add_cycle_id_empty_df_returns_input() -> None:
    df = pd.DataFrame()
    out = add_cycle_id(df)
    assert out.empty


# ──────────────────────────────────────────────────────────────────────────────
# Parity tests against original
# ──────────────────────────────────────────────────────────────────────────────


@_PARITY_SKIP
def test_parity_apply_physical_bounds_flags(synthetic_df: pd.DataFrame, temp_config: dict) -> None:
    orig = _load_original()
    expected = orig.apply_physical_bounds_flags(synthetic_df, "AirTC_Avg", temp_config)
    actual = apply_physical_bounds_flags(synthetic_df, "AirTC_Avg", temp_config)
    pd.testing.assert_series_equal(actual, expected, check_exact=True)


@_PARITY_SKIP
def test_parity_apply_iqr_flags(
    synthetic_df: pd.DataFrame,
) -> None:
    orig = _load_original()
    expected = orig.apply_iqr_flags(synthetic_df, "AirTC_Avg", iqr_factor=1.5)
    actual = apply_iqr_flags(synthetic_df, "AirTC_Avg", iqr_factor=1.5)
    pd.testing.assert_series_equal(actual, expected, check_exact=True)


@_PARITY_SKIP
def test_parity_combine_qc_flags() -> None:
    orig = _load_original()
    bounds = pd.Series([0, 2, 0, 1, 0, 0])
    iqr = pd.Series([1, 0, 0, 0, 1, 0])
    roc = pd.Series([0, 0, 1, 0, 0, 0])
    persistence = pd.Series([0, 0, 0, 0, 0, 1])
    expected = orig.combine_qc_flags(bounds, iqr, roc, persistence)
    actual = combine_qc_flags(bounds, iqr, roc, persistence)
    pd.testing.assert_series_equal(actual, expected, check_exact=True)


@_PARITY_SKIP
def test_parity_apply_rate_of_change_flags() -> None:
    orig = _load_original()
    idx = pd.date_range("2024-01-01", periods=20, freq="4s")
    vals = list(np.arange(20, dtype=float))
    vals[10] = 100.0
    df = pd.DataFrame({"X": vals}, index=idx)
    cfg = {"rate_of_change": {"limit": 5.0}}
    expected = orig.apply_rate_of_change_flags(df, "X", cfg)
    actual = apply_rate_of_change_flags(df, "X", cfg)
    pd.testing.assert_series_equal(actual, expected, check_exact=True)


@_PARITY_SKIP
def test_parity_process_variable_qc_full(synthetic_df: pd.DataFrame, var_config_dict: dict) -> None:
    orig = _load_original()
    expected = orig.process_variable_qc(synthetic_df, "AirTC_Avg", var_config_dict)
    actual = process_variable_qc(synthetic_df, "AirTC_Avg", var_config_dict)
    pd.testing.assert_series_equal(actual["final_flags"], expected["final_flags"], check_exact=True)
    pd.testing.assert_series_equal(
        actual["bounds_flags"], expected["bounds_flags"], check_exact=True
    )
    pd.testing.assert_series_equal(actual["iqr_flags"], expected["iqr_flags"], check_exact=True)
    pd.testing.assert_series_equal(actual["roc_flags"], expected["roc_flags"], check_exact=True)
    pd.testing.assert_series_equal(
        actual["persistence_flags"], expected["persistence_flags"], check_exact=True
    )
    assert actual["summary"] == expected["summary"]


@_PARITY_SKIP
def test_parity_add_cycle_id() -> None:
    orig = _load_original()
    ts = list(pd.date_range("2024-01-01 00:00:00", periods=5, freq="4s")) + list(
        pd.date_range("2024-01-01 01:00:00", periods=5, freq="4s")
    )
    df = pd.DataFrame({"TIMESTAMP": ts, "x": range(10)})
    expected = orig.add_cycle_id(df.copy(), time_col="TIMESTAMP", gap_threshold_sec=300)
    actual = add_cycle_id(df.copy(), time_col="TIMESTAMP", gap_threshold_sec=300)
    pd.testing.assert_series_equal(actual["cycle_id"], expected["cycle_id"], check_exact=True)


@_PARITY_SKIP
def test_parity_apply_battery_proxy_flags() -> None:
    orig = _load_original()
    idx = pd.date_range("2024-01-01", periods=5, freq="4s")
    df1 = pd.DataFrame(
        {
            "BattV_Avg": [13.0, 11.0, 11.0, 9.0, 13.0],
            "CO2_C1_rule_flag": [0, 0, 0, 0, 0],
            "CO2_C1_qc_flag": [0, 0, 0, 0, 0],
        },
        index=idx,
    )
    df2 = df1.copy()
    cfg = {
        "sensors": {
            "BattV_Avg": {
                "warn_below": 12.0,
                "bad_below": 10.0,
                "targets": ["CO2_C1"],
            }
        }
    }
    expected_summary = orig.apply_battery_proxy_flags(df1, cfg)
    actual_summary = apply_battery_proxy_flags(df2, cfg)
    assert expected_summary == actual_summary
    pd.testing.assert_frame_equal(df1, df2)


def test_module_reexports_match_init() -> None:
    """Every name in rules.py is reachable from the qc subpackage."""
    import palmwtc.qc as qc

    for name in [
        "apply_physical_bounds_flags",
        "apply_iqr_flags",
        "combine_qc_flags",
        "generate_qc_summary",
        "get_variable_config",
        "apply_rate_of_change_flags",
        "apply_persistence_flags",
        "apply_battery_proxy_flags",
        "apply_sensor_exclusion_flags",
        "process_variable_qc",
        "add_cycle_id",
        "generate_exclusion_recommendations",
    ]:
        assert hasattr(qc, name), f"palmwtc.qc missing re-export: {name}"
