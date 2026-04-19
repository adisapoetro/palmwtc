"""Characterization tests for ``palmwtc.validation.science``.

Phase 2 port from ``flux_chamber/src/science_validation.py``. Verifies
behaviour preservation: public API shape, DEFAULT_CONFIG keys, and numeric
contract of ``derive_is_daytime`` + ``run_science_validation`` on synthetic
inputs.

The port has *no* cross-module dependencies in the original (only
numpy/pandas/scipy), so tests run against the palmwtc location directly —
no path injection against the flux_chamber source is required.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from palmwtc.validation import DEFAULT_CONFIG, derive_is_daytime, run_science_validation
from palmwtc.validation.science import (
    _light_response,
    _status_atleast,
    _status_inrange,
)
from palmwtc.validation.science import test_inter_chamber as _test_inter_chamber
from palmwtc.validation.science import test_light_response as _test_light_response
from palmwtc.validation.science import test_q10 as _test_q10
from palmwtc.validation.science import test_wue as _test_wue

# ---------------------------------------------------------------------------
# DEFAULT_CONFIG contract (public API — notebook 035 depends on these keys)
# ---------------------------------------------------------------------------
EXPECTED_CONFIG_KEYS = {
    "co2_flux_col",
    "h2o_flux_col",
    "co2_slope_col",
    "radiation_col",
    "temp_col",
    "vpd_col",
    "chamber_col",
    "datetime_col",
    "Amax_range",
    "alpha_range",
    "Q10_range",
    "Q10_r2_min",
    "Q10_min_n",
    "Q10_min_T_iqr",
    "WUE_range",
    "WUE_VPD_r_max",
    "chamber_r_min",
    "T_ref",
    "daytime_hours",
    "light_response_min_n",
    "light_response_par_iqr_min",
}


def test_default_config_is_dict() -> None:
    assert isinstance(DEFAULT_CONFIG, dict)


def test_default_config_has_expected_keys() -> None:
    assert set(DEFAULT_CONFIG.keys()) == EXPECTED_CONFIG_KEYS


def test_default_config_known_values() -> None:
    # Spot-check a handful of load-bearing values — these are part of the
    # documented public contract per CLAUDE.md §3.
    assert DEFAULT_CONFIG["Amax_range"] == (5.0, 35.0)
    assert DEFAULT_CONFIG["alpha_range"] == (0.02, 0.12)
    assert DEFAULT_CONFIG["Q10_range"] == (1.5, 3.0)
    assert DEFAULT_CONFIG["Q10_r2_min"] == 0.10
    assert DEFAULT_CONFIG["Q10_min_n"] == 50
    assert DEFAULT_CONFIG["Q10_min_T_iqr"] == 3.0
    assert DEFAULT_CONFIG["WUE_range"] == (2.0, 8.0)
    assert DEFAULT_CONFIG["WUE_VPD_r_max"] == -0.10
    assert DEFAULT_CONFIG["chamber_r_min"] == 0.70
    assert DEFAULT_CONFIG["T_ref"] == 25.0
    assert DEFAULT_CONFIG["daytime_hours"] == (6, 18)
    assert DEFAULT_CONFIG["light_response_min_n"] == 200
    assert DEFAULT_CONFIG["light_response_par_iqr_min"] == 300.0
    assert DEFAULT_CONFIG["co2_flux_col"] == "flux_absolute"
    assert DEFAULT_CONFIG["chamber_col"] == "Source_Chamber"
    assert DEFAULT_CONFIG["datetime_col"] == "flux_datetime"
    assert DEFAULT_CONFIG["radiation_col"] == "Global_Radiation"


# ---------------------------------------------------------------------------
# Private helper contracts
# ---------------------------------------------------------------------------
def test_status_inrange() -> None:
    assert _status_inrange(10.0, 5.0, 15.0) == "PASS"
    assert _status_inrange(4.0, 5.0, 15.0) == "BORDERLINE"  # within 0.7x
    assert _status_inrange(18.0, 5.0, 15.0) == "BORDERLINE"  # within 1.3x
    assert _status_inrange(1.0, 5.0, 15.0) == "FAIL"
    assert _status_inrange(float("nan"), 5.0, 15.0) == "N/A"
    assert _status_inrange(None, 5.0, 15.0) == "N/A"


def test_status_atleast() -> None:
    assert _status_atleast(0.8, 0.7) == "PASS"
    assert _status_atleast(0.5, 0.7) == "BORDERLINE"
    assert _status_atleast(-0.2, -0.1, flip=True) == "PASS"
    assert _status_atleast(0.0, -0.1, flip=True) == "BORDERLINE"
    assert _status_atleast(float("nan"), 0.7) == "N/A"


def test_light_response_model_shape() -> None:
    par = np.array([0.0, 100.0, 500.0, 2000.0])
    y = _light_response(par, alpha=0.04, Amax=12.0, Rd=2.0)
    # Rectangular hyperbola: at PAR=0, output = -Rd; at PAR -> inf, output -> Amax - Rd.
    assert y[0] == pytest.approx(-2.0)
    assert y[-1] < 12.0
    assert y[-1] > y[0]


# ---------------------------------------------------------------------------
# derive_is_daytime — radiation + hour fallback
# ---------------------------------------------------------------------------
def test_derive_is_daytime_from_radiation() -> None:
    ts = pd.to_datetime(
        [
            "2026-01-01 02:00",  # radiation high, hour is nighttime -> radiation wins
            "2026-01-01 10:00",  # radiation high, hour is daytime
            "2026-01-01 22:00",  # radiation low, hour is nighttime
            "2026-01-01 14:00",  # radiation low, hour is daytime -> radiation wins (night)
        ]
    )
    df = pd.DataFrame(
        {
            "flux_datetime": ts,
            "Global_Radiation": [500.0, 800.0, 0.0, 5.0],
        }
    )
    result = derive_is_daytime(df)
    assert result.tolist() == [True, True, False, False]


def test_derive_is_daytime_nan_radiation_falls_back_to_hour() -> None:
    ts = pd.to_datetime(
        [
            "2026-01-01 10:00",  # daytime hour
            "2026-01-01 22:00",  # nighttime hour
            "2026-01-01 05:59",  # just before daytime window
            "2026-01-01 18:00",  # end of daytime window exclusive
        ]
    )
    df = pd.DataFrame(
        {
            "flux_datetime": ts,
            "Global_Radiation": [np.nan, np.nan, np.nan, np.nan],
        }
    )
    result = derive_is_daytime(df)
    assert result.tolist() == [True, False, False, False]


def test_derive_is_daytime_mixed_nan_and_real() -> None:
    ts = pd.to_datetime(
        [
            "2026-01-01 02:00",  # radiation=500 -> day
            "2026-01-01 10:00",  # radiation NaN, hour=10 -> day via fallback
            "2026-01-01 22:00",  # radiation NaN, hour=22 -> night
            "2026-01-01 10:00",  # radiation=5 -> night (radiation below threshold)
        ]
    )
    df = pd.DataFrame(
        {
            "flux_datetime": ts,
            "Global_Radiation": [500.0, np.nan, np.nan, 5.0],
        }
    )
    result = derive_is_daytime(df)
    assert result.tolist() == [True, True, False, False]


def test_derive_is_daytime_no_radiation_column() -> None:
    ts = pd.to_datetime(["2026-01-01 10:00", "2026-01-01 22:00"])
    df = pd.DataFrame({"flux_datetime": ts})
    result = derive_is_daytime(df)
    assert result.tolist() == [True, False]


def test_derive_is_daytime_custom_threshold() -> None:
    ts = pd.to_datetime(["2026-01-01 02:00", "2026-01-01 02:00"])
    df = pd.DataFrame(
        {
            "flux_datetime": ts,
            "Global_Radiation": [50.0, 5.0],
        }
    )
    result = derive_is_daytime(df, radiation_threshold=20.0)
    assert result.tolist() == [True, False]


# ---------------------------------------------------------------------------
# Synthetic cycles DataFrame builder for full pipeline tests
# ---------------------------------------------------------------------------
def _build_synthetic_cycles(n_per_chamber: int = 400, seed: int = 42) -> pd.DataFrame:
    """Build a synthetic chamber dataset with realistic diurnal structure.

    Two chambers, ~n_per_chamber cycles each. Includes:
      - daytime assimilation (negative flux_absolute) with light response
      - nighttime respiration (positive flux_absolute) with Q10 behaviour
      - H2O and VPD with WUE correlation
    """
    rng = np.random.default_rng(seed)

    # Hours distributed across a day, 400 cycles per chamber over ~30 days
    start = pd.Timestamp("2026-01-01 00:00")
    deltas_h = rng.uniform(0, 24 * 30, size=n_per_chamber * 2)
    rows = []
    for i, dh in enumerate(deltas_h):
        ts = start + pd.Timedelta(hours=float(dh))
        hour = ts.hour
        is_day = 6 <= hour < 18
        chamber = "Chamber_1" if i < n_per_chamber else "Chamber_2"

        if is_day:
            par_like = max(0.0, 400.0 * np.sin(np.pi * (hour - 6) / 12) + rng.normal(0, 50))
            radiation = par_like / 2.02  # invert the 2.02 coefficient
            # Amax ~ 12, alpha ~ 0.04, Rd ~ 2 -> assim
            assim = (0.04 * par_like * 12.0) / (0.04 * par_like + 12.0) - 2.0
            flux_absolute = -assim + rng.normal(0, 0.5)
            co2_slope = flux_absolute * 0.1  # proportional proxy
            h2o_slope = max(0.05, 2.0 + rng.normal(0, 0.3))  # mmol/m2/s
            vpd = max(0.3, 1.5 + rng.normal(0, 0.4))
            temp = 28.0 + rng.normal(0, 2.0)
        else:
            radiation = 0.0
            # Q10 ~ 2.0, T_ref 25 -> R = R_ref * Q10^((T-25)/10)
            temp = 24.0 + rng.normal(0, 3.0)
            R = 3.0 * 2.0 ** ((temp - 25.0) / 10.0) + rng.normal(0, 0.3)
            flux_absolute = max(0.1, R)
            co2_slope = flux_absolute * 0.1
            h2o_slope = max(0.01, 0.3 + rng.normal(0, 0.1))
            vpd = max(0.1, 0.5 + rng.normal(0, 0.2))

        rows.append(
            {
                "flux_datetime": ts,
                "Source_Chamber": chamber,
                "flux_absolute": flux_absolute,
                "co2_slope": co2_slope,
                "h2o_slope": h2o_slope,
                "Global_Radiation": radiation,
                "mean_temp": temp,
                "vpd_kPa": vpd,
            }
        )
    df = pd.DataFrame(rows)
    return df


# ---------------------------------------------------------------------------
# run_science_validation — top-level entry point
# ---------------------------------------------------------------------------
def test_run_science_validation_returns_expected_keys() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    result = run_science_validation(df, label="synthetic")

    # Top-level keys
    assert set(result.keys()) == {
        "label",
        "n_cycles",
        "n_daytime",
        "n_nighttime",
        "light_response",
        "q10",
        "wue",
        "inter_chamber",
        "scorecard",
    }
    assert result["label"] == "synthetic"
    assert result["n_cycles"] == len(df)
    assert result["n_daytime"] + result["n_nighttime"] == len(df)


def test_run_science_validation_scorecard_shape() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    result = run_science_validation(df, label="synth")
    sc = result["scorecard"]
    assert set(sc.keys()) == {"n_pass", "n_borderline", "n_fail", "n_na", "rows"}
    assert isinstance(sc["rows"], list)
    assert len(sc["rows"]) > 0
    for row in sc["rows"]:
        assert set(row.keys()) == {"section", "test", "expected", "observed", "status"}
        assert row["status"] in {"PASS", "BORDERLINE", "FAIL", "N/A"}
    # Internal consistency: sum of bucket counts equals number of rows
    total = sc["n_pass"] + sc["n_borderline"] + sc["n_fail"] + sc["n_na"]
    assert total == len(sc["rows"])


def test_run_science_validation_light_response_keys_per_chamber() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    result = run_science_validation(df)
    light = result["light_response"]
    assert set(light.keys()) == {"Chamber_1", "Chamber_2"}
    for _ch, fr in light.items():
        assert "n" in fr
        assert "status" in fr


def test_run_science_validation_wue_keys() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    result = run_science_validation(df)
    wue = result["wue"]
    # WUE has per-run (not per-chamber) keys
    assert "n" in wue
    assert "status" in wue
    # With synthetic data WUE should have numeric median
    assert "median" in wue


def test_run_science_validation_inter_chamber_keys() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    result = run_science_validation(df)
    inter = result["inter_chamber"]
    assert "status" in inter


def test_run_science_validation_insufficient_data_returns_na() -> None:
    # Small frame -> light_response + q10 hit min_n gates
    df = _build_synthetic_cycles(n_per_chamber=30)
    result = run_science_validation(df, label="tiny")
    for chamber_result in result["light_response"].values():
        assert chamber_result["status"] == "N/A"
    for chamber_result in result["q10"].values():
        assert chamber_result["status"] == "N/A"


def test_run_science_validation_preserves_dataframe() -> None:
    """run_science_validation must not mutate caller's dataframe."""
    df = _build_synthetic_cycles(n_per_chamber=100)
    before_cols = set(df.columns)
    _ = run_science_validation(df)
    after_cols = set(df.columns)
    assert before_cols == after_cols, "run_science_validation should not add _is_daytime to caller"


def test_run_science_validation_derive_daytime_false_requires_col() -> None:
    df = _build_synthetic_cycles(n_per_chamber=100)
    df["_is_daytime"] = derive_is_daytime(df)
    # derive_daytime=False -> uses provided _is_daytime
    result = run_science_validation(df, derive_daytime=False)
    assert result["n_cycles"] == len(df)


def test_run_science_validation_single_chamber_inter_na() -> None:
    df = _build_synthetic_cycles(n_per_chamber=300)
    single = df[df["Source_Chamber"] == "Chamber_1"].copy()
    result = run_science_validation(single)
    assert result["inter_chamber"]["status"] == "N/A"


# ---------------------------------------------------------------------------
# Individual test functions — smoke-level shape assertions
# ---------------------------------------------------------------------------
def test_test_light_response_per_chamber_shape() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    df["_is_daytime"] = derive_is_daytime(df)
    for col in ("flux_absolute", "Global_Radiation"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    result = _test_light_response(df, DEFAULT_CONFIG)
    assert set(result.keys()) == {"Chamber_1", "Chamber_2"}


def test_test_q10_per_chamber_shape() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    df["_is_daytime"] = derive_is_daytime(df)
    for col in ("flux_absolute", "mean_temp"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    result = _test_q10(df, DEFAULT_CONFIG)
    assert set(result.keys()) == {"Chamber_1", "Chamber_2"}


def test_test_wue_returns_flat_dict() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    df["_is_daytime"] = derive_is_daytime(df)
    for col in ("flux_absolute", "h2o_slope", "vpd_kPa"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    result = _test_wue(df, DEFAULT_CONFIG)
    # Not per-chamber — flat dict
    assert "status" in result
    assert "n" in result


def test_test_inter_chamber_returns_flat_dict() -> None:
    df = _build_synthetic_cycles(n_per_chamber=400)
    result = _test_inter_chamber(df, DEFAULT_CONFIG)
    assert "status" in result
