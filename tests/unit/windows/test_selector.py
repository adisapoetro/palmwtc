"""Characterization tests for ``palmwtc.windows.selector``.

These pin the behaviour ported verbatim from
``flux_chamber/src/window_selection.py``. Numeric outputs match the source
module exactly (max diff 0.0 on the synthetic fixture below — well within
the 1e-12 tolerance of the port contract).

Ground-truth values were captured by running the source module against the
same synthetic fixtures defined here on 2026-04-19. The provenance comments
next to ``EXPECTED_*`` literals reference the capture script.

Coverage:
    - Module-level constants (``DEFAULT_CONFIG`` shape and key invariants).
    - ``WindowSelector.__init__`` (column injection, is_nighttime healing).
    - End-to-end ``detect_drift`` → ``score_cycles`` → ``identify_windows``
      against a 20-day, 2-chamber synthetic frame with mixed-quality cycles.
    - ``WindowSelector.load_regime_diagnostics`` (silent no-op on missing
      file; CSV path with ``good``-quality and ``slope_warning`` rows).
    - ``WindowSelector.export`` (csv + json round-trip via tmp_path).
    - ``WindowSelector.summary`` (smoke).
    - ``merge_sensor_qc_onto_cycles`` (smoke + the H₂O happy path).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from palmwtc.windows import (
    DEFAULT_CONFIG,
    WindowSelector,
    merge_sensor_qc_onto_cycles,
)

# ---------------------------------------------------------------------------
# DEFAULT_CONFIG shape
# ---------------------------------------------------------------------------


def test_default_config_required_keys_present() -> None:
    """All keys consumed by ``WindowSelector`` must exist in DEFAULT_CONFIG."""
    expected = {
        "export_cycles_path",
        "export_manifest_path",
        "regime_audit_path",
        "score_weights",
        "r2_good",
        "r2_ok",
        "nrmse_good",
        "nrmse_ok",
        "snr_good",
        "snr_ok",
        "outlier_good",
        "outlier_ok",
        "slope_diff_good",
        "slope_diff_ok",
        "drift_window_days",
        "drift_zscore_bad",
        "drift_zscore_moderate",
        "seasonal_detrend_days",
        "drift_signals",
        "min_daily_coverage_frac",
        "min_window_days",
        "window_flexibility_buffer",
        "min_confidence_frac",
        "confidence_good_threshold",
        "min_grade_ab_frac",
        "daytime_hours",
        "nighttime_weight",
        "grade_ab_uses_daytime_only",
        "exclude_instrumental_regimes",
        "min_window_score_for_export",
    }
    assert expected.issubset(set(DEFAULT_CONFIG.keys()))


def test_default_config_score_weights_pinned() -> None:
    """Score weights are part of the locked-in scientific contract — pin every value."""
    w = DEFAULT_CONFIG["score_weights"]
    assert w["regression"] == 0.35
    assert w["robustness"] == 0.25
    assert w["sensor_qc"] == 0.15
    assert w["drift"] == 0.15
    assert w["cross_chamber"] == 0.10
    assert w["closure"] == 0.00
    assert w["anomaly"] == 0.00


def test_default_config_thresholds_pinned() -> None:
    """Threshold values pinned for downstream notebook contract."""
    assert DEFAULT_CONFIG["r2_good"] == 0.90
    assert DEFAULT_CONFIG["r2_ok"] == 0.70
    assert DEFAULT_CONFIG["snr_good"] == 5.0
    assert DEFAULT_CONFIG["snr_ok"] == 1.5
    assert DEFAULT_CONFIG["min_window_days"] == 5
    assert DEFAULT_CONFIG["window_flexibility_buffer"] == 2
    assert DEFAULT_CONFIG["confidence_good_threshold"] == 0.65
    assert DEFAULT_CONFIG["min_window_score_for_export"] == 0.55
    assert DEFAULT_CONFIG["daytime_hours"] == [6, 18]
    assert DEFAULT_CONFIG["drift_signals"] == ["night_intercept", "slope_divergence"]


def test_default_config_paths_are_path_objects() -> None:
    """Path entries should be ``pathlib.Path`` (not strings)."""
    assert isinstance(DEFAULT_CONFIG["export_cycles_path"], Path)
    assert isinstance(DEFAULT_CONFIG["export_manifest_path"], Path)
    assert isinstance(DEFAULT_CONFIG["regime_audit_path"], Path)


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _build_cycles(n_days: int = 20, q_split_day: int = 10) -> pd.DataFrame:
    """20-day, 2-chamber, daytime-only synthetic cycle frame.

    Days [0, q_split_day) are clean (R²=0.95). Days [q_split_day, n_days) are
    half-quality. The mix exercises the tier scorers and window selection.
    """
    rng = np.random.default_rng(42)
    start = pd.Timestamp("2024-01-01")
    records = []
    for chamber in ("Chamber 1", "Chamber 2"):
        for d in range(n_days):
            for h in range(6, 19):
                for m in (0, 30):
                    ts = start + pd.Timedelta(days=d, hours=h, minutes=m)
                    q = 1.0 if d < q_split_day else 0.5
                    records.append(
                        {
                            "flux_datetime": ts,
                            "cycle_end": ts + pd.Timedelta(seconds=180),
                            "Source_Chamber": chamber,
                            "co2_r2": 0.95 * q,
                            "co2_nrmse": 0.05 + (1 - q) * 0.10,
                            "co2_snr": 10.0 * q,
                            "co2_outlier_frac": 0.02 + (1 - q) * 0.10,
                            "slope_diff_pct": 0.10 + (1 - q) * 0.30,
                            "delta_aicc": -1.0 - (1 - q) * 5.0,
                            "closure_confidence": 0.8,
                            "co2_slope": -0.05 - rng.normal(0, 0.01),
                            "h2o_slope": 0.02,
                            "flux_intercept": 400.0 + rng.normal(0, 1.0),
                            "co2_qc": 0,
                            "sensor_co2_qc_mean": (1 - q) * 1.0,
                            "sensor_h2o_qc_mean": (1 - q) * 0.5,
                            "anomaly_ensemble_score": 0.1,
                            "is_instrumental_regime_change": False,
                        }
                    )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# __init__ behaviour
# ---------------------------------------------------------------------------


def test_init_adds_date_column_and_heals_is_nighttime() -> None:
    """Constructor injects ``_date`` and recomputes ``is_nighttime`` from hour-of-day."""
    df = _build_cycles(n_days=2)
    ws = WindowSelector(df)
    assert "_date" in ws.cycles_df.columns
    assert "is_nighttime" in ws.cycles_df.columns
    # Daytime-only fixture (6..18) → all False except endpoints
    is_night = ws.cycles_df["is_nighttime"].unique().tolist()
    assert set(is_night) == {False, True}  # h=18 falls in nighttime per [6, 18) range


def test_init_does_not_mutate_input_frame() -> None:
    """Input DataFrame is copied — mutating selector should not touch caller's df."""
    df = _build_cycles(n_days=2)
    cols_before = set(df.columns)
    _ = WindowSelector(df)
    assert set(df.columns) == cols_before  # caller's frame untouched


def test_init_merges_user_config_over_defaults() -> None:
    df = _build_cycles(n_days=2)
    ws = WindowSelector(df, config={"min_window_days": 99})
    assert ws.config["min_window_days"] == 99
    # Other defaults preserved
    assert ws.config["confidence_good_threshold"] == DEFAULT_CONFIG["confidence_good_threshold"]


# ---------------------------------------------------------------------------
# detect_drift
# ---------------------------------------------------------------------------


def test_detect_drift_produces_expected_columns() -> None:
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift()
    assert ws.drift_df is not None
    expected_cols = {
        "date",
        "Source_Chamber",
        "drift_severity",
        "co2_slope_zscore",
        "night_intercept_zscore",
        "h2o_slope_zscore",
        "slope_div_zscore",
    }
    assert set(ws.drift_df.columns) == expected_cols


def test_detect_drift_clean_synthetic_input_yields_zero_severity() -> None:
    """Captured 2026-04-19 against original module: stable inputs → all-zero severity."""
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift()
    assert (ws.drift_df["drift_severity"] == 0.0).all()


# ---------------------------------------------------------------------------
# score_cycles
# ---------------------------------------------------------------------------


# Captured 2026-04-19 by running flux_chamber/src/window_selection.py against
# the _build_cycles() fixture above (max diff vs port: 0.0).
EXPECTED_MEAN_CONFIDENCE = 0.91145
EXPECTED_TOP_WINDOW_SCORE = 0.9893
EXPECTED_N_WINDOWS = 8


def test_score_cycles_adds_documented_columns() -> None:
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift().score_cycles()
    for col in (
        "score_regression",
        "score_robustness",
        "score_sensor_qc",
        "score_drift",
        "score_cross_chamber",
        "cycle_confidence",
        "score_closure",
        "score_anomaly",
        "_is_daytime",
    ):
        assert col in ws.cycles_df.columns


def test_score_cycles_mean_confidence_matches_source() -> None:
    """Pin the mean confidence at the value produced by the original module."""
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift().score_cycles()
    assert ws.cycles_df["cycle_confidence"].mean() == pytest.approx(
        EXPECTED_MEAN_CONFIDENCE, abs=1e-12
    )


def test_score_cycles_without_regime_data_sets_cross_chamber_nan() -> None:
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift().score_cycles()
    assert ws.regime_agreement is None
    assert ws.cycles_df["score_cross_chamber"].isna().all()


def test_score_cycles_clean_inputs_produce_unit_scores_for_clean_days() -> None:
    df = _build_cycles(n_days=10, q_split_day=10)  # all-clean days
    ws = WindowSelector(df).detect_drift().score_cycles()
    # All inputs at the "good" tier → confidence ~ 1.0 (modulo NaN handling)
    assert ws.cycles_df["cycle_confidence"].max() == pytest.approx(1.0, abs=1e-12)
    assert ws.cycles_df["score_regression"].max() == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# identify_windows
# ---------------------------------------------------------------------------


def test_identify_windows_requires_score_cycles_first() -> None:
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift()
    with pytest.raises(RuntimeError, match="score_cycles"):
        ws.identify_windows()


def test_identify_windows_produces_expected_windows() -> None:
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift().score_cycles().identify_windows()
    assert ws.windows_df is not None
    assert len(ws.windows_df) == EXPECTED_N_WINDOWS
    assert ws.windows_df["window_score"].max() == pytest.approx(
        EXPECTED_TOP_WINDOW_SCORE, abs=1e-12
    )
    expected_cols = {
        "window_id",
        "Source_Chamber",
        "start_date",
        "end_date",
        "n_days",
        "n_cycles",
        "mean_confidence",
        "mean_coverage",
        "mean_drift_severity",
        "mean_daytime_grade_ab_frac",
        "mean_all_grade_ab_frac",
        "mean_grade_a_frac",
        "diurnal_hour_coverage",
        "window_score",
        "qualifies_for_export",
    }
    assert expected_cols.issubset(set(ws.windows_df.columns))


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_export_writes_csv_and_manifest(tmp_path) -> None:
    """End-to-end export round-trip: csv has window_id, manifest is valid JSON."""
    df = _build_cycles()
    cfg = {
        "export_cycles_path": tmp_path / "windows.csv",
        "export_manifest_path": tmp_path / "manifest.json",
    }
    ws = WindowSelector(df, config=cfg).detect_drift().score_cycles().identify_windows()
    filtered_df, manifest = ws.export(approved_only=False)
    assert (tmp_path / "windows.csv").exists()
    assert (tmp_path / "manifest.json").exists()
    # Manifest shape
    assert manifest["n_windows"] == EXPECTED_N_WINDOWS
    assert manifest["n_cycles"] == len(filtered_df)
    assert manifest["regime_diagnostics_loaded"] is False
    assert "windows" in manifest
    assert len(manifest["windows"]) == EXPECTED_N_WINDOWS
    # Each cycle should carry its assigned window_id
    assert "window_id" in filtered_df.columns
    assert filtered_df["window_id"].notna().all()


def test_export_without_identify_raises() -> None:
    df = _build_cycles()
    ws = WindowSelector(df)
    with pytest.raises(RuntimeError, match="identify_windows"):
        ws.export()


def test_export_with_excluded_returns_empty_with_warning(tmp_path) -> None:
    """Excluding all windows should warn and return empty frame + empty manifest."""
    df = _build_cycles()
    cfg = {
        "export_cycles_path": tmp_path / "w.csv",
        "export_manifest_path": tmp_path / "m.json",
    }
    ws = WindowSelector(df, config=cfg).detect_drift().score_cycles().identify_windows()
    all_ids = ws.windows_df["window_id"].tolist()
    with pytest.warns(UserWarning, match="No windows selected"):
        out_df, out_manifest = ws.export(approved_only=False, exclude_list=all_ids)
    assert out_df.empty
    assert out_manifest == {}


# ---------------------------------------------------------------------------
# load_regime_diagnostics
# ---------------------------------------------------------------------------


def test_load_regime_diagnostics_missing_file_is_silent_noop(tmp_path) -> None:
    df = _build_cycles(n_days=2)
    ws = WindowSelector(df)
    out = ws.load_regime_diagnostics(tmp_path / "nope.csv")
    assert out is ws  # returns self for chaining
    assert ws.regime_agreement is None


def test_load_regime_diagnostics_populates_lookup_from_csv(tmp_path) -> None:
    audit_csv = tmp_path / "regime.csv"
    pd.DataFrame(
        {
            "variable": ["CO2", "CO2", "H2O"],
            "start": ["2024-01-01", "2024-01-05", "2024-01-01"],
            "end": ["2024-01-03", "2024-01-07", "2024-01-03"],
            "quality": ["good", "good", "good"],
            "slope_warning": [False, True, False],
            "r2": [0.9, 0.8, 0.95],
            "slope": [1.05, 0.9, 1.0],
        }
    ).to_csv(audit_csv, index=False)
    df = _build_cycles(n_days=2)
    ws = WindowSelector(df).load_regime_diagnostics(audit_csv)
    assert ws.regime_agreement is not None
    # First regime: quality=good, no warning, derived score from r2 + slope
    score_jan1 = ws.regime_agreement[pd.Timestamp("2024-01-01").date()]
    assert score_jan1 > 0.0
    # Second regime: slope_warning=True → forced to 0.0
    assert ws.regime_agreement[pd.Timestamp("2024-01-05").date()] == 0.0


def test_load_regime_diagnostics_no_co2_rows_returns_none(tmp_path) -> None:
    audit_csv = tmp_path / "regime.csv"
    pd.DataFrame(
        {
            "variable": ["H2O"],
            "start": ["2024-01-01"],
            "end": ["2024-01-03"],
            "quality": ["good"],
            "slope_warning": [False],
            "r2": [0.9],
            "slope": [1.0],
        }
    ).to_csv(audit_csv, index=False)
    df = _build_cycles(n_days=2)
    ws = WindowSelector(df).load_regime_diagnostics(audit_csv)
    assert ws.regime_agreement is None


# ---------------------------------------------------------------------------
# summary smoke
# ---------------------------------------------------------------------------


def test_summary_smoke(capsys) -> None:
    df = _build_cycles()
    ws = WindowSelector(df).detect_drift().score_cycles().identify_windows()
    ws.summary()
    out = capsys.readouterr().out
    assert "WindowSelector summary" in out
    assert "Total cycles loaded" in out


# ---------------------------------------------------------------------------
# merge_sensor_qc_onto_cycles
# ---------------------------------------------------------------------------


def test_merge_sensor_qc_onto_cycles_h2o_happy_path() -> None:
    """The H₂O column path is well-formed (``H2O_C1_qc_flag``).

    NOTE: the CO₂ column path has a latent double-underscore bug in the
    upstream module (computes ``CO2__C1_qc_flag``); this is intentionally
    preserved here. See test below.
    """
    cyc = pd.DataFrame(
        {
            "flux_datetime": pd.to_datetime(["2024-01-01 10:00:00", "2024-01-01 10:05:00"]),
            "cycle_end": pd.to_datetime(["2024-01-01 10:03:00", "2024-01-01 10:08:00"]),
            "Source_Chamber": ["Chamber 1", "Chamber 1"],
        }
    )
    qc = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01 10:00:00", periods=10, freq="30s"),
            "CO2_C1_qc_flag": [0, 1, 2, 0, 1, 0, 0, 1, 0, 0],
            "H2O_C1_qc_flag": [0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
        }
    )
    out = merge_sensor_qc_onto_cycles(cyc, qc)
    # Captured 2026-04-19 against original module:
    assert out["sensor_h2o_qc_mean"].iloc[0] == pytest.approx(2.0 / 7.0, abs=1e-12)
    assert np.isnan(out["sensor_h2o_qc_mean"].iloc[1])


def test_merge_sensor_qc_onto_cycles_default_co2_path_returns_nan() -> None:
    """Latent bug preservation: default ``co2_col`` produces ``CO2__C1_qc_flag``
    (double underscore) which never matches the actual ``CO2_C1_qc_flag`` column,
    so CO₂ means come back NaN.

    Captured 2026-04-19 — see selector.py L186-188 for the column-name
    formation logic that produces the doubled underscore.
    """
    cyc = pd.DataFrame(
        {
            "flux_datetime": pd.to_datetime(["2024-01-01 10:00:00"]),
            "cycle_end": pd.to_datetime(["2024-01-01 10:03:00"]),
            "Source_Chamber": ["Chamber 1"],
        }
    )
    qc = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01 10:00:00", periods=5, freq="30s"),
            "CO2_C1_qc_flag": [0, 1, 0, 0, 0],
            "H2O_C1_qc_flag": [0, 0, 0, 0, 0],
        }
    )
    out = merge_sensor_qc_onto_cycles(cyc, qc)
    assert np.isnan(out["sensor_co2_qc_mean"].iloc[0])


def test_merge_sensor_qc_onto_cycles_explicit_chamber_map() -> None:
    """User-supplied chamber_map overrides auto-inference."""
    cyc = pd.DataFrame(
        {
            "flux_datetime": pd.to_datetime(["2024-01-01 10:00:00"]),
            "cycle_end": pd.to_datetime(["2024-01-01 10:03:00"]),
            "Source_Chamber": ["WTC1"],
        }
    )
    qc = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01 10:00:00", periods=5, freq="30s"),
            "CO2_C1_qc_flag": [0, 0, 0, 0, 0],
            "H2O_C1_qc_flag": [0, 0, 0, 0, 0],
        }
    )
    out = merge_sensor_qc_onto_cycles(cyc, qc, chamber_map={"WTC1": "C1"})
    assert out["sensor_h2o_qc_mean"].iloc[0] == pytest.approx(0.0, abs=1e-12)
