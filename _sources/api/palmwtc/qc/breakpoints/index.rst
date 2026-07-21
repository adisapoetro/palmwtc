palmwtc.qc.breakpoints
======================

.. py:module:: palmwtc.qc.breakpoints

.. autoapi-nested-parse::

   Breakpoint detection and cross-variable consistency checks.

   A *breakpoint* is an instantaneous step change in a sensor stream — for
   example, a sensor swap, a re-calibration, or a sudden data-logger offset.
   The functions here detect those step changes and filter them so that only
   physically meaningful shifts are retained.

   Compare with :mod:`palmwtc.qc.drift`, which handles *gradual* offsets that
   accumulate over weeks or months rather than appearing as a sudden jump.



Functions
---------

.. autoapisummary::

   palmwtc.qc.breakpoints.detect_breakpoints_ruptures
   palmwtc.qc.breakpoints.check_baseline_drift
   palmwtc.qc.breakpoints.check_cross_variable_consistency
   palmwtc.qc.breakpoints.filter_major_breakpoints


Module Contents
---------------

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


.. py:function:: check_baseline_drift(df: pandas.DataFrame, column: str, expected_min: float = None) -> pandas.DataFrame

   Monitor sensor baseline by inspecting daily minimum values.

   For CO₂ sensors the ambient (open-chamber) minimum should stay near
   400-420 µmol mol⁻¹.  A persistent upward trend in the daily minimum
   indicates that the sensor zero is drifting — a gradual process handled
   separately in :mod:`palmwtc.qc.drift`.  This function flags individual
   *days* where the minimum deviates by more than 50 µmol mol⁻¹ from
   ``expected_min``.

   Parameters
   ----------
   df : pd.DataFrame
       Time-indexed DataFrame.  The index must support ``resample``.
   column : str
       Name of the sensor column to check.
   expected_min : float or None, optional
       Expected daily minimum value in the same units as ``column``.  When
       given, days outside the ±50-unit tolerance are flagged.
       ``None`` skips the flagging step and returns only the summary
       statistics.

   Returns
   -------
   pd.DataFrame or None
       ``None`` if ``column`` is not found in ``df``.  Otherwise a
       daily-resampled DataFrame with columns:

       - ``{column}_daily_min`` — daily minimum.
       - ``{column}_daily_max`` — daily maximum.
       - ``{column}_daily_mean`` — daily mean.
       - ``{column}_daily_range`` — daily max minus daily min.
       - ``{column}_trend`` — 7-day rolling mean of ``_daily_mean``,
         first-differenced (rate of change, same units day⁻¹).
       - ``{column}_baseline_drift`` — bool, ``True`` on days where
         ``|daily_min - expected_min| > 50`` (only present when
         ``expected_min`` is not ``None``).

   Examples
   --------
   >>> import pandas as pd, numpy as np
   >>> from palmwtc.qc import check_baseline_drift
   >>> idx = pd.date_range("2023-01-01", periods=48, freq="30min")
   >>> df = pd.DataFrame({"CO2": np.full(48, 410.0)}, index=idx)
   >>> result = check_baseline_drift(df, "CO2", expected_min=400)
   CO2: 0 days with baseline drift (>400±50)
   >>> bool(result["CO2_baseline_drift"].any())
   False


.. py:function:: check_cross_variable_consistency(df: pandas.DataFrame) -> pandas.DataFrame

   Flag physically impossible or mutually inconsistent values across variables.

   Runs four cross-variable checks:

   1. Relative humidity outside [0, 100] % — physically impossible.
   2. Temperature difference > 10 °C between the two chambers — suspicious
      unless one chamber is actively closed.
   3. CO₂ difference > 200 µmol mol⁻¹ between the two chambers during open
      periods.
   4. Soil temperature variability increases with depth — unexpected because
      deeper soil should be more stable than the surface layer.

   Parameters
   ----------
   df : pd.DataFrame
       Time-indexed DataFrame.  Column names follow the LI-COR / oil-palm
       chamber naming convention (``RH_*``, ``Temp_1_C1``, ``CO2_C1``,
       ``Tsol_15_Avg_Soil``, etc.).

   Returns
   -------
   pd.DataFrame
       Boolean flag DataFrame with the same index as ``df``.  Each column
       corresponds to one consistency check; ``True`` means the row failed
       that check.  Columns present depend on which sensor columns exist in
       ``df``.

   Examples
   --------
   >>> import pandas as pd
   >>> from palmwtc.qc import check_cross_variable_consistency
   >>> df = pd.DataFrame({"RH_1": [50.0, 110.0, 80.0]})
   >>> flags = check_cross_variable_consistency(df)
   RH_1: 1 invalid RH values
   >>> list(flags["RH_1_invalid"])
   [False, True, False]


.. py:function:: filter_major_breakpoints(bp_result, min_confidence=0.3, min_mean_shift=15)

   Keep only breakpoints that exceed both a confidence and an amplitude threshold.

   After :func:`detect_breakpoints_ruptures` returns a candidate list, this
   function removes breakpoints that are either statistically weak (low
   confidence score) or physically small (mean shift below
   ``min_mean_shift``).  The two thresholds are applied independently —
   a breakpoint must pass *both* to be retained.

   Parameters
   ----------
   bp_result : dict or None
       Return value of :func:`detect_breakpoints_ruptures`.  ``None`` or
       an empty result returns an empty list without error.
   min_confidence : float, optional
       Minimum confidence score (0.0-1.0) required to retain a breakpoint.
       Scores are computed as ``min(1, |delta_mean| / (3 * pooled_std))``; a
       value of 0.3 keeps breakpoints with at least a 0.9 pooled-SD mean
       shift.  Default
       ``0.3``.
   min_mean_shift : float, optional
       Minimum absolute difference between adjacent segment means required
       to retain a breakpoint.  Units match the sensor variable.
       Default ``15`` (appropriate for CO₂ in µmol mol⁻¹).

   Returns
   -------
   list of pd.Timestamp
       Timestamps of breakpoints that passed both thresholds.  Empty list
       if none pass or if ``bp_result`` is ``None``.

   Examples
   --------
   >>> from palmwtc.qc import filter_major_breakpoints
   >>> result = {
   ...     "n_breakpoints": 1,
   ...     "breakpoints": ["2023-06-01"],
   ...     "segment_info": [{"mean": 400.0, "std": 5.0}, {"mean": 450.0, "std": 5.0}],
   ...     "confidence_scores": [0.5],
   ... }
   >>> kept = filter_major_breakpoints(result, min_confidence=0.3, min_mean_shift=15)
   Filtered 1 breakpoints -> 1 major breakpoints
   >>> len(kept)
   1


