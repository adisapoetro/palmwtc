# ruff: noqa: F841, RUF002, RUF003, SIM108
"""
window_selection (palmwtc port)
================================
Multi-criteria high-confidence window selector for carbon flux calibration data.

Ported verbatim from ``flux_chamber/src/window_selection.py``.

Consumed by:
  - notebooks/031_High_Confidence_Window_Selection.ipynb   (original, kept for reference)
  - notebooks/032_Window_Selection_Physically_Grounded.ipynb (scientifically corrected v2)
  - notebooks/040_Core_Julia_Calibration_XPalm_Flux.ipynb  (can import WindowSelector
                                                             to load an existing manifest)

Pipeline position: after 030 (flux cycles) and before 040 (XPalm calibration).

Funnel (audited 2026-04-15 against current exports):
  Input      01_chamber_cycles.csv                 61,161 cycles (37,847 Ch1 + 23,314 Ch2)
    co2 QC label A: 12,114 / B: 36,989 / C: 12,058
    h2o QC label A: 10,831 / B:  8,905 / C: 39,642 / missing: 1,783
    trainable_co2:           31,344
    trainable_co2_ml:        30,534
    trainable_co2_advanced:  28,597
  Output     032_calibration_windows.csv           23,034 cycles (17,247 Ch1 + 5,787 Ch2)
    n_windows in manifest: 49 (excluded_windows: 0)
Retention from input → windows: 37.7 %. Track A (chamber-LIBZ) calibration should
cite these numbers rather than stale '~22,618 window cycles' figures.

Usage
-----
    from palmwtc.windows import WindowSelector, DEFAULT_CONFIG

    ws = WindowSelector(cycles_df, config=DEFAULT_CONFIG)
    ws.detect_drift()
    ws.score_cycles()
    ws.identify_windows()
    filtered_df, manifest = ws.export()
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats  # noqa: F401  — preserved from upstream module surface

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    # --- I/O paths (notebook should override these) ---
    "export_cycles_path": Path("Data/digital_twin/032_calibration_windows.csv"),
    "export_manifest_path": Path("Data/digital_twin/032_calibration_window_manifest.json"),
    # --- Cross-chamber regime diagnostics (from 026_diag) ---
    # Path to the 026 regime audit CSV.  If the file does not exist,
    # the cross_chamber score defaults to neutral (no penalty).
    "regime_audit_path": Path("Data/Integrated_QC_Data/026_regime_audit.csv"),
    # --- Composite confidence scoring weights (must sum to 1.0) ---
    # Closure and anomaly are computed as diagnostic columns but carry zero weight:
    #   closure:  CO₂/H₂O stoichiometric ratio is a biological variable (RQ varies by substrate,
    #             WUE varies with VPD) — not a physical leakage indicator for tree-sized chambers.
    #   anomaly:  Statistical anomaly detectors (LOF, IForest, STL) flag physiological extremes
    #             (drought stress, cyclone recovery, rapid growth) that have high calibration value.
    "score_weights": {
        "regression": 0.35,  # r2, nrmse, snr, outlier_frac — 4 components (monotonicity removed)
        "robustness": 0.25,  # slope_diff_pct (OLS vs Theil-Sen), delta_aicc (curvature check)
        "sensor_qc": 0.15,  # merged CO2/H2O sensor QC flags (from 021 parquet)
        "drift": 0.15,  # seasonally detrended instrument drift z-score
        "cross_chamber": 0.10,  # cross-chamber agreement from 026 regime diagnostics
        "closure": 0.00,  # diagnostic only — biologically confounded (see above)
        "anomaly": 0.00,  # diagnostic only — cannot distinguish biology from noise (see above)
    },
    # --- Regression quality thresholds ---
    # SNR thresholds calibrated for large-headspace tree chambers: low-flux periods
    # (drought stress, pre-dawn) are physiologically valid and must not be excluded.
    # Monotonicity is NOT used: in a tree chamber under variable tropical irradiance
    # (sunflecks, cloud passages), CO₂ can transiently decrease mid-cycle due to burst
    # photosynthesis — this is real signal, not measurement error.
    "r2_good": 0.90,
    "r2_ok": 0.70,
    "nrmse_good": 0.10,
    "nrmse_ok": 0.20,
    "snr_good": 5.0,
    "snr_ok": 1.5,  # was 10.0 / 3.0 — adjusted for large chamber volumes
    "outlier_good": 0.05,
    "outlier_ok": 0.15,
    "slope_diff_good": 0.30,
    "slope_diff_ok": 0.60,
    # --- Drift detection (seasonally detrended) ---
    # Only instrument-specific signals are active by default.  co2_slope and h2o_slope are
    # removed from the default set because their 14-day z-scores conflate genuine seasonal /
    # phenological changes (leaf flush, bunch development, drought) with instrument drift.
    # Seasonal detrending: a seasonal_detrend_days-day rolling median is subtracted from each
    # signal before computing the short-term rolling z-score, isolating residual drift.
    "drift_window_days": 30,  # was 14 — longer window reduces weather-scale sensitivity
    "drift_zscore_bad": 2.5,
    "drift_zscore_moderate": 1.5,
    "seasonal_detrend_days": 90,  # long-term baseline subtracted before z-scoring
    "drift_signals": [
        "night_intercept",  # zero-point / calibration baseline shift (seasonally detrended)
        "slope_divergence",  # OLS vs Theil-Sen disagreement — instrument noise inflation
    ],
    # --- Window identification ---
    "min_daily_coverage_frac": 0.70,
    "min_window_days": 5,  # minimum qualifying days required within the span
    "window_flexibility_buffer": 2,  # allow up to this many gap days within a window
    # effective span = min_window_days + buffer (e.g. 7 days)
    "min_confidence_frac": 0.60,  # fraction of cycles per day with confidence >= threshold
    "confidence_good_threshold": 0.65,
    "min_grade_ab_frac": 0.60,  # informational only — NOT a qualifying gate.
    # Grade A/B already feeds into sensor_qc score; using it
    # again as a hard gate double-counts sensor QC and may
    # reject valid rapid-drawdown cycles flagged by ROC rules.
    "daytime_hours": [6, 18],  # [start_hour, end_hour) for _is_daytime flag
    # NOTE: is_nighttime column in CSV is broken (all True);
    # always derive from flux_datetime.dt.hour
    "nighttime_weight": 1.0,  # was 0.7 — nighttime cycles carry full weight.
    # Dark respiration is the only clean measurement of Ra
    # and Q10; penalising it degrades respiration calibration.
    "grade_ab_uses_daytime_only": True,  # kept for transparency output only
    "exclude_instrumental_regimes": True,
    # --- Window export ---
    "min_window_score_for_export": 0.55,
}


# ---------------------------------------------------------------------------
# Helper — vectorized interval join (cycle window ↔ high-freq QC parquet)
# ---------------------------------------------------------------------------


def merge_sensor_qc_onto_cycles(
    cycles_df: pd.DataFrame,
    qc_df: pd.DataFrame,
    co2_col: str = "CO2_qc_flag",
    h2o_col: str = "H2O_qc_flag",
    chamber_map: dict | None = None,
) -> pd.DataFrame:
    """Aggregate per-cycle mean sensor QC flags from the high-frequency QC parquet.

    Uses a vectorized interval approach via ``pd.merge_asof`` to avoid per-row
    iteration over 58 k cycles.  The result adds two columns to ``cycles_df``:

    * ``sensor_co2_qc_mean`` — mean CO₂ qc_flag across the cycle window  (0=clean, 2=bad)
    * ``sensor_h2o_qc_mean`` — mean H₂O qc_flag across the cycle window

    Parameters
    ----------
    cycles_df : pd.DataFrame
        Cycle-level data from notebook 030 (must have ``flux_datetime``,
        ``cycle_end``, and ``Source_Chamber``).
    qc_df : pd.DataFrame
        High-frequency sensor QC parquet (from notebooks 021/022).
        Must have a ``TIMESTAMP`` column plus chamber-specific flag columns.
        Column naming expected: ``CO2_C1_qc_flag``, ``CO2_C2_qc_flag``, etc.
        Pass a *pre-loaded* DataFrame — this function does not do I/O.
    co2_col, h2o_col : str
        Base column name stubs (without chamber suffix).
    chamber_map : dict or None
        Maps ``Source_Chamber`` values to the suffix used in ``qc_df``
        (e.g., ``{"Chamber 1": "C1", "Chamber 2": "C2"}``).
        If None, inferred automatically from the first unique chamber names.

    Returns
    -------
    pd.DataFrame
        Copy of ``cycles_df`` with ``sensor_co2_qc_mean`` and
        ``sensor_h2o_qc_mean`` appended.
    """
    if chamber_map is None:
        chambers = cycles_df["Source_Chamber"].dropna().unique()
        chamber_map = {}
        for ch in chambers:
            # Extract trailing digit(s) to form C1, C2, …
            digits = "".join(filter(str.isdigit, str(ch)))
            chamber_map[ch] = f"C{digits}" if digits else ch

    qc_sorted = qc_df.sort_values("TIMESTAMP").reset_index(drop=True)
    cycles_out = cycles_df.copy()
    cycles_out["sensor_co2_qc_mean"] = np.nan
    cycles_out["sensor_h2o_qc_mean"] = np.nan

    for chamber, suffix in chamber_map.items():
        co2_c = (
            f"{co2_col.replace('qc_flag', '')}_{suffix}_qc_flag"
            if "_qc_flag" in co2_col
            else f"CO2_{suffix}_qc_flag"
        )
        h2o_c = f"H2O_{suffix}_qc_flag"

        mask_cyc = cycles_out["Source_Chamber"] == chamber
        sub_cyc = cycles_out.loc[mask_cyc, ["flux_datetime", "cycle_end"]].copy()
        if sub_cyc.empty:
            continue

        # For each cycle: find parquet rows inside [flux_datetime, cycle_end]
        # Strategy: assign each QC row to the cycle whose flux_datetime is the
        # most recent start before that row's timestamp, then filter by cycle_end.
        qc_ts = qc_sorted["TIMESTAMP"].values
        co2_vals = qc_sorted[co2_c].values if co2_c in qc_sorted.columns else None
        h2o_vals = qc_sorted[h2o_c].values if h2o_c in qc_sorted.columns else None

        starts = sub_cyc["flux_datetime"].values.astype("datetime64[ns]")
        ends = sub_cyc["cycle_end"].values.astype("datetime64[ns]")

        # Vectorized: for each parquet timestamp, find which cycle interval it falls in
        # using searchsorted on cycle start times.
        idx_start = np.searchsorted(starts, qc_ts, side="right") - 1
        valid = (idx_start >= 0) & (idx_start < len(starts))

        co2_means = np.full(len(sub_cyc), np.nan)
        h2o_means = np.full(len(sub_cyc), np.nan)

        if valid.any():
            qc_ts_v = qc_ts[valid]
            idx_v = idx_start[valid]
            # Only keep rows where timestamp <= cycle_end
            within = qc_ts_v <= ends[idx_v]
            idx_final = idx_v[within]

            if co2_vals is not None:
                co2_arr = co2_vals[valid][within].astype(float)
                co2_means = _group_mean(idx_final, co2_arr, len(sub_cyc))
            if h2o_vals is not None:
                h2o_arr = h2o_vals[valid][within].astype(float)
                h2o_means = _group_mean(idx_final, h2o_arr, len(sub_cyc))

        cycles_out.loc[mask_cyc, "sensor_co2_qc_mean"] = co2_means
        cycles_out.loc[mask_cyc, "sensor_h2o_qc_mean"] = h2o_means

    return cycles_out


def _group_mean(indices: np.ndarray, values: np.ndarray, n: int) -> np.ndarray:
    """Compute per-group mean of *values* grouped by integer *indices* in [0, n)."""
    sums = np.zeros(n)
    counts = np.zeros(n, dtype=int)
    np.add.at(sums, indices, values)
    np.add.at(counts, indices, 1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        result = np.where(counts > 0, sums / counts, np.nan)
    return result


# ---------------------------------------------------------------------------
# WindowSelector
# ---------------------------------------------------------------------------


class WindowSelector:
    """Multi-criteria window selector for flux calibration data.

    Workflow (call in order)::

        ws = WindowSelector(cycles_df, config)
        ws.detect_drift()      # adds drift_df; required before score_cycles
        ws.score_cycles()      # adds cycle_confidence column to cycles_df
        ws.identify_windows()  # builds windows_df summary table
        df, manifest = ws.export()

    Attributes
    ----------
    cycles_df : pd.DataFrame
        Input + enriched cycle DataFrame (102+ cols).  Modified in-place by
        ``score_cycles`` (adds confidence columns).
    config : dict
        All tunable thresholds.  See ``DEFAULT_CONFIG`` for documented keys.
    drift_df : pd.DataFrame or None
        Per (date, chamber) drift summary — set by ``detect_drift``.
    windows_df : pd.DataFrame or None
        Window summary table — set by ``identify_windows``.
    approved_windows : dict
        ``{window_id: {"approved": bool, "notes": str}}`` — populated by
        the interactive inspector in notebook 031; persisted via ``export``.
    """

    def __init__(self, cycles_df: pd.DataFrame, config: dict | None = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.cycles_df = cycles_df.copy()
        self.cycles_df["flux_datetime"] = pd.to_datetime(
            self.cycles_df["flux_datetime"], errors="coerce"
        )
        if "cycle_end" in self.cycles_df.columns:
            self.cycles_df["cycle_end"] = pd.to_datetime(
                self.cycles_df["cycle_end"], errors="coerce"
            )
        self.cycles_df["_date"] = self.cycles_df["flux_datetime"].dt.date
        # Fix broken is_nighttime column: Global_Radiation is all-NaN in the pipeline,
        # causing the notebook 030 derivation (fillna(-1) < threshold) to be all True.
        # Recompute from hour-of-day so the exported CSV carries a correct value.
        _dt_start, _dt_end = self.config.get("daytime_hours", [6, 18])
        _hours = self.cycles_df["flux_datetime"].dt.hour
        self.cycles_df["is_nighttime"] = (_hours < _dt_start) | (_hours >= _dt_end)
        self.drift_df: pd.DataFrame | None = None
        self.regime_agreement: dict | None = None  # date → agreement_score (from 026)
        self.windows_df: pd.DataFrame | None = None
        self.approved_windows: dict = {}

    # ------------------------------------------------------------------
    # Cross-chamber regime diagnostics (from 026_diag)
    # ------------------------------------------------------------------

    def load_regime_diagnostics(self, path: Path | str | None = None) -> WindowSelector:
        """Load cross-chamber agreement scores from the 026 regime audit CSV.

        Each CO₂ regime is assigned an agreement score based on the inter-chamber
        regression (slope proximity to 1.0 and R²).  The score is stored as a
        per-date lookup in ``self.regime_agreement``.

        If the audit file does not exist (026 not run), this is a silent no-op
        and the cross_chamber component defaults to neutral in ``score_cycles``.

        Parameters
        ----------
        path : Path or str, optional
            Override for the audit CSV path.  Falls back to
            ``config["regime_audit_path"]``.

        Returns
        -------
        self
        """
        audit_path = Path(path or self.config.get("regime_audit_path", ""))
        if not audit_path.exists():
            self.regime_agreement = None
            return self

        audit = pd.read_csv(audit_path)
        co2 = audit[audit["variable"] == "CO2"].copy()
        if co2.empty:
            self.regime_agreement = None
            return self

        lookup: dict = {}
        for _, row in co2.iterrows():
            # Compute agreement score from slope + R²
            if row.get("quality") != "good" or row.get("slope_warning", False):
                score = 0.0
            elif "agreement_score" in co2.columns and pd.notna(row.get("agreement_score")):
                score = float(row["agreement_score"])
            else:
                r2 = float(row["r2"]) if pd.notna(row.get("r2")) else 0.0
                slope = float(row["slope"]) if pd.notna(row.get("slope")) else 1.0
                slope_prox = max(0.0, 1.0 - 2.0 * abs(slope - 1.0))
                score = 0.5 * max(0.0, r2) + 0.5 * slope_prox

            start = pd.to_datetime(row["start"]).date()
            end = pd.to_datetime(row["end"]).date()
            for d in pd.date_range(start, end).date:
                lookup[d] = score

        self.regime_agreement = lookup
        return self

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def detect_drift(self) -> WindowSelector:
        """Compute per-day rolling drift severity for each chamber.

        Active drift signals (configurable via ``config["drift_signals"]``):

        * ``night_intercept``  — seasonally detrended baseline shift of ``flux_intercept``
                                 (nighttime cycles only) — detects zero-point / calibration drift
        * ``slope_divergence`` — seasonally detrended z-score of ``slope_diff_pct``
                                 (OLS vs Theil-Sen disagreement) — detects noise inflation

        Signals **not** active by default (confounded by seasonal biology):

        * ``co2_slope``  — raw z-score of ``co2_slope`` flags seasonal phenology (leaf flush,
                           drought) as drift; only valid if seasonally detrended externally.
        * ``h2o_slope``  — same issue; VPD-driven seasonal stomatal variation dominates.

        **Seasonal detrending**: before computing the short-term rolling z-score (``drift_window_days``),
        a long-term rolling median (``seasonal_detrend_days``, default 90 days) is subtracted from
        each signal.  This removes the seasonal biological baseline, leaving only residual instrument
        drift in the z-score.

        Results are stored in ``self.drift_df`` with columns::

            date, Source_Chamber, drift_severity,
            co2_slope_zscore, night_intercept_zscore,
            h2o_slope_zscore, slope_div_zscore

        ``drift_severity`` = max across active signals, mapped to
        0.0 (clean) / 0.5 (moderate) / 1.0 (severe).
        """
        win = self.config["drift_window_days"]
        z_bad = self.config["drift_zscore_bad"]
        z_mod = self.config["drift_zscore_moderate"]
        long_win = self.config.get("seasonal_detrend_days", 90)
        active = set(self.config.get("drift_signals", list(DEFAULT_CONFIG["drift_signals"])))

        def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
            rm = series.rolling(window, min_periods=3, center=False).mean()
            rs = series.rolling(window, min_periods=3, center=False).std()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return (series - rm) / rs.replace(0, np.nan)

        def _seasonal_detrend(series: pd.Series, long_window: int) -> pd.Series:
            """Subtract long-term rolling median to isolate instrument drift from seasonal biology."""
            min_p = max(3, long_window // 4)
            baseline = series.rolling(long_window, min_periods=min_p, center=True).median()
            return series - baseline

        records = []
        for chamber, grp in self.cycles_df.groupby("Source_Chamber"):
            # Aggregate daily medians (robust to outliers within a day)
            daily_co2 = (
                grp.groupby("_date")["co2_slope"].median()
                if "co2_slope" in grp.columns
                else pd.Series(dtype=float)
            )
            daily_h2o = (
                grp.groupby("_date")["h2o_slope"].median()
                if "h2o_slope" in grp.columns
                else pd.Series(dtype=float)
            )
            daily_sdiv = (
                grp.groupby("_date")["slope_diff_pct"].median()
                if "slope_diff_pct" in grp.columns
                else pd.Series(dtype=float)
            )

            # Nighttime intercept: derive night cycles from hour (is_nighttime column is broken)
            dt_start, dt_end = self.config.get("daytime_hours", [6, 18])
            hours = grp["flux_datetime"].dt.hour
            night_mask = (hours < dt_start) | (hours >= dt_end)
            night = grp[night_mask]
            daily_night_int = (
                night.groupby("_date")["flux_intercept"].median()
                if "flux_intercept" in grp.columns
                else pd.Series(dtype=float)
            )

            # Align all signals to a common date index
            all_dates = sorted(
                set(
                    list(daily_co2.index)
                    + list(daily_h2o.index)
                    + list(daily_sdiv.index)
                    + list(daily_night_int.index)
                )
            )
            date_idx = pd.Index(all_dates)

            co2_s = daily_co2.reindex(date_idx)
            h2o_s = daily_h2o.reindex(date_idx)
            sdiv_s = daily_sdiv.reindex(date_idx)
            nint_s = daily_night_int.reindex(date_idx)

            # Compute detrended z-scores for each active signal
            if "co2_slope" in active and co2_s.notna().sum() >= 3:
                co2_z = _rolling_zscore(_seasonal_detrend(co2_s, long_win), win)
            else:
                co2_z = pd.Series(0.0, index=date_idx)

            if "h2o_slope" in active and h2o_s.notna().sum() >= 3:
                h2o_z = _rolling_zscore(_seasonal_detrend(h2o_s, long_win), win)
            else:
                h2o_z = pd.Series(0.0, index=date_idx)

            if "slope_divergence" in active and sdiv_s.notna().sum() >= 3:
                sdiv_z = _rolling_zscore(_seasonal_detrend(sdiv_s, long_win), win)
            else:
                sdiv_z = pd.Series(0.0, index=date_idx)

            if "night_intercept" in active and nint_s.notna().sum() >= 3:
                nint_z = _rolling_zscore(_seasonal_detrend(nint_s, long_win), win)
            else:
                nint_z = pd.Series(0.0, index=date_idx)

            def _severity(z: pd.Series) -> pd.Series:
                z_abs = z.abs()
                return pd.Series(
                    np.where(z_abs >= z_bad, 1.0, np.where(z_abs >= z_mod, 0.5, 0.0)), index=z.index
                ).fillna(0.0)

            sev_co2 = _severity(co2_z)
            sev_h2o = _severity(h2o_z)
            sev_sdiv = _severity(sdiv_z)
            sev_nint = _severity(nint_z)

            drift_severity = pd.concat([sev_co2, sev_h2o, sev_sdiv, sev_nint], axis=1).max(axis=1)

            for date in all_dates:
                records.append(
                    {
                        "date": date,
                        "Source_Chamber": chamber,
                        "drift_severity": drift_severity.get(date, 0.0),
                        "co2_slope_zscore": float(co2_z.get(date, np.nan) or np.nan),
                        "night_intercept_zscore": float(nint_z.get(date, np.nan) or np.nan),
                        "h2o_slope_zscore": float(h2o_z.get(date, np.nan) or np.nan),
                        "slope_div_zscore": float(sdiv_z.get(date, np.nan) or np.nan),
                    }
                )

        self.drift_df = pd.DataFrame(records)
        return self

    # ------------------------------------------------------------------
    # Individual sub-scorers (each returns float 0-1)
    # ------------------------------------------------------------------

    def _regression_score(self, r2, nrmse, snr, outlier) -> float:
        # Monotonicity removed: in a tree chamber under variable tropical irradiance
        # (sunflecks, cloud passages), non-monotonic CO₂ traces reflect real photosynthetic
        # dynamics, not measurement error.
        cfg = self.config
        s_r2 = (
            (1.0 if r2 >= cfg["r2_good"] else 0.5 if r2 >= cfg["r2_ok"] else 0.0)
            if not _nan(r2)
            else 0.0
        )
        s_nrmse = (
            (1.0 if nrmse <= cfg["nrmse_good"] else 0.5 if nrmse <= cfg["nrmse_ok"] else 0.0)
            if not _nan(nrmse)
            else 0.0
        )
        s_snr = (
            (1.0 if snr >= cfg["snr_good"] else 0.5 if snr >= cfg["snr_ok"] else 0.0)
            if not _nan(snr)
            else 0.0
        )
        s_out = (
            (
                1.0
                if outlier <= cfg["outlier_good"]
                else 0.5
                if outlier <= cfg["outlier_ok"]
                else 0.0
            )
            if not _nan(outlier)
            else 0.0
        )
        return float(np.mean([s_r2, s_nrmse, s_snr, s_out]))

    def _robustness_score(self, slope_diff, delta_aicc) -> float:
        cfg = self.config
        s_slope = (
            (
                1.0
                if slope_diff <= cfg["slope_diff_good"]
                else 0.5
                if slope_diff <= cfg["slope_diff_ok"]
                else 0.0
            )
            if not _nan(slope_diff)
            else 0.5
        )
        # Large negative delta_aicc → strong curvature → regression suspect
        s_aicc = (
            (1.0 if delta_aicc > -4.0 else 0.5 if delta_aicc > -8.0 else 0.0)
            if not _nan(delta_aicc)
            else 0.5
        )
        return float(np.mean([s_slope, s_aicc]))

    def _closure_score(self, closure_confidence) -> float:
        return float(closure_confidence) if not _nan(closure_confidence) else 0.5

    def _sensor_qc_score(self, co2_flag_mean, h2o_flag_mean) -> float:
        # Normalize: flag 0 → 1.0, flag 2 → 0.0
        s_co2 = max(0.0, 1.0 - (co2_flag_mean / 2.0)) if not _nan(co2_flag_mean) else 0.5
        s_h2o = max(0.0, 1.0 - (h2o_flag_mean / 2.0)) if not _nan(h2o_flag_mean) else 0.5
        return float(np.mean([s_co2, s_h2o]))

    def _anomaly_score(self, ensemble_score) -> float:
        return float(1.0 - ensemble_score) if not _nan(ensemble_score) else 0.5

    def _drift_score_lookup(self, date, chamber, drift_lookup: dict) -> float:
        severity = drift_lookup.get((date, chamber), 0.0)
        return float(1.0 - severity)

    # ------------------------------------------------------------------
    # Cycle confidence scoring (vectorized)
    # ------------------------------------------------------------------

    def score_cycles(self) -> WindowSelector:
        """Add ``cycle_confidence`` (0-1) and per-component sub-scores to ``cycles_df``.

        New columns added (all 0–1):
            ``score_regression``    — R², NRMSE, SNR, outlier_frac (4 components; monotonicity removed)
            ``score_robustness``    — OLS vs Theil-Sen slope agreement, AICc curvature test
            ``score_sensor_qc``     — CO₂/H₂O sensor flag mean from 021 parquet
            ``score_drift``         — seasonally detrended instrument drift score
            ``score_cross_chamber`` — cross-chamber agreement from 026 regime diagnostics (NaN if unavailable)
            ``score_closure``       — diagnostic only (not in composite); CO₂/H₂O ratio is biological
            ``score_anomaly``       — diagnostic only (not in composite); flags biology as noise
            ``cycle_confidence``    — weighted composite of the five active components

        Nighttime de-emphasis removed: nighttime cycles carry full weight because dark
        respiration measurements are the primary constraint for Ra and Q10 parameters.

        Requires ``detect_drift()`` to have been called first (for drift scores).
        If not called, drift component defaults to 1.0 (no drift assumed).
        """
        df = self.cycles_df
        cfg = self.config
        w = cfg["score_weights"]

        # Build drift lookup: (date, chamber) → severity
        if self.drift_df is not None:
            drift_lookup = {
                (row["date"], row["Source_Chamber"]): row["drift_severity"]
                for _, row in self.drift_df.iterrows()
            }
        else:
            drift_lookup = {}

        # Helper: safe column getter (returns NaN array if col missing)
        def col(name):
            return df[name].values if name in df.columns else np.full(len(df), np.nan)

        r2 = col("co2_r2")
        nrmse = col("co2_nrmse")
        snr = col("co2_snr")
        outlier = col("co2_outlier_frac")
        slope_diff = col("slope_diff_pct")
        delta_aicc = col("delta_aicc")
        closure = col("closure_confidence")  # diagnostic only
        co2_flag = col("sensor_co2_qc_mean")
        h2o_flag = col("sensor_h2o_qc_mean")
        ensemble = col("anomaly_ensemble_score")  # diagnostic only
        dates = df["_date"].values
        chambers = df["Source_Chamber"].values

        n = len(df)

        # ------ Fully vectorized sub-scores using numpy comparisons ------

        def _tier_high(
            arr: np.ndarray, good: float, ok: float, nan_default: float = 0.0
        ) -> np.ndarray:
            """Higher-is-better 3-tier scorer: ≥good→1.0, ≥ok→0.5, else→0.0."""
            a = arr.astype(float)
            out = np.where(
                np.isnan(a), nan_default, np.where(a >= good, 1.0, np.where(a >= ok, 0.5, 0.0))
            )
            return out

        def _tier_low(
            arr: np.ndarray, good: float, ok: float, nan_default: float = 0.0
        ) -> np.ndarray:
            """Lower-is-better 3-tier scorer: ≤good→1.0, ≤ok→0.5, else→0.0."""
            a = arr.astype(float)
            out = np.where(
                np.isnan(a), nan_default, np.where(a <= good, 1.0, np.where(a <= ok, 0.5, 0.0))
            )
            return out

        s_r2 = _tier_high(r2, cfg["r2_good"], cfg["r2_ok"])
        s_snr = _tier_high(snr, cfg["snr_good"], cfg["snr_ok"])
        s_nrmse = _tier_low(nrmse, cfg["nrmse_good"], cfg["nrmse_ok"])
        s_out = _tier_low(outlier, cfg["outlier_good"], cfg["outlier_ok"])
        # Monotonicity removed from regression: non-monotonic CO₂ in a tree chamber
        # under variable irradiance is real photosynthetic signal, not measurement error.
        s_regression = np.mean([s_r2, s_nrmse, s_snr, s_out], axis=0)

        s_sdiff = _tier_low(
            slope_diff, cfg["slope_diff_good"], cfg["slope_diff_ok"], nan_default=0.5
        )
        # delta_aicc: less negative (closer to 0) is better → treat as higher-is-better
        # with thresholds at -4.0 (good) and -8.0 (ok)
        s_aicc = _tier_high(delta_aicc, -4.0, -8.0, nan_default=0.5)
        s_robustness = np.mean([s_sdiff, s_aicc], axis=0)
        s_closure = np.where(
            ~np.isnan(closure.astype(float)), np.clip(closure.astype(float), 0.0, 1.0), 0.5
        )
        # Vectorized sensor QC score: flag 0 → 1.0, flag 2 → 0.0; NaN → 0.5
        co2_f = co2_flag.astype(float)
        h2o_f = h2o_flag.astype(float)
        s_co2_arr = np.where(np.isnan(co2_f), 0.5, np.clip(1.0 - co2_f / 2.0, 0.0, 1.0))
        s_h2o_arr = np.where(np.isnan(h2o_f), 0.5, np.clip(1.0 - h2o_f / 2.0, 0.0, 1.0))
        s_sensor_qc = (s_co2_arr + s_h2o_arr) / 2.0

        s_anomaly = np.where(
            ~np.isnan(ensemble.astype(float)), np.clip(1.0 - ensemble.astype(float), 0.0, 1.0), 0.5
        )

        # Vectorized drift score via merge (avoids per-row dict lookup over 58k rows)
        if self.drift_df is not None:
            drift_ref = self.drift_df[["date", "Source_Chamber", "drift_severity"]].rename(
                columns={"date": "_date"}
            )
            tmp_keys = pd.DataFrame({"_date": dates, "Source_Chamber": chambers})
            tmp_merged = tmp_keys.merge(drift_ref, on=["_date", "Source_Chamber"], how="left")
            s_drift = 1.0 - tmp_merged["drift_severity"].fillna(0.0).values
        else:
            s_drift = np.ones(n)

        # Cross-chamber agreement score (from 026 regime diagnostics)
        if self.regime_agreement is not None:
            s_cross_chamber = np.array([self.regime_agreement.get(d, 0.5) for d in dates])
        else:
            s_cross_chamber = None  # signal: not available → renormalize weights

        # Composite confidence — physically grounded components only.
        # closure and anomaly carry weight 0.0 in DEFAULT_CONFIG; they are stored
        # as diagnostic columns but do not contribute to cycle_confidence.
        # When cross_chamber data is unavailable (026 not run), its weight is
        # redistributed proportionally across the other active components so
        # the composite score is mathematically identical to the pre-026 formula.
        if s_cross_chamber is not None:
            confidence = (
                w["regression"] * s_regression
                + w["robustness"] * s_robustness
                + w["sensor_qc"] * s_sensor_qc
                + w["drift"] * s_drift
                + w.get("cross_chamber", 0.0) * s_cross_chamber
            )
        else:
            # Renormalize: redistribute cross_chamber weight proportionally
            w_cc = w.get("cross_chamber", 0.0)
            base = w["regression"] + w["robustness"] + w["sensor_qc"] + w["drift"]
            if base > 0 and w_cc > 0:
                scale = (base + w_cc) / base
            else:
                scale = 1.0
            confidence = scale * (
                w["regression"] * s_regression
                + w["robustness"] * s_robustness
                + w["sensor_qc"] * s_sensor_qc
                + w["drift"] * s_drift
            )

        # Derive day/night flag from hour (is_nighttime column in CSV is broken — all True).
        # nighttime_weight is 1.0 by default: dark respiration cycles carry full weight
        # because they are the primary constraint for Ra and Q10 calibration in XPalm.
        dt_start, dt_end = cfg.get("daytime_hours", [6, 18])
        hours_arr = df["flux_datetime"].dt.hour.values
        is_night_arr = (hours_arr < dt_start) | (hours_arr >= dt_end)

        df = df.copy()
        df["score_regression"] = s_regression.round(4)
        df["score_robustness"] = s_robustness.round(4)
        df["score_sensor_qc"] = s_sensor_qc.round(4)
        df["score_drift"] = s_drift.round(4)
        df["score_cross_chamber"] = (
            s_cross_chamber.round(4) if s_cross_chamber is not None else np.full(n, np.nan)
        )
        df["cycle_confidence"] = confidence.round(4)
        # Diagnostic columns — not in composite, kept for visualization and post-hoc review
        df["score_closure"] = s_closure.round(4)  # biologically confounded; informational only
        df["score_anomaly"] = s_anomaly.round(4)  # flags stress biology; informational only
        df["_is_daytime"] = ~is_night_arr  # stored for identify_windows() grade transparency
        self.cycles_df = df
        return self

    # ------------------------------------------------------------------
    # Window identification
    # ------------------------------------------------------------------

    def identify_windows(self) -> WindowSelector:
        """Find high-confidence windows per chamber with rolling flexibility.

        Algorithm
        ---------
        For each (chamber, date):

        1. ``daily_coverage`` = n_cycles / 95th-pct(cycles/day), capped at 1.0
        2. ``daily_good_frac`` = fraction of cycles with
           ``cycle_confidence >= config["confidence_good_threshold"]``
        3. Mark day as *qualifying* if:
           - ``daily_coverage >= min_daily_coverage_frac``
           - ``daily_good_frac >= min_confidence_frac``
           - No ``is_instrumental_regime_change == True`` on that day
             (when ``exclude_instrumental_regimes`` is True)
           Note: ``grade_ab_frac`` (co2_qc ≤ 1) is computed for transparency but is
           NOT a qualifying gate — it double-counts sensor_qc which is already in
           ``cycle_confidence``, and 021 ROC flags can erroneously reject valid rapid
           photosynthetic drawdown cycles.
        4. Find windows where ≥ ``min_window_days`` qualifying days occur within a
           ``min_window_days + window_flexibility_buffer`` day span.  This allows up to
           ``window_flexibility_buffer`` non-qualifying gap days (power outages, maintenance)
           within an otherwise good period without breaking the window.
        5. Window score = weighted combination::

               0.40 × mean_cycle_confidence
             + 0.25 × mean_daily_coverage
             + 0.20 × (1 – mean_drift_severity)
             + 0.15 × diurnal_hour_coverage

           where ``diurnal_hour_coverage`` = fraction of hours 5–18 represented by ≥1 cycle
           (14 hours; extended from 7–17 to include dawn/dusk transitions for light-response fitting).

        Results stored in ``self.windows_df`` with columns::

            window_id, Source_Chamber, start_date, end_date, n_days,
            n_cycles, mean_confidence, mean_coverage, mean_drift_severity,
            mean_daytime_grade_ab_frac, mean_all_grade_ab_frac, mean_grade_a_frac,
            diurnal_hour_coverage, window_score, qualifies_for_export
        """
        if "cycle_confidence" not in self.cycles_df.columns:
            raise RuntimeError("Call score_cycles() before identify_windows().")

        cfg = self.config
        min_cov = cfg["min_daily_coverage_frac"]
        min_good = cfg["min_confidence_frac"]
        conf_thresh = cfg["confidence_good_threshold"]
        min_days = cfg["min_window_days"]
        flex_buf = cfg.get("window_flexibility_buffer", 0)
        effective_span = min_days + flex_buf
        excl_regimes = cfg["exclude_instrumental_regimes"]
        grade_ab_uses_daytime = cfg.get("grade_ab_uses_daytime_only", True)

        # Drift lookup for window-level mean severity
        if self.drift_df is not None:
            drift_lookup = self.drift_df.set_index(["date", "Source_Chamber"])[
                "drift_severity"
            ].to_dict()
        else:
            drift_lookup = {}

        windows = []
        win_id = 0

        for chamber, grp in self.cycles_df.groupby("Source_Chamber"):
            # Max cycles per day (reference for coverage fraction)
            max_per_day = grp.groupby("_date").size().quantile(0.95)
            if max_per_day < 1:
                continue

            # Per-day stats
            daily_stats = []
            for date, day in grp.groupby("_date"):
                n_cyc = len(day)
                coverage = min(n_cyc / max_per_day, 1.0)
                good_frac = (day["cycle_confidence"] >= conf_thresh).mean()
                has_regime = False
                if excl_regimes and "is_instrumental_regime_change" in day.columns:
                    has_regime = bool(day["is_instrumental_regime_change"].any())

                # Diurnal hour coverage (hours 5–18 inclusive: 14 hours)
                # Extended from 7–17 to include dawn/dusk transitions needed for
                # light-response curve fitting (Kok effect, day/night boundary).
                hours = day["flux_datetime"].dt.hour
                daytime_hours = set(hours[(hours >= 5) & (hours <= 18)])
                diurnal_cov = len(daytime_hours) / 14.0  # 5,6,…,18 = 14 hours

                # Grade A/B fraction — direct anchor to co2_qc from notebook 021.
                # When grade_ab_uses_daytime=True, uses only daytime cycles (from _is_daytime,
                # derived from hour-of-day — NOT the broken is_nighttime column which is all True).
                if "co2_qc" in day.columns:
                    all_grade_ab = float((day["co2_qc"] <= 1).mean())
                    grade_a_frac = float((day["co2_qc"] == 0).mean())
                    if grade_ab_uses_daytime and "_is_daytime" in day.columns:
                        dt_cycles = day[day["_is_daytime"]]
                        if len(dt_cycles) > 0:
                            grade_ab_frac = float((dt_cycles["co2_qc"] <= 1).mean())
                        else:
                            grade_ab_frac = all_grade_ab  # no daytime cycles: fall back
                    else:
                        grade_ab_frac = all_grade_ab
                else:
                    grade_ab_frac = 1.0  # no grade data — treat as passing
                    all_grade_ab = 1.0
                    grade_a_frac = 1.0

                qualifying = (
                    coverage >= min_cov and good_frac >= min_good and not has_regime
                    # grade_ab_frac is NOT a gate here — it is computed above for transparency
                    # only. Using it as a gate double-counts sensor_qc (already in cycle_confidence)
                    # and rejects valid rapid-drawdown cycles flagged by 021 ROC rules.
                )
                daily_stats.append(
                    {
                        "date": date,
                        "n_cycles": n_cyc,
                        "coverage": coverage,
                        "good_frac": good_frac,
                        "grade_ab_frac": grade_ab_frac,  # used for qualifying (daytime if configured)
                        "all_grade_ab_frac": all_grade_ab,  # transparency: all cycles
                        "grade_a_frac": grade_a_frac,
                        "diurnal_cov": diurnal_cov,
                        "qualifying": qualifying,
                        "mean_confidence": day["cycle_confidence"].mean(),
                    }
                )

            stats_df = pd.DataFrame(daily_stats).sort_values("date").reset_index(drop=True)

            # Find windows using rolling flexibility (Fix 6):
            # Require >= min_days qualifying days within any effective_span-day span.
            # This allows up to window_flexibility_buffer gap days (power outages, maintenance)
            # without breaking an otherwise good window.
            q_arr = stats_df["qualifying"].astype(int).values
            n_rows = len(q_arr)
            used = np.zeros(n_rows, dtype=bool)  # preserved from upstream (unused)
            candidate_windows = []

            i = 0
            while i <= n_rows - min_days:
                span_end = min(i + effective_span, n_rows)
                span_qual = q_arr[i:span_end]
                if span_qual.sum() >= min_days:
                    # Greedy: take all days from i to span_end-1 as window span
                    start_d = stats_df.iloc[i]["date"]
                    end_d = stats_df.iloc[span_end - 1]["date"]
                    run = stats_df.iloc[i:span_end]
                    candidate_windows.append((start_d, end_d, run))
                    i += min_days  # advance by min_days (non-overlapping)
                else:
                    i += 1

            for start_d, end_d, run in candidate_windows:
                # Cycles in this window
                cyc_mask = (
                    (self.cycles_df["Source_Chamber"] == chamber)
                    & (self.cycles_df["_date"] >= start_d)
                    & (self.cycles_df["_date"] <= end_d)
                )
                win_cycles = self.cycles_df[cyc_mask]

                mean_conf = win_cycles["cycle_confidence"].mean()
                mean_cov = run["coverage"].mean()
                mean_diurnal = run["diurnal_cov"].mean()
                run_dates = run["date"].tolist()
                mean_drift = float(
                    np.mean([drift_lookup.get((d, chamber), 0.0) for d in run_dates])
                )

                window_score = (
                    0.40 * mean_conf
                    + 0.25 * mean_cov
                    + 0.20 * (1.0 - mean_drift)
                    + 0.15 * mean_diurnal
                )

                # Grade fractions for transparency
                mean_grade_ab = (
                    run["grade_ab_frac"].mean() if "grade_ab_frac" in run.columns else float("nan")
                )
                mean_all_grade_ab = (
                    run["all_grade_ab_frac"].mean()
                    if "all_grade_ab_frac" in run.columns
                    else mean_grade_ab
                )
                mean_grade_a = (
                    run["grade_a_frac"].mean() if "grade_a_frac" in run.columns else float("nan")
                )

                win_id += 1
                windows.append(
                    {
                        "window_id": win_id,
                        "Source_Chamber": chamber,
                        "start_date": start_d,
                        "end_date": end_d,
                        "n_days": len(run),
                        "n_cycles": len(win_cycles),
                        "mean_confidence": round(mean_conf, 4),
                        "mean_coverage": round(mean_cov, 4),
                        "mean_drift_severity": round(mean_drift, 4),
                        "mean_daytime_grade_ab_frac": round(mean_grade_ab, 4),  # criterion used
                        "mean_all_grade_ab_frac": round(mean_all_grade_ab, 4),  # all cycles
                        "mean_grade_a_frac": round(mean_grade_a, 4),
                        "diurnal_hour_coverage": round(mean_diurnal, 4),
                        "window_score": round(window_score, 4),
                        "qualifies_for_export": window_score >= cfg["min_window_score_for_export"],
                    }
                )

        self.windows_df = (
            (
                pd.DataFrame(windows)
                .sort_values("window_score", ascending=False)
                .reset_index(drop=True)
            )
            if windows
            else pd.DataFrame()
        )
        return self

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(
        self,
        approved_only: bool = True,
        exclude_list: list[int] | None = None,
    ) -> tuple[pd.DataFrame, dict]:
        """Filter cycles to approved windows and write outputs.

        Parameters
        ----------
        approved_only : bool
            If True (default) and ``approved_windows`` is non-empty, only
            export cycles belonging to approved windows.  Falls back to
            ``qualifies_for_export`` flag when no manual approvals exist.
        exclude_list : list of int, optional
            Window IDs to explicitly exclude from export (after visual
            inspection in 034 or other audit notebooks).

        Returns
        -------
        (filtered_df, manifest) : tuple
            ``filtered_df`` — cycle-level DataFrame ready for XPalm calibration.
            ``manifest`` — dict written to ``calibration_window_manifest.json``.
        """
        if self.windows_df is None or self.windows_df.empty:
            raise RuntimeError("Call identify_windows() before export().")

        cfg = self.config

        # Determine which windows to export
        if approved_only and self.approved_windows:
            export_ids = {
                wid for wid, info in self.approved_windows.items() if info.get("approved", False)
            }
        else:
            export_ids = set(
                self.windows_df.loc[self.windows_df["qualifies_for_export"], "window_id"]
            )

        # Apply manual exclusions
        if exclude_list:
            export_ids -= set(exclude_list)

        if not export_ids:
            warnings.warn(
                "No windows selected for export. Returning empty DataFrame.", stacklevel=2
            )
            return pd.DataFrame(), {}

        # Filter cycles
        keep_masks = []
        for _, row in self.windows_df[self.windows_df["window_id"].isin(export_ids)].iterrows():
            keep_masks.append(
                (self.cycles_df["Source_Chamber"] == row["Source_Chamber"])
                & (self.cycles_df["_date"] >= row["start_date"])
                & (self.cycles_df["_date"] <= row["end_date"])
            )
        combined_mask = keep_masks[0]
        for m in keep_masks[1:]:
            combined_mask = combined_mask | m

        filtered_df = self.cycles_df[combined_mask].drop(columns=["_date"]).copy()

        # Assign window_id to each cycle (from matching window dates/chamber)
        filtered_df["window_id"] = np.nan
        for _, row in self.windows_df[self.windows_df["window_id"].isin(export_ids)].iterrows():
            mask = (
                (filtered_df["Source_Chamber"] == row["Source_Chamber"])
                & (filtered_df["flux_datetime"].dt.date >= row["start_date"])
                & (filtered_df["flux_datetime"].dt.date <= row["end_date"])
            )
            filtered_df.loc[mask, "window_id"] = int(row["window_id"])
            filtered_df.loc[mask, "window_score"] = float(row["window_score"])

        # Build manifest
        win_records = []
        for _, row in self.windows_df[self.windows_df["window_id"].isin(export_ids)].iterrows():
            approval = self.approved_windows.get(row["window_id"], {})
            win_records.append(
                {
                    "window_id": int(row["window_id"]),
                    "chamber": row["Source_Chamber"],
                    "start_date": str(row["start_date"]),
                    "end_date": str(row["end_date"]),
                    "n_days": int(row["n_days"]),
                    "n_cycles": int(row["n_cycles"]),
                    "mean_confidence": float(row["mean_confidence"]),
                    "window_score": float(row["window_score"]),
                    "approved": approval.get("approved", True),
                    "notes": approval.get("notes", ""),
                }
            )

        manifest = {
            "generated_by": "032_Window_Selection_Physically_Grounded",
            "config_snapshot": {
                k: v
                for k, v in cfg.items()
                if k not in ("export_cycles_path", "export_manifest_path")
            },
            "n_windows": len(win_records),
            "n_cycles": len(filtered_df),
            "excluded_windows": exclude_list or [],
            "regime_diagnostics_loaded": self.regime_agreement is not None,
            "windows": win_records,
        }

        # Write outputs
        out_csv = Path(cfg["export_cycles_path"])
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        filtered_df.to_csv(out_csv, index=False)
        print(f"Exported {len(filtered_df):,} cycles → {out_csv}")

        out_json = Path(cfg["export_manifest_path"])
        out_json.parent.mkdir(parents=True, exist_ok=True)
        with open(out_json, "w") as fh:
            json.dump(manifest, fh, indent=2, default=str)
        print(f"Manifest ({len(win_records)} windows) → {out_json}")

        return filtered_df, manifest

    # ------------------------------------------------------------------
    # Convenience summary
    # ------------------------------------------------------------------

    def summary(self) -> None:
        """Print a quick overview of the selection results."""
        print("=== WindowSelector summary ===")
        print(f"  Total cycles loaded : {len(self.cycles_df):,}")
        if "cycle_confidence" in self.cycles_df.columns:
            print(f"  Confidence mean     : {self.cycles_df['cycle_confidence'].mean():.3f}")
            good_thresh = self.config["confidence_good_threshold"]
            n_good = (self.cycles_df["cycle_confidence"] >= good_thresh).sum()
            print(
                f"  Cycles ≥ {good_thresh:.2f}       : {n_good:,} ({n_good / len(self.cycles_df):.1%})"
            )
        if self.drift_df is not None:
            severe = (self.drift_df["drift_severity"] == 1.0).sum()
            print(f"  Days with severe drift : {severe}")
        if self.windows_df is not None and not self.windows_df.empty:
            n_qual = self.windows_df["qualifies_for_export"].sum()
            print(f"  Windows found       : {len(self.windows_df)}")
            print(f"  Qualifying windows  : {n_qual}")
            print(f"  Top window score    : {self.windows_df['window_score'].max():.3f}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _nan(v) -> bool:
    """Return True if v is NaN or None."""
    try:
        return v is None or np.isnan(float(v))
    except (TypeError, ValueError):
        return True
