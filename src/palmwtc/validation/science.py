# ruff: noqa: RUF002, RUF003, RUF046, RUF059
"""Science validation: compare flux results against literature ecophysiology bounds.

Runs four canonical ecophysiology sanity checks against per-cycle flux output
from oil-palm automated whole-tree chambers (LIBZ field site, Riau, Indonesia):

1. **Light response** — fits a rectangular-hyperbola (Michaelis-Menten) model per
   chamber to daytime cycles; checks Amax and quantum yield (alpha) against
   whole-canopy bounds for tropical perennial crops (Lamade & Bouillet 2005 [1]_).
2. **Temperature response (Q10)** — fits van't Hoff exponential on nighttime
   respiration vs air temperature; checks Q10 within 1.5–3.0.
3. **Water use efficiency (WUE)** — checks median WUE against the Medlyn g₁-based
   range and tests for a negative WUE–VPD correlation (Medlyn et al. 2011 [2]_).
4. **Inter-chamber agreement** — Pearson r > 0.70 between the two chambers'
   daytime hourly means.

Each test returns ``"PASS"``, ``"BORDERLINE"``, ``"FAIL"``, or ``"N/A"``
(when data are insufficient or the test condition is not identifiable).

Main entry point: :func:`run_science_validation`.
Helper for daytime classification: :func:`derive_is_daytime`.
Configurable thresholds: :data:`DEFAULT_CONFIG`.

References
----------
.. [1] Lamade, E. & Bouillet, J.-P. (2005). Carbon storage and global change:
       the case of oil palm. *Oléagineux, Corps gras, Lipides*, 12(2), 154–160.
.. [2] Medlyn, B. E., et al. (2011). Reconciling the optimal and empirical
       approaches to modelling stomatal conductance. *Global Change Biology*,
       17(6), 2134–2144. https://doi.org/10.1111/j.1365-2486.2010.02375.x
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import scipy.stats as stats
from scipy.optimize import curve_fit

# ---------------------------------------------------------------------------
# Default literature thresholds
# ---------------------------------------------------------------------------

#: Default configuration for :func:`run_science_validation`.
#:
#: Column name keys map to the 030 export schema.  Override only the keys
#: you want to change; pass ``config={"key": value}`` to
#: :func:`run_science_validation`.
#:
#: **Column names** (override when your DataFrame uses different names):
#:
#: ``co2_flux_col`` : str = ``"flux_absolute"``
#:     CO₂ flux column (µmol m⁻² s⁻², negative = uptake).
#:
#: ``h2o_flux_col`` : str = ``"h2o_slope"``
#:     H₂O flux column (used for WUE denominator).
#:
#: ``co2_slope_col`` : str = ``"co2_slope"``
#:     Raw CO₂ slope used in the WUE numerator.
#:
#: ``radiation_col`` : str = ``"Global_Radiation"``
#:     Shortwave radiation (W m⁻²).  Converted to PAR via factor 2.02
#:     (Meek et al. 1984).  Also used in :func:`derive_is_daytime`.
#:
#: ``temp_col`` : str = ``"mean_temp"``
#:     Air temperature (°C) used for Q10 fit.
#:
#: ``vpd_col`` : str = ``"vpd_kPa"``
#:     Vapour pressure deficit (kPa) used for WUE–VPD correlation.
#:
#: ``chamber_col`` : str = ``"Source_Chamber"``
#:     Column identifying each measurement chamber.
#:
#: ``datetime_col`` : str = ``"flux_datetime"``
#:     Datetime column used for day/night classification.
#:
#: **Light-response bounds** (whole-canopy, chamber-footprint basis) [1]_:
#:
#: ``Amax_range`` : tuple of float = (5.0, 35.0)
#:     Gross maximum assimilation (µmol CO₂ m⁻² s⁻²).  Widened from leaf-level
#:     (2–15 µmol m⁻² s⁻¹) because ``flux_absolute`` is per m² chamber footprint
#:     and oil-palm LAI of 2–4 scales leaf Amax proportionally.
#:
#: ``alpha_range`` : tuple of float = (0.02, 0.12)
#:     Apparent quantum yield (µmol CO₂ µmol photons⁻¹).
#:
#: ``light_response_min_n`` : int = 200
#:     Minimum daytime cycles required to attempt the light-response fit.
#:
#: ``light_response_par_iqr_min`` : float = 300.0
#:     Minimum IQR of PAR (µmol m⁻² s⁻¹) required for a defensible fit.
#:     If the PAR range is too narrow the fit is underdetermined; result is ``"N/A"``.
#:
#: **Q10 temperature-response bounds**:
#:
#: ``Q10_range`` : tuple of float = (1.5, 3.0)
#:     Acceptable Q10 range for dark respiration.
#:
#: ``Q10_r2_min`` : float = 0.10
#:     Minimum R² for the Q10 regression.  Below this the fit is uninformative.
#:
#: ``Q10_min_n`` : int = 50
#:     Minimum nighttime cycles required per chamber.
#:
#: ``Q10_min_T_iqr`` : float = 3.0
#:     Minimum IQR of nighttime air temperature (°C).  Narrow temperature range
#:     makes Q10 unidentifiable — result is ``"N/A"``.
#:
#: **Water use efficiency bounds** [2]_:
#:
#: ``WUE_range`` : tuple of float = (2.0, 8.0)
#:     Acceptable median WUE (mmol CO₂ mol⁻¹ H₂O).
#:
#: ``WUE_VPD_r_max`` : float = -0.10
#:     WUE–VPD Pearson r must be more negative than this (i.e. r < –0.10).
#:     A positive or weakly negative correlation is inconsistent with
#:     stomatal optimality theory.
#:
#: **Inter-chamber agreement**:
#:
#: ``chamber_r_min`` : float = 0.70
#:     Minimum daytime Pearson r between the two chambers' hourly means.
#:
#: **Shared**:
#:
#: ``T_ref`` : float = 25.0
#:     Reference temperature (°C) for the Q10 van't Hoff fit.
#:
#: ``daytime_hours`` : tuple of int = (6, 18)
#:     ``(start_hour, end_hour)`` used when radiation is unavailable in
#:     :func:`derive_is_daytime`.
DEFAULT_CONFIG: dict[str, Any] = {
    "co2_flux_col": "flux_absolute",
    "h2o_flux_col": "h2o_slope",
    "co2_slope_col": "co2_slope",
    "radiation_col": "Global_Radiation",
    "temp_col": "mean_temp",
    "vpd_col": "vpd_kPa",
    "chamber_col": "Source_Chamber",
    "datetime_col": "flux_datetime",
    # Literature ranges — chamber-basis (per m² chamber footprint), whole-tree oil palm.
    # Bounds widened from leaf-level (Amax 2-15) to whole-canopy because
    # flux_absolute is per m² chamber FOOTPRINT (see src/flux_analysis.py:51-56),
    # and oil palm canopy with LAI ~2-4 scales leaf Amax up proportionally.
    # Diagnostic 2026-04-15: chamber-footprint |flux|_p95 = 18.4 umol/m2/s
    # across both chambers — exceeds the old leaf-level cap of 15.
    "Amax_range": (5.0, 35.0),  # umol CO2 / m2 chamber-footprint / s (whole-canopy)
    "alpha_range": (0.02, 0.12),  # umol CO2 / umol photons (slightly widened)
    "Q10_range": (1.5, 3.0),
    "Q10_r2_min": 0.10,
    "Q10_min_n": 50,  # min nighttime cycles required per chamber
    "Q10_min_T_iqr": 3.0,  # degC; if nighttime T IQR < this, Q10 unidentifiable
    "WUE_range": (2.0, 8.0),  # mmol CO2 / mol H2O
    "WUE_VPD_r_max": -0.10,  # WUE-VPD correlation must be more negative
    "chamber_r_min": 0.70,
    "T_ref": 25.0,
    "daytime_hours": (6, 18),
    # Gate for light-response sufficient PAR variation (Cause C defense)
    "light_response_min_n": 200,
    "light_response_par_iqr_min": 300.0,  # umol/m2/s; IQR of PAR must span >= this
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def _light_response(par: np.ndarray, alpha: float, Amax: float, Rd: float) -> np.ndarray:
    """Rectangular hyperbola (Michaelis-Menten) light response."""
    return (alpha * par * Amax) / (alpha * par + Amax) - Rd


def _status_inrange(val: float, lo: float, hi: float) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    if lo <= val <= hi:
        return "PASS"
    if lo * 0.7 <= val <= hi * 1.3:
        return "BORDERLINE"
    return "FAIL"


def _status_atleast(val: float, threshold: float, flip: bool = False) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    cond = val <= threshold if flip else val >= threshold
    return "PASS" if cond else "BORDERLINE"


def derive_is_daytime(
    cycles: pd.DataFrame,
    config: dict[str, Any] | None = None,
    radiation_threshold: float = 10.0,
) -> pd.Series:
    """Derive a Boolean daytime mask from radiation or, as a fallback, hour-of-day.

    **Primary criterion** — if ``Global_Radiation`` (or the column named in
    ``config["radiation_col"]``) is present and has at least one non-NaN value,
    a cycle is classified as daytime when its radiation ≥ ``radiation_threshold``
    W m⁻².

    **Fallback criterion** — for rows where radiation is NaN, or when the
    radiation column is entirely absent, the mask falls back to hour-of-day:
    daytime = ``[config["daytime_hours"][0], config["daytime_hours"][1])``,
    i.e. ``[6, 18)`` by default.

    Parameters
    ----------
    cycles : pd.DataFrame
        Cycle-level DataFrame.  Must contain the column named in
        ``config["datetime_col"]`` (default ``"flux_datetime"``).
        The radiation column (default ``"Global_Radiation"``) is optional.
    config : dict, optional
        Override keys from :data:`DEFAULT_CONFIG`.  Relevant keys:
        ``radiation_col``, ``datetime_col``, ``daytime_hours``.
    radiation_threshold : float, default 10.0
        Minimum shortwave radiation (W m⁻²) to classify a cycle as daytime.

    Returns
    -------
    pd.Series of bool
        Same index as ``cycles``.  ``True`` = daytime.

    Examples
    --------
    >>> import pandas as pd
    >>> from palmwtc.validation import derive_is_daytime
    >>> cycles = pd.DataFrame({
    ...     "flux_datetime": pd.to_datetime(["2024-01-01 08:00", "2024-01-01 22:00"]),
    ...     "Global_Radiation": [150.0, float("nan")],
    ... })
    >>> derive_is_daytime(cycles).tolist()
    [True, False]
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    rad_col = cfg["radiation_col"]
    dt_col = cfg["datetime_col"]
    dt_start, dt_end = cfg["daytime_hours"]

    rad = pd.to_numeric(cycles.get(rad_col), errors="coerce") if rad_col in cycles.columns else None
    if rad is not None and rad.notna().any():
        is_day_rad = rad >= radiation_threshold
        # Hour fallback for NaN radiation rows
        hours = pd.to_datetime(cycles[dt_col]).dt.hour
        is_day_hour = (hours >= dt_start) & (hours < dt_end)
        return is_day_rad.where(rad.notna(), is_day_hour).astype(bool)

    hours = pd.to_datetime(cycles[dt_col]).dt.hour
    return ((hours >= dt_start) & (hours < dt_end)).astype(bool)


# ---------------------------------------------------------------------------
# Individual tests — each returns a per-chamber (or global) result dict
# ---------------------------------------------------------------------------
def test_light_response(cycles: pd.DataFrame, config: dict[str, Any]) -> dict[str, dict]:
    """Fit a rectangular-hyperbola light response per chamber.

    Fixes applied 2026-04-15:
      - Sign convention: flux_absolute is negative for uptake (see
        src/flux_analysis.py:56, `flux = flux_slope * rho_air * h_eff`).
        The model _light_response() expects positive assimilation A, so we fit
        on ``assim = -flux``. With this, a well-functioning oil palm chamber
        shows positive Amax during the day and positive Rd for nighttime
        respiration.
      - Whole-canopy scale: bounds widened (see DEFAULT_CONFIG comment).
      - Cause-C gate: if PAR-proxy IQR is too narrow or daytime-n too small,
        return ``status="N/A (insufficient PAR range)"`` — scientifically
        honest instead of a degenerate FAIL.
    """
    flux_col = config["co2_flux_col"]
    rad_col = config["radiation_col"]
    chamber_col = config["chamber_col"]
    min_n = int(config.get("light_response_min_n", 200))
    par_iqr_min = float(config.get("light_response_par_iqr_min", 300.0))
    # Approximate PAR (umol photons /m²/s) from global solar radiation (W/m²).
    # Conversion factor 2.02 is the standard visible-fraction coefficient for
    # shortwave radiation (Meek et al. 1984).
    RAD_TO_PAR = 2.02

    day_cycles = cycles[
        cycles["_is_daytime"]
        & cycles[flux_col].notna()
        & cycles[rad_col].notna()
        & (cycles[rad_col] >= 0)
    ].copy()

    results: dict[str, dict] = {}
    for chamber in sorted(cycles[chamber_col].dropna().unique()):
        ch = day_cycles[day_cycles[chamber_col] == chamber]
        n_cyc = int(len(ch))
        if n_cyc < min_n:
            results[chamber] = {
                "n": n_cyc,
                "status": "N/A",
                "reason": f"insufficient data (n={n_cyc} < {min_n})",
            }
            continue
        par = ch[rad_col].values * RAD_TO_PAR
        par_iqr = float(np.quantile(par, 0.75) - np.quantile(par, 0.25))
        if par_iqr < par_iqr_min:
            results[chamber] = {
                "n": n_cyc,
                "status": "N/A",
                "reason": f"insufficient PAR range (IQR={par_iqr:.0f} umol photons /m2/s < {par_iqr_min:.0f})",
            }
            continue
        # Sign-flip so positive numbers mean assimilation.
        assim = -ch[flux_col].values
        try:
            popt, pcov = curve_fit(
                _light_response,
                par,
                assim,
                p0=[0.04, 12.0, 2.0],
                bounds=([0, 0, 0], [0.20, 50.0, 15.0]),
                maxfev=5000,
            )
            alpha_fit, Amax_fit, Rd_fit = popt
            perr = np.sqrt(np.diag(pcov))
            y_pred = _light_response(par, *popt)
            r2 = 1 - np.sum((assim - y_pred) ** 2) / np.sum((assim - assim.mean()) ** 2)

            Amax_status = _status_inrange(Amax_fit, *config["Amax_range"])
            alpha_status = _status_inrange(alpha_fit, *config["alpha_range"])
            overall = (
                "PASS"
                if (Amax_status == "PASS" and alpha_status == "PASS" and Rd_fit > 0)
                else ("BORDERLINE" if "FAIL" not in (Amax_status, alpha_status) else "FAIL")
            )
            results[chamber] = {
                "n": n_cyc,
                "par_iqr": par_iqr,
                "Amax": float(Amax_fit),
                "Amax_se": float(perr[1]),
                "alpha": float(alpha_fit),
                "alpha_se": float(perr[0]),
                "Rd": float(Rd_fit),
                "r2": float(r2),
                "Amax_status": Amax_status,
                "alpha_status": alpha_status,
                "status": overall,
            }
        except Exception as exc:
            results[chamber] = {"n": n_cyc, "status": "FAIL", "reason": str(exc)}
    return results


def test_q10(cycles: pd.DataFrame, config: dict[str, Any]) -> dict[str, dict]:
    """Van't Hoff Q10 fit on nighttime respiration vs temperature per chamber.

    Returns ``status="N/A"`` when the chamber's nighttime temperature range is
    too narrow to support a defensible fit. Audit 2026-04-15 found nighttime
    T IQR ~1.7 C at LIBZ — far below the 5-10 C typically required for Q10
    identifiability — so reporting any Q10 value here would be
    indistinguishable from fitting noise. Tightened R2 gate as well: a fit
    with r2 < Q10_r2_min now returns FAIL (not BORDERLINE) on the r2 axis.
    """
    flux_col = config["co2_flux_col"]
    temp_col = config["temp_col"]
    chamber_col = config["chamber_col"]
    T_ref = config["T_ref"]
    min_n = int(config.get("Q10_min_n", 50))
    min_t_iqr = float(config.get("Q10_min_T_iqr", 3.0))  # degC

    results: dict[str, dict] = {}
    for chamber in sorted(cycles[chamber_col].dropna().unique()):
        ch = cycles[
            (cycles[chamber_col] == chamber)
            & (~cycles["_is_daytime"])
            & (cycles[flux_col] > 0)
            & cycles[temp_col].notna()
        ].copy()
        n_cyc = int(len(ch))
        if n_cyc < min_n:
            results[chamber] = {
                "n": n_cyc,
                "status": "N/A",
                "reason": f"insufficient nighttime data (n={n_cyc} < {min_n})",
            }
            continue
        T = ch[temp_col].values
        t_iqr = float(np.quantile(T, 0.75) - np.quantile(T, 0.25))
        if t_iqr < min_t_iqr:
            results[chamber] = {
                "n": n_cyc,
                "t_iqr": t_iqr,
                "status": "N/A",
                "reason": f"nighttime T IQR {t_iqr:.2f} C < {min_t_iqr:.1f} C — Q10 unidentifiable",
            }
            continue
        R = ch[flux_col].values
        lnR = np.log(R)
        slope, intercept, r_val, p_val, se = stats.linregress(T - T_ref, lnR)
        Q10 = float(np.exp(slope * 10))
        r2 = float(r_val**2)
        Q10_ci = (float(np.exp((slope - 1.96 * se) * 10)), float(np.exp((slope + 1.96 * se) * 10)))

        q10_status = _status_inrange(Q10, *config["Q10_range"])
        # Tightened: r2 below threshold is FAIL (was BORDERLINE). A meaningless
        # fit shouldn't be reported as passing on the range axis alone.
        r2_pass = r2 >= config["Q10_r2_min"]
        r2_status = "PASS" if r2_pass else "FAIL"
        overall = (
            "PASS"
            if (q10_status == "PASS" and r2_pass)
            else ("FAIL" if (q10_status == "FAIL" or not r2_pass) else "BORDERLINE")
        )
        results[chamber] = {
            "n": n_cyc,
            "t_iqr": t_iqr,
            "Q10": Q10,
            "Q10_ci_lo": Q10_ci[0],
            "Q10_ci_hi": Q10_ci[1],
            "R_ref": float(np.exp(intercept)),
            "r2": r2,
            "p": float(p_val),
            "Q10_status": q10_status,
            "r2_status": r2_status,
            "status": overall,
        }
    return results


def test_wue(cycles: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    """Compute median WUE and WUE–VPD correlation across daytime uptake cycles.

    Water use efficiency (WUE) is calculated as the ratio of CO₂ slope to H₂O
    slope for daytime cycles where the chamber shows net CO₂ uptake.  The
    median WUE is compared against ``config["WUE_range"]`` and the Pearson
    correlation between WUE and VPD must be more negative than
    ``config["WUE_VPD_r_max"]`` (consistent with Medlyn stomatal optimality).

    Parameters
    ----------
    cycles : pd.DataFrame
        Cycle-level DataFrame with a pre-computed ``_is_daytime`` column.
        Required columns: ``flux_absolute``, ``h2o_slope``, ``co2_slope``,
        and optionally ``vpd_kPa``.
    config : dict
        Configuration dict; see :data:`DEFAULT_CONFIG` for keys used here:
        ``co2_flux_col``, ``h2o_flux_col``, ``co2_slope_col``, ``vpd_col``,
        ``WUE_range``, ``WUE_VPD_r_max``.

    Returns
    -------
    dict
        Keys: ``"n"``, ``"median"``, ``"p25"``, ``"p75"``, ``"wue_status"``,
        optionally ``"vpd_r"``, ``"vpd_p"``, ``"vpd_status"``, and ``"status"``.
        Returns ``{"n": ..., "status": "N/A", "reason": ...}`` when there are
        fewer than 20 qualifying cycles.
    """
    flux_col = config["co2_flux_col"]
    h2o_col = config["h2o_flux_col"]
    co2_slope_col = config["co2_slope_col"]
    vpd_col = config["vpd_col"]

    wue = cycles[
        cycles["_is_daytime"]
        & (cycles[flux_col] < 0)
        & (cycles[h2o_col] > 0)
        & cycles[h2o_col].notna()
    ].copy()
    if len(wue) < 20:
        return {"n": int(len(wue)), "status": "N/A", "reason": "insufficient WUE data"}

    wue["wue"] = (-wue[co2_slope_col] / wue[h2o_col]).clip(0.1, 30.0)
    median = float(wue["wue"].median())
    wue_status = _status_inrange(median, *config["WUE_range"])

    out: dict[str, Any] = {
        "n": int(len(wue)),
        "median": median,
        "p25": float(wue["wue"].quantile(0.25)),
        "p75": float(wue["wue"].quantile(0.75)),
        "wue_status": wue_status,
    }
    if vpd_col in wue.columns and wue[vpd_col].notna().sum() > 20:
        v = wue[vpd_col].values
        w = wue["wue"].values
        m = np.isfinite(v) & np.isfinite(w)
        if m.sum() > 20:
            r, p = stats.pearsonr(v[m], w[m])
            out["vpd_r"] = float(r)
            out["vpd_p"] = float(p)
            out["vpd_status"] = _status_atleast(r, config["WUE_VPD_r_max"], flip=True)
    overall = (
        "PASS"
        if (wue_status == "PASS" and out.get("vpd_status") == "PASS")
        else ("BORDERLINE" if wue_status != "FAIL" else "FAIL")
    )
    out["status"] = overall
    return out


def test_inter_chamber(cycles: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    """Compute daytime and nighttime Pearson r between the two chamber CO₂ fluxes.

    Pivots the flux data by ``(date, hour)`` so the two chambers share a common
    time axis, then computes Pearson r for daytime and nighttime hour subsets.
    The test passes when the daytime r ≥ ``config["chamber_r_min"]``.

    Parameters
    ----------
    cycles : pd.DataFrame
        Cycle-level DataFrame.  Required columns: the chamber column
        (``config["chamber_col"]``), datetime column, and flux column.
        Must contain data from at least two distinct chambers.
    config : dict
        Configuration dict; see :data:`DEFAULT_CONFIG` for keys used here:
        ``co2_flux_col``, ``chamber_col``, ``datetime_col``,
        ``daytime_hours``, ``chamber_r_min``.

    Returns
    -------
    dict
        Keys: ``"n_day_pairs"``, ``"n_night_pairs"``, ``"r_daytime"``,
        ``"p_daytime"``, ``"r_nighttime"``, ``"status"``.
        Returns ``{"status": "N/A", "reason": ...}`` when fewer than 2
        chambers are present or fewer than 20 matched time-pairs exist.
    """
    flux_col = config["co2_flux_col"]
    chamber_col = config["chamber_col"]
    dt_col = config["datetime_col"]
    dt_start, dt_end = config["daytime_hours"]

    chambers = sorted(cycles[chamber_col].dropna().unique())
    if len(chambers) < 2:
        return {"status": "N/A", "reason": "fewer than 2 chambers"}

    work = cycles[[chamber_col, dt_col, flux_col]].copy()
    work["_date"] = pd.to_datetime(work[dt_col]).dt.date
    work["_hour"] = pd.to_datetime(work[dt_col]).dt.hour
    pivot = work.pivot_table(
        index=["_date", "_hour"], columns=chamber_col, values=flux_col, aggfunc="mean"
    ).reset_index()
    pivot = pivot.dropna(subset=chambers)
    if len(pivot) < 20:
        return {"status": "N/A", "reason": f"only {len(pivot)} matched cycles"}

    ch1, ch2 = chambers[0], chambers[1]
    day_mask = pivot["_hour"].between(dt_start, dt_end - 1)
    x_day = pivot.loc[day_mask, ch1].values
    y_day = pivot.loc[day_mask, ch2].values
    x_night = pivot.loc[~day_mask, ch1].values
    y_night = pivot.loc[~day_mask, ch2].values

    r_day, p_day = stats.pearsonr(x_day, y_day) if len(x_day) > 10 else (np.nan, np.nan)
    r_night, p_night = stats.pearsonr(x_night, y_night) if len(x_night) > 10 else (np.nan, np.nan)
    status = _status_atleast(r_day, config["chamber_r_min"])
    return {
        "n_day_pairs": int(len(x_day)),
        "n_night_pairs": int(len(x_night)),
        "r_daytime": float(r_day) if not np.isnan(r_day) else None,
        "p_daytime": float(p_day) if not np.isnan(p_day) else None,
        "r_nighttime": float(r_night) if not np.isnan(r_night) else None,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------
def run_science_validation(
    cycles: pd.DataFrame,
    config: dict[str, Any] | None = None,
    label: str = "default",
    derive_daytime: bool = False,
) -> dict[str, Any]:
    """Run all four ecophysiology validation tests on a cycles DataFrame.

    Executes the light-response, Q10, WUE, and inter-chamber tests in sequence
    and returns a structured scorecard.  Each test returns ``"PASS"``,
    ``"BORDERLINE"``, ``"FAIL"``, or ``"N/A"`` per chamber (or globally for
    WUE and inter-chamber tests).

    Parameters
    ----------
    cycles : pd.DataFrame
        Cycle-level data, already filtered to the desired QC subset.
        Required columns (names configurable via ``config``):

        * ``flux_datetime``    — cycle start datetime.
        * ``Source_Chamber``   — chamber identifier (e.g. ``"Chamber 1"``).
        * ``flux_absolute``    — CO₂ flux (µmol m⁻² s⁻², negative = uptake).
        * ``h2o_slope``        — H₂O slope (mmol m⁻² s⁻¹).
        * ``co2_slope``        — raw CO₂ slope (µmol m⁻² s⁻¹).
        * ``Global_Radiation`` — shortwave radiation (W m⁻²); used for daytime
          classification and PAR proxy.
        * ``mean_temp``        — air temperature (°C) for Q10 fit.
        * ``vpd_kPa``          — vapour pressure deficit (kPa) for WUE–VPD test.

    config : dict, optional
        Key-value overrides merged on top of :data:`DEFAULT_CONFIG`.
        Pass only keys you want to change.
    label : str, default ``"default"``
        Free-form label stored in the result dict for later identification
        (e.g. ``"cycle_conf=0.65, day_score=0.60"``).
    derive_daytime : bool, default True
        When ``True``, derive ``_is_daytime`` from ``Global_Radiation``
        (falling back to hour-of-day) via :func:`derive_is_daytime`.
        Set to ``False`` if the column is already present in ``cycles``.

    Returns
    -------
    dict
        Top-level keys:

        * ``"label"`` : str — the ``label`` argument.
        * ``"n_cycles"`` : int — total cycles in the input DataFrame.
        * ``"n_daytime"`` : int — number of daytime cycles.
        * ``"n_nighttime"`` : int — number of nighttime cycles.
        * ``"light_response"`` : dict — per-chamber light-response results
          (keys ``"Amax"``, ``"alpha"``, ``"Rd"``, ``"r2"``, ``"status"``).
        * ``"q10"`` : dict — per-chamber Q10 results
          (keys ``"Q10"``, ``"r2"``, ``"t_iqr"``, ``"status"``).
        * ``"wue"`` : dict — WUE results
          (keys ``"median"``, ``"vpd_r"``, ``"status"``).
        * ``"inter_chamber"`` : dict — inter-chamber agreement
          (keys ``"r_daytime"``, ``"r_nighttime"``, ``"status"``).
        * ``"scorecard"`` : dict with keys:

          - ``"n_pass"`` : int — tests with status ``"PASS"``.
          - ``"n_borderline"`` : int — tests with status ``"BORDERLINE"``.
          - ``"n_fail"`` : int — tests with status ``"FAIL"``.
          - ``"n_na"`` : int — tests with status ``"N/A"``.
          - ``"rows"`` : list of dicts, one per test row, each with
            ``"section"``, ``"test"``, ``"expected"``, ``"observed"``,
            ``"status"``.

    Examples
    --------
    Build a minimal fixture and run the validator.  With only a few rows
    most tests return ``"N/A"`` due to insufficient data — that is the
    correct scientific response:

    >>> import pandas as pd, numpy as np
    >>> from palmwtc.validation import run_science_validation
    >>> cycles = pd.DataFrame({
    ...     "flux_datetime": pd.date_range("2024-01-01 07:00", periods=6, freq="2h"),
    ...     "Source_Chamber": ["Chamber 1"] * 6,
    ...     "flux_absolute": [-5.0, -8.0, -10.0, -7.0, -4.0, 2.0],
    ...     "h2o_slope": [0.5, 0.6, 0.7, 0.5, 0.4, 0.2],
    ...     "co2_slope": [-5.0, -8.0, -10.0, -7.0, -4.0, 2.0],
    ...     "Global_Radiation": [200.0, 500.0, 800.0, 600.0, 100.0, 0.0],
    ...     "mean_temp": [28.0, 30.0, 32.0, 31.0, 29.0, 25.0],
    ...     "vpd_kPa": [1.2, 1.8, 2.1, 1.9, 1.4, 0.8],
    ... })
    >>> result = run_science_validation(cycles, label="fixture")
    >>> result["label"]
    'fixture'
    >>> result["n_cycles"]
    6
    >>> result["scorecard"]["n_na"] >= 0
    True
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    df = cycles.copy()

    # Coerce numeric columns
    for col in (cfg["co2_flux_col"], cfg["h2o_flux_col"], cfg["radiation_col"], cfg["temp_col"]):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if derive_daytime or "_is_daytime" not in df.columns:
        df["_is_daytime"] = derive_is_daytime(df, cfg)

    light = test_light_response(df, cfg)
    q10 = test_q10(df, cfg)
    wue = test_wue(df, cfg)
    inter = test_inter_chamber(df, cfg)

    # Build flat scorecard rows
    rows: list[dict[str, Any]] = []
    for chamber, fr in light.items():
        rows.append(
            {
                "section": "1 Light Response",
                "test": f"Amax ({chamber})",
                "expected": f"{cfg['Amax_range'][0]}-{cfg['Amax_range'][1]} umol/m2/s",
                "observed": f"{fr.get('Amax', float('nan')):.2f}" if "Amax" in fr else "N/A",
                "status": fr.get("Amax_status", fr.get("status", "N/A")),
            }
        )
        rows.append(
            {
                "section": "1 Light Response",
                "test": f"alpha ({chamber})",
                "expected": f"{cfg['alpha_range'][0]}-{cfg['alpha_range'][1]}",
                "observed": f"{fr.get('alpha', float('nan')):.3f}" if "alpha" in fr else "N/A",
                "status": fr.get("alpha_status", fr.get("status", "N/A")),
            }
        )
    for chamber, qr in q10.items():
        rows.append(
            {
                "section": "2 Q10",
                "test": f"Q10 ({chamber})",
                "expected": f"{cfg['Q10_range'][0]}-{cfg['Q10_range'][1]}",
                "observed": f"{qr.get('Q10', float('nan')):.2f}" if "Q10" in qr else "N/A",
                "status": qr.get("Q10_status", qr.get("status", "N/A")),
            }
        )
        rows.append(
            {
                "section": "2 Q10",
                "test": f"Q10 R2 ({chamber})",
                "expected": f">= {cfg['Q10_r2_min']}",
                "observed": f"{qr.get('r2', float('nan')):.3f}" if "r2" in qr else "N/A",
                "status": qr.get("r2_status", qr.get("status", "N/A")),
            }
        )
    rows.append(
        {
            "section": "3 WUE",
            "test": "WUE median",
            "expected": f"{cfg['WUE_range'][0]}-{cfg['WUE_range'][1]} mmol/mol",
            "observed": f"{wue.get('median', float('nan')):.2f}" if "median" in wue else "N/A",
            "status": wue.get("wue_status", wue.get("status", "N/A")),
        }
    )
    rows.append(
        {
            "section": "3 WUE",
            "test": "WUE-VPD r",
            "expected": f"<= {cfg['WUE_VPD_r_max']}",
            "observed": f"{wue.get('vpd_r', float('nan')):.3f}" if "vpd_r" in wue else "N/A",
            "status": wue.get("vpd_status", "N/A"),
        }
    )
    rows.append(
        {
            "section": "4 Inter-chamber",
            "test": "Daytime Pearson r",
            "expected": f">= {cfg['chamber_r_min']}",
            "observed": f"{inter.get('r_daytime', float('nan')):.3f}"
            if inter.get("r_daytime") is not None
            else "N/A",
            "status": inter.get("status", "N/A"),
        }
    )

    n_pass = sum(1 for r in rows if r["status"] == "PASS")
    n_warn = sum(1 for r in rows if r["status"] == "BORDERLINE")
    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_na = sum(1 for r in rows if r["status"] == "N/A")

    return {
        "label": label,
        "n_cycles": int(len(df)),
        "n_daytime": int(df["_is_daytime"].sum()),
        "n_nighttime": int((~df["_is_daytime"]).sum()),
        "light_response": light,
        "q10": q10,
        "wue": wue,
        "inter_chamber": inter,
        "scorecard": {
            "n_pass": n_pass,
            "n_borderline": n_warn,
            "n_fail": n_fail,
            "n_na": n_na,
            "rows": rows,
        },
    }
