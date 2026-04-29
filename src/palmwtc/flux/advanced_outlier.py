"""Advanced outlier-detection helpers used by the chamber flux pipeline.

This module ports three building blocks that previously lived inline in
``research/notebooks/030`` so they can be called from the public
:mod:`palmwtc.flux` API and from the package's flux pipeline orchestrator:

* :data:`DEFAULT_ADVANCED_OUTLIER_CONFIG` — the tuning constants for STL,
  rolling z-score, and the rank-normalised ensemble score.
* :func:`compute_stl_residual_scores` — per-chamber Seasonal-Trend-LOWESS
  decomposition of the cycle-level CO₂ slope, producing a residual,
  a robust z-score of that residual (IQR-based), and soft/hard flags.
* :func:`compute_rolling_zscore` — per-chamber centred rolling-window
  z-score on the cycle-level CO₂ slope, producing a z-score and a
  binary outlier flag.
* :func:`compute_ensemble_score` — rank-based [0, 1] normalisation of
  every detector column present (``ml_if_score``, ``ml_mcd_dist``,
  ``lof_score``, ``tif_score``, ``stl_residual_zscore``,
  ``rolling_zscore``), then a weighted sum into
  ``anomaly_ensemble_score`` and a binary
  ``anomaly_ensemble_flag = score > threshold``.  Detectors whose
  source column is missing from the input frame are skipped silently.

The functions mutate **a copy** of the input DataFrame; they never
modify the caller's frame in place.

Design notes
------------
* STL needs ``statsmodels`` (added as a core dep in palmwtc 0.4.0).  If a
  chamber has fewer than ``3 x stl_period`` hourly bins or its residual
  IQR is below 1e-9, that chamber's STL columns are returned as NaN/0
  with an explanatory message — never raise.
* The ensemble's ``rank_norm`` helper imputes NaN inputs to the median
  before ranking and zeros the rank afterwards (NaN treated as
  "not anomalous"), matching the inline notebook implementation
  exactly.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import rankdata as _rankdata

# ---------------------------------------------------------------------------
# Tuning constants (mirrors notebook 030's ADVANCED_OUTLIER_CONFIG)
# ---------------------------------------------------------------------------

DEFAULT_ADVANCED_OUTLIER_CONFIG: dict[str, Any] = {
    # --- LOF (consumed by ensemble; computation lives elsewhere) ---
    "lof_n_neighbors": 20,
    "lof_contamination": 0.05,
    "lof_algorithm": "ball_tree",
    # --- Temporal IForest (consumed by ensemble; computation lives elsewhere) ---
    "tif_n_estimators": 100,
    "tif_max_samples": 10_000,
    "tif_contamination": 0.05,
    # --- STL ---
    "stl_period": 24,            # hours per diurnal cycle
    "stl_robust": True,
    "stl_soft_iqr_mult": 2.0,
    "stl_hard_iqr_mult": 3.5,
    "stl_max_interp_gap_hours": 3,
    "stl_inner_iter": 2,
    "stl_outer_iter": 7,
    # --- Rolling Z-score ---
    "rz_window_cycles": 12,      # ~3h at 1 cycle/15min
    "rz_min_periods": 4,
    "rz_threshold": 3.0,
    # --- Ensemble weights (must sum to 1.0) ---
    "ensemble_weights": {
        "ml_if":  0.15,
        "ml_mcd": 0.15,
        "lof":    0.20,
        "tif":    0.15,
        "stl":    0.20,
        "rz":     0.15,
    },
    "ensemble_flag_threshold": 0.65,
    # --- Training (consumed by detectors not in this module) ---
    "train_on_passing_only": True,
    "passing_qc_max": 1,
    "random_state": 42,
}


# ---------------------------------------------------------------------------
# STL residual scoring
# ---------------------------------------------------------------------------


def _stl_one_chamber(ch_df, chamber, slope_col, cfg):
    """Run STL decomposition for a single chamber (private helper).

    Returns a dict carrying the chamber name, the row index it was scored
    against, and four output Series.  Designed to run in a joblib subprocess.
    """
    from statsmodels.tsa.seasonal import (
        STL,  # local import to keep palmwtc importable without statsmodels
    )

    dt_col = "flux_datetime" if "flux_datetime" in ch_df.columns else "flux_date"
    _dt = pd.to_datetime(ch_df[dt_col], errors="coerce")
    _hour_bin = _dt.dt.floor("1h")

    result = {
        "chamber": chamber,
        "index": ch_df.index,
        "stl_residual":        pd.Series(np.nan, index=ch_df.index),
        "stl_residual_zscore": pd.Series(np.nan, index=ch_df.index),
        "stl_soft_flag":       pd.Series(0,       index=ch_df.index),
        "stl_hard_flag":       pd.Series(0,       index=ch_df.index),
    }

    hourly = (
        ch_df.assign(_hour_bin=_hour_bin)
        .groupby("_hour_bin")[slope_col]
        .median()
        .rename("flux_hourly")
    )
    full_idx = pd.date_range(hourly.index.min(), hourly.index.max(), freq="1h")
    hourly = (
        hourly.reindex(full_idx)
        .interpolate(
            method="time",
            limit=cfg["stl_max_interp_gap_hours"],
            limit_direction="both",
        )
        .dropna()
    )

    if len(hourly) < 3 * cfg["stl_period"]:
        result["_msg"] = f"  STL [{chamber}]: insufficient data ({len(hourly)}h) — skipped"
        return result

    stl_res = STL(
        hourly,
        period=cfg["stl_period"],
        robust=cfg["stl_robust"],
    ).fit(
        inner_iter=cfg.get("stl_inner_iter", 2),
        outer_iter=cfg.get("stl_outer_iter", 7),
    )
    resid = pd.Series(stl_res.resid, index=hourly.index)

    q25, q75 = np.percentile(resid.dropna(), [25, 75])
    iqr_val = q75 - q25
    if iqr_val < 1e-9:
        result["_msg"] = f"  STL [{chamber}]: residual IQR near zero — skipped"
        return result

    robust_sigma = iqr_val / 1.3489

    stl_hourly_df = pd.DataFrame(
        {
            "_hour_bin": resid.index,
            "stl_residual": resid.values,
            "stl_residual_zscore": (resid / robust_sigma).values,
        }
    ).sort_values("_hour_bin")

    ch_sorted = (
        ch_df.assign(_hour_bin=_hour_bin)
        .sort_values("_hour_bin")
        .reset_index()
    )
    merged = pd.merge_asof(
        ch_sorted[["index", "_hour_bin"]],
        stl_hourly_df,
        on="_hour_bin",
        direction="nearest",
        tolerance=pd.Timedelta("90min"),
    ).set_index("index")

    result["stl_residual"].loc[merged.index] = merged["stl_residual"]
    result["stl_residual_zscore"].loc[merged.index] = merged["stl_residual_zscore"]

    abs_z = result["stl_residual_zscore"].abs()
    result["stl_soft_flag"] = (abs_z > cfg["stl_soft_iqr_mult"]).astype(int)
    result["stl_hard_flag"] = (abs_z > cfg["stl_hard_iqr_mult"]).astype(int)

    n_soft = int(result["stl_soft_flag"].sum())
    n_hard = int(result["stl_hard_flag"].sum())
    result["_msg"] = (
        f"  STL [{chamber}]: soft flags={n_soft} (>{cfg['stl_soft_iqr_mult']}xIQR), "
        f"hard flags={n_hard} (>{cfg['stl_hard_iqr_mult']}xIQR)"
    )
    return result


def compute_stl_residual_scores(
    df: pd.DataFrame,
    cfg: dict[str, Any] = DEFAULT_ADVANCED_OUTLIER_CONFIG,
) -> pd.DataFrame:
    """Per-chamber STL decomposition (parallel via ``joblib``).

    Adds four columns to a copy of ``df``:

    * ``stl_residual`` — STL residual at the cycle's hourly bin
    * ``stl_residual_zscore`` — robust z-score of the residual
      (residual / (IQR / 1.3489))
    * ``stl_soft_flag`` — ``int`` 0/1, set to 1 when
      ``|stl_residual_zscore| > cfg["stl_soft_iqr_mult"]``
    * ``stl_hard_flag`` — same with ``cfg["stl_hard_iqr_mult"]``

    Parameters
    ----------
    df : pd.DataFrame
        Cycle-level frame.  Must contain at least:

        - ``Source_Chamber`` — chamber identifier (string).  If missing,
          the whole frame is treated as one chamber called ``"all"``.
        - ``flux_slope`` *or* ``co2_slope`` — slope to decompose.
        - ``flux_datetime`` *or* ``flux_date`` — datetime per cycle.

    cfg : dict, optional
        Configuration overriding :data:`DEFAULT_ADVANCED_OUTLIER_CONFIG`.
        Relevant keys: ``stl_period``, ``stl_robust``, ``stl_inner_iter``,
        ``stl_outer_iter``, ``stl_max_interp_gap_hours``,
        ``stl_soft_iqr_mult``, ``stl_hard_iqr_mult``.

    Returns
    -------
    pd.DataFrame
        A copy of ``df`` with the four new columns appended.

    Notes
    -----
    Requires ``statsmodels`` (palmwtc core dep since 0.4.0).  Imported lazily
    inside :func:`_stl_one_chamber` so importing this module does not pull in
    statsmodels until the first STL call.
    """
    out = df.copy()
    slope_col = "flux_slope" if "flux_slope" in out.columns else "co2_slope"

    for col in ("stl_residual", "stl_residual_zscore"):
        out[col] = np.nan
    for col in ("stl_soft_flag", "stl_hard_flag"):
        out[col] = 0

    chambers = (
        out["Source_Chamber"].unique().tolist()
        if "Source_Chamber" in out.columns
        else ["all"]
    )

    ch_dfs = [
        out[out["Source_Chamber"] == ch] if ch != "all" else out
        for ch in chambers
    ]
    results = Parallel(n_jobs=min(len(chambers), 2), backend="loky")(
        delayed(_stl_one_chamber)(ch_df, ch, slope_col, cfg)
        for ch_df, ch in zip(ch_dfs, chambers, strict=False)
    )

    for res in results:
        idx = res["index"]
        out.loc[idx, "stl_residual"]        = res["stl_residual"].values
        out.loc[idx, "stl_residual_zscore"] = res["stl_residual_zscore"].values
        out.loc[idx, "stl_soft_flag"]       = res["stl_soft_flag"].values
        out.loc[idx, "stl_hard_flag"]       = res["stl_hard_flag"].values

    return out


# ---------------------------------------------------------------------------
# Rolling z-score
# ---------------------------------------------------------------------------


def compute_rolling_zscore(
    df: pd.DataFrame,
    cfg: dict[str, Any] = DEFAULT_ADVANCED_OUTLIER_CONFIG,
) -> pd.DataFrame:
    """Per-chamber centred rolling-window z-score on the cycle-level slope.

    Adds two columns to a copy of ``df``:

    * ``rolling_zscore`` — float z-score using a centred rolling mean and
      std with window size ``cfg["rz_window_cycles"]``.
    * ``rolling_zscore_flag`` — ``int`` 0/1, set to 1 when
      ``|rolling_zscore| > cfg["rz_threshold"]``.

    Parameters
    ----------
    df : pd.DataFrame
        Cycle-level frame.  Must contain ``Source_Chamber``,
        ``flux_slope`` (or ``co2_slope``), and ``flux_datetime`` (or
        ``flux_date``).
    cfg : dict, optional
        Configuration overriding :data:`DEFAULT_ADVANCED_OUTLIER_CONFIG`.
        Relevant keys: ``rz_window_cycles``, ``rz_min_periods``,
        ``rz_threshold``.

    Returns
    -------
    pd.DataFrame
        A copy of ``df`` with the two new columns appended.
    """
    out = df.copy()
    dt_col = "flux_datetime" if "flux_datetime" in out.columns else "flux_date"
    slope_col = "flux_slope" if "flux_slope" in out.columns else "co2_slope"
    out["rolling_zscore"] = np.nan
    out["rolling_zscore_flag"] = 0

    chambers = (
        out["Source_Chamber"].unique().tolist()
        if "Source_Chamber" in out.columns
        else ["all"]
    )
    w = cfg["rz_window_cycles"]
    min_p = cfg["rz_min_periods"]
    thr = cfg["rz_threshold"]

    for chamber in chambers:
        ch_mask = (
            (out["Source_Chamber"] == chamber)
            if chamber != "all"
            else pd.Series(True, index=out.index)
        )
        ch_sorted = out[ch_mask].sort_values(dt_col)
        slopes = ch_sorted[slope_col]

        roll_mean = slopes.rolling(window=w, min_periods=min_p, center=True).mean()
        roll_std = slopes.rolling(window=w, min_periods=min_p, center=True).std()
        roll_std_safe = roll_std.replace(0, np.nan)
        z = (slopes - roll_mean) / roll_std_safe

        out.loc[ch_mask, "rolling_zscore"] = z.values
        out.loc[ch_mask, "rolling_zscore_flag"] = (
            (z.abs() > thr).fillna(0).astype(int).values
        )

    return out


# ---------------------------------------------------------------------------
# Ensemble score
# ---------------------------------------------------------------------------


_DETECTOR_MAP = {
    # key: (column, higher_is_worse)  —  None == symmetric (use |abs| then rank)
    "ml_if":  ("ml_if_score",        False),
    "ml_mcd": ("ml_mcd_dist",        True),
    "lof":    ("lof_score",          False),
    "tif":    ("tif_score",          False),
    "stl":    ("stl_residual_zscore", None),
    "rz":     ("rolling_zscore",     None),
}


def _rank_norm(series: pd.Series, higher_is_worse: bool, n: int) -> np.ndarray:
    """Rank-based [0, 1] normalisation, NaN-imputing helper.

    Imputes NaN values to the median before ranking, then resets those
    positions to 0.0 ("not anomalous") in the output.  Matches the
    notebook 030 inline implementation exactly.
    """
    vals = series.values.copy().astype(float)
    nan_mask = np.isnan(vals)
    if nan_mask.any():
        vals[nan_mask] = np.nanmedian(vals)
    ranks = (_rankdata(vals) - 1) / max(n - 1, 1)
    if not higher_is_worse:
        ranks = 1.0 - ranks
    ranks[nan_mask] = 0.0
    return ranks


def compute_ensemble_score(
    df: pd.DataFrame,
    cfg: dict[str, Any] = DEFAULT_ADVANCED_OUTLIER_CONFIG,
) -> pd.DataFrame:
    """Rank-normalise every detector present and combine into an ensemble score.

    Looks for six detector columns (``ml_if_score``, ``ml_mcd_dist``,
    ``lof_score``, ``tif_score``, ``stl_residual_zscore``,
    ``rolling_zscore``) and rank-normalises each present one to ``[0, 1]``
    where ``1.0 = most anomalous``.  Symmetric scores (STL z-score,
    rolling z-score) are absolute-valued before ranking.  Lower-is-worse
    scores (IF, LOF, TIF) are flipped after ranking.

    Adds these columns to a copy of ``df``:

    * ``{key}_norm`` for every detector key whose source column was found
    * ``anomaly_ensemble_score`` — weighted average of the present
      ``{key}_norm`` columns, using ``cfg["ensemble_weights"]`` and
      re-normalised by the sum of weights actually used
    * ``anomaly_ensemble_flag`` — ``int`` 0/1 set to 1 when
      ``anomaly_ensemble_score > cfg["ensemble_flag_threshold"]``

    Detectors whose source column is missing are silently skipped (no
    ``{key}_norm`` column is added and the key contributes nothing to the
    weighted sum).

    Parameters
    ----------
    df : pd.DataFrame
        Cycle-level frame, ideally already enriched by
        :func:`compute_ml_anomaly_flags`,
        :func:`compute_stl_residual_scores`, and
        :func:`compute_rolling_zscore`.
    cfg : dict, optional
        Configuration overriding :data:`DEFAULT_ADVANCED_OUTLIER_CONFIG`.
        Relevant keys: ``ensemble_weights``, ``ensemble_flag_threshold``.

    Returns
    -------
    pd.DataFrame
        A copy of ``df`` with the new ``{key}_norm``,
        ``anomaly_ensemble_score``, and ``anomaly_ensemble_flag`` columns.
    """
    out = df.copy()
    n = len(out)
    if n == 0:
        out["anomaly_ensemble_score"] = []
        out["anomaly_ensemble_flag"] = []
        return out

    weights = cfg["ensemble_weights"]
    weighted_sum = np.zeros(n)
    weight_total = 0.0

    for key, (col, higher_is_worse) in _DETECTOR_MAP.items():
        if col not in out.columns:
            continue
        if higher_is_worse is None:
            normed = _rank_norm(out[col].abs(), higher_is_worse=True, n=n)
        else:
            normed = _rank_norm(out[col], higher_is_worse=higher_is_worse, n=n)
        out[f"{key}_norm"] = normed
        w = weights.get(key, 0.0)
        weighted_sum += normed * w
        weight_total += w

    if weight_total > 0:
        out["anomaly_ensemble_score"] = weighted_sum / weight_total
    else:
        out["anomaly_ensemble_score"] = 0.0

    thr = cfg["ensemble_flag_threshold"]
    out["anomaly_ensemble_flag"] = (out["anomaly_ensemble_score"] > thr).astype(int)
    return out


__all__ = [
    "DEFAULT_ADVANCED_OUTLIER_CONFIG",
    "compute_ensemble_score",
    "compute_rolling_zscore",
    "compute_stl_residual_scores",
]
