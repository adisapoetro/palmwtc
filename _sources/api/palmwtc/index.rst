palmwtc
=======

.. py:module:: palmwtc

.. autoapi-nested-parse::

   palmwtc — Automated whole-tree chamber workflow for oil-palm ecophysiology.

   Top-level convenience re-exports of the most-used symbols. Subpackages
   (``palmwtc.io``, ``palmwtc.qc``, ``palmwtc.flux``, ``palmwtc.windows``,
   ``palmwtc.validation``, ``palmwtc.viz``, ``palmwtc.hardware``) are
   importable directly and own the full per-area public API.

   Symbols whose names collide across subpackages (e.g. ``DEFAULT_CONFIG``,
   which differs in shape between ``flux``, ``windows``, and ``validation``)
   are NOT re-exported here — import them from the subpackage to avoid
   ambiguity.



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/cli/index
   /api/palmwtc/config/index
   /api/palmwtc/data/index
   /api/palmwtc/flux/index
   /api/palmwtc/hardware/index
   /api/palmwtc/io/index
   /api/palmwtc/notebooks_runner/index
   /api/palmwtc/pipeline/index
   /api/palmwtc/qc/index
   /api/palmwtc/validation/index
   /api/palmwtc/viz/index
   /api/palmwtc/windows/index


Attributes
----------

.. autoapisummary::

   palmwtc.__version__


Classes
-------

.. autoapisummary::

   palmwtc.QCProcessor
   palmwtc.WindowSelector


Functions
---------

.. autoapisummary::

   palmwtc.calculate_absolute_flux
   palmwtc.calculate_flux_cycles
   palmwtc.calculate_h2o_absolute_flux
   palmwtc.calculate_h2o_flux_cycles
   palmwtc.compute_closure_confidence
   palmwtc.compute_day_scores
   palmwtc.identify_cycles
   palmwtc.prepare_chamber_data
   palmwtc.score_cycle
   palmwtc.score_day_quality
   palmwtc.find_latest_qc_file
   palmwtc.get_cloud_sensor_dirs
   palmwtc.get_usecols
   palmwtc.load_from_multiple_dirs
   palmwtc.load_monthly_data
   palmwtc.load_radiation_data
   palmwtc.apply_iqr_flags
   palmwtc.apply_physical_bounds_flags
   palmwtc.combine_qc_flags
   palmwtc.detect_breakpoints_ruptures
   palmwtc.detect_drift_windstats
   palmwtc.process_variable_qc
   palmwtc.render_field_alert_html
   palmwtc.derive_is_daytime
   palmwtc.run_science_validation
   palmwtc.interactive_flux_dashboard
   palmwtc.plot_flux_heatmap
   palmwtc.plot_tropical_seasonal_diurnal
   palmwtc.set_style
   palmwtc.merge_sensor_qc_onto_cycles


Package Contents
----------------

.. py:function:: calculate_absolute_flux(row: pandas.Series) -> float

   Compute the absolute CO₂ flux from a chamber-cycle slope.

   Converts a CO₂ concentration rate measured inside a closed whole-tree
   chamber (ppm s⁻¹) into an absolute flux on the tree's ground-footprint
   basis (µmol m⁻² s⁻¹). Chamber volume is selected from the measurement
   date because the chambers were resized as the palms grew.

   Parameters
   ----------
   row : pd.Series
       One row of a chamber-cycle table. Must contain:

       ``flux_slope`` : float
           CO₂ concentration rate during closure (ppm s⁻¹). Negative when
           the tree is releasing CO₂ (net respiration); positive when CO₂
           is being consumed.
       ``flux_date`` : pd.Timestamp
           When the cycle was measured. Used to pick chamber volume from
           the internal resize schedule. If absent, returns ``numpy.nan``.

       Optional columns (safe to omit):

       ``mean_temp`` : float, default 25.0
           Chamber-internal air temperature during the cycle (°C).
           Falls back to 25 °C when absent or NaN.
       ``tree_volume`` : float, default 0.0
           Estimated palm trunk + frond volume (m³) to subtract from the
           base chamber volume. Falls back to 0 when absent or NaN.

   Returns
   -------
   float
       Absolute CO₂ flux in µmol m⁻² s⁻¹ (whole-tree ground-footprint
       basis).

       **Sign convention**: negative = net CO₂ release by the tree
       (respiration > photosynthesis); positive = net CO₂ uptake.
       This mirrors the sign of ``flux_slope``.

   Raises
   ------
   KeyError
       If ``flux_slope`` is missing from ``row``.

   Notes
   -----
   The conversion formula is:

   .. code-block:: none

       flux = flux_slope × (P_std / (R × T_K)) × (V_net / A)

   where ``P_std = 101325 Pa`` (constant), ``R = 8.314 J mol⁻¹ K⁻¹``,
   ``T_K = mean_temp + 273.15``.

   Because ``flux_slope`` is in ppm s⁻¹ (= 10⁻⁶ mol mol⁻¹ s⁻¹) and the
   molar air density ``P/(RT)`` is in mol m⁻³, the product gives
   10⁻⁶ mol m⁻² s⁻¹ = µmol m⁻² s⁻¹ directly.

   Chamber volume comes from the hard-coded resize schedule (cutoff
   2025-07-01). The optional ``tree_volume`` subtraction is clamped so
   the net volume never falls below 0.1 m³.

   Examples
   --------
   >>> import pandas as pd
   >>> from palmwtc.flux.absolute import calculate_absolute_flux
   >>> row = pd.Series({
   ...     'flux_slope': -0.5,
   ...     'flux_date': pd.Timestamp('2024-06-15'),
   ...     'mean_temp': 28.0,
   ... })
   >>> round(calculate_absolute_flux(row), 2)
   -40.47

   A missing ``flux_date`` returns NaN (the cycle cannot be assigned to
   a chamber size):

   >>> row_no_date = pd.Series({'flux_slope': -0.5, 'mean_temp': 28.0})
   >>> import numpy as np
   >>> bool(np.isnan(calculate_absolute_flux(row_no_date)))
   True

   See Also
   --------
   calculate_h2o_absolute_flux : Water-vapour analogue of this function.
   palmwtc.flux.cycles.calculate_flux_cycles : Batch version applying
       this per-cycle to a full cycles DataFrame.


.. py:function:: calculate_flux_cycles(chamber_df, chamber_name, cycle_gap_sec=300, start_cutoff_sec=50, start_search_sec=60, min_points=20, min_duration_sec=180, outlier_z=2, max_outlier_refit_frac=0.2, use_multiprocessing=True, n_jobs=None, **kwargs)

   Identify measurement cycles and compute CO₂ flux for each cycle.

   This is the main CO₂ flux batch function.  It calls
   :func:`palmwtc.flux.cycles.identify_cycles` to segment the time series
   into closed-chamber measurement cycles, then dispatches each cycle to
   :func:`palmwtc.flux.cycles.evaluate_cycle` (optionally in parallel via
   :class:`multiprocessing.Pool`).

   Parameters
   ----------
   chamber_df : pd.DataFrame
       Output of :func:`prepare_chamber_data`.  Must contain ``TIMESTAMP``,
       ``CO2``, and optionally ``Temp`` and ``Flag``.
   chamber_name : str
       Human-readable chamber label, stored in the output column
       ``Source_Chamber`` (e.g. ``'Chamber 1'``).
   cycle_gap_sec : int
       Time gap in seconds that triggers a new cycle boundary.  Default
       ``300`` (5 minutes).
   start_cutoff_sec : int
       Seconds to skip from cycle start before beginning the regression
       window search.  Removes the initial chamber-mixing transient.
       Default ``50``.
   start_search_sec : int
       How far into the cycle (seconds) the window-start search extends.
       Default ``60``.
   min_points : int
       Minimum number of valid points required for a cycle to be processed.
       Default ``20``.
   min_duration_sec : int
       Minimum regression window length in seconds.  Default ``180``.
   outlier_z : float
       Z-score threshold for iterative outlier removal.  Default ``2``.
   max_outlier_refit_frac : float
       Maximum fraction of points that may be removed as outliers; if
       exceeded the original fit is used.  Default ``0.2``.
   use_multiprocessing : bool
       When ``True`` and there are more than 50 cycles, process in parallel
       using :class:`multiprocessing.Pool`.  Falls back to serial on any
       multiprocessing error.  Default ``True``.
   n_jobs : int or None
       Number of parallel workers.  Defaults to ``min(8, cpu_count)``.
   **kwargs
       Absorbed silently so callers can pass ``**DEFAULT_CONFIG`` directly.

   Returns
   -------
   pd.DataFrame
       One row per successfully processed cycle.  Columns (from
       :func:`palmwtc.flux.cycles.evaluate_cycle`):

       - ``Source_Chamber`` — *chamber_name*.
       - ``cycle_id`` — integer cycle identifier.
       - ``flux_date`` — start timestamp of the cycle.
       - ``cycle_end`` — end timestamp of the cycle.
       - ``cycle_duration_sec`` — total cycle duration in seconds.
       - ``window_start_sec``, ``window_end_sec`` — regression window
         boundaries relative to cycle start.
       - ``duration_sec`` — regression window duration in seconds.
       - ``n_points_total`` — total points in the full cycle.
       - ``n_points_used`` — points used in the final regression.
       - ``flux_slope`` — OLS slope of CO₂ vs. time (ppm s⁻¹).
       - ``flux_intercept`` — OLS intercept (ppm).
       - ``r2`` — R² of the OLS linear fit.
       - ``p_value``, ``std_err`` — regression statistics.
       - ``rmse`` — root-mean-square error of the fit (ppm).
       - ``nrmse`` — RMSE normalized by the CO₂ range in the window.
       - ``snr`` — signal-to-noise ratio: ``|slope| × duration / rmse``.
       - ``snr_noise`` — SNR using early-cycle noise estimate (NaN if
         not computed).
       - ``noise_sigma`` — early-cycle noise standard deviation (ppm).
       - ``monotonicity`` — fraction of consecutive CO₂ steps moving in
         the slope direction (noise-filtered).
       - ``outlier_frac`` — fraction of points removed as outliers.
       - ``aicc_linear``, ``aicc_quadratic``, ``delta_aicc`` — AICc of
         the linear and quadratic fits; large negative ``delta_aicc``
         flags curvature.
       - ``slope_ts``, ``slope_ts_low``, ``slope_ts_high`` — Theil-Sen
         slope and 95 % confidence interval (ppm s⁻¹).
       - ``slope_diff_pct`` — relative difference between OLS and
         Theil-Sen slopes.
       - ``mean_temp`` — mean air temperature in the cycle (°C).
       - ``qc_flag`` — max hardware QC flag in the cycle.
       - ``co2_range`` — CO₂ concentration range in the window (ppm).
       - ``bimodal_flag`` — ``True`` if a bimodal CO₂ distribution was
         detected (possible closure gap).
       - ``bimodal_gap_ppm``, ``bimodal_lower_mean``,
         ``bimodal_upper_mean`` — bimodal split statistics.
       - ``flux_absolute`` — absolute flux in µmol m⁻² s⁻¹ computed by
         :func:`palmwtc.flux.absolute.calculate_absolute_flux`.

       Returns an empty DataFrame if *chamber_df* is empty or contains no
       valid cycles.

   See Also
   --------
   prepare_chamber_data : Produces the required *chamber_df* input.
   calculate_h2o_flux_cycles : H₂O analogue.
   palmwtc.flux.cycles.evaluate_cycle : Called for each individual cycle.
   palmwtc.flux.cycles.score_cycle : QC scoring applied after this step.

   Examples
   --------
   # doctest: +SKIP
   # Requires prepared chamber data from prepare_chamber_data().
   flux_df = calculate_flux_cycles(chamber_df, "Chamber 1")
   print(flux_df[["flux_date", "flux_slope", "r2", "flux_absolute"]].head())


.. py:function:: calculate_h2o_absolute_flux(row: pandas.Series) -> float

   Compute the absolute H₂O flux from a chamber-cycle slope.

   Converts a water-vapour mixing-ratio rate measured inside a closed
   whole-tree chamber (mmol mol⁻¹ s⁻¹) into an absolute flux on the tree's
   ground-footprint basis (mmol m⁻² s⁻¹). Uses the same chamber geometry
   and ideal-gas-law conversion as :func:`calculate_absolute_flux`.

   Parameters
   ----------
   row : pd.Series
       One row of a chamber-cycle table. Must contain:

       ``h2o_slope`` : float
           H₂O mixing-ratio rate during closure (mmol mol⁻¹ s⁻¹). Positive
           when water vapour is accumulating inside the chamber
           (transpiration). If absent or NaN, returns ``numpy.nan``.
       ``flux_date`` : pd.Timestamp
           When the cycle was measured. Used to pick chamber volume from
           the internal resize schedule. If absent, returns ``numpy.nan``.

       Optional columns (safe to omit):

       ``mean_temp`` : float, default 25.0
           Chamber-internal air temperature during the cycle (°C).
           Falls back to 25 °C when absent or NaN.
       ``tree_volume`` : float, default 0.0
           Estimated palm trunk + frond volume (m³) to subtract from the
           base chamber volume. Falls back to 0 when absent or NaN.

   Returns
   -------
   float
       Absolute H₂O flux in mmol m⁻² s⁻¹ (whole-tree ground-footprint
       basis).

       **Sign convention**: positive = net water-vapour release by the
       tree (transpiration); negative = net condensation.
       This mirrors the sign of ``h2o_slope``.

       Returns ``numpy.nan`` if ``h2o_slope`` or ``flux_date`` is
       missing / NaN.

   Notes
   -----
   The conversion formula is identical to that of
   :func:`calculate_absolute_flux`:

   .. code-block:: none

       flux = h2o_slope × (P_std / (R × T_K)) × (V_net / A)

   where ``P_std = 101325 Pa``, ``R = 8.314 J mol⁻¹ K⁻¹``.

   Because ``h2o_slope`` is already in mmol mol⁻¹ s⁻¹ (= 10⁻³ mol mol⁻¹ s⁻¹)
   and the molar air density ``P/(RT)`` is in mol m⁻³, the product gives
   10⁻³ mol m⁻² s⁻¹ = mmol m⁻² s⁻¹ directly (no additional unit
   conversion needed).

   Chamber volume comes from the same date-based resize schedule used
   by :func:`calculate_absolute_flux` (cutoff 2025-07-01).

   Examples
   --------
   >>> import pandas as pd
   >>> from palmwtc.flux.absolute import calculate_h2o_absolute_flux
   >>> row = pd.Series({
   ...     'h2o_slope': 0.1,
   ...     'flux_date': pd.Timestamp('2024-06-15'),
   ...     'mean_temp': 28.0,
   ... })
   >>> round(calculate_h2o_absolute_flux(row), 2)
   8.09

   A missing ``h2o_slope`` returns NaN:

   >>> row_no_slope = pd.Series({
   ...     'flux_date': pd.Timestamp('2024-06-15'),
   ...     'mean_temp': 28.0,
   ... })
   >>> import numpy as np
   >>> bool(np.isnan(calculate_h2o_absolute_flux(row_no_slope)))
   True

   See Also
   --------
   calculate_absolute_flux : CO₂ analogue of this function.
   palmwtc.flux.cycles.calculate_flux_cycles : Batch version applying
       CO₂ flux per-cycle to a full cycles DataFrame.


.. py:function:: calculate_h2o_flux_cycles(chamber_df, chamber_name, cycle_gap_sec=300, min_points=20, min_duration_sec=180, h2o_qc_thresholds=None, **kwargs)

   Compute H₂O flux for every cycle in *chamber_df*.

   Mirrors :func:`calculate_flux_cycles` for water vapour.  For each cycle,
   calls :func:`calculate_h2o_flux_for_cycle` and then
   :func:`score_h2o_flux_qc`, automatically switching to nighttime thresholds
   when Global_Radiation < 10 W m⁻² (or when the cycle starts before 06:00
   or after 18:00, if radiation is not available).

   Parameters
   ----------
   chamber_df : pd.DataFrame
       Output of :func:`prepare_chamber_data`.  Must contain ``TIMESTAMP``
       and ``H2O``; optionally ``Global_Radiation`` for nighttime detection.
   chamber_name : str
       Chamber label stored in ``Source_Chamber`` (e.g. ``'Chamber 1'``).
   cycle_gap_sec : int
       Gap in seconds that marks cycle boundaries.  Default ``300``.
   min_points : int
       Minimum valid H₂O points required per cycle.  Default ``20``.
   min_duration_sec : float
       Minimum cycle duration in seconds.  Default ``180``.
   h2o_qc_thresholds : dict or None
       Override the daytime H₂O thresholds.  Nighttime thresholds are
       always selected automatically from :data:`NIGHTTIME_H2O_QC_THRESHOLDS`
       regardless of this parameter.  Default: :data:`DEFAULT_H2O_QC_THRESHOLDS`.
   **kwargs
       Absorbed silently so callers can pass ``**DEFAULT_CONFIG`` directly.

   Returns
   -------
   pd.DataFrame
       One row per valid cycle.  Columns:

       - ``cycle_id`` — integer cycle identifier.
       - ``Source_Chamber`` — *chamber_name*.
       - ``h2o_qc`` — QC tier: 0 = A, 1 = B, 2 = C.
       - ``h2o_qc_label`` — ``'A'``, ``'B'``, or ``'C'``.
       - ``h2o_qc_reason`` — semicolon-separated failing-test strings.
       - All keys returned by :func:`calculate_h2o_flux_for_cycle`:
         ``h2o_slope``, ``h2o_intercept``, ``h2o_r2``, ``h2o_nrmse``,
         ``h2o_snr``, ``h2o_outlier_frac``, ``h2o_monotonic_frac``,
         ``h2o_n_points``, ``h2o_duration``, ``h2o_conc_mean``,
         ``h2o_conc_range``.

       Returns an empty DataFrame if *chamber_df* is empty, has no ``H2O``
       column, or all H₂O values are NaN.

   See Also
   --------
   calculate_flux_cycles : CO₂ analogue.
   prepare_chamber_data : Produces the required *chamber_df* input.
   score_h2o_flux_qc : H₂O QC grading function.

   Examples
   --------
   # doctest: +SKIP
   # Requires prepared chamber data from prepare_chamber_data().
   h2o_df = calculate_h2o_flux_cycles(chamber_df, "Chamber 1")
   print(h2o_df[["cycle_id", "h2o_slope", "h2o_qc_label"]].head())


.. py:function:: compute_closure_confidence(r2, nrmse, global_radiation, rad_max=800.0)

   Compute a chamber closure confidence score between 0 and 1.

   Combines R², NRMSE, and global radiation into a single scalar that
   expresses how confident we are that the chamber was properly sealed
   during a flux cycle.

   Physical reasoning: poor fit quality (low R², high NRMSE) is more
   likely to indicate a physical leak when photosynthetic demand is high
   (bright conditions).  The same poor fit at night or on a cloudy day
   could simply reflect a small signal close to sensor noise.  The score
   therefore penalizes low R² and high NRMSE more strongly when radiation
   is high.

   Formula
   -------
   .. math::

       r2\_conf = clip\left(\frac{R^2 - 0.25}{0.94 - 0.25}, 0, 1\right)

       rad\_norm = clip\left(\frac{G}{G_{max}}, 0, 1\right)

       confidence = clip\left(r2\_conf
           - 0.4 \times rad\_norm \times (1 - r2\_conf)
           - 0.2 \times rad\_norm \times clip(NRMSE / 0.20, 0, 1),
       0, 1\right)

   Parameters
   ----------
   r2 : float or array-like
       R² of the OLS linear CO₂ vs. time fit (0–1).  NaN is treated as 0.
   nrmse : float or array-like
       Normalized RMSE (RMSE / CO₂ range).  NaN is treated as 0.
   global_radiation : float or array-like
       Incoming solar radiation in W m⁻².  NaN is treated as 0 (worst-case
       penalty removed).
   rad_max : float
       Radiation level at which the radiation penalty is at its maximum.
       Default ``800.0`` W m⁻² (typical clear-sky midday value in the
       tropics).

   Returns
   -------
   float or numpy.ndarray
       Closure confidence score in [0, 1].  A score near 1 indicates a
       well-sealed chamber with a clean linear CO₂ trend.  A score near 0
       indicates likely leakage or strong non-linearity under high light.

   Notes
   -----
   The R² bounds (0.25 to 0.94) and penalty weights (0.4, 0.2) were
   calibrated against manual inspection of gap-width experiment data.

   See Also
   --------
   calculate_flux_cycles : Produces the R², NRMSE, and radiation values
       consumed here.

   Examples
   --------
   >>> from palmwtc.flux.chamber import compute_closure_confidence
   >>> round(float(compute_closure_confidence(0.98, 0.03, 0.0)), 3)
   1.0
   >>> round(float(compute_closure_confidence(0.95, 0.05, 200.0)), 3)
   0.988
   >>> round(float(compute_closure_confidence(0.50, 0.25, 600.0)), 3)
   0.021
   >>> round(float(compute_closure_confidence(0.40, 0.30, 700.0)), 3)
   0.0


.. py:function:: compute_day_scores(flux_df: pandas.DataFrame, day_score_threshold: float = 0.6) -> pandas.DataFrame

   Apply :func:`score_day_quality` across all days and chambers and merge back.

   This is the top-level aggregation step that runs after per-cycle scoring
   (:func:`score_cycle`) and temporal coherence flagging
   (:func:`compute_temporal_coherence`).  It:

   1. Extracts the date from ``flux_datetime`` or ``flux_date``.
   2. Filters to clean cycles (``flux_qc <= 1``, ``temporal_coherence_flag == 0``,
      ``hourly_cv_flag == 0``).
   3. Groups by (date, chamber) and calls :func:`score_day_quality`.
   4. Left-merges the three summary columns (``day_score``,
      ``n_cycles_daytime``, ``n_hours_covered``) back onto the full
      DataFrame so every row carries its day's score.

   Days that do not meet :func:`score_day_quality`'s eligibility criteria
   (< 3 cycles or < 4 hours) receive ``day_score = 0.0``.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Full cycle-level DataFrame as produced by
       :func:`~palmwtc.flux.chamber.calculate_flux_cycles`.  Must contain:

       - ``flux_qc`` — rule-based QC flag (0, 1, 2).
       - ``temporal_coherence_flag`` — from :func:`compute_temporal_coherence`.
       - ``hourly_cv_flag`` — from :func:`compute_temporal_coherence`.
       - ``flux_datetime`` or ``flux_date`` — cycle timestamp.
       - ``Source_Chamber`` — chamber identifier (optional; if present,
         scores are computed separately per chamber).

   day_score_threshold : float
       Informational threshold for downstream summary statistics (default 0.60).
       Days below this value are considered low-quality in summary reports.
       This parameter does **not** filter any rows.

   Returns
   -------
   pd.DataFrame
       Copy of ``flux_df`` with three new columns merged in:

       ``day_score`` : float
           Composite 0–1 quality score for the cycle's date and chamber.
           0.0 for days with insufficient data.
       ``n_cycles_daytime`` : int
           Number of passing daytime cycles on that date.
       ``n_hours_covered`` : int
           Number of distinct daytime hours with passing cycles.

   See Also
   --------
   score_day_quality : Scoring logic for a single (date, chamber) group.
   compute_temporal_coherence : Must be called before this function.

   Examples
   --------
   >>> import pandas as pd  # doctest: +SKIP
   >>> # Requires a full flux DataFrame from calculate_flux_cycles() and
   >>> # compute_temporal_coherence(); see tutorial notebook 032.


.. py:function:: identify_cycles(data: pandas.DataFrame, time_col: str = 'TIMESTAMP', gap_sec: float = CYCLE_GAP_SEC) -> pandas.DataFrame

   Assign a monotonically increasing cycle ID to each row.

   A new cycle starts whenever the time gap between consecutive rows
   exceeds ``gap_sec`` seconds.  The function sorts by ``time_col`` first,
   so row order in the input does not matter.

   Parameters
   ----------
   data : pd.DataFrame
       Raw sensor DataFrame.  Must contain a datetime-like column named
       ``time_col``.
   time_col : str
       Name of the datetime column (default ``'TIMESTAMP'``).
   gap_sec : float
       Gap threshold in seconds.  Any gap larger than this value starts a
       new cycle (default :data:`CYCLE_GAP_SEC` = 300 s).

   Returns
   -------
   pd.DataFrame
       Copy of ``data`` sorted by ``time_col`` with three new columns:

       ``delta_t_sec`` : float
           Seconds elapsed since the previous row (NaN for the first row).
       ``new_cycle`` : bool
           True where a new cycle begins (gap > ``gap_sec`` or first row).
       ``cycle_id`` : int
           Zero-based cumulative cycle counter.  All rows belonging to the
           same closure event share the same integer ID.

   Examples
   --------
   >>> import pandas as pd
   >>> from palmwtc.flux.cycles import identify_cycles
   >>> ts = pd.to_datetime(["2024-01-01 08:00:00", "2024-01-01 08:00:30",
   ...                      "2024-01-01 08:10:00"])  # 9.5-min gap → new cycle
   >>> df = pd.DataFrame({"TIMESTAMP": ts, "CO2": [400, 401, 402]})
   >>> out = identify_cycles(df)
   >>> list(out["cycle_id"])
   [1, 1, 2]


.. py:function:: prepare_chamber_data(data, chamber_suffix, accepted_co2_qc_flags=(0, ), accepted_h2o_qc_flags=(0, 1), prefer_corrected_h2o=True, require_h2o_for_wpl=False, apply_wpl=False, h2o_valid_range=(0.0, 60.0), max_abs_wpl_rel_change=0.12, **kwargs)

   Select, filter, and WPL-correct sensor streams for one chamber.

   This is the first step in the flux pipeline.  It takes the full
   multi-chamber dataset (as loaded by :mod:`palmwtc.io`), extracts the
   columns for a single chamber, applies QC flag row-filtering, and runs the
   WPL dilution correction.  The returned DataFrame is the direct input for
   :func:`calculate_flux_cycles` and :func:`calculate_h2o_flux_cycles`.

   Parameters
   ----------
   data : pd.DataFrame
       Full QC-flagged dataset.  Expected columns (where ``{s}`` = suffix):

       - ``TIMESTAMP`` — datetime column.
       - ``CO2_{s}`` — raw (wet) CO₂ in ppm.
       - ``H2O_{s}`` or ``H2O_{s}_corrected`` — water vapour in mmol mol⁻¹.
       - ``Temp_1_{s}`` — air temperature inside the chamber in °C.
       - ``CO2_{s}_qc_flag`` — integer QC flag for CO₂ (0 = good).
       - ``H2O_{s}_qc_flag`` — integer QC flag for H₂O (0 = good, 1 = minor).

       Missing columns are silently skipped; only ``TIMESTAMP`` and ``CO2``
       are required in the output.
   chamber_suffix : str
       Chamber identifier appended to column names.  Typically ``'C1'`` or
       ``'C2'`` for the two whole-tree chambers.
   accepted_co2_qc_flags : list of int or None
       Keep only rows whose ``CO2_{suffix}_qc_flag`` is in this list.
       Pass ``None`` to skip CO₂ flag filtering entirely.
       Default from :data:`DEFAULT_CONFIG`: ``[0]``.
   accepted_h2o_qc_flags : list of int or None
       Same for H₂O.  Default from :data:`DEFAULT_CONFIG`: ``[0, 1]``
       (flag 1 is a minor sensor warning that still yields usable H₂O).
   prefer_corrected_h2o : bool
       When ``True`` (default), use ``H2O_{suffix}_corrected`` if present;
       fall back to ``H2O_{suffix}`` otherwise.
   require_h2o_for_wpl : bool
       When ``True`` (default), raise :exc:`ValueError` if no H₂O column
       is found and ``apply_wpl=True``.  Set to ``False`` to fall back to
       the uncorrected wet CO₂ value.
   apply_wpl : bool
       When ``True`` (default), run :func:`apply_wpl_correction` and expose
       diagnostic columns.  When ``False``, ``CO2`` is set equal to
       ``CO2_raw`` and all WPL columns are NaN/0.
   h2o_valid_range : tuple of float
       ``(lo, hi)`` physical validity range for H₂O in mmol mol⁻¹.
       Values outside this range are set to NaN before WPL correction.
       Default: ``(0.0, 60.0)``.
   max_abs_wpl_rel_change : float
       Rows where ``|wpl_delta_ppm / CO2_raw|`` exceeds this value get
       their ``Flag`` upgraded to 2 (bad).  Default: ``0.12`` (12 %).
   **kwargs
       Extra keyword arguments are accepted but ignored.  This allows
       passing ``**DEFAULT_CONFIG`` directly without unpacking individual
       keys.

   Returns
   -------
   pd.DataFrame
       One row per retained timestamp, sorted by ``TIMESTAMP``, with a
       reset integer index.  Columns:

       - ``TIMESTAMP`` — datetime.
       - ``CO2`` — working CO₂ in ppm: WPL-corrected when possible, raw
         when WPL is disabled or H₂O is unavailable.
       - ``CO2_raw`` — original wet CO₂ measurement in ppm.
       - ``CO2_corrected`` — WPL-corrected CO₂ in ppm (NaN if WPL
         disabled or H₂O missing for a given row).
       - ``H2O`` — water vapour in mmol mol⁻¹ (NaN outside valid range).
       - ``Temp`` — air temperature in °C (NaN if column absent in input).
       - ``CO2_Flag`` — original CO₂ hardware QC flag (int).
       - ``H2O_Flag`` — original H₂O hardware QC flag (int).
       - ``Flag`` — combined flag: max(CO2_Flag, H2O_Flag), upgraded to 2
         for rows with excessive WPL correction.
       - ``wpl_factor`` — WPL multiplication factor per row (NaN if WPL
         disabled or H₂O missing).
       - ``wpl_valid_input`` — 1 where a valid WPL factor was computed, 0
         otherwise.
       - ``wpl_delta_ppm`` — ``CO2_corrected - CO2_raw`` in ppm.
       - ``wpl_rel_change`` — ``wpl_delta_ppm / CO2_raw`` (dimensionless).

   Raises
   ------
   ValueError
       If ``apply_wpl=True`` and ``require_h2o_for_wpl=True`` but no H₂O
       column is found for the requested ``chamber_suffix``.

   See Also
   --------
   calculate_flux_cycles : Consumes the output of this function for CO₂ flux.
   calculate_h2o_flux_cycles : Consumes the output for H₂O flux.
   summarize_wpl_correction : Computes dataset-level WPL statistics.

   Examples
   --------
   # doctest: +SKIP
   # Requires a real multi-chamber DataFrame from palmwtc.io.load_chamber_data.
   chamber_df = prepare_chamber_data(raw_df, "C1")
   print(chamber_df.columns.tolist())


.. py:function:: score_cycle(row: dict, raw_flag: int, thresholds: dict, enforce_hard_limits: bool = False, snr_field: str = 'snr', is_nighttime: bool = False, nighttime_thresholds: dict | None = None) -> tuple[int, int, str]

   Score a single flux cycle and return a three-part QC result.

   This function is called row-by-row from
   :func:`~palmwtc.flux.chamber.calculate_flux_cycles` after
   :func:`evaluate_cycle` has computed the cycle statistics.  It applies
   the A/B/C tier rule-based QC system and then combines the model score
   with the raw hardware sensor flag.

   A "good" cycle (QC flag 0, tier A) meets **all** of the following
   physical criteria:

   - **Enough data**: ≥ :data:`MIN_POINTS` usable points and fit window
     ≥ :data:`MIN_DURATION_SEC` seconds.
   - **Linear signal**: R² ≥ ``r2_A`` threshold (default 0.90 daytime) —
     the chamber concentration must rise or fall in a straight line,
     indicating steady-state respiration or photosynthesis flux.
   - **Low residuals**: NRMSE ≤ ``nrmse_A`` — normalised root-mean-square
     error (RMSE / CO₂ range) quantifies scatter around the linear fit.
   - **Detectable signal**: SNR ≥ ``snr_A`` — signal amplitude relative
     to noise floor; small but real respiratory signals at night often
     fall below the daytime SNR threshold, which is why
     :data:`NIGHTTIME_QC_THRESHOLDS` relaxes this to ``snr_A = 5``.
   - **Monotonic slope**: ≥ ``monotonic_A`` fraction of consecutive steps
     point in the same direction as the overall slope.  The threshold is
     scaled down for signals smaller than ``signal_ppm_guard`` ppm because
     instrument noise statistically produces non-monotonic steps for very
     small CO₂ changes.
   - **Few outliers**: outlier fraction ≤ ``outlier_A`` after MAD removal.
   - **Linear curvature**: the AICc improvement from fitting a quadratic
     instead of a linear model must be minimal (``delta_aicc > curvature_aicc``).
   - **OLS/Theil-Sen agreement**: relative slope difference
     ≤ ``slope_diff_A`` — large disagreement indicates leverage points or
     skewed scatter, suggesting the slope estimate is unreliable.

   Cycles that fail one or two of the B-tier thresholds receive flag 1
   (tier B, still usable with reduced confidence).  Cycles with ≥
   ``b_count_C`` B-tier issues or any single hard failure receive flag 2
   (tier C, excluded from flux aggregation by default).

   Parameters
   ----------
   row : dict-like
       Dictionary (or pandas Series) with at minimum the keys produced by
       :func:`evaluate_cycle`:
       ``n_points_used``, ``duration_sec``, ``r2``, ``nrmse``, ``snr``,
       ``monotonicity``, ``outlier_frac``, ``delta_aicc``,
       ``slope_diff_pct``, ``flux_slope``, ``flux_absolute``, ``co2_range``.
   raw_flag : int
       Raw hardware sensor QC flag from the LI-COR or logger (0 = good,
       1 = suspect, 2 = bad).  This is combined with the model score
       via ``max(model_qc, raw_flag)``.
   thresholds : dict
       Daytime QC threshold dict — typically :data:`QC_THRESHOLDS`.
       See the docstring of :data:`QC_THRESHOLDS` for all valid keys.
   enforce_hard_limits : bool
       If True, also apply the absolute physical limits in
       :data:`HARD_LIMITS` (extreme slope, extreme flux, large CO₂ range).
       Default False.
   snr_field : str
       Which SNR column to read from ``row``: ``'snr'`` (regression-based,
       default) or ``'snr_noise'`` (noise-floor-based, requires a
       pre-closure noise window in the raw data).
   is_nighttime : bool
       When True and ``nighttime_thresholds`` is provided, the relaxed
       :data:`NIGHTTIME_QC_THRESHOLDS` are used instead of ``thresholds``.
       Nighttime is defined as ``Global_Radiation < 10 W m⁻²``.
   nighttime_thresholds : dict or None
       Relaxed threshold dict for nighttime — typically
       :data:`NIGHTTIME_QC_THRESHOLDS`.  Ignored when ``is_nighttime=False``.

   Returns
   -------
   model_qc : int
       QC score from the statistical model alone (0, 1, or 2).
   combined_qc : int
       ``max(model_qc, raw_flag)`` — the final QC flag stored as
       ``flux_qc`` in the output DataFrame.
   reasons_str : str
       Semicolon-separated list of failure reasons, e.g.
       ``'r2_moderate;low_snr;sensor_flag_1'``.  Empty string when the
       cycle passes all checks.  Individual reason codes:

       ``too_few_points``         — fewer than ``min_points`` used points.
       ``short_duration``         — fit window < ``min_duration_sec``.
       ``low_r2``                 — R² < B threshold.
       ``r2_moderate``            — R² between A and B thresholds.
       ``high_nrmse``             — NRMSE > B threshold.
       ``nrmse_moderate``         — NRMSE between A and B thresholds.
       ``low_snr``                — SNR < B threshold.
       ``snr_moderate``           — SNR between A and B thresholds.
       ``non_monotonic``          — monotonicity < effective B threshold.
       ``monotonic_moderate``     — monotonicity between A and B thresholds.
       ``many_outliers``          — outlier fraction > B threshold.
       ``some_outliers``          — outlier fraction between A and B thresholds.
       ``curvature``              — AICc improvement for quadratic > B threshold.
       ``strong_curvature``       — AICc improvement > C threshold.
       ``slope_disagreement``     — OLS/Theil-Sen slope difference > threshold.
       ``many_moderate_issues:N`` — N B-tier issues demoted to C.
       ``extreme_slope``          — slope > :data:`HARD_LIMITS` max.
       ``extreme_flux``           — absolute flux > :data:`HARD_LIMITS` max.
       ``large_co2_range``        — CO₂ range > :data:`HARD_LIMITS` max.
       ``sensor_flag_N``          — raw hardware flag = N (1 or 2).

   See Also
   --------
   evaluate_cycle : Produces the per-cycle statistics that ``row`` must contain.
   compute_day_scores : Aggregates cycle scores to a daily composite.

   Examples
   --------
   >>> from palmwtc.flux.cycles import score_cycle, QC_THRESHOLDS
   >>> row = {
   ...     "n_points_used": 12, "duration_sec": 180, "r2": 0.95,
   ...     "nrmse": 0.05, "snr": 15.0, "monotonicity": 0.90,
   ...     "outlier_frac": 0.02, "delta_aicc": 1.0,
   ...     "slope_diff_pct": 0.10, "flux_slope": -0.05,
   ...     "flux_absolute": -2.0, "co2_range": 10.0,
   ... }
   >>> model_qc, combined_qc, reasons = score_cycle(row, raw_flag=0,
   ...                                              thresholds=QC_THRESHOLDS)
   >>> combined_qc  # passes all checks
   0
   >>> reasons
   ''


.. py:function:: score_day_quality(day_df: pandas.DataFrame, daytime_hours: range = range(7, 19)) -> dict | None

   Compute a 0–1 composite quality score for one day of flux data.

   This function is called once per (date, chamber) group by
   :func:`compute_day_scores` after filtering to passing cycles only.
   The score summarises five independent aspects of day quality:

   +----------+-------------------------------------------+--------+
   | Weight   | Criterion                                 | Max    |
   +==========+===========================================+========+
   | 0.30     | Temporal coverage                         | 1.0    |
   +----------+-------------------------------------------+--------+
   | 0.30     | Median R² of passing cycles               | 1.0    |
   +----------+-------------------------------------------+--------+
   | 0.20     | Sign consistency (fraction negative slope)| 1.0    |
   +----------+-------------------------------------------+--------+
   | 0.10     | Diurnal shape (peak uptake hour 09–14 h)  | 1.0    |
   +----------+-------------------------------------------+--------+
   | 0.10     | NRMSE quality (1 − mean_nrmse / 0.20)    | 1.0    |
   +----------+-------------------------------------------+--------+

   **Temporal coverage** is the number of unique hours covered divided by
   11 (the nominal 07:00–17:00 daytime window), capped at 1.0.

   **R² quality** is the median R² over all passing daytime cycles.
   This is more robust than the mean because a few outlier cycles with
   low R² do not dominate the score.

   **Sign consistency** is the fraction of cycles with a negative slope
   (net CO₂ uptake).  A value near 1.0 means the canopy was photosynthesising
   consistently throughout the day; near 0 means net respiration dominated.

   **Diurnal shape** scores 1.0 if the hour with the strongest median
   uptake (most negative slope) falls between 09:00 and 14:00, which is
   the physically expected peak photosynthesis window for oil palm.
   Otherwise 0.5.

   **NRMSE quality** penalises days with noisier cycles:
   ``max(0, 1 − mean_nrmse / 0.20)``.  A mean NRMSE of 0.20 or higher
   gives a zero contribution from this component.

   Parameters
   ----------
   day_df : pd.DataFrame
       Subset of the flux DataFrame for **one date and one chamber**, already
       filtered to passing cycles (``flux_qc <= 1`` and
       ``temporal_coherence_flag == 0``).  Must contain the columns
       ``flux_datetime`` or ``flux_date``, ``flux_slope`` or ``co2_slope``,
       ``r2`` or ``co2_r2``, and ``nrmse`` or ``co2_nrmse``.
   daytime_hours : range
       Hours treated as daytime (default ``range(7, 19)`` = 07:00–18:00
       inclusive).

   Returns
   -------
   dict or None
       Returns ``None`` if the day has fewer than 3 daytime cycles or fewer
       than 4 hours covered (insufficient data to score reliably).

       Otherwise a dict with keys:

       ``n_cycles_daytime`` : int
           Number of passing daytime cycles.
       ``n_hours_covered`` : int
           Number of distinct hours with at least one passing cycle.
       ``coverage_score`` : float [0, 1]
       ``quality_score`` : float [0, 1]   — median R².
       ``frac_negative`` : float [0, 1]   — fraction of cycles with negative slope.
       ``shape_score`` : float {0.5, 1.0} — diurnal shape.
       ``nrmse_score`` : float [0, 1]
       ``day_score`` : float [0, 1]       — weighted composite.

   See Also
   --------
   compute_day_scores : Applies this function across all days and chambers.

   Examples
   --------
   >>> import pandas as pd  # doctest: +SKIP
   >>> # Requires a filtered single-day flux DataFrame from
   >>> # calculate_flux_cycles(); see tutorial notebook 032.


.. py:function:: find_latest_qc_file(qc_dir: str | pathlib.Path, pattern: str = 'QC_Flagged_Data_*.csv', source: str = '020') -> pathlib.Path | None

   Find a QC output file in *qc_dir* by upstream pipeline stage.

   Searches for the canonical output file for a given pipeline stage.
   When the named file does not exist, falls back through a hierarchy
   of legacy filenames before returning ``None``.

   Lookup order
   ------------
   1. Named stage file (e.g. ``020_rule_qc_output.parquet``).
   2. ``QC_Flagged_Data_latest.parquet`` (legacy fixed name).
   3. Newest ``QC_Flagged_Data_*.parquet`` (legacy timestamped).
   4. Newest file matching *pattern* (CSV glob, newest-first).
   5. ``None`` if nothing matches.

   Parameters
   ----------
   qc_dir : str or pathlib.Path
       Directory to search for QC output files.
   pattern : str, optional
       Glob pattern used for the final CSV fallback.
       Default: ``"QC_Flagged_Data_*.csv"``.
   source : {"020", "022", "025", "026"}, optional
       Which pipeline stage's output to look for:

       - ``"020"`` → ``020_rule_qc_output.parquet``
       - ``"022"`` → ``022_ml_qc_output.parquet``
       - ``"025"`` → ``025_cross_chamber_corrected.parquet``
       - ``"026"`` → ``026_segmented_bias_corrected.parquet``

       Default: ``"020"``.

   Returns
   -------
   pathlib.Path or None
       Absolute path to the best-matching file, or ``None`` if no
       file was found.

   Examples
   --------
   Create a directory with a stage-020 output and resolve it:

   >>> import tempfile, pathlib
   >>> with tempfile.TemporaryDirectory() as d:
   ...     p = pathlib.Path(d)
   ...     _ = (p / "020_rule_qc_output.parquet").touch()
   ...     result = find_latest_qc_file(p, source="020")
   ...     result.name
   '020_rule_qc_output.parquet'

   When the named file is absent the function returns ``None``:

   >>> import tempfile, pathlib
   >>> with tempfile.TemporaryDirectory() as d:
   ...     find_latest_qc_file(pathlib.Path(d), source="020") is None
   True


.. py:function:: get_cloud_sensor_dirs(chamber_base: pathlib.Path | str) -> dict[str, list[dict]]

   Discover all raw-data directories for each sensor type under the cloud chamber base.

   Walks the Google Drive mount layout used by the LIBZ deployment.  The
   result is a dict of directory entries ready for
   :func:`~palmwtc.io.load_from_multiple_dirs`.

   Search order (determines deduplication priority in
   :func:`~palmwtc.io.load_from_multiple_dirs`):

   1. ``<chamber_base>/main/<sensor>/`` — primary archive; chamber
      subdirectories have monthly sub-folders (``is_flat=False``); climate
      and soil-sensor subdirectories are flat (``is_flat=True``).
   2. ``<chamber_base>/update_YYMMDD/<MM_sensortype>/`` — incremental update
      folders, sorted chronologically.  All are flat (``is_flat=True``).

   Sensor-type detection uses case-insensitive substring matching against
   the subdirectory name:

   - ``"chamber_1"`` — names containing ``"chamber1"`` or ``"chamber_1"``.
   - ``"chamber_2"`` — names containing ``"chamber2"`` or ``"chamber_2"``.
   - ``"climate"``   — names containing ``"climate"``.
   - ``"soil_sensor"`` — names containing ``"soil"``.

   Parameters
   ----------
   chamber_base : Path or str
       Root of the mounted Google Drive share for one chamber site
       (e.g. the local path of the shared drive folder).

   Returns
   -------
   dict[str, list[dict]]
       Keys are ``"chamber_1"``, ``"chamber_2"``, ``"climate"``, and
       ``"soil_sensor"``.  Each value is a list of ``{"path": Path,
       "is_flat": bool}`` dicts, suitable as the *dir_entries* argument of
       :func:`~palmwtc.io.load_from_multiple_dirs`.  Missing sensor types
       have an empty list.

   Examples
   --------
   >>> from pathlib import Path
   >>> from palmwtc.io import get_cloud_sensor_dirs
   >>> dirs = get_cloud_sensor_dirs(Path("/mnt/gdrive/LIBZ_Chamber"))  # doctest: +SKIP
   >>> list(dirs.keys())  # doctest: +SKIP
   ['chamber_1', 'chamber_2', 'climate', 'soil_sensor']


.. py:function:: get_usecols(path: str | pathlib.Path) -> list[str]

   Return the columns worth loading from a QC output file.

   Reads only the schema or header of the file (not the data rows) and
   returns the subset of columns that are needed for flux calculations
   and WPL corrections. Irrelevant columns are excluded to limit memory
   use when calling :func:`pandas.read_parquet` or
   :func:`pandas.read_csv`.

   The *required* set is::

       TIMESTAMP, CO2_C1, CO2_C2, Temp_1_C1, Temp_1_C2,
       CO2_C1_qc_flag, CO2_C2_qc_flag,
       H2O_C1, H2O_C2, H2O_C1_qc_flag, H2O_C2_qc_flag,
       H2O_C1_corrected, H2O_C2_corrected

   The *optional* set (included when present) is::

       RH_1_C1, RH_1_C2

   Parameters
   ----------
   path : str or pathlib.Path
       Path to a QC output file. Suffix determines the read strategy:
       ``".parquet"`` reads only the Parquet footer (fast, no data
       rows); any other extension reads the first row of a CSV header.

   Returns
   -------
   list of str
       Column names present in the file that belong to the required or
       optional sets, in the order they appear in the file schema.

   Examples
   --------
   >>> import tempfile, pathlib
   >>> import pandas as pd
   >>> with tempfile.TemporaryDirectory() as d:
   ...     f = pathlib.Path(d) / "qc.csv"
   ...     pd.DataFrame(columns=["TIMESTAMP", "CO2_C1", "junk"]).to_csv(f, index=False)
   ...     cols = get_usecols(f)
   ...     "TIMESTAMP" in cols and "CO2_C1" in cols and "junk" not in cols
   True


.. py:function:: load_from_multiple_dirs(dir_entries: list[dict], start_date=None, end_date=None) -> pandas.DataFrame | None

   Load TOA5 data from several directories and merge into one DataFrame.

   Designed for deployments where a **main archive** directory is supplemented
   by one or more **update** directories (e.g. incremental SD-card downloads).
   Records are sorted by ``TIMESTAMP`` before deduplication so that, when a
   timestamp appears in both main and update, the update-folder version is
   kept (``keep="last"``).

   Parameters
   ----------
   dir_entries : list of dict
       Ordered list of source directories.  Each element must have:

       - ``"path"`` : :class:`pathlib.Path` — directory to scan.
       - ``"is_flat"`` : bool — ``True`` if files sit directly in the
         directory; ``False`` for a nested (monthly subfolder) layout.
   start_date : datetime-like, optional
       Inclusive lower bound on ``TIMESTAMP``.  *None* loads all records.
   end_date : datetime-like, optional
       Inclusive upper bound on ``TIMESTAMP``.  *None* loads all records.

   Returns
   -------
   pd.DataFrame or None
       Single DataFrame with unique ``TIMESTAMP`` rows in ascending order,
       or *None* when no data is found in any of the supplied directories.

   Examples
   --------
   >>> from pathlib import Path
   >>> from palmwtc.io import load_from_multiple_dirs
   >>> entries = [
   ...     {"path": Path("/data/main/chamber_1"), "is_flat": False},
   ...     {"path": Path("/data/update_240901/01_chamber1"), "is_flat": True},
   ... ]
   >>> df = load_from_multiple_dirs(entries)  # doctest: +SKIP


.. py:function:: load_monthly_data(data_dir: pathlib.Path, months: list[str] | None = None) -> pandas.DataFrame

   Load pre-integrated monthly CSV files and apply hardware outlier filters.

   Reads all ``Integrated_Data_YYYY-MM.csv`` files found in *data_dir*, sorts
   them chronologically, concatenates them, and removes rows that violate the
   following first-pass physical bounds:

   - Atmospheric pressure < 50 kPa → likely sensor dropout.
   - Temperature (any channel) < -100 °C or > 100 °C → hardware error.
   - Relative humidity or vapour pressure < -100 → hardware error.
   - Soil water potential > 1000 kPa → hardware overflow.

   Parameters
   ----------
   data_dir : Path
       Directory that contains the ``Integrated_Data_*.csv`` files
       (the ``Integrated_Monthly`` folder in the standard export layout).
   months : list of str, optional
       Subset of YYYY-MM strings to load, e.g. ``["2024-10", "2024-11"]``.
       When *None* (default), all CSV files in *data_dir* are loaded.

   Returns
   -------
   pd.DataFrame
       Concatenated data with ``TIMESTAMP`` as the index (``DatetimeTzNaive``),
       sorted ascending.  Outlier rows are dropped in-place.

   Examples
   --------
   >>> from pathlib import Path
   >>> from palmwtc.io import load_monthly_data
   >>> df = load_monthly_data(Path("/data/Integrated_Monthly"))  # doctest: +SKIP
   >>> df.index.name  # doctest: +SKIP
   'TIMESTAMP'


.. py:function:: load_radiation_data(aws_file_path: pathlib.Path | str) -> pandas.DataFrame | None

   Load global solar radiation (W m⁻²) from an automatic weather station Excel file.

   The AWS export format varies across logger versions.  This function
   normalises both the timestamp field (looking for ``TIMESTAMP``,
   ``Date``+``Time``, or any column containing "time"/"date" in its name)
   and the radiation column (looking for ``Global_Radiation``, or any
   column containing "radiation" or "solar"+"rad").

   Parameters
   ----------
   aws_file_path : Path or str
       Path to the AWS Excel file (``.xlsx`` or ``.xls``).

   Returns
   -------
   pd.DataFrame or None
       DataFrame sorted by ``TIMESTAMP`` with at least a ``TIMESTAMP``
       column (``datetime64``) and, when found, a ``Global_Radiation``
       column (W m⁻², ``float64``).  Returns *None* if the file does not
       exist or cannot be parsed.

   Notes
   -----
   The normalisation heuristic picks the **first** matching radiation column
   it finds.  If the AWS export contains multiple radiation channels, verify
   which column is selected.

   Examples
   --------
   >>> from pathlib import Path
   >>> from palmwtc.io import load_radiation_data
   >>> df = load_radiation_data(Path("/data/aws/AWS_2024.xlsx"))  # doctest: +SKIP
   >>> "Global_Radiation" in df.columns  # doctest: +SKIP
   True


.. py:class:: QCProcessor(df: pandas.DataFrame, config_dict: dict)

   Object-oriented wrapper for the whole-tree chamber QC pipeline.

   Stores the working dataframe and variable configuration so callers do not
   need to pass them to every function call. Call :meth:`process_variable`
   once per sensor column; the resulting flag columns accumulate in
   :attr:`df`. Retrieve the final annotated dataframe with
   :meth:`get_processed_dataframe`.

   Parameters
   ----------
   df : pd.DataFrame
       Raw or lightly pre-processed sensor dataframe. The index may be a
       ``DatetimeTZIndex`` or a plain ``RangeIndex``; a ``TIMESTAMP`` column
       is supported as well. The dataframe is copied on construction so the
       original is never mutated.
   config_dict : dict
       Variable-level QC configuration. Keys are arbitrary config-group
       names (e.g. ``"co2"``). Each value is a sub-dict that must contain
       either ``"columns": [list-of-column-names]`` or
       ``"pattern": "<prefix>"`` (for soil sensor arrays whose column names
       share a common prefix) plus physical limit keys such as ``"hard"``
       and ``"soft"``. Passed directly to
       :func:`~palmwtc.qc.rules.get_variable_config`; see that function for
       the full schema.

   Attributes
   ----------
   df : pd.DataFrame
       Working copy of the input dataframe. Grows one ``{var}_rule_flag``
       column (and updates or creates ``{var}_qc_flag``) each time
       :meth:`process_variable` is called.
   var_config_dict : dict
       The configuration dict passed at construction, stored unchanged.

   Methods
   -------
   process_variable(var_name, ...)
       Run the full QC pipeline for one variable and store the flags in
       :attr:`df`.
   get_processed_dataframe()
       Return :attr:`df` with all flag columns added so far.

   Examples
   --------
   Build a tiny sensor dataframe and run QC on one column:

   >>> import pandas as pd
   >>> import numpy as np
   >>> from palmwtc.qc.processor import QCProcessor
   >>> rng = np.random.default_rng(0)
   >>> df = pd.DataFrame({"CO2_LI850": rng.uniform(350, 450, 20)})
   >>> # config_dict keys are config-group names; each entry lists the
   >>> # variable columns it covers via "columns" or "pattern".
   >>> config = {
   ...     "co2": {
   ...         "columns": ["CO2_LI850"],
   ...         "hard": [300, 600],
   ...         "soft": [350, 550],
   ...         "rate_of_change": {"limit": 50},
   ...         "persistence": {"window": 5},
   ...     }
   ... }
   >>> qc = QCProcessor(df=df, config_dict=config)
   >>> result = qc.process_variable("CO2_LI850", random_seed=42)
   >>> "CO2_LI850_rule_flag" in qc.df.columns
   True
   >>> set(qc.df["CO2_LI850_rule_flag"].unique()).issubset({0, 1, 2})
   True


   .. py:attribute:: df


   .. py:attribute:: var_config_dict


   .. py:method:: process_variable(var_name: str, random_seed: int = None, skip_persistence: list = None, skip_roc: list = None, use_sensor_exclusions: bool = False, exclusion_config_path=None) -> dict

      Run the full QC pipeline for one variable and store flags in :attr:`df`.

      Delegates to :func:`~palmwtc.qc.rules.process_variable_qc` with the
      configuration slice for *var_name* from :attr:`var_config_dict`. After
      the call the flag columns ``{var_name}_rule_flag`` and
      ``{var_name}_qc_flag`` are written into :attr:`df` in place.

      Parameters
      ----------
      var_name : str
          Column name in :attr:`df` to process (e.g. ``"CO2_LI850"``).
      random_seed : int, optional
          Seed passed to the Isolation Forest (ML outlier step). ``None``
          means non-deterministic.
      skip_persistence : list of str, optional
          Variable names for which the persistence (stuck-sensor) check is
          bypassed. Defaults to an empty list.
      skip_roc : list of str, optional
          Variable names for which the rate-of-change spike check is
          bypassed. Defaults to an empty list.
      use_sensor_exclusions : bool, default False
          If ``True``, load a YAML sensor-exclusion config and apply
          exclusion flags before combining.
      exclusion_config_path : path-like or None, optional
          Path to the YAML exclusion config file. Only used when
          *use_sensor_exclusions* is ``True``. If ``None`` the default
          location resolved by :func:`~palmwtc.qc.rules.process_variable_qc`
          is used.

      Returns
      -------
      dict
          Result dict from :func:`~palmwtc.qc.rules.process_variable_qc`
          with at least the following keys:

          ``"final_flags"`` : pd.Series
              Integer flag series (0 = good, 1 = suspect, 2 = bad).
          ``"summary"`` : dict
              Per-flag counts and percentages; keys are
              ``"total_points"``, ``"flag_0_count"``, ``"flag_0_percent"``,
              ``"flag_1_count"``, ``"flag_1_percent"``,
              ``"flag_2_count"``, ``"flag_2_percent"``.
          ``"bounds_flags"`` : pd.Series
              Raw flags from the physical-bounds check (may be absent if
              the step was skipped).
          ``"iqr_flags"`` : pd.Series
              Raw flags from the IQR outlier check (may be absent).

      Raises
      ------
      KeyError
          If *var_name* is not found in :attr:`var_config_dict`.

      Examples
      --------
      >>> import pandas as pd
      >>> import numpy as np
      >>> from palmwtc.qc.processor import QCProcessor
      >>> df = pd.DataFrame({"H2O_LI850": np.linspace(10, 30, 20)})
      >>> config = {
      ...     "h2o": {
      ...         "columns": ["H2O_LI850"],
      ...         "hard": [0, 50],
      ...         "soft": [1, 45],
      ...         "rate_of_change": {"limit": 10},
      ...         "persistence": {"window": 5},
      ...     }
      ... }
      >>> qc = QCProcessor(df=df, config_dict=config)
      >>> result = qc.process_variable("H2O_LI850", random_seed=0)
      >>> isinstance(result, dict)
      True
      >>> "final_flags" in result
      True



   .. py:method:: get_processed_dataframe() -> pandas.DataFrame

      Return the working dataframe with all QC flag columns added so far.

      Returns
      -------
      pd.DataFrame
          The internal :attr:`df` copy, which includes one
          ``{var}_rule_flag`` column and one ``{var}_qc_flag`` column for
          each variable processed with :meth:`process_variable`.

      Examples
      --------
      >>> import pandas as pd
      >>> import numpy as np
      >>> from palmwtc.qc.processor import QCProcessor
      >>> df = pd.DataFrame({"CO2_LI850": np.linspace(380, 420, 10)})
      >>> config = {
      ...     "co2": {
      ...         "columns": ["CO2_LI850"],
      ...         "hard": [300, 600],
      ...         "soft": [350, 550],
      ...         "rate_of_change": {"limit": 50},
      ...         "persistence": {"window": 5},
      ...     }
      ... }
      >>> qc = QCProcessor(df=df, config_dict=config)
      >>> _ = qc.process_variable("CO2_LI850", random_seed=0)
      >>> out = qc.get_processed_dataframe()
      >>> "CO2_LI850_qc_flag" in out.columns
      True



.. py:function:: apply_iqr_flags(df, var_name, iqr_factor=1.5)

   Flag statistical outliers using the interquartile range (IQR) method.

   Computes Q1, Q3, and IQR over all valid (non-NaN) rows in the
   column, then flags values outside ``[Q1 - k*IQR, Q3 + k*IQR]``
   where ``k = iqr_factor``.

   Parameters
   ----------
   df : pd.DataFrame
       Time-indexed sensor data. Must contain at least the column
       ``var_name``. Non-numeric values are coerced to ``NaN``.
   var_name : str
       Name of the column in ``df`` to check
       (e.g. ``"H2O_C1"``, ``"AirTC_Avg"``).
   iqr_factor : float, optional
       Multiplier applied to the IQR to define the outlier fence.
       Default ``1.5`` (the classic Tukey fence). Use a larger value
       (e.g. ``3.0``) for variables with heavy right tails such as
       soil CO₂ efflux.

   Returns
   -------
   pd.Series
       Integer flag series aligned to ``df.index``:

       - ``0`` — within the IQR fence (Good).
       - ``1`` — outside the IQR fence (Suspect).

   Notes
   -----
   IQR-based flagging assumes a roughly symmetric distribution. Tropical
   chamber CO₂ is typically log-normal within a day, so this is a
   coarse filter intended to catch orders-of-magnitude anomalies rather
   than subtle drift. At least 4 valid data points are required;
   fewer returns all zeros. If all values are identical (IQR = 0) the
   function also returns all zeros to avoid flagging constant series
   that may represent a gap period.

   Examples
   --------
   >>> import pandas as pd
   >>> df = pd.DataFrame({"CO2_C1": [400.0, 410.0, 405.0, 395.0, 9999.0]})
   >>> flags = apply_iqr_flags(df, "CO2_C1", iqr_factor=1.5)
   >>> flags.tolist()
   [0, 0, 0, 0, 1]


.. py:function:: apply_physical_bounds_flags(df, var_name, config)

   Flag rows where a variable falls outside its physical bounds.

   Compares each value of ``var_name`` in ``df`` against hard and soft
   limits defined in the variable config. Hard bounds represent absolute
   sensor limits (saturation, cable disconnect); soft bounds represent
   expected operating range under normal field conditions.

   Parameters
   ----------
   df : pd.DataFrame
       Time-indexed sensor data. Must contain at least the column
       ``var_name``. Non-numeric values are coerced to ``NaN`` and
       treated as missing (not flagged).
   var_name : str
       Name of the column in ``df`` to check
       (e.g. ``"CO2_C1"``, ``"SWC_C1_15cm"``).
   config : dict
       Variable config dict. Recognised keys:

       ``"hard"`` : list of [low, high], optional
           Absolute sensor limits in native units. Values outside this
           range receive flag ``2`` (Bad).
       ``"soft"`` : list of [low, high], optional
           Expected operating limits in native units. Values outside
           soft but inside hard receive flag ``1`` (Suspect).

   Returns
   -------
   pd.Series
       Integer flag series aligned to ``df.index``:

       - ``0`` — within soft bounds (or no bounds configured).
       - ``1`` — outside soft bounds but within hard bounds (Suspect).
       - ``2`` — outside hard bounds (Bad).

   Notes
   -----
   Both ``"hard"`` and ``"soft"`` keys are optional. If only ``"hard"``
   is present, there are no Suspect flags — values are either 0 or 2.
   If only ``"soft"`` is present, there are no Bad flags.

   For the LI-850 CO₂ channel (range 0-20 000 ppm), typical hard
   limits are ``[0, 20000]`` and soft limits are ``[350, 2000]`` for
   tropical oil-palm chambers.

   Examples
   --------
   >>> import pandas as pd
   >>> df = pd.DataFrame({"CO2_C1": [300.0, 1500.0, 25000.0]})
   >>> cfg = {"hard": [0.0, 20000.0], "soft": [350.0, 2000.0]}
   >>> flags = apply_physical_bounds_flags(df, "CO2_C1", cfg)
   >>> flags.tolist()
   [1, 0, 2]


.. py:function:: combine_qc_flags(bounds_flags, iqr_flags, roc_flags=None, persistence_flags=None)

   Merge per-rule flag series into a single combined quality flag.

   Applies a worst-case (maximum) merge logic with priority ordering:

   1. Physical bounds flags set the base (can produce flag 2).
   2. IQR, rate-of-change, and persistence flags elevate 0 → 1.
   3. A flag 2 value is never demoted to 1 or 0.

   Parameters
   ----------
   bounds_flags : pd.Series
       Flags from the physical bounds check (values 0, 1, or 2).
       Used as the starting base for the merge.
   iqr_flags : pd.Series
       Flags from the IQR outlier check (values 0 or 1).
       Must share the same index as ``bounds_flags``.
   roc_flags : pd.Series, optional
       Flags from the rate-of-change (spike) check (values 0 or 1).
       If ``None``, treated as all zeros.
   persistence_flags : pd.Series, optional
       Flags from the persistence (flat-line) check (values 0 or 1).
       If ``None``, treated as all zeros.

   Returns
   -------
   pd.Series
       Combined integer flag series (0, 1, or 2) aligned to
       ``bounds_flags.index``.

   Examples
   --------
   >>> import pandas as pd
   >>> bounds = pd.Series([0, 2, 0, 0])
   >>> iqr    = pd.Series([0, 0, 1, 0])
   >>> roc    = pd.Series([0, 0, 0, 1])
   >>> combined = combine_qc_flags(bounds, iqr, roc_flags=roc)
   >>> combined.tolist()
   [0, 2, 1, 1]


.. py:function:: detect_breakpoints_ruptures(df, var_name, qc_flag_col=None, penalty=10, n_bkps=None, min_confidence=None, min_segment_size=100, max_samples=10000, group_col=None, algorithm='Binseg', model='l2', window_width=100)

   Detect structural breakpoints in a time series using the ruptures library.

   Wraps the ``Binseg``, ``Pelt``, or ``Window`` algorithm from *ruptures*
   [1]_ to locate instantaneous step changes (breakpoints) in a sensor
   variable.  Supports an optional aggregation path — grouping by
   ``group_col`` (e.g. ``'cycle_id'``) before fitting — which is much
   faster when the raw signal has millions of rows.

   Parameters
   ----------
   df : pd.DataFrame
       Input data.  Index should be a ``DatetimeIndex`` for timestamp
       mapping to work correctly.
   var_name : str
       Column name of the variable to analyse.
   qc_flag_col : str or None, optional
       Column whose non-zero values are treated as bad data and excluded
       before fitting.  ``None`` uses all rows.
   penalty : float, optional
       Regularisation penalty for the PELT / Binseg cost function.
       Higher values increase the minimum cost needed to add a breakpoint,
       so the algorithm returns *fewer* breakpoints.  Lower values make the
       detector more sensitive (more breakpoints detected).  Default ``10``.
   n_bkps : int or None, optional
       If given, force exactly this many breakpoints.  Overrides ``penalty``
       for ``Binseg`` and ``Window`` algorithms.
   min_confidence : float or None, optional
       Minimum confidence score in [0, 1] to retain a breakpoint after
       detection.  A score of 1.0 means the inter-segment mean shift
       exceeds three pooled standard deviations.  Breakpoints below this
       threshold are pruned iteratively (least confident first).
   min_segment_size : int, optional
       Minimum number of data points that each segment must contain.
       Ignored for the ``Window`` algorithm.  Default ``100``.
   max_samples : int, optional
       Maximum number of rows used when *not* aggregating.  Rows beyond
       this count are downsampled uniformly.  Default ``10000``.
   group_col : str or None, optional
       Column to aggregate by before detection (e.g. ``'cycle_id'``).
       When given, each group is replaced by its mean value, greatly
       reducing the effective signal length.
   algorithm : {'Binseg', 'Pelt', 'Window'}, optional
       ruptures algorithm to use.  Default ``'Binseg'``.

       - ``'Binseg'`` — binary segmentation; fast, approximate.
       - ``'Pelt'`` — optimal segmentation via dynamic programming; slower
         but exact.  Uses ``penalty`` only (``n_bkps`` ignored).
       - ``'Window'`` — sliding-window approach; good for slowly drifting
         signals.
   model : str, optional
       Cost model for the ruptures algorithm.  ``'l2'`` detects mean-level
       shifts (most common for sensor offsets).  ``'rbf'`` uses a
       kernel-based cost that handles non-Gaussian distributions and
       variance changes — useful when the sensor noise itself changes at
       the breakpoint.  ``'l1'`` is robust to outliers.  Default ``'l2'``.
   window_width : int, optional
       Half-width (in samples) of the sliding window for the ``Window``
       algorithm.  Halved automatically if the signal is too short.
       Default ``100``.

   Returns
   -------
   dict or None
       ``None`` if the variable is missing or no valid data remain.
       Otherwise a dictionary with keys:

       - ``'breakpoints'`` — list of ``pd.Timestamp`` objects, one per
         detected breakpoint.
       - ``'n_breakpoints'`` — integer count.
       - ``'segment_info'`` — list of dicts, each with ``'start'``,
         ``'end'``, ``'mean'``, and ``'std'`` for that segment.
       - ``'confidence_scores'`` — list of floats in [0, 1], one per
         internal boundary (len = n_breakpoints).
       - ``'used_qc_filter'`` — bool, whether ``qc_flag_col`` was applied.

   Notes
   -----
   The confidence score for a boundary is
   ``min(1, |mean2 - mean1| / (3 * pooled_std))``, where ``mean1`` and
   ``mean2`` are the adjacent segment means and ``pooled_std`` is their
   pooled standard deviation.
   A score of 1.0 means the step is at least 3 pooled-SD wide -- the
   standard threshold for a physically significant sensor shift.

   When ``group_col`` is used, the minimum segment size is clamped to
   5 groups regardless of ``min_segment_size``.

   References
   ----------
   .. [1] Truong, C., Oudre, L., & Vayatis, N. (2020). Selective review
          of offline change point detection methods. *Signal
          Processing*, 167, 107299.
          https://doi.org/10.1016/j.sigpro.2019.107299

   Examples
   --------
   >>> import pandas as pd, numpy as np
   >>> from palmwtc.qc import detect_breakpoints_ruptures
   >>> rng = np.random.default_rng(0)
   >>> idx = pd.date_range("2023-01-01", periods=200, freq="30min")
   >>> vals = np.concatenate([rng.normal(400, 5, 100), rng.normal(450, 5, 100)])
   >>> df = pd.DataFrame({"CO2": vals}, index=idx)
   >>> result = detect_breakpoints_ruptures(df, "CO2", penalty=5)  # doctest: +SKIP
   >>> result["n_breakpoints"]  # doctest: +SKIP
   1


.. py:function:: detect_drift_windstats(df: pandas.DataFrame, var_name: str, qc_flag_col: str = None, window: int = 48) -> dict

   Detect gradual sensor drift using a rolling-window Z-score.

   Computes how far the rolling mean deviates from the global mean,
   expressed in units of the global standard deviation.  A persistently
   high (or low) score across many consecutive windows indicates that the
   sensor has drifted away from its typical operating point.

   **Drift vs breakpoints.** Drift is a *gradual* offset that develops over
   days to weeks, for example a CO₂ sensor whose zero point shifts as the
   optical path ages.  A breakpoint is an *instantaneous* step change caused
   by a sensor swap or re-calibration.  Use
   :func:`~palmwtc.qc.breakpoints.detect_breakpoints_ruptures` to find the
   latter; this function targets the former.

   Parameters
   ----------
   df : pd.DataFrame
       Input data.  Index can be any type; a ``DatetimeIndex`` is
       recommended for downstream time-based analysis.
   var_name : str
       Column name of the variable to analyse.
   qc_flag_col : str or None, optional
       Column whose non-zero values are excluded from the rolling and global
       statistics (set to ``NaN`` before computing).  Pass ``None`` to use
       all rows.  Default ``None``.
   window : int, optional
       Number of consecutive timestamps in each rolling window.  Larger
       windows smooth out short spikes but may obscure drift that develops
       over timescales shorter than ``window``.  The rolling calculation
       requires at least ``max(1, window // 2)`` non-NaN values per window.
       Default ``48`` (24 h at 30-minute resolution).

   Returns
   -------
   dict or None
       ``None`` if ``var_name`` is not in ``df`` or if the global standard
       deviation is zero or NaN.  Otherwise a dictionary with keys:

       - ``'scores'`` — ``pd.DataFrame`` with one column
         ``{var_name}_drift_score``, containing the Z-score of the rolling
         mean at each timestamp.
       - ``'metric'`` — the string ``'rolling_z_score'``.
       - ``'window'`` — the ``window`` value that was used.

   Notes
   -----
   The drift score at time ``t`` is::

       score(t) = (rolling_mean(t) - global_mean) / global_std

   Values beyond roughly ±2 suggest the local mean has shifted by 2
   standard deviations from the long-term average.  There is no fixed
   threshold; a practical rule of thumb is to inspect periods where
   ``|score| > 1.5`` for more than one window duration.

   The tuning parameters interact: a short ``window`` with a low
   ``z_threshold`` (set by the caller) catches small, fast drift but
   generates more false positives.  A long ``window`` reduces noise but may
   average out the drift signal.

   Examples
   --------
   >>> import pandas as pd, numpy as np
   >>> from palmwtc.qc import detect_drift_windstats
   >>> rng = np.random.default_rng(1)
   >>> idx = pd.date_range("2023-01-01", periods=96, freq="30min")
   >>> vals = np.concatenate([rng.normal(400, 2, 48), rng.normal(410, 2, 48)])
   >>> df = pd.DataFrame({"CO2": vals}, index=idx)
   >>> result = detect_drift_windstats(df, "CO2", window=24)
   >>> "CO2_drift_score" in result["scores"].columns
   True
   >>> result["metric"]
   'rolling_z_score'


.. py:function:: process_variable_qc(df, var_name, var_config_dict, random_seed=None, skip_persistence_for=None, skip_rate_of_change_for=None, use_sensor_exclusions=True, exclusion_config_path=None)

   Run all QC rule checks for one variable and return combined flags.

   Orchestrates the full QC pipeline in order:

   1. Sensor exclusion windows (optional; flag 2 never demoted).
   2. Physical bounds (hard and soft limits).
   3. IQR-based outlier detection.
   4. Rate-of-change (spike) detection.
   5. Persistence (flat-line) detection.
   6. Combine all flags into a single worst-case flag per row.

   Parameters
   ----------
   df : pd.DataFrame
       Time-indexed sensor data. Must contain at least the column
       ``var_name``. Non-numeric values in ``var_name`` are coerced to
       ``NaN``.
   var_name : str
       Name of the column in ``df`` to process
       (e.g. ``"CO2_C1"``, ``"SWC_C1_15cm"``).
   var_config_dict : dict
       Variable configuration dictionary (typically from
       ``variable_config.json``). Passed to ``get_variable_config``
       to look up the per-variable config block.
   random_seed : int, optional
       Accepted for API compatibility but not used. Has no effect.
   skip_persistence_for : list of str, optional
       If ``var_name`` is in this list, the persistence check is
       skipped and its flags default to 0. Useful for variables with
       naturally flat periods (e.g. soil temperature at depth).
   skip_rate_of_change_for : list of str, optional
       If ``var_name`` is in this list, the rate-of-change check is
       skipped and its flags default to 0. Useful for variables where
       fast step-changes are physically expected (e.g. chamber CO₂
       at cycle transitions).
   use_sensor_exclusions : bool, optional
       If ``True``, load and apply date-range exclusion windows from
       ``config/sensor_exclusions.yaml`` before other QC checks.
       Default ``False``.
   exclusion_config_path : str or Path, optional
       Override path to ``sensor_exclusions.yaml``. Only used when
       ``use_sensor_exclusions=True``.

   Returns
   -------
   dict
       Dictionary with the following keys:

       ``"final_flags"`` : pd.Series
           Combined worst-case flag (0, 1, or 2) for each row.
       ``"exclusion_flags"`` : pd.Series
           Flags from sensor exclusion windows (0, 1, or 2).
       ``"bounds_flags"`` : pd.Series
           Flags from physical bounds check (0, 1, or 2).
       ``"iqr_flags"`` : pd.Series
           Flags from IQR outlier check (0 or 1).
       ``"roc_flags"`` : pd.Series
           Flags from rate-of-change check (0 or 1).
       ``"persistence_flags"`` : pd.Series
           Flags from persistence check (0 or 1).
       ``"summary"`` : dict
           Counts and percentages per flag level from
           ``generate_qc_summary``.
       ``"config"`` : dict
           The variable config block that was used (absent when no
           config was found for ``var_name``).

   Notes
   -----
   When no config is found for ``var_name`` in ``var_config_dict``, a
   warning is printed and all flag series are returned as zeros (no
   filtering applied). This allows the pipeline to proceed even for
   variables without explicit configuration.

   Examples
   --------
   >>> import pandas as pd
   >>> idx = pd.date_range("2024-01-01", periods=5, freq="4s")
   >>> df = pd.DataFrame({"CO2_C1": [400.0, 405.0, 402.0, 410.0, 50000.0]}, index=idx)
   >>> cfg = {
   ...     "co2": {
   ...         "columns": ["CO2_C1"],
   ...         "hard": [0.0, 20000.0],
   ...         "soft": [350.0, 2000.0],
   ...     }
   ... }
   >>> result = process_variable_qc(df, "CO2_C1", cfg)
   >>> result["final_flags"].tolist()
   [0, 0, 0, 0, 2]


.. py:function:: render_field_alert_html(context: dict, template_name: str = 'field_alert.html', template_dir: pathlib.Path | None = None) -> str

   Render the field-alert Jinja2 template to an HTML string.

   Loads the Jinja2 template from *template_dir* and renders it with the
   context dict produced by :func:`build_field_alert_context`.  The
   resulting HTML string can be written to a file, displayed in a notebook
   with ``IPython.display.HTML``, or sent as the body of a field-alert
   email.

   Parameters
   ----------
   context : dict
       Context dict from :func:`build_field_alert_context`.
       Required keys:

       ``"report_date"`` : str
           ISO datetime string shown in the report header.
       ``"lookback_days"`` : int
           Number of days covered by the report window.
       ``"window_start"`` : str
           Start of the data window (``"YYYY-MM-DD HH:MM"``).
       ``"window_end"`` : str
           End of the data window (``"YYYY-MM-DD HH:MM"``).
       ``"system_status"`` : str
           One of ``"HEALTHY"``, ``"WARNING"``, or ``"CRITICAL"``.
       ``"status_color"`` : str
           CSS hex colour (e.g. ``"#2ecc71"``).
       ``"avg_score"`` : str
           Average health score as an integer string (e.g. ``"87"``).
       ``"total_sensors"`` : int
           Total number of sensors in the report.
       ``"healthy_count"`` : int
           Number of sensors with status ``"Healthy"``.
       ``"attention_sensors"`` : list of dict
           Sensors below the healthy threshold; each dict has
           ``"variable"``, ``"score"``, ``"status"``, ``"color_hex"``.
       ``"critical_recs"`` : list of dict
           Critical maintenance recommendations; each dict has
           ``"sensor"``, ``"message"``, ``"severity"``.
       ``"warning_recs"`` : list of dict
           Warning-level maintenance recommendations.
       ``"cv_issues"`` : list of dict
           Cross-variable consistency issues with ``"name"`` and ``"pct"``.
       ``"health_rows"`` : list of dict
           All sensor rows (used for the full table in the template).
       ``"recommendations"`` : list of dict
           All recommendations (critical + warning combined).
       ``"qc_source"`` : str
           Notebook identifier for the QC source (e.g. ``"020"``).

   template_name : str, default ``"field_alert.html"``
       Filename of the Jinja2 template inside *template_dir*.
   template_dir : pathlib.Path or None, optional
       Directory that contains the Jinja2 template.  When ``None`` (the
       default) the function looks for the template at
       ``<package_root>/dashboard/email_report/templates/``.

   Returns
   -------
   str
       Rendered HTML string.

   Raises
   ------
   jinja2.TemplateNotFound
       If *template_name* does not exist inside *template_dir*.

   Examples
   --------
   Requires the ``field_alert.html`` Jinja2 template on disk at the
   default template location; skip in environments without it:

   >>> html = render_field_alert_html({})  # doctest: +SKIP
   >>> html.startswith("<!DOCTYPE html") or "<html" in html  # doctest: +SKIP
   True


.. py:function:: derive_is_daytime(cycles: pandas.DataFrame, config: dict[str, Any] | None = None, radiation_threshold: float = 10.0) -> pandas.Series

   Derive a Boolean daytime mask from radiation or, as a fallback, hour-of-day.

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


.. py:function:: run_science_validation(cycles: pandas.DataFrame, config: dict[str, Any] | None = None, label: str = 'default', derive_daytime: bool = False) -> dict[str, Any]

   Run all four ecophysiology validation tests on a cycles DataFrame.

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


.. py:function:: interactive_flux_dashboard(flux_df: pandas.DataFrame, chamber_raw: dict[str, pandas.DataFrame], stride: int = 15, renderer: str = 'plotly_mimetype', replace_previous: bool = True, debug: bool = True, enable_detail: bool = True, detail_max_points_overview: int = 80000, detail_max_points_zoom: int = 400000, detail_debounce_s: float = 0.25) -> None

   Multi-chamber flux dashboard with QC filters and zoom-to-reveal detail.

   Renders an ipywidgets-based dashboard in Jupyter with two sections:

   1. **Overview panel** — all chambers stacked, measured CO2 (thinned by
      *stride*) above and flux scatter below, coloured per chamber.
   2. **Detail panel** (when *enable_detail* is ``True``) — one chamber at
      a time, starting from the full overview density; as you zoom in,
      more raw points are loaded from the full dataset up to
      *detail_max_points_zoom*.

   Widget controls:

   * *Measured CO2 QC* dropdown — filter the raw CO2 scatter by flag
     (All / Flag 0 only / Flags 0+1).
   * *Flux Data QC* dropdown — filter the flux scatter by ``qc_flag``.
   * *Detail Chamber* dropdown — select which chamber to show in the
     detail panel.
   * *Show detail* checkbox — toggle the detail panel on/off.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux results. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier (e.g. ``"Chamber 1"``). Matched against
           keys in *chamber_raw*.
       ``flux_date`` : datetime-like
           Cycle timestamp. Plotted on the x-axis of flux sub-panels.
       ``flux_absolute`` : float
           Flux value shown in the overview and detail flux sub-panels.
       ``qc_flag`` : int
           Quality flag used by the flux filter dropdown.
       ``cycle_id`` : int or str, optional
           Shown in the hover tooltip. A placeholder column is used if
           absent.
   chamber_raw : dict[str, pd.DataFrame]
       Mapping from chamber name to raw logger data. Each value must
       contain:

       ``TIMESTAMP`` : datetime-like
           Logger timestamp. Converted to datetime in place on first call.
       ``CO2`` : float
           Raw CO2 concentration (ppm). Plotted in the measured CO2
           sub-panels.
       ``Flag`` : int, optional
           Used by the *Measured CO2 QC* filter dropdown.
   stride : int
       Downsample step applied to raw CO2 data in the overview.
       Every *stride*-th row is kept. Default ``15``.
   renderer : str
       Plotly renderer string passed to ``pio.renderers.default`` and
       ``fig.show()``. Default ``"plotly_mimetype"`` (standard Jupyter).
   replace_previous : bool
       If ``True``, close any widgets from a previous call in the same
       kernel and clear output before rendering. Default ``True``.
   debug : bool
       Print diagnostic lines (renderer name, chamber list) to stdout.
       Default ``True``.
   enable_detail : bool
       Whether to build and show the detail panel with its extra widgets.
       Set to ``False`` to show only the overview. Default ``True``.
   detail_max_points_overview : int
       Maximum raw CO2 points shown in the detail panel at full zoom-out.
       Default ``80_000``.
   detail_max_points_zoom : int
       Maximum raw CO2 points loaded into the detail panel when zoomed in.
       Default ``400_000``.
   detail_debounce_s : float
       Minimum seconds between successive zoom-triggered data refreshes
       in the detail panel. Prevents excessive updates while panning.
       Default ``0.25``.

   Returns
   -------
   None
       Renders directly into the Jupyter output cell via
       ``IPython.display.display``. No figure object is returned.

   Notes
   -----
   **Requires Jupyter notebook or lab** and the ``palmwtc[interactive]``
   extra (``ipywidgets`` + ``IPython``).  Both packages are imported
   inside the function body so the module stays importable in a
   core-only install, but calling this function without them will raise
   ``ImportError``.

   Outside Jupyter the ``display()`` call silently produces no output.
   Use the ``plot_*_interactive`` helpers above for environments that
   support plain ``fig.show()``.

   The detail panel uses a ``go.FigureWidget`` so that Python callbacks
   (``fig.observe``) can update trace data reactively when the user
   zooms. The overview uses a static ``go.Figure`` re-rendered on each
   filter change.

   Examples
   --------
   >>> from palmwtc.viz.interactive import interactive_flux_dashboard
   >>> interactive_flux_dashboard(  # doctest: +SKIP
   ...     flux_df,
   ...     chamber_raw={"Chamber 1": raw1_df, "Chamber 2": raw2_df},
   ... )

   See Also
   --------
   plot_flux_timeseries_tiers_interactive : Simpler static tiered
       timeseries figure (no widgets, returns a Figure).
   palmwtc.viz.diagnostics.plot_cycle_diagnostics : Static matplotlib
       diagnostic panels for individual cycles.


.. py:function:: plot_flux_heatmap(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', title: str = 'Flux Heatmap (Hour vs Month)') -> matplotlib.pyplot.Figure | None

   Heatmap of mean flux by hour-of-day and month-year.

   Produces three vertically stacked subplots:

   1. Overall (all chambers combined).
   2. Chamber 1 only.
   3. Chamber 2 only.

   Each subplot has hour of day (0-23) on the y-axis and month-year
   periods on the x-axis. Cell colour encodes mean flux, centred at
   zero (``RdBu_r`` palette: red = positive efflux, blue = uptake).

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux data. Must contain:

       ``flux_date`` : datetime-like
           Timestamp; hour and month-year are extracted from this column.
       ``Source_Chamber`` : str
           Chamber identifier. Subplots 2 and 3 filter on
           ``"Chamber 1"`` and ``"Chamber 2"`` exactly.
       ``<variable>`` : float
           Flux column used for heatmap cell values.
   variable : str, optional
       Column in ``flux_df`` to aggregate. Default is
       ``"flux_absolute"``.
   title : str, optional
       Base title; each subplot appends its own suffix
       (e.g. ``"- Chamber 1"``). Default is
       ``"Flux Heatmap (Hour vs Month)"``.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure with three heatmap subplots, or ``None`` if
       ``flux_df`` is empty.

   Notes
   -----
   Subplots where the filtered data is empty show a ``"No Data"``
   label instead of a heatmap. Month-year periods on the x-axis
   are sorted chronologically by pandas ``Period`` ordering.

   Examples
   --------
   >>> from palmwtc.viz.timeseries import plot_flux_heatmap
   >>> fig = plot_flux_heatmap(cycles_df)  # doctest: +SKIP


.. py:function:: plot_tropical_seasonal_diurnal(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', estimator: str = 'mean', title_suffix: str = '') -> matplotlib.pyplot.Figure | None

   Overlay diurnal flux pattern per tropical season on a single axis.

   Draws one line per season (Wet and Dry) and per chamber. The x-axis
   is hour of day (0-23), the y-axis is the flux value aggregated
   across all dates in that season-hour combination.

   Season assignment follows the standard SE-Asia rule:

   - **Dry Season**: May to September (months 5-9).
   - **Wet Season**: October to April (months 10-4).

   Useful for spotting shifts in CO2 uptake phase (morning vs afternoon
   activity) between seasons.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux data. Must contain:

       ``flux_date`` : datetime-like
           Timestamp of each measurement cycle; month and hour are
           extracted from this column.
       ``Source_Chamber`` : str
           Chamber identifier used to differentiate line styles.
       ``<variable>`` : float
           Flux column plotted on the y-axis.
   variable : str, optional
       Column in ``flux_df`` to use as the y-axis value.
       Default is ``"flux_absolute"``.
   estimator : str, optional
       Aggregation function passed to ``seaborn.lineplot``
       (e.g. ``"mean"``, ``"median"``). Default is ``"mean"``.
   title_suffix : str, optional
       Extra text appended to the figure title, useful for adding
       a date range or site label. Default is ``""``.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure containing the diurnal plot, or ``None`` if
       ``flux_df`` is empty.

   Notes
   -----
   Shaded bands around each line represent one standard deviation
   (``errorbar="sd"``). Lines are coloured orange (Dry) and blue (Wet);
   line style differentiates chambers.

   Examples
   --------
   >>> from palmwtc.viz.timeseries import plot_tropical_seasonal_diurnal
   >>> fig = plot_tropical_seasonal_diurnal(cycles_df)  # doctest: +SKIP


.. py:function:: set_style() -> None

   Apply the standard palmwtc matplotlib/seaborn theme.

   Sets the seaborn ``"whitegrid"`` theme and fixes the default figure size
   to ``(12, 6)`` inches.  Call this once at the top of a notebook or script
   before producing any plots.

   Returns
   -------
   None
       This function returns nothing.  It modifies global matplotlib
       rcParams and the seaborn theme as a side effect.

   Notes
   -----
   This function is **side-effecting**: it changes ``matplotlib.rcParams``
   and the active seaborn theme for the entire Python session.  Any plots
   created after calling this function will use the new settings.  To undo,
   call ``matplotlib.rcdefaults()`` or ``seaborn.reset_defaults()``.

   The function is idempotent — calling it multiple times has the same
   result as calling it once.

   Examples
   --------
   >>> from palmwtc.viz.style import set_style
   >>> set_style()  # doctest: +SKIP


.. py:class:: WindowSelector(cycles_df: pandas.DataFrame, config: dict | None = None)

   Select high-confidence calibration windows from per-cycle flux quality scores.

   A *window* is a contiguous date range of oil-palm chamber cycles whose
   per-cycle confidence scores are high enough to use as training data for the
   XPalm digital-twin model.  The selector walks the scored cycles, identifies
   qualifying spans, and packages them as a cycle CSV + JSON manifest.

   Parameters
   ----------
   cycles_df : pd.DataFrame
       Cycle-level data from notebook 030 (``01_chamber_cycles.csv``).
       Required columns: ``flux_datetime``, ``Source_Chamber``.
       Optional but used when present: ``cycle_end``, ``co2_r2``, ``co2_nrmse``,
       ``co2_snr``, ``co2_outlier_frac``, ``slope_diff_pct``, ``delta_aicc``,
       ``sensor_co2_qc_mean``, ``sensor_h2o_qc_mean``, ``flux_intercept``,
       ``anomaly_ensemble_score``, ``closure_confidence``, ``co2_qc``.
   config : dict, optional
       Key-value overrides merged on top of :data:`DEFAULT_CONFIG`.
       Pass only the keys you want to change; all others keep their defaults.

   Attributes
   ----------
   cycles_df : pd.DataFrame
       Working copy of the input cycles.  After :meth:`score_cycles` this gains
       per-component score columns (``score_regression``, ``score_robustness``,
       etc.) and the composite ``cycle_confidence`` column.
   config : dict
       Merged configuration (your overrides + :data:`DEFAULT_CONFIG` fallbacks).
   drift_df : pd.DataFrame or None
       Per ``(date, Source_Chamber)`` drift summary — set by :meth:`detect_drift`.
       Columns: ``date``, ``Source_Chamber``, ``drift_severity``, z-score columns.
   regime_agreement : dict or None
       Date → cross-chamber agreement score from the 026 regime audit.
       Set by :meth:`load_regime_diagnostics`; None if the file was not found.
   windows_df : pd.DataFrame or None
       Window summary table — set by :meth:`identify_windows`.
       One row per window; columns include ``window_id``, ``start_date``,
       ``end_date``, ``n_cycles``, ``window_score``, ``qualifies_for_export``.
   approved_windows : dict
       ``{window_id: {"approved": bool, "notes": str}}`` — populated by the
       interactive inspector in the calibration notebook.  Persisted via
       :meth:`export`.

   Methods
   -------
   load_regime_diagnostics(path)
       Load cross-chamber agreement scores from the 026 audit CSV.
   detect_drift()
       Compute per-day rolling drift severity per chamber.
   score_cycles()
       Add ``cycle_confidence`` and per-component sub-scores to ``cycles_df``.
   identify_windows()
       Find high-confidence date windows per chamber.
   export(approved_only, exclude_list)
       Filter cycles to approved windows, write CSV + JSON, return both.
   summary()
       Print a brief text overview of selection results.

   Examples
   --------
   Build a selector on a small fixture and inspect the result:

   >>> import pandas as pd
   >>> from palmwtc.windows import WindowSelector
   >>> cycles = pd.DataFrame({
   ...     "flux_datetime": pd.date_range("2024-01-01", periods=4, freq="6h"),
   ...     "Source_Chamber": ["Chamber 1"] * 4,
   ... })
   >>> ws = WindowSelector(cycles)
   >>> len(ws.cycles_df)
   4
   >>> ws.config["min_window_days"]
   5

   Full pipeline (needs a real cycles DataFrame with flux columns):

   >>> ws.detect_drift().score_cycles().identify_windows()  # doctest: +SKIP
   >>> filtered_df, manifest = ws.export()  # doctest: +SKIP


   .. py:attribute:: config


   .. py:attribute:: cycles_df


   .. py:attribute:: drift_df
      :type:  pandas.DataFrame | None
      :value: None



   .. py:attribute:: regime_agreement
      :type:  dict | None
      :value: None



   .. py:attribute:: windows_df
      :type:  pandas.DataFrame | None
      :value: None



   .. py:attribute:: approved_windows
      :type:  dict


   .. py:method:: load_regime_diagnostics(path: pathlib.Path | str | None = None) -> WindowSelector

      Load cross-chamber agreement scores from the 026 regime audit CSV.

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



   .. py:method:: detect_drift() -> WindowSelector

      Compute per-day rolling drift severity for each chamber.

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

      Returns
      -------
      self : WindowSelector
          Returns ``self`` to allow method chaining.



   .. py:method:: _regression_score(r2, nrmse, snr, outlier) -> float


   .. py:method:: _robustness_score(slope_diff, delta_aicc) -> float


   .. py:method:: _closure_score(closure_confidence) -> float


   .. py:method:: _sensor_qc_score(co2_flag_mean, h2o_flag_mean) -> float


   .. py:method:: _anomaly_score(ensemble_score) -> float


   .. py:method:: _drift_score_lookup(date, chamber, drift_lookup: dict) -> float


   .. py:method:: score_cycles() -> WindowSelector

      Add ``cycle_confidence`` (0–1) and per-component sub-scores to ``cycles_df``.

      New columns added to ``self.cycles_df`` (all 0–1):

      * ``score_regression``    — R², NRMSE, SNR, outlier fraction (4 components;
        monotonicity is intentionally excluded because non-monotonic CO₂ traces
        in a tree chamber under variable irradiance reflect real photosynthesis).
      * ``score_robustness``    — OLS vs Theil-Sen slope agreement, AICc curvature test.
      * ``score_sensor_qc``     — CO₂/H₂O sensor flag mean from 021 parquet.
      * ``score_drift``         — seasonally detrended instrument drift score.
      * ``score_cross_chamber`` — cross-chamber agreement from 026 regime diagnostics
        (NaN when the 026 audit file was not loaded).
      * ``score_closure``       — *diagnostic only*, not in composite; CO₂/H₂O ratio
        is a biological variable, not a physical leakage indicator.
      * ``score_anomaly``       — *diagnostic only*, not in composite; anomaly detectors
        flag drought stress and rapid leaf flush that have calibration value.
      * ``cycle_confidence``    — weighted composite of the five active components
        (see ``score_weights`` in :data:`DEFAULT_CONFIG`).

      Nighttime cycles carry full weight (``nighttime_weight = 1.0``) because dark
      respiration is the primary constraint for Ra and Q10 calibration in XPalm.

      When cross-chamber data is unavailable, its weight (0.10 by default) is
      redistributed proportionally across the remaining four components.

      Returns
      -------
      self : WindowSelector
          Returns ``self`` to allow method chaining.

      Raises
      ------
      (no explicit raises)
          Silently proceeds even when optional score columns are absent from
          ``cycles_df``; missing columns default to ``NaN`` → neutral score.

      Notes
      -----
      Call :meth:`detect_drift` first.  If not called, drift component defaults
      to 1.0 (no drift assumed), which gives slightly optimistic scores.



   .. py:method:: identify_windows() -> WindowSelector

      Find high-confidence windows per chamber with rolling flexibility.

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

      Returns
      -------
      self : WindowSelector
          Returns ``self`` to allow method chaining.

      Raises
      ------
      RuntimeError
          If :meth:`score_cycles` has not been called yet
          (``cycle_confidence`` column is missing from ``cycles_df``).



   .. py:method:: export(approved_only: bool = True, exclude_list: list[int] | None = None) -> tuple[pandas.DataFrame, dict]

      Filter cycles to approved windows and write outputs.

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



   .. py:method:: summary() -> None

      Print a brief overview of the selection results to stdout.

      Shows total cycle count, mean confidence, severe-drift day count, and
      window counts.  Safe to call at any pipeline stage; lines whose
      prerequisite step has not run are silently omitted.

      Returns
      -------
      None



.. py:function:: merge_sensor_qc_onto_cycles(cycles_df: pandas.DataFrame, qc_df: pandas.DataFrame, co2_col: str = 'CO2_qc_flag', h2o_col: str = 'H2O_qc_flag', chamber_map: dict | None = None) -> pandas.DataFrame

   Aggregate per-cycle mean sensor QC flags from the high-frequency QC parquet.

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


.. py:data:: __version__

