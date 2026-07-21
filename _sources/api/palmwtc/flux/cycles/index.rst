palmwtc.flux.cycles
===================

.. py:module:: palmwtc.flux.cycles

.. autoapi-nested-parse::

   Per-cycle identification and quality scoring for chamber flux measurements.

   A **chamber cycle** is a single closed-chamber measurement sequence — typically
   ~5 minutes of 30-second-cadence readings at near-constant ambient conditions
   inside one whole-tree chamber (WTC), producing one CO₂ flux value and one H₂O
   flux value per cycle per chamber.

   This module covers the full cycle-level QC pipeline:

   - **Cycle identification**: assign cycle IDs from raw sensor streams based on
     time-gap thresholds (:func:`identify_cycles`).
   - **Best-window selection**: find the most linear sub-segment within each cycle
     (:func:`select_best_window_fast`).
   - **Bimodal fault detection**: detect instrument-fault signatures — two
     concentration modes within a single cycle — that point to a real-time-clock
     glitch or interleaved sample streams (:func:`detect_bimodal_cycle`).
   - **Per-cycle evaluation**: fit a linear slope, compute diagnostic statistics
     (R², NRMSE, SNR, monotonicity, curvature, Theil-Sen agreement), and convert
     slope → absolute flux (:func:`evaluate_cycle`).
   - **Per-cycle scoring**: apply the A/B/C tier rule-based QC system and combine
     with the raw sensor hardware flag (:func:`score_cycle`).
   - **Day-level quality scoring**: aggregate cycle scores to a 0–1 composite day
     score based on coverage, linearity, sign consistency, diurnal shape, and NRMSE
     (:func:`score_day_quality`, :func:`compute_day_scores`).
   - **Temporal coherence**: flag cycles that are implausible given their immediate
     neighbours (unexpected slope jumps or mid-day sign flips,
     :func:`compute_temporal_coherence`).
   - **ML anomaly detection**: Isolation Forest + Robust Covariance (MCD) overlay
     to catch multivariate anomalies among rule-based-passing cycles
     (:func:`compute_ml_anomaly_flags`).

   Quality-score thresholds are defined by :data:`QC_THRESHOLDS` (daytime) and
   :data:`NIGHTTIME_QC_THRESHOLDS` (nighttime, relaxed).  Hard physical limits that
   override scoring are in :data:`HARD_LIMITS`.  The default ML feature set is
   :data:`DEFAULT_ML_FEATURES`.

   Cycle-level outputs (columns produced by :func:`evaluate_cycle`) are consumed by
   :func:`~palmwtc.flux.chamber.calculate_flux_cycles` in the sibling module
   ``palmwtc.flux.chamber``.



Attributes
----------

.. autoapisummary::

   palmwtc.flux.cycles._SKLEARN_AVAILABLE
   palmwtc.flux.cycles.CYCLE_GAP_SEC
   palmwtc.flux.cycles.START_CUTOFF_SEC
   palmwtc.flux.cycles.START_SEARCH_SEC
   palmwtc.flux.cycles.MIN_POINTS
   palmwtc.flux.cycles.MIN_DURATION_SEC
   palmwtc.flux.cycles.OUTLIER_Z
   palmwtc.flux.cycles.MAX_OUTLIER_REFIT_FRAC
   palmwtc.flux.cycles.NOISE_EPS_PPM
   palmwtc.flux.cycles.USE_MULTIPROCESSING
   palmwtc.flux.cycles.QC_THRESHOLDS
   palmwtc.flux.cycles.NIGHTTIME_QC_THRESHOLDS
   palmwtc.flux.cycles.DEFAULT_ML_FEATURES
   palmwtc.flux.cycles.HARD_LIMITS
   palmwtc.flux.cycles._ML_FEATURE_ALIASES


Functions
---------

.. autoapisummary::

   palmwtc.flux.cycles.calc_aicc
   palmwtc.flux.cycles.fit_linear_optimized
   palmwtc.flux.cycles.fit_quadratic_fast
   palmwtc.flux.cycles.mad_outlier_mask
   palmwtc.flux.cycles.monotonic_fraction
   palmwtc.flux.cycles.identify_cycles
   palmwtc.flux.cycles.select_best_window_fast
   palmwtc.flux.cycles.detect_bimodal_cycle
   palmwtc.flux.cycles.evaluate_cycle
   palmwtc.flux.cycles._evaluate_cycle_wrapper
   palmwtc.flux.cycles.score_cycle
   palmwtc.flux.cycles.compute_temporal_coherence
   palmwtc.flux.cycles.score_day_quality
   palmwtc.flux.cycles.compute_day_scores
   palmwtc.flux.cycles.compute_ml_anomaly_flags


Module Contents
---------------

.. py:data:: _SKLEARN_AVAILABLE
   :value: True


.. py:data:: CYCLE_GAP_SEC
   :value: 300


   Seconds of silence between consecutive measurements that mark a new cycle.

   Any timestamp gap longer than this value triggers a new ``cycle_id`` in
   :func:`identify_cycles`.  Default 300 s (5 min) matches the automated
   opening/closing cadence of the whole-tree chambers.


.. py:data:: START_CUTOFF_SEC
   :value: 50


   Seconds from cycle start to skip before searching for the fit window.

   The first ~50 s after chamber closure are unstable (headspace flushing and
   pressure equilibration).  :func:`select_best_window_fast` ignores all data
   before this offset.


.. py:data:: START_SEARCH_SEC
   :value: 60


   Width (seconds) of the window-start search zone after ``START_CUTOFF_SEC``.

   :func:`select_best_window_fast` tries every candidate start index in the
   range ``[START_CUTOFF_SEC, START_CUTOFF_SEC + START_SEARCH_SEC]``.


.. py:data:: MIN_POINTS
   :value: 8


   Minimum number of data points required in the fit window.

   Cycles with fewer usable points after outlier removal are assigned QC flag 2
   (``too_few_points``).


.. py:data:: MIN_DURATION_SEC
   :value: 60


   Minimum fit-window duration in seconds.

   Windows shorter than this are skipped by :func:`select_best_window_fast` and
   cycles that cannot meet it are flagged 2 (``short_duration``).


.. py:data:: OUTLIER_Z
   :value: 3.5


   MAD-based Z-score threshold for identifying within-cycle outlier readings.

   See :func:`mad_outlier_mask`.  A value of 3.5 corresponds roughly to the
   99.9th percentile under a normal distribution.


.. py:data:: MAX_OUTLIER_REFIT_FRAC
   :value: 0.2


   Maximum fraction of points that may be removed as outliers before refit.

   If outlier fraction exceeds this threshold the original (un-cleaned) fit is
   kept, preventing over-removal of valid high-variance cycles.


.. py:data:: NOISE_EPS_PPM
   :value: 0.5


   Noise floor (ppm) used by :func:`monotonic_fraction`.

   Step changes smaller than this threshold are not counted when computing the
   monotonic fraction — they are indistinguishable from sensor quantisation
   noise.


.. py:data:: USE_MULTIPROCESSING
   :value: True


   Default flag passed to callers (e.g. notebook 032) for pool-based evaluation.

   This constant is read by the caller, not used internally in this module.


.. py:data:: QC_THRESHOLDS

   Daytime QC thresholds used by :func:`score_cycle`.

   Keys (all floats unless noted):

   ``min_points`` / ``min_duration_sec``
       Hard minimum point count and duration — see :data:`MIN_POINTS` /
       :data:`MIN_DURATION_SEC`.

   ``r2_A`` / ``r2_B``
       A-tier threshold (0.90) and B-tier lower bound (0.70).  R² below the
       B value triggers QC flag 2 (``low_r2``).

   ``nrmse_A`` / ``nrmse_B``
       Normalised RMSE thresholds (RMSE / CO₂ range).  Above B → flag 2
       (``high_nrmse``).

   ``snr_A`` / ``snr_B``
       Signal-to-noise ratio thresholds.  Above A = clean, between A/B = B-tier,
       below B = flag 2 (``low_snr``).

   ``monotonic_A`` / ``monotonic_B``
       Fraction of point-to-point steps in the same direction as the overall
       slope.  Values below ``signal_ppm_guard`` use a scaled B threshold to
       account for noise-dominated small signals.

   ``outlier_A`` / ``outlier_B``
       Fraction of points removed as MAD outliers.  Above B → flag 2
       (``many_outliers``).

   ``curvature_aicc`` / ``curvature_aicc_C``
       AICc difference (quadratic − linear).  Negative means the quadratic fit
       is preferred; very negative (< ``curvature_aicc_C``) indicates strong
       non-linearity → flag 2 (``strong_curvature``).

   ``slope_diff_A`` / ``slope_diff_B``
       Relative difference between OLS slope and Theil-Sen slope.  Large
       values indicate leverage or asymmetric scatter.

   ``signal_ppm_guard``
       Minimum total CO₂ change (ppm) to apply the strict monotonicity check.
       Below this value the B threshold is scaled down proportionally.

   ``b_count_C``
       If a cycle accumulates ≥ ``b_count_C`` B-tier issues it is demoted to C
       (QC flag 2, reason ``many_moderate_issues``).


.. py:data:: NIGHTTIME_QC_THRESHOLDS

   Relaxed QC thresholds applied when ``Global_Radiation < 10 W m⁻²``.

   At night, respiration signals are smaller and the CO₂ slope is close to zero,
   so noise-to-signal ratios are inherently higher.  These thresholds follow the
   same key structure as :data:`QC_THRESHOLDS` but with lower R² requirements,
   higher NRMSE/SNR tolerances, and a looser monotonicity floor.
   :func:`score_cycle` selects this dict automatically when ``is_nighttime=True``.


.. py:data:: DEFAULT_ML_FEATURES
   :value: ['r2', 'nrmse', 'snr', 'monotonicity', 'outlier_frac', 'slope_diff_pct', 'delta_aicc',...


   Default feature columns passed to :func:`compute_ml_anomaly_flags`.

   ``flux_slope`` is intentionally excluded: an extreme but physically real flux
   should not be penalised by the anomaly detector.  All features here describe
   *how well the cycle was measured*, not *what the measurement value was*.
   Column name aliases (e.g. ``r2`` → ``co2_r2``) are resolved automatically.


.. py:data:: HARD_LIMITS

   Absolute physical limits applied by :func:`score_cycle` when
   ``enforce_hard_limits=True``.

   ``max_abs_slope``
       Maximum plausible CO₂ slope in ppm s⁻¹ (default 10.0).
   ``max_abs_flux``
       Maximum plausible absolute flux in µmol m⁻² s⁻¹ (default 100.0).
   ``max_co2_range``
       Maximum CO₂ range within a single cycle in ppm (default 2000.0).


.. py:function:: calc_aicc(rss, n, k)

   Calculate AICc (Corrected Akaike Information Criterion).


.. py:function:: fit_linear_optimized(t, y, compute_stats=False)

   Fit linear regression y = mx + c.
   optimized using numpy vectorization.

   Returns:
       slope, intercept, r2, p_value, std_err, rmse, rss, aicc, residuals


.. py:function:: fit_quadratic_fast(t, y)

.. py:function:: mad_outlier_mask(residuals, z_thresh=OUTLIER_Z)

.. py:function:: monotonic_fraction(y, slope, noise_eps=NOISE_EPS_PPM)

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


.. py:function:: select_best_window_fast(t, y, start_cutoff_sec, start_search_sec, min_points, min_duration_sec, outlier_z=OUTLIER_Z, max_outlier_refit_frac=MAX_OUTLIER_REFIT_FRAC)

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


.. py:function:: evaluate_cycle(group, chamber_name, time_col='TIMESTAMP', co2_col='CO2', temp_col='Temp', qc_col='Flag', options=None)

.. py:function:: _evaluate_cycle_wrapper(args)

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


.. py:data:: _ML_FEATURE_ALIASES

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


