palmwtc.flux
============

.. py:module:: palmwtc.flux

.. autoapi-nested-parse::

   CO₂ and H₂O flux calculation from whole-tree chamber cycles.

   - :mod:`~palmwtc.flux.absolute` — single-cycle ppm s⁻¹ → µmol m⁻² s⁻¹
     conversion (CO₂) and mmol mol⁻¹ s⁻¹ → mmol m⁻² s⁻¹ (H₂O) via
     ideal gas law.
   - :mod:`~palmwtc.flux.chamber` — chamber geometry, tree-biomass lookup,
     and batch per-cycle flux computation. Also holds the default QC
     threshold dicts used by cycle scoring.
   - :mod:`~palmwtc.flux.cycles` — cycle identification, quality scoring,
     bimodal-fault detection, and daily-score aggregation.
   - :mod:`~palmwtc.flux.scaling` — LAI estimation and ground → leaf-area
     flux conversion; PAR estimation from shortwave radiation.



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/flux/absolute/index
   /api/palmwtc/flux/advanced_outlier/index
   /api/palmwtc/flux/chamber/index
   /api/palmwtc/flux/cycles/index
   /api/palmwtc/flux/scaling/index


Attributes
----------

.. autoapisummary::

   palmwtc.flux.DEFAULT_ADVANCED_OUTLIER_CONFIG
   palmwtc.flux.DEFAULT_CO2_QC_THRESHOLDS
   palmwtc.flux.DEFAULT_CONFIG
   palmwtc.flux.DEFAULT_H2O_QC_THRESHOLDS
   palmwtc.flux.DEFAULT_WPL_QC_THRESHOLDS
   palmwtc.flux.NIGHTTIME_CO2_QC_THRESHOLDS
   palmwtc.flux.NIGHTTIME_H2O_QC_THRESHOLDS
   palmwtc.flux.NIGHTTIME_QC_THRESHOLDS


Functions
---------

.. autoapisummary::

   palmwtc.flux.calculate_absolute_flux
   palmwtc.flux.calculate_flux_for_chamber
   palmwtc.flux.calculate_h2o_absolute_flux
   palmwtc.flux.compute_ensemble_score
   palmwtc.flux.compute_rolling_zscore
   palmwtc.flux.compute_stl_residual_scores
   palmwtc.flux.apply_wpl_correction
   palmwtc.flux.apply_wpl_qc_overrides
   palmwtc.flux.build_cycle_wpl_metrics
   palmwtc.flux.calculate_flux_cycles
   palmwtc.flux.calculate_h2o_flux_cycles
   palmwtc.flux.calculate_h2o_flux_for_cycle
   palmwtc.flux.compute_closure_confidence
   palmwtc.flux.get_tree_volume_at_date
   palmwtc.flux.load_tree_biophysics
   palmwtc.flux.prepare_chamber_data
   palmwtc.flux.score_h2o_flux_qc
   palmwtc.flux.summarize_wpl_correction
   palmwtc.flux._evaluate_cycle_wrapper
   palmwtc.flux.compute_day_scores
   palmwtc.flux.compute_ml_anomaly_flags
   palmwtc.flux.compute_temporal_coherence
   palmwtc.flux.detect_bimodal_cycle
   palmwtc.flux.identify_cycles
   palmwtc.flux.score_cycle
   palmwtc.flux.score_day_quality
   palmwtc.flux.add_par_estimates
   palmwtc.flux.calculate_lai_effective
   palmwtc.flux.estimate_leaf_area
   palmwtc.flux.estimate_par_from_radiation
   palmwtc.flux.load_biophysical_data
   palmwtc.flux.scale_to_leaf_basis


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


.. py:function:: calculate_flux_for_chamber(chamber_df, chamber_name, temp_col='Temp', min_points=5, min_r2=0.0, start_cutoff=50)

   Identify cycles and compute absolute CO₂ flux for one chamber.

   Segments a raw time-series DataFrame into closure cycles (gaps
   > 300 s mark a new cycle), fits a linear slope to the CO₂
   concentration over each cycle, then converts those slopes to
   absolute fluxes using :func:`calculate_absolute_flux`.

   This is a legacy convenience wrapper retained for API compatibility.
   The active pipeline (notebooks 030/033/080) uses
   :func:`palmwtc.flux.cycles.calculate_flux_cycles` instead.

   Parameters
   ----------
   chamber_df : pd.DataFrame
       Raw time-series for a single chamber. Expected columns:

       ``TIMESTAMP`` : datetime-like
           Measurement time (used to detect cycle boundaries and to
           set ``flux_date`` on the output).
       ``CO2`` : float
           CO₂ concentration (ppm).
       ``{temp_col}`` : float, optional
           Chamber air temperature (°C). Column name set by the
           ``temp_col`` argument.
       ``Flag`` : int, optional
           QC flag. Maximum flag value within the cycle is recorded as
           ``qc_flag`` in the output.

   chamber_name : str
       Label for this chamber, used in progress messages and the
       ``Source_Chamber`` column of the output.
   temp_col : str, default ``"Temp"``
       Name of the temperature column in ``chamber_df``.
   min_points : int, default 5
       Minimum number of measurements (after the start cutoff) required
       to fit a slope. Cycles with fewer points are skipped.
   min_r2 : float, default 0.0
       Minimum R² threshold. Cycles below this value are skipped.
       Default 0.0 accepts all slopes regardless of fit quality.
   start_cutoff : int, default 50
       Seconds to ignore from the start of each cycle before fitting
       the slope. Removes the initial mixing transient.

   Returns
   -------
   pd.DataFrame
       One row per accepted cycle, with columns:

       - ``Source_Chamber`` : chamber label.
       - ``cycle_id`` : sequential integer.
       - ``flux_date`` : cycle start timestamp.
       - ``flux_slope`` : CO₂ slope (ppm s⁻¹) from linear regression.
       - ``r_squared`` : R² of the regression.
       - ``mean_temp`` : mean chamber temperature (°C) over the cycle.
       - ``qc_flag`` : maximum QC flag value in the cycle.
       - ``n_points`` : number of data points used.
       - ``duration_sec`` : seconds from the start-cutoff to the last
         point used.
       - ``flux_absolute`` : absolute CO₂ flux (µmol m⁻² s⁻¹) from
         :func:`calculate_absolute_flux`.

       Returns an empty DataFrame if ``chamber_df`` is empty or no
       cycles pass the quality thresholds.

   See Also
   --------
   calculate_absolute_flux : Per-row conversion used internally.
   palmwtc.flux.cycles.calculate_flux_cycles : Preferred batch
       pipeline replacement for this function.


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


.. py:data:: DEFAULT_ADVANCED_OUTLIER_CONFIG
   :type:  dict[str, Any]

.. py:function:: compute_ensemble_score(df: pandas.DataFrame, cfg: dict[str, Any] = DEFAULT_ADVANCED_OUTLIER_CONFIG) -> pandas.DataFrame

   Rank-normalise every detector present and combine into an ensemble score.

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


.. py:function:: compute_rolling_zscore(df: pandas.DataFrame, cfg: dict[str, Any] = DEFAULT_ADVANCED_OUTLIER_CONFIG) -> pandas.DataFrame

   Per-chamber centred rolling-window z-score on the cycle-level slope.

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


.. py:function:: compute_stl_residual_scores(df: pandas.DataFrame, cfg: dict[str, Any] = DEFAULT_ADVANCED_OUTLIER_CONFIG) -> pandas.DataFrame

   Per-chamber STL decomposition (parallel via ``joblib``).

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


.. py:data:: DEFAULT_CO2_QC_THRESHOLDS

   Daytime CO₂ QC grading thresholds for :func:`palmwtc.flux.cycles.score_cycle`.

   Each threshold has an ``_A`` (Grade A boundary) and ``_B`` (Grade B boundary)
   variant. A cycle that passes all ``_A`` tests is Grade A (tier 0). A cycle
   that fails one or more ``_A`` tests but passes all ``_B`` tests is Grade B
   (tier 1). Failing any ``_B`` test downgrades to Grade C (tier 2).

   Keys
   ----
   r2_A, r2_B : float
       Minimum R² of the OLS linear fit. Daytime photosynthesis and respiration
       cycles have large, clean CO₂ signals so the bar is high (0.90 / 0.70).
   nrmse_A, nrmse_B : float
       Maximum normalized RMSE (RMSE divided by CO₂ concentration range). Low
       values (0.10 / 0.20) indicate a clean linear trend.
   snr_A, snr_B : float
       Minimum signal-to-noise ratio, defined as (|slope| × duration) / RMSE.
       Measures whether the CO₂ trend is distinguishable from measurement noise.
   monotonic_A, monotonic_B : float
       Minimum fraction of consecutive concentration steps that move in the
       direction of the fitted slope (steps smaller than ``noise_eps_ppm`` are
       ignored). Daytime CO₂ should rise or fall steadily inside a closed chamber.
   outlier_A, outlier_B : float
       Maximum fraction of points removed as statistical outliers before
       re-fitting (0.05 / 0.15).
   curvature_aicc : float
       AICc difference (quadratic minus linear) threshold. Values more negative
       than this indicate significant curvature, flagging possible leaks or
       mixing issues. Note: this key is read by
       :func:`palmwtc.flux.cycles.score_cycle`, not by functions in this module
       directly.
   slope_diff_A, slope_diff_B : float
       Maximum relative difference between OLS slope and Theil-Sen slope
       (``|slope_ols - slope_ts| / |slope_ols|``). Large differences indicate
       leverage points or non-linearity.
   signal_ppm_guard : float
       Total CO₂ change (ppm) below which the ``monotonic_A/B`` thresholds are
       scaled down proportionally. Prevents mass rejection of low-flux cycles
       where noise-to-signal ratio is inherently higher.

   See Also
   --------
   NIGHTTIME_CO2_QC_THRESHOLDS : Relaxed version for dark/respiration cycles.
   palmwtc.flux.cycles.score_cycle : Function that consumes these thresholds.


.. py:data:: DEFAULT_CONFIG

   Default pipeline configuration for cycle detection, regression, and WPL.

   Pass ``{**DEFAULT_CONFIG, "key": new_value}`` to any pipeline function to
   override individual settings without losing the other defaults.

   Keys
   ----
   cycle_gap_sec : int
       Minimum gap in seconds between two successive measurements that
       triggers the start of a new measurement cycle (default ``300``).
   start_cutoff_sec : int
       Number of seconds to skip from the beginning of a cycle before
       starting the regression window search (default ``50``).
       Skips the initial chamber-mixing transient.
   start_search_sec : int
       How far into the cycle (seconds) the window-start search extends
       (default ``60``).
   min_points : int
       Minimum number of valid data points required to attempt a flux
       regression (default ``20``).
   min_duration_sec : int
       Minimum regression window length in seconds (default ``180``).
   outlier_z : float
       Z-score threshold for iterative outlier removal before re-fitting
       (default ``2``).
   max_outlier_refit_frac : float
       Maximum fraction of points that may be removed as outliers; if
       exceeded the original fit is kept (default ``0.2``).
   noise_eps_ppm : float
       Noise floor in ppm used when computing the monotonicity fraction
       (steps smaller than this are treated as noise, not signal direction,
       default ``0.5``).
   accepted_co2_qc_flags : list of int
       Only rows whose ``CO2_{suffix}_qc_flag`` is in this list are kept
       (default ``[0]``; ``None`` keeps all rows).
   accepted_h2o_qc_flags : list of int
       Same for ``H2O_{suffix}_qc_flag`` (default ``[0, 1]``; H₂O flag 1
       is a minor sensor warning that still produces usable data).
   prefer_corrected_h2o : bool
       When ``True``, use ``H2O_{suffix}_corrected`` over raw
       ``H2O_{suffix}`` if the corrected column is present (default
       ``True``).
   require_h2o_for_wpl : bool
       When ``True``, :func:`prepare_chamber_data` raises ``ValueError``
       if no H₂O column is found and WPL correction is requested (default
       ``True``). Set to ``False`` to fall back to wet CO₂.
   h2o_valid_range : tuple of float
       Physical validity bounds for H₂O in mmol mol⁻¹ as ``(lo, hi)``
       (default ``(0.0, 60.0)``). Values outside this range are set to
       NaN before WPL correction.
   max_abs_wpl_rel_change : float
       Maximum plausible absolute relative WPL correction (default
       ``0.12``, i.e. 12 %). Rows with larger corrections get a Flag
       upgrade to 2.
   use_multiprocessing : bool
       Use :class:`multiprocessing.Pool` for cycle batches larger than 50
       cycles (default ``True``).
   n_jobs : int
       Number of parallel worker processes (default ``min(8, cpu_count)``).


.. py:data:: DEFAULT_H2O_QC_THRESHOLDS

   Daytime H₂O QC grading thresholds for :func:`score_h2o_flux_qc`.

   H₂O thresholds are systematically looser than the CO₂ counterparts in
   :data:`DEFAULT_CO2_QC_THRESHOLDS`. Two reasons:

   1. The LI-COR LI-850 H₂O channel has higher absolute noise (~0.1–0.2 mmol
      mol⁻¹ RMS) than the CO₂ channel, reducing R² and SNR for the same
      physical signal size.
   2. Transpiration signals in humid tropical conditions are often 0.5–3 mmol
      mol⁻¹ over a 5-minute cycle — smaller fractional change than CO₂ during
      active photosynthesis.

   Keys
   ----
   r2_A, r2_B : float
       Minimum R² of the OLS linear fit (0.70 / 0.50).
   nrmse_A, nrmse_B : float
       Maximum normalized RMSE (0.15 / 0.25).
   snr_A, snr_B : float
       Minimum SNR, computed as (|Theil-Sen slope| × duration) / residual std
       (5.0 / 3.0).
   monotonic_A, monotonic_B : float
       Minimum fraction of H₂O steps larger than 0.05 mmol mol⁻¹ that move in
       the fitted-slope direction (0.70 / 0.40). The 0.05 mmol mol⁻¹ noise floor
       prevents sensor jitter from deflating the fraction.
   outlier_A, outlier_B : float
       Maximum fraction of outlier points allowed before downgrading (0.15 /
       0.25). Looser than CO₂ because H₂O droplets on the optical path can
       cause isolated spikes.
   signal_mmol_guard : float
       H₂O concentration range (mmol mol⁻¹) below which ``nrmse_B`` and
       ``monotonic_B`` are relaxed proportionally (default 0.3). Prevents mass
       rejection of valid but low-transpiration cycles.

   See Also
   --------
   NIGHTTIME_H2O_QC_THRESHOLDS : Relaxed version for nocturnal cycles.
   score_h2o_flux_qc : Function that consumes these thresholds.


.. py:data:: DEFAULT_WPL_QC_THRESHOLDS

   Per-cycle WPL correction validity thresholds used by :func:`apply_wpl_qc_overrides`.

   These thresholds check whether the WPL correction was well-conditioned for a
   given cycle, not whether the underlying CO₂ flux regression was good. A cycle
   can have perfect R² but still have a poor WPL correction if many H₂O readings
   were out-of-range or the humidity was unusually high.

   Keys
   ----
   valid_frac_A, valid_frac_B : float
       Minimum fraction of points in the cycle for which a valid WPL factor
       could be computed (i.e. H₂O was within ``h2o_valid_range`` and non-NaN).
       Grade A requires 98 % coverage; Grade B requires 95 %.
   rel_change_p95_A, rel_change_p95_B : float
       95th percentile of the absolute relative WPL correction
       (``|wpl_delta_ppm / CO2_raw|``) within the cycle.  Values above 7 %
       indicate unusually large humidity-driven adjustments that can distort
       the flux.  Values above 4 % are flagged as moderate (Grade B).
   factor_max_B : float
       Maximum WPL multiplication factor (``1 + χ_w / (1000 − χ_w)``) seen in
       the cycle.  A factor above 1.08 corresponds to approximately 86 mmol
       mol⁻¹ H₂O (86 % relative humidity at ~30 °C at sea level), which is
       outside the normal operating range and may indicate a wet-sensor event.

   See Also
   --------
   apply_wpl_qc_overrides : Function that applies these thresholds.
   DEFAULT_CONFIG : Contains ``h2o_valid_range`` and ``max_abs_wpl_rel_change``
       which are checked at the point level (before cycle aggregation) by
       :func:`prepare_chamber_data`.


.. py:data:: NIGHTTIME_CO2_QC_THRESHOLDS

   Relaxed CO₂ QC thresholds for nighttime cycles (Global_Radiation < 10 W m⁻²).

   This is an alias for :data:`palmwtc.flux.cycles.NIGHTTIME_QC_THRESHOLDS`.
   It is exposed here so callers that work only with :mod:`palmwtc.flux.chamber`
   do not need to import from the lower-level :mod:`palmwtc.flux.cycles` module.

   Why nighttime cycles need relaxed thresholds
   --------------------------------------------
   During the day, photosynthesis drives a strong, fast CO₂ drawdown inside the
   closed chamber (often 20–100 ppm over 5 minutes). This yields high R², SNR,
   and monotonicity, making the daytime ``_A`` thresholds easy to meet.

   At night, only leaf + soil respiration remain. CO₂ rise rates are typically
   3–15 ppm over 5 minutes — a much smaller signal that sits closer to instrument
   noise (~0.2–0.5 ppm RMS for LI-COR LI-850). Applying daytime thresholds to
   these cycles rejects most valid nighttime measurements.

   Relaxed values (compared to :data:`DEFAULT_CO2_QC_THRESHOLDS`)
   ---------------------------------------------------------------
   - ``r2_A`` 0.90 → 0.70, ``r2_B`` 0.70 → 0.40 — lower R² is expected when
     the signal is small relative to noise.
   - ``snr_A`` 10.0 → 5.0, ``snr_B`` 3.0 → 2.0 — smaller CO₂ trends mean
     lower SNR even in well-sealed chambers.
   - ``monotonic_A`` 0.80 → 0.50, ``monotonic_B`` 0.45 → 0.30 — a 5 ppm
     respiration signal with 0.5 ppm noise gives ~50 % monotonicity even when
     the signal is real.
   - ``signal_ppm_guard`` 5.0 → 3.0 — the guard activates earlier for the
     smaller nighttime signals.

   See Also
   --------
   DEFAULT_CO2_QC_THRESHOLDS : Daytime thresholds.
   palmwtc.flux.cycles.NIGHTTIME_QC_THRESHOLDS : Canonical source of these values.


.. py:data:: NIGHTTIME_H2O_QC_THRESHOLDS

   Relaxed H₂O QC thresholds for nighttime cycles (Global_Radiation < 10 W m⁻²).

   Why nighttime H₂O needs the most relaxed thresholds
   ----------------------------------------------------
   Stomata close at night, so transpiration drops to near zero.  A typical
   nighttime H₂O slope is 0.0–0.1 mmol mol⁻¹ min⁻¹ — often indistinguishable
   from sensor drift.  Applying daytime thresholds to these cycles would grade
   nearly all of them C, making nighttime water-balance closure impossible.
   The physical expectation at night is a **flat or very slowly rising** H₂O
   trace, not a steep linear increase.

   Relaxed values (compared to :data:`DEFAULT_H2O_QC_THRESHOLDS`)
   --------------------------------------------------------------
   - ``r2_A`` 0.70 → 0.50, ``r2_B`` 0.50 → 0.25 — a flat trace has R² ≈ 0
     by definition; low R² at night is not a data-quality failure.
   - ``nrmse_A`` 0.15 → 0.25, ``nrmse_B`` 0.25 → 0.45 — when the H₂O range
     is 0.1–0.2 mmol mol⁻¹, sensor noise dominates NRMSE.
   - ``snr_A`` 5.0 → 3.0, ``snr_B`` 3.0 → 1.5 — near-zero signal means SNR
     is near noise floor even in a well-sealed chamber.
   - ``monotonic_A`` 0.50 → 0.50, ``monotonic_B`` 0.40 → 0.30 — random-walk
     noise on a flat trace produces ~50 % monotonicity by chance.
   - ``signal_mmol_guard`` 0.30 → 0.15 — the guard activates at even smaller
     H₂O changes to protect valid low-transpiration cycles.

   See Also
   --------
   DEFAULT_H2O_QC_THRESHOLDS : Daytime thresholds.
   score_h2o_flux_qc : Function that applies these thresholds.


.. py:function:: apply_wpl_correction(co2_wet, h2o_mmol_mol)

   Convert wet CO₂ (ppm) to dry CO₂ using the WPL dilution correction.

   The Webb-Pearman-Leuning (WPL) correction removes the apparent dilution
   of CO₂ caused by the simultaneous presence of water vapour in the air
   sample. The formula is:

   .. math::

       CO_{2,dry} = CO_{2,wet} \times \left(1 + \frac{\chi_w}{1000 - \chi_w}\right)

   where :math:`\chi_w` is the H₂O mole fraction in mmol mol⁻¹.

   This is a simplified single-pass WPL for closed-chamber systems where
   temperature and pressure are treated as constant within a cycle.

   Parameters
   ----------
   co2_wet : array-like
       Wet CO₂ mole fraction in ppm (µmol mol⁻¹).
   h2o_mmol_mol : array-like
       Water vapour mole fraction in mmol mol⁻¹.  Values that would make
       the denominator ``(1000 - χ_w)`` non-positive are treated as invalid.

   Returns
   -------
   co2_dry : pd.Series
       Dry CO₂ in ppm.  NaN where either input is NaN or H₂O ≥ 1000 mmol
       mol⁻¹ (physically impossible, but guarded against).
   factor : pd.Series
       WPL multiplication factor ``1 + χ_w / (1000 - χ_w)``.  NaN where
       inputs are invalid.
   valid : pd.Series of bool
       ``True`` for rows where both inputs were valid and a WPL factor could
       be computed.

   Notes
   -----
   The WPL factor for typical tropical conditions (25 mmol mol⁻¹ H₂O,
   ~50 % RH at 30 °C) is approximately 1.026, adding ~2.6 % to the raw CO₂
   reading.  At 40 mmol mol⁻¹ (high humidity), the factor is ~1.042.

   See Also
   --------
   prepare_chamber_data : Calls this function and attaches outputs as columns.


.. py:function:: apply_wpl_qc_overrides(row, model_qc, flux_qc, reason_text, wpl_qc_thresholds=None, h2o_valid_range=(0.0, 60.0))

   Apply WPL-specific checks and upgrade QC tiers if needed.

   Checks whether the WPL correction was well-conditioned for a given cycle
   (sufficient valid H₂O data, reasonable correction magnitude, plausible
   WPL factor).  If any check fails, the ``model_qc`` and ``flux_qc`` tiers
   are upgraded (never downgraded) and a reason string is appended.

   This function is called after :func:`build_cycle_wpl_metrics` and
   :func:`palmwtc.flux.cycles.score_cycle` in the post-processing pipeline,
   not by :func:`calculate_flux_cycles` directly.

   Parameters
   ----------
   row : pd.Series or dict
       A single cycle row containing WPL metrics produced by
       :func:`build_cycle_wpl_metrics`: ``wpl_valid_fraction``,
       ``wpl_abs_rel_change_p95``, ``wpl_factor_max``, and ``h2o_max``.
   model_qc : int
       Current model QC tier (0 = A, 1 = B, 2 = C) to be potentially
       upgraded.
   flux_qc : int
       Current flux QC tier to be potentially upgraded.
   reason_text : str
       Semicolon-separated QC reasons accumulated so far.  New reasons are
       appended and duplicates are removed.
   wpl_qc_thresholds : dict or None
       Override :data:`DEFAULT_WPL_QC_THRESHOLDS`.
   h2o_valid_range : tuple of float
       ``(lo, hi)`` valid H₂O range in mmol mol⁻¹ (default
       ``(0.0, 60.0)``).  H₂O values above ``hi`` trigger a Grade C
       downgrade.

   Returns
   -------
   tuple of (int, int, int, str)
       ``(model_qc, flux_qc, wpl_qc, reason_text)`` where:

       - ``model_qc``, ``flux_qc`` are the (possibly upgraded) input tiers.
       - ``wpl_qc`` is the WPL-specific tier (0, 1, or 2) that drove the
         upgrade.
       - ``reason_text`` is the updated semicolon-separated reason string.

   See Also
   --------
   DEFAULT_WPL_QC_THRESHOLDS : Threshold values and key descriptions.
   build_cycle_wpl_metrics : Produces the per-cycle WPL metrics consumed here.


.. py:function:: build_cycle_wpl_metrics(chamber_df, chamber_name, cycle_gap_sec=300)

   Aggregate WPL correction metrics per measurement cycle.

   Produces one row per cycle with mean/max WPL factor, mean/max WPL
   delta, valid-data fraction, p95 relative change, and H₂O statistics.
   These per-cycle values are the input for :func:`apply_wpl_qc_overrides`.

   Parameters
   ----------
   chamber_df : pd.DataFrame
       Output of :func:`prepare_chamber_data`.
   chamber_name : str
       Chamber label (e.g. ``'Chamber 1'``), stored in the output column
       ``Source_Chamber``.
   cycle_gap_sec : int
       Gap in seconds that marks the boundary between cycles, passed to
       :func:`palmwtc.flux.cycles.identify_cycles`.

   Returns
   -------
   pd.DataFrame
       One row per cycle.  Columns:

       - ``cycle_id`` — integer cycle identifier.
       - ``Source_Chamber`` — *chamber_name*.
       - ``wpl_factor_mean`` — mean WPL factor within the cycle.
       - ``wpl_factor_max`` — maximum WPL factor within the cycle.
       - ``wpl_delta_ppm_mean`` — mean WPL additive correction (ppm).
       - ``wpl_delta_ppm_max`` — maximum WPL additive correction (ppm).
       - ``wpl_valid_fraction`` — fraction of rows with a non-NaN
         ``CO2_corrected`` value.
       - ``wpl_abs_rel_change_p95`` — 95th percentile of absolute relative
         WPL correction within the cycle.
       - ``h2o_mean`` — mean H₂O (mmol mol⁻¹) within the cycle.
       - ``h2o_max`` — maximum H₂O (mmol mol⁻¹) within the cycle.

       Returns an empty DataFrame if *chamber_df* is empty.

   See Also
   --------
   apply_wpl_qc_overrides : Consumes the per-cycle metrics produced here.
   summarize_wpl_correction : Dataset-level WPL summary.


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


.. py:function:: calculate_h2o_flux_for_cycle(cycle_data, gas_col='H2O', min_points=20, min_duration_sec=180)

   Compute H₂O slope and fit statistics for a single measurement cycle.

   Uses Theil-Sen regression to estimate the slope (robust to outliers) and
   OLS for R², RMSE, and residual statistics.  SNR is computed as
   ``|slope_ts × duration| / residual_std``, matching the CO₂ definition.
   Monotonicity is computed only on H₂O steps larger than 0.05 mmol mol⁻¹
   (approximately 5× LI-COR H₂O RMS noise) to avoid deflation by sensor
   jitter.

   Parameters
   ----------
   cycle_data : pd.DataFrame
       Single-cycle data slice.  Must contain ``TIMESTAMP`` and *gas_col*.
   gas_col : str
       Name of the H₂O column (default ``'H2O'``).
   min_points : int
       Minimum number of non-NaN H₂O values required (default ``20``).
   min_duration_sec : float
       Minimum span of the cycle in seconds (default ``180``).

   Returns
   -------
   dict or None
       ``None`` if the cycle has fewer than *min_points* valid rows or
       shorter than *min_duration_sec*.  Otherwise a dict with keys:

       - ``h2o_slope`` — Theil-Sen slope (mmol mol⁻¹ s⁻¹).
       - ``h2o_intercept`` — Theil-Sen intercept (mmol mol⁻¹).
       - ``h2o_r2`` — OLS R² (dimensionless, 0–1).
       - ``h2o_nrmse`` — NRMSE: OLS RMSE divided by H₂O range; NaN if
         range is zero.
       - ``h2o_snr`` — signal-to-noise ratio.
       - ``h2o_outlier_frac`` — fraction of points more than 2.5× MAD
         from the OLS fit.
       - ``h2o_monotonic_frac`` — fraction of noise-filtered consecutive
         steps in the slope direction; NaN if all steps are below the
         noise floor.
       - ``h2o_n_points`` — number of non-NaN points used.
       - ``h2o_duration`` — cycle duration in seconds.
       - ``h2o_conc_mean`` — mean H₂O concentration (mmol mol⁻¹).
       - ``h2o_conc_range`` — H₂O concentration range in the cycle
         (mmol mol⁻¹).

   See Also
   --------
   calculate_h2o_flux_cycles : Calls this function for every cycle.
   score_h2o_flux_qc : Uses the returned dict to assign a QC grade.


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


.. py:function:: get_tree_volume_at_date(df_vigor, tree_id, target_date)

   Time-interpolate the Vigor Index (m³) for a tree at a specific date.

   If an exact measurement exists on *target_date*, that value is returned
   directly.  Otherwise, the Vigor Index time series for the tree is
   linearly interpolated between the two nearest measurements.  No
   extrapolation is performed — dates outside the measurement range return
   ``None`` because the time-based interpolation does not fill beyond the
   index boundaries.

   Parameters
   ----------
   df_vigor : pd.DataFrame or None
       Output of :func:`load_tree_biophysics`.  ``None`` returns ``None``
       immediately.
   tree_id : str
       Tree identifier matching the ``Tree ID`` column in *df_vigor*
       (e.g. ``'EKA1-001'``).
   target_date : str or datetime-like
       The date for which to estimate the tree volume.  String values are
       parsed via :func:`pandas.to_datetime`.

   Returns
   -------
   float or None
       Vigor Index in m³ at *target_date*, or ``None`` if *df_vigor* is
       ``None``, *tree_id* is not found, or the date is outside the
       measured range.

   Notes
   -----
   The interpolation method is pandas ``'time'``, which assumes a constant
   growth rate between measurement visits.  Palm canopy volume grows roughly
   monotonically over the study period, so linear interpolation is
   appropriate for the typical visit interval of a few months.

   See Also
   --------
   load_tree_biophysics : Loads and parses the biophysical spreadsheet.

   Examples
   --------
   # doctest: +SKIP
   # Requires a DataFrame from load_tree_biophysics().
   vol = get_tree_volume_at_date(df_vigor, "EKA1-001", "2023-06-15")
   print(f"Tree volume: {vol:.4f} m3")


.. py:function:: load_tree_biophysics(base_dir)

   Load palm tree biophysical parameters from the PalmStudio spreadsheet.

   Reads ``Vigor_Index_PalmStudio.xlsx`` (expected at ``{base_dir}/``),
   converts Indonesian column names to English, converts measurements from
   centimetres to metres, and extracts the clone identifier from the tree
   ID string.

   The Vigor Index is the estimated above-ground biomass volume (cm³ in the
   spreadsheet, converted to m³ here).  It is computed by PalmStudio from
   measured height and canopy radii.  It is used by
   :func:`get_tree_volume_at_date` to time-interpolate tree volume for
   any given measurement date.

   Parameters
   ----------
   base_dir : str or Path
       Directory that contains ``Vigor_Index_PalmStudio.xlsx``.

   Returns
   -------
   pd.DataFrame or None
       One row per measurement visit per tree.  Columns:

       - ``Tree ID`` — tree identifier string (e.g. ``'EKA1-001'``).
       - ``Date`` — measurement date (datetime).
       - ``Height_m`` — total tree height in metres.
       - ``Max_Radius_m`` — maximum canopy radius in metres.
       - ``Est_Width_m`` — estimated canopy width (2 × mean radius) in
         metres.
       - ``Vigor_Index_m3`` — estimated tree volume in m³ (converted from
         cm³ by dividing by 1 000 000).
       - ``Clone`` — clone name extracted from ``Tree ID``
         (e.g. ``'EKA 1'``).

       Returns ``None`` (with a printed warning) if the file is not found.

   Notes
   -----
   The spreadsheet uses Indonesian column headings (``Tanggal``,
   ``Kode pohon``, ``Tinggi Pohon (cm)``).  This function handles the
   renaming automatically.

   See Also
   --------
   get_tree_volume_at_date : Time-interpolates Vigor Index from the table
       returned by this function.

   Examples
   --------
   # doctest: +SKIP
   # Requires Vigor_Index_PalmStudio.xlsx in the data directory.
   df_vigor = load_tree_biophysics("/path/to/data")
   print(df_vigor[["Tree ID", "Date", "Vigor_Index_m3"]].head())


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


.. py:function:: score_h2o_flux_qc(h2o_metrics, h2o_qc_thresholds=None, is_nighttime=False)

   Assign a QC grade to a single H₂O flux cycle.

   Applies a two-tier threshold system: a cycle that passes all ``_A``
   tests is Grade A (tier 0); failing any ``_A`` test but passing all
   ``_B`` tests gives Grade B (tier 1); failing any ``_B`` test gives
   Grade C (tier 2).

   A signal-size guard relaxes the ``nrmse_B`` and ``monotonic_B``
   thresholds proportionally for cycles where the H₂O range is smaller
   than ``signal_mmol_guard`` — preventing mass rejection of valid but
   low-transpiration cycles.

   Parameters
   ----------
   h2o_metrics : dict or None
       Output of :func:`calculate_h2o_flux_for_cycle`.  If ``None``,
       returns tier 2 / Grade C with reason ``'No valid H2O data'``.
   h2o_qc_thresholds : dict or None
       Override the default thresholds.  When ``None``, selects
       :data:`NIGHTTIME_H2O_QC_THRESHOLDS` if ``is_nighttime=True``,
       otherwise :data:`DEFAULT_H2O_QC_THRESHOLDS`.
   is_nighttime : bool
       Switches to the nighttime threshold set when ``True`` and no
       explicit thresholds are supplied.

   Returns
   -------
   tier : int
       0 for Grade A, 1 for Grade B, 2 for Grade C.
   label : str
       ``'A'``, ``'B'``, or ``'C'``.
   reasons : list of str
       Each failing test appends a human-readable string such as
       ``'R2=0.45<0.70'``.  Empty when all tests pass.

   See Also
   --------
   DEFAULT_H2O_QC_THRESHOLDS : Daytime threshold values and key descriptions.
   NIGHTTIME_H2O_QC_THRESHOLDS : Nighttime threshold values.
   calculate_h2o_flux_cycles : Calls this function for every cycle.


.. py:function:: summarize_wpl_correction(chamber_df)

   Return a dataset-level summary of WPL correction statistics.

   Useful for a quick sanity check: if the median WPL factor or p95
   relative change looks unusual, it may indicate sensor drift, water
   condensation on the optical path, or a humidity calibration issue.

   Parameters
   ----------
   chamber_df : pd.DataFrame
       Output of :func:`prepare_chamber_data`.  Must contain columns
       ``wpl_delta_ppm``, ``wpl_rel_change``, ``wpl_factor``, and
       optionally ``CO2_corrected``.

   Returns
   -------
   dict
       Empty dict if *chamber_df* is empty or missing WPL columns.
       Otherwise, keys are:

       - ``n_points`` — total row count.
       - ``valid_points`` — rows where ``CO2_corrected`` is not NaN.
       - ``median_factor`` — median WPL multiplication factor.
       - ``median_delta_ppm`` — median WPL additive correction (ppm).
       - ``p95_abs_rel_change`` — 95th percentile of ``|wpl_rel_change|``.

   See Also
   --------
   build_cycle_wpl_metrics : Per-cycle version of the same diagnostics.
   apply_wpl_qc_overrides : Uses per-cycle metrics to upgrade QC tiers.


.. py:data:: NIGHTTIME_QC_THRESHOLDS

   Relaxed QC thresholds applied when ``Global_Radiation < 10 W m⁻²``.

   At night, respiration signals are smaller and the CO₂ slope is close to zero,
   so noise-to-signal ratios are inherently higher.  These thresholds follow the
   same key structure as :data:`QC_THRESHOLDS` but with lower R² requirements,
   higher NRMSE/SNR tolerances, and a looser monotonicity floor.
   :func:`score_cycle` selects this dict automatically when ``is_nighttime=True``.


.. py:function:: _evaluate_cycle_wrapper(args)

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


.. py:function:: compute_ml_anomaly_flags(df: pandas.DataFrame, features: list[str] | None = None, contamination: float = 0.05, n_if_estimators: int = 200, max_if_samples: int = 10000, max_mcd_fit_samples: int = 5000, mcd_support_fraction: float = 0.75, mcd_threshold_percentile: float = 95.0, train_on_passing_only: bool = True, passing_qc_col: str = 'flux_qc', passing_qc_max: int = 1, combination_mode: str = 'AND', random_state: int = 42, n_jobs: int = -1) -> pandas.DataFrame

   Add ML-based anomaly flags to a cycle-level flux DataFrame.

   Trains two unsupervised anomaly detectors on cycles that passed the
   rule-based QC (``flux_qc <= passing_qc_max``), then scores **all** cycles.
   The ML flag is complementary to the A/B/C tier system: it detects
   multivariate anomalies — unusual *combinations* of quality metrics —
   that the individual threshold checks in :func:`score_cycle` may miss.

   Because the models train only on passing cycles, the "normal" region of
   feature space is defined by cycles the rule-based system already trusts.
   Cycles flagged by ML but not by the rule-based system represent edge cases
   that are individually plausible on each metric but collectively unusual.

   Models
   ------
   Isolation Forest [1]_ (``sklearn.ensemble.IsolationForest``)
       Random-subspace tree ensemble.  Anomalies are isolated with fewer
       splits than inliers.  O(n log n) fit and score; ``max_samples`` is
       capped at ``max_if_samples`` so memory is bounded even at 1 M rows.
       On machines with a CUDA GPU, :func:`~palmwtc.hardware.gpu.get_isolation_forest`
       substitutes cuML's GPU-accelerated implementation automatically.

   Robust Covariance / MCD (``sklearn.covariance.MinCovDet``)
       Minimum Covariance Determinant estimator [2]_ — a robust alternative
       to the standard covariance matrix that is resistant to outliers in the
       training data.  Fit on a random subsample of at most
       ``max_mcd_fit_samples`` rows.  Mahalanobis distances for **all** rows
       are computed via a batched matrix multiply — O(n × p²), not O(n²) —
       safe at 1 M rows.  The anomaly threshold is the
       ``mcd_threshold_percentile``-th percentile of training-set distances
       (empirical calibration, avoiding the multivariate-normality assumption
       of chi-squared thresholding).

   Parameters
   ----------
   df : pd.DataFrame
       Cycle-level DataFrame as produced by
       :func:`~palmwtc.flux.chamber.calculate_flux_cycles` and scored by
       :func:`score_cycle`.
   features : list of str or None
       Feature column names to use.  If None, :data:`DEFAULT_ML_FEATURES` is
       used.  Column name aliases are resolved automatically (e.g. ``r2`` →
       ``co2_r2``).  At least 3 resolvable features must be present; otherwise
       a ``ValueError`` is raised.
   contamination : float
       Expected fraction of anomalies for Isolation Forest (default 0.05 = 5%).
   n_if_estimators : int
       Number of trees in the Isolation Forest (default 200).
   max_if_samples : int
       Maximum number of training samples per Isolation Forest tree
       (default 10 000).
   max_mcd_fit_samples : int
       Maximum number of rows used to fit the MinCovDet estimator
       (default 5 000).
   mcd_support_fraction : float
       Fraction of observations used to compute the robust MCD scatter
       estimate (default 0.75 — 75% of the fit sample).
   mcd_threshold_percentile : float
       Percentile of training-set Mahalanobis distances used as the MCD
       anomaly threshold (default 95.0).
   train_on_passing_only : bool
       If True (default), only cycles with ``flux_qc <= passing_qc_max``
       are used to train the models.  This ensures the models learn from
       verified good measurements.
   passing_qc_col : str
       Name of the rule-based QC column (default ``'flux_qc'``).
   passing_qc_max : int
       Maximum QC value for training inclusion (default 1 = tier A and B).
   combination_mode : str
       How to combine the two detector outputs:

       ``'AND'`` (default)
           Both detectors must agree.  Flags ~3% of A/B cycles.
       ``'OR'``
           Either detector alone triggers the flag.  Flags ~7% of A/B cycles.
   random_state : int
       Random seed for reproducibility (default 42).
   n_jobs : int
       Number of parallel workers for Isolation Forest fitting (default -1 =
       all available CPUs).

   Returns
   -------
   pd.DataFrame
       Copy of ``df`` with three new columns:

       ``ml_if_score`` : float
           Raw Isolation Forest anomaly score (more negative = more anomalous).
       ``ml_mcd_dist`` : float
           Mahalanobis distance from the robust MCD centroid (larger = more
           anomalous).
       ``ml_anomaly_flag`` : int
           Combined binary flag: 1 = anomalous, 0 = OK.

   Raises
   ------
   ImportError
       If scikit-learn is not installed (it is an optional dependency).
   ValueError
       If fewer than 3 feature columns can be resolved, or if the training
       set has too few rows.

   Notes
   -----
   The ``_completeness_ratio`` feature (``n_points_used / n_points_total``)
   is derived automatically if both columns are present and is added to the
   feature matrix as an extra dimension.  It is removed from the output
   DataFrame before returning.

   References
   ----------
   .. [1] Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation forest.
          *2008 Eighth IEEE International Conference on Data Mining*, 413–422.
          https://doi.org/10.1109/ICDM.2008.17
   .. [2] Rousseeuw, P. J., & Driessen, K. V. (1999). A fast algorithm for
          the minimum covariance determinant estimator. *Technometrics*,
          41(3), 212–223. https://doi.org/10.1080/00401706.1999.10485670

   See Also
   --------
   score_cycle : Rule-based QC that this function complements.
   DEFAULT_ML_FEATURES : Default feature list (``flux_slope`` is excluded).

   Examples
   --------
   >>> import pandas as pd  # doctest: +SKIP
   >>> # Requires a scored flux DataFrame from calculate_flux_cycles() and
   >>> # score_cycle(); see tutorial notebook 032 for a full walkthrough.


.. py:function:: compute_temporal_coherence(flux_df: pandas.DataFrame, max_slope_ratio: float = 3.0, transition_hours: tuple = (6, 7, 8, 17, 18, 19), hourly_cv_threshold: float = 0.5) -> pandas.DataFrame

   Flag cycles that are implausible given their immediate neighbours.

   Two complementary checks are applied:

   1. **Temporal coherence (per-cycle)**: compares each passing cycle's
      slope to the previous passing cycle's slope *on the same day*.
      A cycle is flagged if:

      - It has the **same sign** as its predecessor but the magnitude
        ratio exceeds ``max_slope_ratio`` (sudden unexplained jump).
      - It has the **opposite sign** to its predecessor during mid-day
        hours (08:00–16:00) and the absolute slope is > 0.005 ppm s⁻¹
        (not a genuine zero-crossing — transition hours like dawn/dusk
        are exempt because photosynthesis can genuinely flip sign there).

   2. **Hourly CV flag**: within each (date, hour) group of passing cycles,
      the coefficient of variation CV = std(slopes) / mean(|slopes|) is
      computed.  If CV > ``hourly_cv_threshold``, all cycles in that group
      receive ``hourly_cv_flag = 1`` (erratic within-hour scatter, likely
      indicating unstable ambient conditions or chamber leakage).

   Only cycles with ``flux_qc <= 1`` are checked; QC-2 cycles are skipped
   (they carry ``temporal_coherence_flag = 0`` by default and should be
   excluded before further analysis anyway).

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level DataFrame produced by
       :func:`~palmwtc.flux.chamber.calculate_flux_cycles`.  Must contain:

       - ``flux_datetime`` or ``flux_date`` — datetime of cycle start.
       - ``flux_slope`` or ``co2_slope``    — CO₂ slope in ppm s⁻¹.
       - ``flux_qc``                        — rule-based QC flag (0, 1, 2).

   max_slope_ratio : float
       Maximum |slope_i / slope_prev| ratio within a same-sign pair before
       the cycle is flagged as a temporal jump (default 3.0).
   transition_hours : tuple of int
       Hours of day where sign flips are physically expected (dawn and dusk).
       Cycles at these hours are exempt from the sign-flip check.
       Default ``(6, 7, 8, 17, 18, 19)``; hour 8 is included because
       VPD-delayed stomatal opening can shift the transition past 08:00
       in humid tropical conditions.
   hourly_cv_threshold : float
       CV threshold for the within-hour check (default 0.50 = 50%).
       CV > 0.50 means the within-hour scatter exceeds half the mean
       absolute flux, which is unusual for stable chamber measurements.

   Returns
   -------
   pd.DataFrame
       Copy of ``flux_df`` with two additional columns:

       ``temporal_coherence_flag`` : int (0 or 1)
           1 if the cycle was flagged by the pairwise slope-jump or
           sign-flip check.
       ``hourly_cv_flag`` : int (0 or 1)
           1 if the cycle belongs to a (date, hour) group with CV above
           ``hourly_cv_threshold``.

   Notes
   -----
   The function accepts both ``flux_datetime`` and ``flux_date`` as the
   datetime column name, and both ``flux_slope`` and ``co2_slope`` as the
   slope column name, to be compatible with both the notebook-produced
   DataFrame and the digital-twin CSV format.

   See Also
   --------
   compute_day_scores : Uses the flags produced here to filter clean cycles.

   Examples
   --------
   >>> import pandas as pd  # doctest: +SKIP
   >>> # Full example requires a multi-row flux DataFrame from
   >>> # calculate_flux_cycles(); see tutorial notebook 032.


.. py:function:: detect_bimodal_cycle(values: numpy.ndarray, bin_width: float = 5.0, min_gap_bins: int = 4, min_side_points: int = 3) -> dict

   Detect bimodal CO₂ or H₂O distribution within a single cycle.

   Bimodality here means two clean clusters separated by a run of empty
   histogram bins — the signature of an instrument fault rather than
   real biological variability.

   The most common fault source is a **real-time-clock (RTC) glitch** in
   the LI-COR multiplexer: when the logger's timestamp loses sync for a few
   seconds, measurements from two different time windows (e.g. one from
   earlier in the cycle and one current) are interleaved into the same
   cycle record.  The two windows have different ambient CO₂ levels, so
   the within-cycle distribution splits into two separate clusters with a
   distinct gap between them.

   This is **not** the same as a wide or noisy distribution.  A cycle with
   large random scatter around a single trend will be unimodal and will
   not be flagged by this function.  The bimodal flag is complementary to
   the R²/NRMSE checks in :func:`score_cycle`: a bimodal cycle often still
   has a plausible R² if both clusters happen to share the same trend.

   The function is called inside :func:`evaluate_cycle` on the full raw
   cycle (before the best-window selection) so that the fault can be
   detected even if the fit window excludes part of the contaminated data.

   Parameters
   ----------
   values : array-like
       Raw concentration values for one cycle (ppm CO₂ or g kg⁻¹ H₂O).
       NaN and Inf values are ignored.
   bin_width : float
       Histogram bin width in the same units as ``values`` (default 5 ppm).
   min_gap_bins : int
       Minimum number of consecutive empty histogram bins between two
       non-empty regions required to call a cycle bimodal (default 4 bins
       = 20 ppm gap at the default ``bin_width``).
   min_side_points : int
       Minimum number of data points required on each side of the gap
       (default 3).  Prevents false positives from single-point outliers.

   Returns
   -------
   dict
       Dictionary with four keys:

       ``is_bimodal`` : bool
           True if a bimodal distribution was detected.
       ``gap_ppm`` : float
           Width of the empty gap in the same units as ``values`` (0.0 if
           not bimodal).
       ``lower_mean`` : float
           Mean of the lower concentration cluster (NaN if not bimodal).
       ``upper_mean`` : float
           Mean of the upper concentration cluster (NaN if not bimodal).

   Notes
   -----
   The algorithm:

   1. Build a histogram of ``values`` with ``bin_width``-wide bins.
   2. Locate the longest run of consecutive zero-count bins between the
      first and last non-empty bin.
   3. If that run spans ≥ ``min_gap_bins`` bins and both sides have
      ≥ ``min_side_points`` points, flag as bimodal.

   The cycle must contain at least 10 finite values and span more than
   ``bin_width × (min_gap_bins + 2)`` ppm; otherwise the function returns
   ``is_bimodal=False`` without computing the histogram.

   Examples
   --------
   Two clusters separated by a 30-ppm gap:

   >>> import numpy as np
   >>> from palmwtc.flux.cycles import detect_bimodal_cycle
   >>> low  = np.linspace(395, 398, 8)
   >>> high = np.linspace(430, 433, 8)
   >>> result = detect_bimodal_cycle(np.concatenate([low, high]))
   >>> result["is_bimodal"]
   True
   >>> result["gap_ppm"] >= 20.0
   True

   A noisy but unimodal cycle is not flagged:

   >>> rng = np.random.default_rng(0)
   >>> unimodal = 400 + rng.normal(0, 2, 20)
   >>> detect_bimodal_cycle(unimodal)["is_bimodal"]
   False


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


.. py:function:: add_par_estimates(flux_df: pandas.DataFrame, radiation_column: str = 'GlobalRadiation_Avg', par_column: str = 'PAR_estimated') -> pandas.DataFrame

   Add an estimated PAR column to a flux DataFrame.

   Calls :func:`estimate_par_from_radiation` on *radiation_column* and
   stores the result in *par_column*.  When *radiation_column* is absent,
   *par_column* is filled with ``NaN`` and a warning is printed.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux cycle data.  Should contain a column with global shortwave
       radiation in W m⁻²; see *radiation_column*.
   radiation_column : str, optional
       Name of the global radiation column in *flux_df*.
       Default: ``'GlobalRadiation_Avg'``.
   par_column : str, optional
       Name for the new PAR column.
       Default: ``'PAR_estimated'``.

   Returns
   -------
   pd.DataFrame
       Copy of *flux_df* with one additional column *par_column*
       (µmol m⁻² s⁻¹).

   Examples
   --------
   >>> import pandas as pd
   >>> df = pd.DataFrame({"GlobalRadiation_Avg": [0.0, 500.0, 1000.0]})
   >>> result = add_par_estimates(df)
   >>> [round(float(v), 1) for v in result["PAR_estimated"]]
   [0.0, 1028.2, 2056.5]


.. py:function:: calculate_lai_effective(flux_df: pandas.DataFrame, biophys_df: pandas.DataFrame, chamber_floor_area: dict | None = None) -> pandas.DataFrame

   Compute effective LAI for each flux cycle and attach it to the DataFrame.

   For each row in *flux_df* the function looks up the biophysical measurement
   that is closest in time (within 30 days) for the same chamber, estimates the
   total leaf area with :func:`estimate_leaf_area`, then divides by the chamber
   floor area to obtain LAI_effective.

   .. math::

       \text{LAI}_{\text{eff}} = \frac{\text{leaf\_area\_m2}}{\text{chamber\_floor\_area\_m2}}

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux cycle data.  Must contain:

       - ``flux_date`` — date of the flux cycle (datetime or date-like).
       - ``Source_Chamber`` — chamber name string, either ``'Chamber 1'`` or
         ``'Chamber 2'``.

   biophys_df : pd.DataFrame
       Output of :func:`load_biophysical_data`.  Must contain ``date``,
       ``chamber``, and ``n_leaves`` columns.

   chamber_floor_area : dict or None, optional
       Override the floor area (m²) per date and chamber::

           {date: {1: area_m2, 2: area_m2}}

       When ``None``, a date-based default is used:
       before 2025-07-01 → 4 m² (2 m × 2 m footprint);
       from 2025-07-01 onwards → 16 m² (4 m × 4 m footprint).

   Returns
   -------
   pd.DataFrame
       Copy of *flux_df* with four additional columns:

       - ``n_leaves`` — leaf count from the nearest biophysical visit.
       - ``leaf_area_m2`` — estimated total leaf area (m²).
       - ``chamber_floor_area_m2`` — floor area used for this cycle (m²).
       - ``lai_effective`` — dimensionless LAI (m² leaf m⁻² ground).

       Rows for which no biophysical measurement falls within 30 days, or
       whose chamber name is not recognised, retain ``NaN`` in all four
       columns.

   Notes
   -----
   Temporal matching uses the nearest biophysical visit, not linear
   interpolation.  The 30-day tolerance prevents using measurements from a
   different phenological stage.

   Examples
   --------
   Conceptual usage — requires a valid biophysical spreadsheet:

   >>> biophys = load_biophysical_data("path/to/Vigor_Index_PalmStudio.xlsx")  # doctest: +SKIP
   >>> result = calculate_lai_effective(flux_df, biophys)  # doctest: +SKIP
   >>> result["lai_effective"].between(1, 8).all()  # doctest: +SKIP
   True


.. py:function:: estimate_leaf_area(n_leaves: float | numpy.ndarray, tree_code: str | None = None, method: str = 'conservative') -> float | numpy.ndarray

   Estimate total leaf area (m²) from leaf count.

   Oil-palm leaf area varies with leaf rank (position on the stem) and tree
   age.  Chamber trees at the LIBZ site are younger and smaller than mature
   field palms, so a conservative area-per-leaf assumption avoids
   over-estimating LAI and over-scaling fluxes.

   Parameters
   ----------
   n_leaves : float or array-like
       Number of leaves counted on the tree.
   tree_code : str or None, optional
       Tree-code string (e.g. ``'2.2/EKA-1/2107'``).  Currently unused;
       reserved for future species-specific look-ups.
   method : {'conservative', 'literature_max', 'fixed'}, optional
       Area-per-leaf assumption to apply.  Default is ``'conservative'``.

       ``'conservative'``
           4 m² leaf⁻¹.  Appropriate for the younger chamber palms at LIBZ.
           Derived as a weighted average across leaf ranks:
           young leaves (rank 1–3) ≈ 2 m², productive leaves (rank 4–15)
           ≈ 5 m², old leaves (rank 16+) ≈ 3 m² → weighted mean ≈ 4 m².
       ``'literature_max'``
           12 m² leaf⁻¹.  Upper bound from literature for mature field palms.
       ``'fixed'``
           6 m² leaf⁻¹.  Middle-ground estimate.

   Returns
   -------
   float or ndarray
       Total leaf area in m².

   Raises
   ------
   ValueError
       If *method* is not one of the recognised strings.

   Notes
   -----
   Literature values for *mature* field oil palms range from 8–15 m² per
   productive leaf (mean ≈ 12 m²).  Chamber palms at LIBZ are 3–6 m² per
   leaf.  Using ``'conservative'`` gives a target LAI of roughly 2–6, which
   is realistic for oil palm.

   Examples
   --------
   >>> estimate_leaf_area(30, method="conservative")
   120.0
   >>> estimate_leaf_area(30, method="literature_max")
   360.0
   >>> import numpy as np
   >>> counts = np.array([20, 30, 40])
   >>> estimate_leaf_area(counts, method="conservative")
   array([ 80., 120., 160.])


.. py:function:: estimate_par_from_radiation(radiation_w_m2: float | numpy.ndarray, conversion_factor: float = 0.45) -> float | numpy.ndarray

   Estimate PAR from global shortwave radiation using the McCree factor.

   Applies a two-step conversion:

   1. Multiply global radiation by *conversion_factor* to isolate the
      PAR waveband (400–700 nm).
   2. Convert the PAR energy flux (W m⁻²) to quantum flux
      (µmol m⁻² s⁻¹) using 4.57 µmol J⁻¹, the broadband energy-to-photon
      factor for the solar spectrum determined by McCree (1972) [1]_.

   Parameters
   ----------
   radiation_w_m2 : float or array-like
       Global shortwave radiation (W m⁻²).
   conversion_factor : float, optional
       Fraction of global radiation in the PAR waveband (400–700 nm).
       Default is ``0.45``, appropriate for a cloudless tropical sky.
       Range for real conditions: 0.45–0.50.

   Returns
   -------
   float or ndarray
       Estimated PAR in µmol m⁻² s⁻¹.

   Notes
   -----
   The energy-to-quantum conversion factor of 4.57 µmol J⁻¹ is the
   broadband value for the full solar spectrum in the 400–700 nm range,
   as reported by McCree (1972) [1]_.  Using a fixed factor introduces
   a small error under heavy cloud cover (when the spectrum shifts), but
   the bias is generally < 5 % for tropical sites.

   Typical PAR values:

   - Full tropical sunlight: ~2 000 µmol m⁻² s⁻¹.
   - Overcast day: ~500 µmol m⁻² s⁻¹.
   - Dawn / dusk: ~200 µmol m⁻² s⁻¹.

   References
   ----------
   .. [1] McCree, K. J. (1972). Test of current definitions of
          photosynthetically active radiation against leaf
          photosynthesis data. *Agricultural Meteorology*, 10, 443-453.
          https://doi.org/10.1016/0002-1571(72)90045-3

   Examples
   --------
   >>> round(estimate_par_from_radiation(1000.0), 2)
   2056.5
   >>> round(estimate_par_from_radiation(0.0), 2)
   0.0
   >>> import numpy as np
   >>> vals = estimate_par_from_radiation(np.array([0.0, 500.0, 1000.0]))
   >>> [round(float(v), 1) for v in vals]
   [0.0, 1028.2, 2056.5]


.. py:function:: load_biophysical_data(file_path: str | pathlib.Path | None = None) -> pandas.DataFrame

   Load oil-palm biophysical parameters from the PalmStudio spreadsheet.

   Reads ``Vigor_Index_PalmStudio.xlsx``, converts Indonesian column names
   to English, and maps tree codes to chamber numbers.  The resulting
   DataFrame is the primary input for :func:`calculate_lai_effective`.

   Parameters
   ----------
   file_path : str or Path or None, optional
       Path to ``Vigor_Index_PalmStudio.xlsx``.  When ``None`` the function
       looks for the file at
       ``<package_root>/Raw/BiophysicalParam/Vigor_Index_PalmStudio.xlsx``.
       For the bundled synthetic sample, pass the path explicitly.

   Returns
   -------
   pd.DataFrame
       One row per measurement visit.  Columns:

       - ``date`` — measurement date (datetime64).
       - ``chamber`` — chamber number (1 or 2); rows without a recognised
         tree code are dropped.
       - ``tree_code`` — original tree-code string from the spreadsheet
         (e.g. ``'2.2/EKA-1/2107'``).
       - ``height_cm`` — total tree height (cm).
       - ``r1_cm``, ``r2_cm`` — canopy radii (cm).
       - ``n_leaves`` — total number of leaves counted.
       - ``vigor_index`` — estimated above-ground biomass volume (m³),
         as computed by PalmStudio from height and canopy radii.

   Raises
   ------
   FileNotFoundError
       If *file_path* is ``None`` and the default path does not exist.

   Examples
   --------
   Load from an explicit path (synthetic fixture shown conceptually):

   >>> df = load_biophysical_data("tests/fixtures/Vigor_Index_PalmStudio.xlsx")  # doctest: +SKIP
   >>> df.columns.tolist()  # doctest: +SKIP
   ['date', 'tree_code', 'n_leaves', 'height_cm', 'r1_cm', 'r2_cm', 'vigor_index', 'chamber']


.. py:function:: scale_to_leaf_basis(flux_df: pandas.DataFrame, lai_column: str = 'lai_effective') -> pandas.DataFrame

   Scale ground-area fluxes to leaf-area basis by dividing by LAI.

   .. math::

       F_{\text{leaf}} = \frac{F_{\text{ground}}}{\text{LAI}_{\text{eff}}}

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux cycle data.  Must contain:

       - ``flux_absolute`` — CO₂ flux on ground-area basis
         (µmol m⁻² ground s⁻¹).
       - The column named by *lai_column* — LAI from
         :func:`calculate_lai_effective` (m² leaf m⁻² ground).

   lai_column : str, optional
       Name of the LAI column in *flux_df*.  Default: ``'lai_effective'``.

   Returns
   -------
   pd.DataFrame
       Copy of *flux_df* with one additional column:

       - ``flux_absolute_leaf`` — CO₂ flux on leaf-area basis
         (µmol m⁻² leaf s⁻¹).

       Rows where LAI is ``NaN`` or zero retain ``NaN`` in
       ``flux_absolute_leaf``.

   Notes
   -----
   Typical ground-area fluxes for oil-palm whole-tree chambers at LIBZ:

   - Daytime net CO₂ uptake: −5 to −15 µmol m⁻² ground s⁻¹
     (negative = uptake by convention).
   - Nighttime respiration: +1 to +4 µmol m⁻² ground s⁻¹.

   After dividing by LAI ≈ 3, the leaf-area fluxes become:

   - Daytime: −1.7 to −5 µmol m⁻² leaf s⁻¹.
   - Nighttime: +0.3 to +1.3 µmol m⁻² leaf s⁻¹.

   Literature gross photosynthesis rates for oil-palm leaves are
   10–25 µmol m⁻² leaf s⁻¹; the net uptake values above are lower
   because they include daytime respiration and whole-canopy integration.

   Examples
   --------
   >>> import pandas as pd, numpy as np
   >>> df = pd.DataFrame({
   ...     "flux_absolute": [-12.0, 2.0, np.nan],
   ...     "lai_effective": [3.0, 3.0, 3.0],
   ... })
   >>> result = scale_to_leaf_basis(df)
   >>> result["flux_absolute_leaf"].tolist()
   [-4.0, 0.6666666666666666, nan]


