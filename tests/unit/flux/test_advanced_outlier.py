"""Unit tests for palmwtc.flux.advanced_outlier.

Covers the three functions ported from research/notebooks/030 in palmwtc 0.4.0:

- :func:`compute_stl_residual_scores`
- :func:`compute_rolling_zscore`
- :func:`compute_ensemble_score`

The tests build small synthetic cycle-level frames so each function's
behaviour is easy to verify by inspection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from palmwtc.flux import (
    DEFAULT_ADVANCED_OUTLIER_CONFIG,
    compute_ensemble_score,
    compute_rolling_zscore,
    compute_stl_residual_scores,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _two_chamber_diurnal(n_hours: int = 96, seed: int = 0) -> pd.DataFrame:
    """Synthesise a two-chamber cycle frame with a diurnal slope signal.

    Each chamber has 1 cycle per hour for ``n_hours`` hours, with a clean
    diurnal (24-hour period) sinusoid plus small Gaussian noise.  Used to
    verify STL and rolling-zscore behaviour.
    """
    rng = np.random.default_rng(seed)
    n_per_chamber = n_hours
    rows = []
    base = pd.Timestamp("2026-01-01 00:00")
    for chamber in ("Chamber 1", "Chamber 2"):
        for i in range(n_per_chamber):
            t = base + pd.Timedelta(hours=i)
            slope = -3.0 * np.sin(2 * np.pi * (i % 24) / 24) + rng.normal(0, 0.1)
            rows.append(
                {
                    "Source_Chamber": chamber,
                    "flux_datetime": t,
                    "flux_slope": float(slope),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DEFAULT_ADVANCED_OUTLIER_CONFIG
# ---------------------------------------------------------------------------


def test_default_config_has_expected_top_level_keys():
    cfg = DEFAULT_ADVANCED_OUTLIER_CONFIG
    expected = {
        "stl_period",
        "stl_robust",
        "stl_soft_iqr_mult",
        "stl_hard_iqr_mult",
        "stl_max_interp_gap_hours",
        "rz_window_cycles",
        "rz_min_periods",
        "rz_threshold",
        "ensemble_weights",
        "ensemble_flag_threshold",
    }
    missing = expected - set(cfg)
    assert not missing, f"DEFAULT_ADVANCED_OUTLIER_CONFIG missing keys: {missing}"


def test_default_ensemble_weights_sum_to_one():
    weights = DEFAULT_ADVANCED_OUTLIER_CONFIG["ensemble_weights"]
    assert weights == pytest.approx(
        {"ml_if": 0.15, "ml_mcd": 0.15, "lof": 0.20, "tif": 0.15, "stl": 0.20, "rz": 0.15}
    )
    assert sum(weights.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# compute_stl_residual_scores
# ---------------------------------------------------------------------------


def test_compute_stl_residual_scores_returns_expected_columns():
    df = _two_chamber_diurnal(n_hours=96, seed=0)
    out = compute_stl_residual_scores(df)
    assert {"stl_residual", "stl_residual_zscore", "stl_soft_flag", "stl_hard_flag"}.issubset(
        out.columns
    )


def test_compute_stl_residual_scores_does_not_mutate_input():
    df = _two_chamber_diurnal(n_hours=96, seed=1)
    df_before = df.copy()
    _ = compute_stl_residual_scores(df)
    pd.testing.assert_frame_equal(df, df_before)


def test_compute_stl_residual_scores_flags_are_int_0_or_1():
    df = _two_chamber_diurnal(n_hours=96, seed=2)
    out = compute_stl_residual_scores(df)
    for col in ("stl_soft_flag", "stl_hard_flag"):
        unique_vals = set(out[col].dropna().unique().tolist())
        assert unique_vals.issubset({0, 1}), f"{col} has values outside {{0,1}}: {unique_vals}"


def test_compute_stl_residual_scores_short_chamber_returns_nan_zero():
    """A chamber with fewer than 3*stl_period hourly bins must not raise — gets NaN/0."""
    df = _two_chamber_diurnal(n_hours=24, seed=3)  # < 3*24 hourly bins
    out = compute_stl_residual_scores(df)
    assert out["stl_residual"].isna().all()
    assert (out["stl_soft_flag"] == 0).all()
    assert (out["stl_hard_flag"] == 0).all()


# ---------------------------------------------------------------------------
# compute_rolling_zscore
# ---------------------------------------------------------------------------


def test_compute_rolling_zscore_returns_expected_columns():
    df = _two_chamber_diurnal(n_hours=96, seed=0)
    out = compute_rolling_zscore(df)
    assert {"rolling_zscore", "rolling_zscore_flag"}.issubset(out.columns)


def test_compute_rolling_zscore_flags_an_injected_outlier():
    """Inject a single huge spike; rolling z-score must flag it."""
    df = _two_chamber_diurnal(n_hours=96, seed=4)
    # Spike in the middle of Chamber 1
    spike_idx = df[df["Source_Chamber"] == "Chamber 1"].index[48]
    df.loc[spike_idx, "flux_slope"] = 1000.0
    out = compute_rolling_zscore(df)
    assert out.loc[spike_idx, "rolling_zscore_flag"] == 1


def test_compute_rolling_zscore_does_not_mutate_input():
    df = _two_chamber_diurnal(n_hours=96, seed=5)
    df_before = df.copy()
    _ = compute_rolling_zscore(df)
    pd.testing.assert_frame_equal(df, df_before)


# ---------------------------------------------------------------------------
# compute_ensemble_score
# ---------------------------------------------------------------------------


def test_compute_ensemble_score_with_only_stl_and_rz():
    """Run STL + rolling-z on a frame, then ensemble — should produce
    anomaly_ensemble_score in [0, 1] and a binary flag column."""
    df = _two_chamber_diurnal(n_hours=120, seed=6)
    df = compute_stl_residual_scores(df)
    df = compute_rolling_zscore(df)
    out = compute_ensemble_score(df)
    assert "anomaly_ensemble_score" in out.columns
    assert "anomaly_ensemble_flag" in out.columns
    score = out["anomaly_ensemble_score"].dropna()
    assert score.min() >= 0.0 - 1e-9
    assert score.max() <= 1.0 + 1e-9
    # Flag is binary
    assert set(out["anomaly_ensemble_flag"].unique().tolist()).issubset({0, 1})
    # `{key}_norm` columns added only for present detectors
    assert "stl_norm" in out.columns
    assert "rz_norm" in out.columns
    assert "ml_if_norm" not in out.columns  # not provided
    assert "lof_norm" not in out.columns


def test_compute_ensemble_score_handles_empty_frame():
    """Empty input must not raise."""
    df = pd.DataFrame(
        columns=[
            "Source_Chamber",
            "flux_datetime",
            "flux_slope",
            "stl_residual_zscore",
            "rolling_zscore",
        ]
    )
    out = compute_ensemble_score(df)
    assert "anomaly_ensemble_score" in out.columns
    assert "anomaly_ensemble_flag" in out.columns
    assert len(out) == 0


def test_compute_ensemble_score_skips_missing_detectors():
    """When zero detector columns are present, score=0 and flag=0 everywhere."""
    df = pd.DataFrame(
        {
            "Source_Chamber": ["Chamber 1"] * 5,
            "flux_datetime": pd.date_range("2026-01-01", periods=5, freq="h"),
            "flux_slope": [-1.0, -2.0, -3.0, -2.0, -1.0],
        }
    )
    out = compute_ensemble_score(df)
    assert (out["anomaly_ensemble_score"] == 0.0).all()
    assert (out["anomaly_ensemble_flag"] == 0).all()


def test_compute_ensemble_score_higher_for_more_anomalous_inputs():
    """Sanity: a frame where the STL z-score has one large outlier should
    get a higher anomaly_ensemble_score for that row than for the others."""
    df = pd.DataFrame(
        {
            "Source_Chamber": ["Chamber 1"] * 10,
            "flux_datetime": pd.date_range("2026-01-01", periods=10, freq="h"),
            "flux_slope": [-1.0] * 10,
            "stl_residual_zscore": [0.0, 0.1, 0.0, -0.1, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0],
            "rolling_zscore": [0.0] * 10,
        }
    )
    out = compute_ensemble_score(df)
    spike_score = out.loc[6, "anomaly_ensemble_score"]
    others = out.loc[[0, 1, 2, 3, 4, 5, 7, 8, 9], "anomaly_ensemble_score"]
    assert spike_score > others.max(), (
        f"spike anomaly_ensemble_score {spike_score} should exceed all others (max {others.max()})"
    )
