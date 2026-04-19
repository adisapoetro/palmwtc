"""Characterization tests for ``palmwtc.flux.cycles``.

These pin the behaviour ported verbatim from
``flux_chamber/src/flux_qc_fast.py``. Numeric outputs are asserted to match
the original within 1e-12 (or via exact equality for integer-valued metrics).

Ground-truth values were captured by running the source module against the
same synthetic fixtures defined here — see the comments next to each
``EXPECTED_*`` literal for provenance.

These tests are entirely self-contained: none of them require sibling
``palmwtc.flux.absolute`` / ``palmwtc.flux.chamber`` modules to be present.
The optional ``calculate_absolute_flux`` import in cycles.py degrades to
``None`` exactly like the original did, which keeps cycle scoring unaffected.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from palmwtc.flux.cycles import (
    NIGHTTIME_QC_THRESHOLDS,
    QC_THRESHOLDS,
    calc_aicc,
    compute_day_scores,
    compute_temporal_coherence,
    detect_bimodal_cycle,
    fit_linear_optimized,
    fit_quadratic_fast,
    identify_cycles,
    mad_outlier_mask,
    monotonic_fraction,
    score_cycle,
    score_day_quality,
)

_HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_nighttime_thresholds_keys_preserved() -> None:
    """``NIGHTTIME_QC_THRESHOLDS`` keeps the exact key set from the source module."""
    expected = {
        "b_count_C",
        "curvature_aicc",
        "curvature_aicc_C",
        "min_duration_sec",
        "min_points",
        "monotonic_A",
        "monotonic_B",
        "nrmse_A",
        "nrmse_B",
        "outlier_A",
        "outlier_B",
        "r2_A",
        "r2_B",
        "signal_ppm_guard",
        "slope_diff_A",
        "slope_diff_B",
        "snr_A",
        "snr_B",
    }
    assert set(NIGHTTIME_QC_THRESHOLDS.keys()) == expected


def test_nighttime_thresholds_values_pinned() -> None:
    """A few representative numeric values are pinned to the source defaults."""
    assert NIGHTTIME_QC_THRESHOLDS["r2_A"] == 0.70
    assert NIGHTTIME_QC_THRESHOLDS["r2_B"] == 0.40
    assert NIGHTTIME_QC_THRESHOLDS["snr_A"] == 5.0
    assert NIGHTTIME_QC_THRESHOLDS["signal_ppm_guard"] == 3.0
    assert NIGHTTIME_QC_THRESHOLDS["b_count_C"] == 4


def test_qc_thresholds_values_pinned() -> None:
    """Daytime ``QC_THRESHOLDS`` defaults preserved verbatim from the source."""
    assert QC_THRESHOLDS["r2_A"] == 0.90
    assert QC_THRESHOLDS["r2_B"] == 0.70
    assert QC_THRESHOLDS["snr_A"] == 10.0
    assert QC_THRESHOLDS["signal_ppm_guard"] == 5.0
    assert QC_THRESHOLDS["b_count_C"] == 3


# ---------------------------------------------------------------------------
# Core math helpers
# ---------------------------------------------------------------------------


def test_calc_aicc_handles_too_few_points() -> None:
    assert np.isinf(calc_aicc(rss=1.0, n=3, k=2))


def test_calc_aicc_recipe_matches_source() -> None:
    """Recompute the formula by hand and assert exact match."""
    rss, n, k = 0.05, 10, 2
    rss_clamped = max(rss, 1e-12)
    aic = n * np.log(rss_clamped / n) + 2 * k
    expected = aic + (2 * k * (k + 1)) / (n - k - 1)
    assert calc_aicc(rss, n, k) == pytest.approx(expected, abs=1e-12)


def test_fit_linear_optimized_matches_synthetic_truth() -> None:
    """Slope/intercept/R² captured from running the original module on the
    same inputs (see test docstring for provenance)."""
    t = np.arange(10, dtype=float)
    y = 2.0 * t + 1.0 + np.array([0.0, 0.1, -0.1, 0.05, -0.05, 0.02, -0.02, 0.01, -0.01, 0.0])
    slope, intercept, r2, _, _, rmse, _, aicc, residuals = fit_linear_optimized(
        t, y, compute_stats=False
    )
    assert slope == pytest.approx(1.9978181818181815, abs=1e-12)
    assert intercept == pytest.approx(1.0098181818181815, abs=1e-12)
    assert r2 == pytest.approx(0.9999222386694221, abs=1e-12)
    assert rmse == pytest.approx(0.05060362904700856, abs=1e-12)
    assert aicc == pytest.approx(-53.96035398499195, abs=1e-12)
    assert residuals.shape == (10,)


def test_fit_linear_optimized_too_few_points() -> None:
    out = fit_linear_optimized(np.array([1.0]), np.array([2.0]))
    slope, intercept, r2, _p, _se, _rmse, _rss, aicc, _residuals = out
    assert np.isnan(slope)
    assert np.isnan(intercept)
    assert r2 == 0.0
    assert np.isinf(aicc)


def test_fit_linear_optimized_compute_stats_path() -> None:
    """Ensure the compute_stats=True branch populates p_value/std_err."""
    t = np.arange(10, dtype=float)
    y = 3.0 * t + 5.0
    out = fit_linear_optimized(t, y, compute_stats=True)
    _, _, _, p_value, std_err, *_ = out
    # Perfect fit → std_err == 0 and p_value finite
    assert std_err == pytest.approx(0.0, abs=1e-12)
    assert np.isfinite(p_value)


def test_fit_quadratic_fast_recovers_known_coefficients() -> None:
    t = np.linspace(0, 10, 50)
    coeffs_true = (0.5, -1.5, 2.0)
    y = coeffs_true[0] * t**2 + coeffs_true[1] * t + coeffs_true[2]
    coeffs, rss, _, residuals = fit_quadratic_fast(t, y)
    assert coeffs[0] == pytest.approx(coeffs_true[0], abs=1e-10)
    assert coeffs[1] == pytest.approx(coeffs_true[1], abs=1e-10)
    assert coeffs[2] == pytest.approx(coeffs_true[2], abs=1e-10)
    assert rss == pytest.approx(0.0, abs=1e-18)
    assert residuals.shape == (50,)


def test_mad_outlier_mask_flags_known_outlier() -> None:
    residuals = np.array([0.0, 0.1, -0.1, 0.05, 5.0, -0.02, 0.0])
    mask = mad_outlier_mask(residuals)
    assert mask.tolist() == [False, False, False, False, True, False, False]


def test_mad_outlier_mask_zero_mad_returns_zeros() -> None:
    residuals = np.zeros(10)
    mask = mad_outlier_mask(residuals)
    assert mask.dtype == bool
    assert not mask.any()


def test_monotonic_fraction_perfectly_increasing() -> None:
    assert monotonic_fraction(np.arange(10.0), 1.0) == 1.0


def test_monotonic_fraction_zero_slope_returns_nan() -> None:
    assert np.isnan(monotonic_fraction(np.arange(10.0), 0.0))


def test_monotonic_fraction_too_few_points_returns_nan() -> None:
    assert np.isnan(monotonic_fraction(np.array([1.0, 2.0]), 1.0))


# ---------------------------------------------------------------------------
# identify_cycles
# ---------------------------------------------------------------------------


def test_identify_cycles_groups_by_gap() -> None:
    """Source ground truth captured 2026-04-17 with original module."""
    times = pd.to_datetime(
        [
            "2024-01-01 00:00:00",
            "2024-01-01 00:00:30",
            "2024-01-01 00:01:00",
            "2024-01-01 00:10:00",  # >5 min gap → new cycle
            "2024-01-01 00:10:30",
            "2024-01-01 00:20:00",  # >5 min gap → another new cycle
        ]
    )
    df = pd.DataFrame({"TIMESTAMP": times, "CO2": [400.0, 401, 402, 410, 411, 420]})
    out = identify_cycles(df)
    assert out["cycle_id"].tolist() == [1, 1, 1, 2, 2, 3]
    assert out["new_cycle"].tolist() == [True, False, False, True, False, True]
    assert "delta_t_sec" in out.columns


def test_identify_cycles_respects_custom_gap() -> None:
    times = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 00:00:10", "2024-01-01 00:00:25"])
    df = pd.DataFrame({"TIMESTAMP": times, "CO2": [400.0, 401, 402]})
    # gap=5s breaks all three into separate cycles
    out = identify_cycles(df, gap_sec=5)
    assert out["cycle_id"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# detect_bimodal_cycle
# ---------------------------------------------------------------------------


def test_detect_bimodal_cycle_unimodal_input() -> None:
    rng = np.random.default_rng(0)
    v = rng.normal(400, 5, 50)
    out = detect_bimodal_cycle(v)
    assert out["is_bimodal"] is False
    assert out["gap_ppm"] == 0.0
    assert np.isnan(out["lower_mean"])
    assert np.isnan(out["upper_mean"])


def test_detect_bimodal_cycle_clear_two_clusters() -> None:
    """Two clusters at 400 and 500 ppm → ~90 ppm empty gap (well past 20 ppm cutoff)."""
    v = np.concatenate([np.full(20, 400.0), np.full(20, 500.0)])
    out = detect_bimodal_cycle(v)
    assert out["is_bimodal"] is True
    assert out["gap_ppm"] == pytest.approx(90.0, abs=1e-12)
    assert out["lower_mean"] == pytest.approx(400.0, abs=1e-12)
    assert out["upper_mean"] == pytest.approx(500.0, abs=1e-12)


def test_detect_bimodal_cycle_too_few_points() -> None:
    out = detect_bimodal_cycle(np.array([400.0, 401.0]))
    assert out["is_bimodal"] is False


def test_detect_bimodal_cycle_handles_nans() -> None:
    """NaNs are stripped before histogramming."""
    v = np.concatenate([np.full(20, 400.0), np.full(20, 500.0), np.array([np.nan, np.nan])])
    out = detect_bimodal_cycle(v)
    assert out["is_bimodal"] is True


# ---------------------------------------------------------------------------
# score_cycle
# ---------------------------------------------------------------------------


_GOOD_ROW = {
    "n_points_used": 100,
    "duration_sec": 120,
    "r2": 0.95,
    "nrmse": 0.05,
    "snr": 20.0,
    "monotonicity": 0.95,
    "outlier_frac": 0.01,
    "delta_aicc": -2.0,
    "slope_diff_pct": 0.10,
    "flux_slope": -0.05,
    "co2_range": 50.0,
    "flux_absolute": -10.0,
}


def test_score_cycle_clean_row_passes_with_no_reasons() -> None:
    model_qc, combined, reasons = score_cycle(_GOOD_ROW, raw_flag=0, thresholds=QC_THRESHOLDS)
    assert model_qc == 0
    assert combined == 0
    assert reasons == ""


def test_score_cycle_nighttime_path_uses_relaxed_thresholds() -> None:
    """A clean row scored as nighttime should still pass."""
    model_qc, combined, reasons = score_cycle(
        _GOOD_ROW,
        raw_flag=0,
        thresholds=QC_THRESHOLDS,
        is_nighttime=True,
        nighttime_thresholds=NIGHTTIME_QC_THRESHOLDS,
    )
    assert model_qc == 0
    assert combined == 0
    assert reasons == ""


def test_score_cycle_bad_row_yields_expected_reasons() -> None:
    """Captured ground-truth string from the source module."""
    bad = dict(
        _GOOD_ROW,
        r2=0.40,
        nrmse=0.30,
        snr=2.0,
        monotonicity=0.20,
        outlier_frac=0.30,
    )
    model_qc, combined, reasons = score_cycle(bad, raw_flag=2, thresholds=QC_THRESHOLDS)
    assert model_qc == 2
    assert combined == 2
    assert reasons == "low_r2;high_nrmse;low_snr;non_monotonic;many_outliers;sensor_flag_2"


def test_score_cycle_b_count_demotion() -> None:
    """Three B-tier hits (>= b_count_C=3) should escalate to C even if no single
    metric is C-tier on its own."""
    moderate = dict(
        _GOOD_ROW,
        r2=0.85,  # → B (r2_moderate)
        nrmse=0.15,  # → B (nrmse_moderate)
        snr=5.0,  # → B (snr_moderate)
    )
    model_qc, _combined, reasons = score_cycle(moderate, raw_flag=0, thresholds=QC_THRESHOLDS)
    assert model_qc == 2
    assert "many_moderate_issues:3" in reasons


def test_score_cycle_hard_limits_extreme_slope() -> None:
    extreme = dict(_GOOD_ROW, flux_slope=20.0)
    model_qc, _combined, reasons = score_cycle(
        extreme, raw_flag=0, thresholds=QC_THRESHOLDS, enforce_hard_limits=True
    )
    assert model_qc == 2
    assert "extreme_slope" in reasons


def test_score_cycle_raw_flag_clamped_to_two() -> None:
    """Raw flags > 2 are clamped to 2."""
    _, combined, reasons = score_cycle(_GOOD_ROW, raw_flag=99, thresholds=QC_THRESHOLDS)
    assert combined == 2
    assert "sensor_flag_2" in reasons


# ---------------------------------------------------------------------------
# compute_temporal_coherence
# ---------------------------------------------------------------------------


def test_compute_temporal_coherence_smooth_series_no_flags() -> None:
    """A monotonically varying series without any cliffs should not be flagged."""
    n = 24
    ts = pd.date_range("2024-01-01 06:00", periods=n, freq="30min")
    flux_df = pd.DataFrame(
        {
            "flux_datetime": ts,
            "flux_slope": np.linspace(-0.1, -0.05, n),
            "flux_qc": [0] * n,
        }
    )
    out = compute_temporal_coherence(flux_df)
    assert out["temporal_coherence_flag"].sum() == 0
    assert out["hourly_cv_flag"].sum() == 0


def test_compute_temporal_coherence_flags_jump() -> None:
    """A 10x jump in same-sign slope outside transition hours should flag the second cycle."""
    ts = pd.to_datetime(
        [
            "2024-01-01 10:00:00",
            "2024-01-01 10:30:00",
        ]
    )
    flux_df = pd.DataFrame(
        {
            "flux_datetime": ts,
            "flux_slope": [-0.05, -0.50],  # ratio = 10 > max_slope_ratio default 3
            "flux_qc": [0, 0],
        }
    )
    out = compute_temporal_coherence(flux_df)
    # First row has no prev → 0; second should be flagged
    assert out["temporal_coherence_flag"].iloc[0] == 0
    assert out["temporal_coherence_flag"].iloc[1] == 1


def test_compute_temporal_coherence_keeps_no_underscored_cols() -> None:
    ts = pd.date_range("2024-01-01 06:00", periods=4, freq="30min")
    flux_df = pd.DataFrame(
        {
            "flux_datetime": ts,
            "flux_slope": [-0.05] * 4,
            "flux_qc": [0] * 4,
        }
    )
    out = compute_temporal_coherence(flux_df)
    leaked = [c for c in out.columns if c.startswith("_")]
    assert leaked == []


# ---------------------------------------------------------------------------
# score_day_quality / compute_day_scores
# ---------------------------------------------------------------------------


def _synthetic_day(chamber: str = "C1", flux_qc: int = 0, slope: float = -0.05) -> pd.DataFrame:
    hours = np.arange(7, 19)
    ts = [pd.Timestamp(2024, 1, 1, h, m) for h in hours for m in (0, 30)]
    return pd.DataFrame(
        {
            "flux_datetime": ts,
            "flux_slope": [slope] * len(ts),
            "r2": [0.95] * len(ts),
            "nrmse": [0.05] * len(ts),
            "flux_qc": [flux_qc] * len(ts),
            "Source_Chamber": [chamber] * len(ts),
        }
    )


def test_score_day_quality_synthetic_clean_day() -> None:
    """Captured ground truth: 12 hours, perfect r²=0.95, nrmse=0.05.

    Component scores were captured from the source module on the same
    synthetic input (see _synthetic_day above).
    """
    day = _synthetic_day()
    out = score_day_quality(day)
    assert out is not None
    assert out["n_cycles_daytime"] == 24
    assert out["n_hours_covered"] == 12
    assert out["coverage_score"] == pytest.approx(1.0, abs=1e-12)
    assert out["quality_score"] == pytest.approx(0.95, abs=1e-12)
    assert out["frac_negative"] == pytest.approx(1.0, abs=1e-12)
    # Constant slope across hours → idxmin is hour 7 → shape_score = 0.5
    assert out["shape_score"] == pytest.approx(0.5, abs=1e-12)
    assert out["nrmse_score"] == pytest.approx(0.75, abs=1e-12)
    assert out["day_score"] == pytest.approx(0.91, abs=1e-12)


def test_score_day_quality_too_few_cycles_returns_none() -> None:
    df = pd.DataFrame(
        {
            "flux_datetime": pd.to_datetime(["2024-01-01 10:00", "2024-01-01 11:00"]),
            "flux_slope": [-0.05, -0.05],
            "r2": [0.9, 0.9],
            "nrmse": [0.05, 0.05],
        }
    )
    assert score_day_quality(df) is None


def test_compute_day_scores_end_to_end() -> None:
    day = _synthetic_day()
    out = compute_day_scores(day)
    # Day score should be the same value as the per-day score, broadcast to every row.
    assert out["day_score"].iloc[0] == pytest.approx(0.91, abs=1e-12)
    assert (out["day_score"] == out["day_score"].iloc[0]).all()
    # Required columns present
    for col in ("day_score", "n_cycles_daytime", "n_hours_covered"):
        assert col in out.columns
    # Helper underscore column should be dropped
    assert "_date_only" not in out.columns


def test_compute_day_scores_handles_no_eligible_groups() -> None:
    """All rows fail the QC<=1 filter → fallback to zero-filled outputs."""
    day = _synthetic_day(flux_qc=2)
    out = compute_day_scores(day)
    assert (out["day_score"] == 0.0).all()
    assert (out["n_cycles_daytime"] == 0).all()
    assert (out["n_hours_covered"] == 0).all()


# ---------------------------------------------------------------------------
# compute_ml_anomaly_flags  (smoke test, sklearn-gated)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_SKLEARN, reason="requires [ml] extra (scikit-learn)")
def test_compute_ml_anomaly_flags_smoke() -> None:
    """Smoke: function runs end-to-end on a synthetic cycle frame and adds
    the three documented columns."""
    from palmwtc.flux.cycles import compute_ml_anomaly_flags

    rng = np.random.default_rng(42)
    n = 200
    df = pd.DataFrame(
        {
            "r2": rng.uniform(0.7, 1.0, n),
            "nrmse": rng.uniform(0.0, 0.2, n),
            "snr": rng.uniform(5.0, 30.0, n),
            "monotonicity": rng.uniform(0.5, 1.0, n),
            "outlier_frac": rng.uniform(0.0, 0.1, n),
            "slope_diff_pct": rng.uniform(0.0, 0.4, n),
            "delta_aicc": rng.uniform(-10.0, 0.0, n),
            "co2_range": rng.uniform(20.0, 200.0, n),
            "h2o_r2": rng.uniform(0.7, 1.0, n),
            "h2o_snr": rng.uniform(5.0, 30.0, n),
            "h2o_outlier_frac": rng.uniform(0.0, 0.1, n),
            "n_points_used": rng.integers(50, 200, n),
            "n_points_total": rng.integers(200, 250, n),
            "flux_qc": [0] * n,
        }
    )
    out = compute_ml_anomaly_flags(df, random_state=42)
    assert "ml_if_score" in out.columns
    assert "ml_mcd_dist" in out.columns
    assert "ml_anomaly_flag" in out.columns
    # Output flag is binary
    assert set(out["ml_anomaly_flag"].unique()).issubset({0, 1})
    # Helper temp column scrubbed
    assert "_completeness_ratio" not in out.columns


@pytest.mark.skipif(not _HAS_SKLEARN, reason="requires [ml] extra (scikit-learn)")
def test_compute_ml_anomaly_flags_rejects_bad_combination_mode() -> None:
    from palmwtc.flux.cycles import compute_ml_anomaly_flags

    rng = np.random.default_rng(0)
    n = 100
    df = pd.DataFrame(
        {
            "r2": rng.uniform(0.7, 1.0, n),
            "nrmse": rng.uniform(0.0, 0.2, n),
            "snr": rng.uniform(5.0, 30.0, n),
            "monotonicity": rng.uniform(0.5, 1.0, n),
            "outlier_frac": rng.uniform(0.0, 0.1, n),
            "slope_diff_pct": rng.uniform(0.0, 0.4, n),
            "delta_aicc": rng.uniform(-10.0, 0.0, n),
            "co2_range": rng.uniform(20.0, 200.0, n),
            "h2o_r2": rng.uniform(0.7, 1.0, n),
            "h2o_snr": rng.uniform(5.0, 30.0, n),
            "h2o_outlier_frac": rng.uniform(0.0, 0.1, n),
            "flux_qc": [0] * n,
        }
    )
    with pytest.raises(ValueError, match="combination_mode"):
        compute_ml_anomaly_flags(df, combination_mode="XOR")


# ---------------------------------------------------------------------------
# _evaluate_cycle_wrapper signature variants
# ---------------------------------------------------------------------------


def test_evaluate_cycle_wrapper_three_arg_form() -> None:
    """The 3-tuple form should call evaluate_cycle without options."""
    from palmwtc.flux.cycles import _evaluate_cycle_wrapper

    # Build a tiny cycle with too-few points so evaluate_cycle returns None
    # quickly — we're only testing the wrapper unpacks args without crashing.
    df = pd.DataFrame(
        {
            "TIMESTAMP": pd.to_datetime(["2024-01-01 00:00:00"]),
            "CO2": [400.0],
            "cycle_id": [1],
        }
    )
    result = _evaluate_cycle_wrapper((1, df, "C1"))
    assert result is None


def test_evaluate_cycle_wrapper_four_arg_form() -> None:
    """The 4-tuple form should accept an options dict."""
    from palmwtc.flux.cycles import _evaluate_cycle_wrapper

    df = pd.DataFrame(
        {
            "TIMESTAMP": pd.to_datetime(["2024-01-01 00:00:00"]),
            "CO2": [400.0],
            "cycle_id": [1],
        }
    )
    result = _evaluate_cycle_wrapper((1, df, "C1", {"min_points": 8}))
    assert result is None
