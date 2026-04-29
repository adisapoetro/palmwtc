palmwtc.qc
==========

.. py:module:: palmwtc.qc

.. autoapi-nested-parse::

   Quality control for whole-tree chamber sensor streams.

   Rule-based flagging (physical bounds, IQR, rate of change, persistence,
   battery proxy, sensor exclusions) lives in :mod:`~palmwtc.qc.rules`.
   Breakpoint and drift detection are in :mod:`~palmwtc.qc.breakpoints`
   and :mod:`~palmwtc.qc.drift` respectively. ML-assisted outlier
   detection (Isolation Forest, optional GPU acceleration) lives in
   :mod:`~palmwtc.qc.ml`. A stateful orchestrator,
   :class:`~palmwtc.qc.QCProcessor`, is in :mod:`~palmwtc.qc.processor`.
   HTML field-alert reporting is in :mod:`~palmwtc.qc.reporting`.

   Tuned for:

   - CO2 and H2O concentration from a LI-COR LI-850 gas analyser inside a
     whole-tree chamber enclosing an individual oil palm.
   - Soil water content and temperature at 5, 15, 30, 60, and 80 cm depths.
   - Ambient climate (air temperature, humidity, rainfall, shortwave
     radiation) from a co-located weather station.

   All public symbols from the sub-modules are re-exported here so callers
   can write ``from palmwtc.qc import apply_physical_bounds_flags`` without
   knowing the sub-module layout. See :attr:`__all__` for the full list.



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/qc/breakpoints/index
   /api/palmwtc/qc/drift/index
   /api/palmwtc/qc/ml/index
   /api/palmwtc/qc/processor/index
   /api/palmwtc/qc/reporting/index
   /api/palmwtc/qc/rules/index


Attributes
----------

.. autoapisummary::

   palmwtc.qc.DEVICE


Classes
-------

.. autoapisummary::

   palmwtc.qc.QCProcessor


Functions
---------

.. autoapisummary::

   palmwtc.qc.check_baseline_drift
   palmwtc.qc.check_cross_variable_consistency
   palmwtc.qc.detect_breakpoints_ruptures
   palmwtc.qc.filter_major_breakpoints
   palmwtc.qc.apply_drift_correction
   palmwtc.qc.detect_drift_windstats
   palmwtc.qc.get_isolation_forest
   palmwtc.qc.build_field_alert_context
   palmwtc.qc.export_qc_data
   palmwtc.qc.generate_qc_summary_from_results
   palmwtc.qc.render_field_alert_html
   palmwtc.qc.add_cycle_id
   palmwtc.qc.apply_battery_proxy_flags
   palmwtc.qc.apply_iqr_flags
   palmwtc.qc.apply_persistence_flags
   palmwtc.qc.apply_physical_bounds_flags
   palmwtc.qc.apply_rate_of_change_flags
   palmwtc.qc.apply_sensor_exclusion_flags
   palmwtc.qc.combine_qc_flags
   palmwtc.qc.generate_exclusion_recommendations
   palmwtc.qc.generate_qc_summary
   palmwtc.qc.get_variable_config
   palmwtc.qc.process_variable_qc


Package Contents
----------------

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


.. py:function:: apply_drift_correction(df, var_name, breakpoints, reference_baseline=None)

   Apply piecewise mean-shift correction to align each segment to a reference baseline.

   Uses the breakpoints returned by
   :func:`~palmwtc.qc.breakpoints.detect_breakpoints_ruptures` (or any list
   of timestamps) to split the time series into segments.  Each segment's
   mean is shifted so that it equals ``reference_baseline``.  The first
   segment sets the reference if no explicit baseline is given.

   This is a simple mean-shift approach.  It corrects stable offsets between
   segments but does **not** model within-segment drift (a linear or
   polynomial trend inside one segment).

   Parameters
   ----------
   df : pd.DataFrame
       Input data.  Index must be a ``DatetimeIndex`` for timestamp
       comparisons to work correctly.
   var_name : str
       Column name of the variable to correct.
   breakpoints : list of timestamp-like
       Breakpoint timestamps that define segment boundaries.  Values are
       coerced to ``pd.Timestamp``.  An empty list returns the original
       series unchanged.
   reference_baseline : float or None, optional
       Target mean value for all segments in the same units as ``var_name``.
       ``None`` uses the first segment's own mean as the reference.

   Returns
   -------
   corrected : pd.Series
       Corrected values with the same index and name as ``df[var_name]``.
   offsets : pd.Series
       Offset applied at each row (``segment_mean - reference_baseline``).
       Subtract this from the original to reproduce the corrected values.
       Returns ``(None, None)`` if ``var_name`` is not in ``df``.

   Examples
   --------
   >>> import pandas as pd, numpy as np
   >>> from palmwtc.qc import apply_drift_correction
   >>> idx = pd.date_range("2023-01-01", periods=4, freq="30min")
   >>> df = pd.DataFrame({"CO2": [400.0, 402.0, 420.0, 418.0]}, index=idx)
   >>> bps = [pd.Timestamp("2023-01-01 01:00")]
   >>> corrected, offsets = apply_drift_correction(df, "CO2", bps)  # doctest: +SKIP
   >>> float(corrected.iloc[2])  # doctest: +SKIP
   401.0


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


.. py:data:: DEVICE
   :type:  str
   :value: 'cuda'


   Detected accelerator name: one of ``"cuda"``, ``"mps"``, or ``"cpu"``.

   Set at import time. Does not update if the accelerator state changes
   during a session.


.. py:function:: get_isolation_forest(**kwargs) -> Any

   Return a GPU (cuML) or CPU (sklearn) IsolationForest.

   Accepts the same keyword arguments as
   :class:`sklearn.ensemble.IsolationForest`.  On CUDA, kwargs that cuML
   does not support (``n_jobs``, ``max_features``, ``warm_start``) are
   silently dropped before the cuML constructor is called.

   The returned object exposes the same interface regardless of backend:
   ``.fit(X)``, ``.score_samples(X)``, ``.predict(X)``.

   Parameters
   ----------
   **kwargs
       Keyword arguments forwarded to ``IsolationForest``.  Common ones:

       n_estimators : int, default 100
           Number of trees.
       max_samples : int or float or ``"auto"``, default ``"auto"``
           Number of samples to draw per tree.
       contamination : float or ``"auto"``, default ``"auto"``
           Expected fraction of outliers in the training set.
       random_state : int or None, default None
           Seed for reproducibility.

   Returns
   -------
   cuml.ensemble.IsolationForest or sklearn.ensemble.IsolationForest
       ``cuml.ensemble.IsolationForest`` when :data:`DEVICE` is
       ``"cuda"``; ``sklearn.ensemble.IsolationForest`` otherwise.
       Both share the same ``.fit`` / ``.score_samples`` / ``.predict``
       interface.

   Notes
   -----
   The CUDA fallback chain is: CUDA → CPU (no MPS path because cuML is
   CUDA-only).  The check is performed once at module import via
   :func:`detect_device`; the result is cached in :data:`DEVICE`.

   Examples
   --------
   >>> from palmwtc.hardware.gpu import get_isolation_forest
   >>> iforest = get_isolation_forest(n_estimators=100, random_state=42)  # doctest: +SKIP
   >>> iforest.fit(X_train)  # doctest: +SKIP
   >>> scores = iforest.score_samples(X_all)  # doctest: +SKIP

   References
   ----------
   .. [1] Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation
          forest. *2008 Eighth IEEE International Conference on Data
          Mining*, 413-422. https://doi.org/10.1109/ICDM.2008.17


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



.. py:function:: build_field_alert_context(df: pandas.DataFrame, config: dict, priority_variables: list[str] | None = None) -> dict

   Build the Jinja2 template context for the daily field-alert HTML report.

   Computes per-sensor health scores, assembles maintenance recommendations,
   detects cross-variable consistency issues, and packages everything into a
   flat dict that can be passed directly to :func:`render_field_alert_html`.

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged dataframe, **already filtered to the desired lookback
       window** (e.g. the last 7 days). The function reads flag columns
       whose names match ``{var}_rule_flag`` or ``{var}_qc_flag``, and
       optionally reads ``cv_*`` cross-variable consistency columns. The
       timestamp may be in the index or in a column named ``"TIMESTAMP"``.
   config : dict
       Run configuration with at least the following keys:

       ``"healthy_threshold"`` : float
           Minimum health score (0-100) to label a sensor *Healthy*.
           Default used when absent: 80.
       ``"warning_threshold"`` : float
           Minimum health score (0-100) to label a sensor *Warning*
           (below this is *Critical*). Default: 50.
       ``"lookback_days"`` : int
           Number of days the dataframe covers (used for display only).
           Default: 7.
       ``"qc_source"`` : str
           Notebook number or identifier that produced the QC flags
           (e.g. ``"020"``). Default: ``"020"``.

   priority_variables : list of str or None, optional
       Explicit list of variable column names to include in the report.
       If ``None`` (the default), all variables are auto-detected from
       columns whose names end with ``_rule_flag`` or ``_qc_flag``.

   Returns
   -------
   dict
       Context dict ready to pass to :func:`render_field_alert_html`.
       Keys include:

       ``"report_date"`` : str
           ISO datetime string of when the context was built.
       ``"lookback_days"`` : int
           Value from *config* (or the default 7).
       ``"window_start"`` : str
           Earliest timestamp in the dataframe window (``"YYYY-MM-DD HH:MM"``).
       ``"window_end"`` : str
           Latest timestamp in the dataframe window.
       ``"system_status"`` : str
           One of ``"HEALTHY"``, ``"WARNING"``, or ``"CRITICAL"``.
       ``"status_color"`` : str
           CSS hex colour corresponding to *system_status*.
       ``"avg_score"`` : str
           Average health score across all sensors, formatted as an integer
           string (e.g. ``"87"``).
       ``"total_sensors"`` : int
           Number of sensor variables included in the report.
       ``"healthy_count"`` : int
           Number of sensors whose status is ``"Healthy"``.
       ``"attention_sensors"`` : list of dict
           Sensors below *healthy_threshold*, sorted worst-first. Each dict
           has keys ``"variable"``, ``"score"``, ``"status"``,
           ``"color_hex"``.
       ``"critical_recs"`` : list of dict
           Maintenance recommendations with severity ``"critical"``. Each
           dict has keys ``"sensor"``, ``"message"``, ``"severity"``.
       ``"warning_recs"`` : list of dict
           Maintenance recommendations with severity ``"warning"``.
       ``"cv_issues"`` : list of dict
           Cross-variable consistency issues where the flagged fraction is
           greater than zero. Each dict has keys ``"name"`` and ``"pct"``.
       ``"health_rows"`` : list of dict
           All sensors (healthy and unhealthy), sorted worst-first.
       ``"recommendations"`` : list of dict
           All recommendations (critical + warning combined).
       ``"qc_source"`` : str
           Pass-through of ``config["qc_source"]``.

   Notes
   -----
   Health scores are computed by
   ``palmwtc.dashboard.core.health_scoring.compute_sensor_health_score``.
   Recommendations are generated by
   ``palmwtc.dashboard.core.recommendations.generate_recommendations``.
   Both are loaded lazily; if ``palmwtc.dashboard`` is not installed, the
   function falls back to the ``dashboard`` package found relative to the
   package root.

   Chemical formula strings in variable names, sensor labels, and
   recommendation messages are prettified to HTML subscripts before the
   context is returned (e.g. ``"CO2"`` becomes ``"CO<sub>2</sub>"``).

   Examples
   --------
   Requires ``palmwtc.dashboard.core`` (or the ``dashboard`` fallback) to
   be importable; skip in environments without it:

   >>> context = build_field_alert_context(None, config={})  # doctest: +SKIP
   >>> context["system_status"] in {"HEALTHY", "WARNING", "CRITICAL"}  # doctest: +SKIP
   True


.. py:function:: export_qc_data(df: pandas.DataFrame, output_dir: str = '../Data/QC_Reports', keep_csv_backup: bool = False) -> pathlib.Path

   Write a QC-flagged dataframe to Parquet and optionally a CSV backup.

   The primary output file is always ``QC_Flagged_Data_latest.parquet``
   (zstd compression, overwrites on every call). If no Parquet engine is
   installed a CSV fallback is written instead and a warning is issued.
   When *keep_csv_backup* is ``True`` a timestamped CSV copy is also written
   alongside the primary output.

   If the dataframe index is named ``"TIMESTAMP"`` it is reset to become a
   regular column in the output file (Parquet does not preserve named
   indexes well across tools).

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged dataframe to export.  Must contain the flag columns
       produced by :class:`~palmwtc.qc.processor.QCProcessor` or
       :func:`~palmwtc.qc.rules.process_variable_qc`.
   output_dir : str, default ``"../Data/QC_Reports"``
       Directory where output files are written. Created if it does not
       exist.
   keep_csv_backup : bool, default False
       If ``True``, write an additional timestamped CSV file named
       ``QC_Flagged_Data_YYYYMMDD_HHMMSS.csv`` next to the primary output.

   Returns
   -------
   pathlib.Path
       Absolute path to the primary file that was written (the Parquet
       file, or the CSV fallback if Parquet is unavailable).

   Warns
   -----
   UserWarning
       Emitted when no Parquet engine is installed and the CSV fallback
       is used.

   Examples
   --------
   Write a tiny flagged dataframe to a temporary directory:

   >>> import tempfile, pandas as pd
   >>> from palmwtc.qc.reporting import export_qc_data
   >>> df = pd.DataFrame({"CO2_LI850": [400.0, 401.0], "CO2_LI850_qc_flag": [0, 0]})
   >>> with tempfile.TemporaryDirectory() as tmp:
   ...     p = export_qc_data(df, output_dir=tmp)
   ...     p.name  # doctest: +SKIP
   'QC_Flagged_Data_latest.parquet'


.. py:function:: generate_qc_summary_from_results(qc_results: dict) -> pandas.DataFrame

   Flatten per-variable QC result dicts into a sorted summary DataFrame.

   Iterates over the output of
   :func:`~palmwtc.qc.rules.process_variable_qc` (one entry per variable)
   and assembles a single table with flag counts, flag percentages, and
   optional breakdown columns. The table is sorted descending by
   ``Flag_0_Pct`` so the healthiest variables appear first.

   Parameters
   ----------
   qc_results : dict
       Mapping of variable name (str) to the result dict returned by
       :func:`~palmwtc.qc.rules.process_variable_qc`. Each result dict
       must contain either a ``"summary"`` sub-dict or the summary keys
       directly (the *V2 optimization* short-circuit path).  The summary
       sub-dict must have the keys:

       ``"total_points"`` : int
           Total number of records.
       ``"flag_0_count"`` : int
           Number of records with flag 0 (good).
       ``"flag_0_percent"`` : float
           Fraction of records with flag 0, as a percentage (0-100).
       ``"flag_1_count"`` : int
           Number of records with flag 1 (suspect).
       ``"flag_1_percent"`` : float
           Fraction of records with flag 1, as a percentage (0-100).
       ``"flag_2_count"`` : int
           Number of records with flag 2 (bad).
       ``"flag_2_percent"`` : float
           Fraction of records with flag 2, as a percentage (0-100).

       Optional top-level keys that add extra columns when present:

       ``"bounds_flags"`` : pd.Series
           Raw physical-bounds flags; adds ``"Bounds_Failures"`` column.
       ``"iqr_flags"`` : pd.Series
           Raw IQR outlier flags; adds ``"IQR_Outliers"`` column.

   Returns
   -------
   pd.DataFrame
       One row per variable, sorted descending by ``Flag_0_Pct``.
       Always-present columns:

       ``"Variable"``, ``"Total_Records"``,
       ``"Flag_0_Good"``, ``"Flag_0_Pct"``,
       ``"Flag_1_Suspect"``, ``"Flag_1_Pct"``,
       ``"Flag_2_Bad"``, ``"Flag_2_Pct"``.

       Optional columns (only present when the corresponding raw flags
       exist in the input):
       ``"Bounds_Failures"``, ``"IQR_Outliers"``.

   Examples
   --------
   >>> import pandas as pd
   >>> import numpy as np
   >>> from palmwtc.qc.reporting import generate_qc_summary_from_results
   >>> results = {
   ...     "CO2_LI850": {
   ...         "summary": {
   ...             "total_points": 100,
   ...             "flag_0_count": 90, "flag_0_percent": 90.0,
   ...             "flag_1_count": 7,  "flag_1_percent": 7.0,
   ...             "flag_2_count": 3,  "flag_2_percent": 3.0,
   ...         }
   ...     },
   ...     "H2O_LI850": {
   ...         "summary": {
   ...             "total_points": 100,
   ...             "flag_0_count": 95, "flag_0_percent": 95.0,
   ...             "flag_1_count": 4,  "flag_1_percent": 4.0,
   ...             "flag_2_count": 1,  "flag_2_percent": 1.0,
   ...         }
   ...     },
   ... }
   >>> df = generate_qc_summary_from_results(results)
   >>> list(df["Variable"])  # sorted best first
   ['H2O_LI850', 'CO2_LI850']
   >>> df.shape
   (2, 8)


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


.. py:function:: add_cycle_id(df, time_col='TIMESTAMP', gap_threshold_sec=300)

   Assign a sequential cycle ID to rows based on time gaps.

   A new measurement cycle begins whenever the time difference between
   consecutive rows exceeds ``gap_threshold_sec`` seconds. In the
   whole-tree chamber setup, each automated flux measurement cycle is
   separated from the next by a ventilation period during which the
   chamber is open; those open periods create gaps in the logged data.

   Parameters
   ----------
   df : pd.DataFrame
       Sensor data. The function works with either a ``TIMESTAMP``
       column (or another column given by ``time_col``) or a
       ``pd.DatetimeIndex``. If neither is present a warning is printed
       and ``df`` is returned unchanged.
   time_col : str, optional
       Name of the timestamp column. Default ``"TIMESTAMP"``.
   gap_threshold_sec : float, optional
       Minimum gap duration in seconds that triggers a new cycle ID.
       Default ``300`` (5 minutes). Set lower for higher-frequency data
       or shorter ventilation periods.

   Returns
   -------
   pd.DataFrame
       Copy of ``df`` with an added integer column ``"cycle_id"``
       starting at 1 and incrementing at each detected gap.

   Notes
   -----
   The first row always starts cycle 1 (its time-diff is ``NaT``/NaN).
   Cycle IDs are contiguous integers; they do not encode absolute time
   or date.

   Examples
   --------
   >>> import pandas as pd
   >>> idx = pd.date_range("2024-01-01", periods=6, freq="4s")
   >>> df = pd.DataFrame({"CO2_C1": [400.0] * 6}, index=idx)
   >>> df_with_gap = pd.concat([df.iloc[:3], df.iloc[3:].shift(freq="10min")])
   >>> result = add_cycle_id(df_with_gap)
   >>> result["cycle_id"].tolist()
   [1, 1, 1, 2, 2, 2]


.. py:function:: apply_battery_proxy_flags(df, battery_proxy_config)

   Propagate data-logger battery health flags to dependent measurements.

   For each configured battery sensor column: when the battery voltage
   falls below a warning threshold, dependent measurement variables are
   elevated to Suspect (flag 1); below a bad threshold they are elevated
   to Bad (flag 2). Existing flag 2 values are never demoted.

   Parameters
   ----------
   df : pd.DataFrame
       DataFrame containing battery voltage columns and, for each
       target variable, both a ``{var}_rule_flag`` column and
       optionally a ``{var}_qc_flag`` column. Modified in place.
   battery_proxy_config : dict
       The ``"battery_proxy"`` section from the variable config JSON.
       Expected structure::

           {
             "sensors": {
               "<batt_col>": {
                 "warn_below": <float>,
                 "bad_below": <float>,
                 "targets": ["<var1>", "<var2>", ...]
               },
               ...
             }
           }

       Where:

       ``"<batt_col>"`` : str
           Column name of the battery voltage sensor
           (e.g. ``"BattV_Min"``).
       ``"warn_below"`` : float
           Voltage threshold in volts below which target flags are
           elevated to 1 (Suspect).
       ``"bad_below"`` : float
           Voltage threshold in volts below which target flags are
           elevated to 2 (Bad).
       ``"targets"`` : list of str
           Variable names whose ``{var}_rule_flag`` columns are updated
           when the battery voltage is low.

   Returns
   -------
   dict
       ``{batt_col: {"warn_count": int, "bad_count": int,
       "targets_updated": list}}`` — one entry per configured battery
       sensor, reporting how many rows were affected at each severity
       level and which target variables were updated.

   Notes
   -----
   Battery-voltage proxy flagging matters in the whole-tree chamber
   setup because the data-logger (CR1000X) runs from a 12 V sealed
   lead-acid battery charged by a small solar panel. During cloudy
   multi-day periods the battery can drop enough to cause the LI-850
   to produce noisy or clipped readings before the logger shuts down.
   Flagging those measurements proactively prevents erroneous
   flux estimates.

   Examples
   --------
   >>> import pandas as pd
   >>> df = pd.DataFrame({
   ...     "BattV_Min": [12.5, 11.5, 10.8],
   ...     "CO2_C1_rule_flag": [0, 0, 0],
   ...     "CO2_C1_qc_flag":   [0, 0, 0],
   ... })
   >>> batt_cfg = {
   ...     "sensors": {
   ...         "BattV_Min": {
   ...             "warn_below": 11.8,
   ...             "bad_below": 11.0,
   ...             "targets": ["CO2_C1"],
   ...         }
   ...     }
   ... }
   >>> result = apply_battery_proxy_flags(df, batt_cfg)
   >>> df["CO2_C1_rule_flag"].tolist()
   [0, 1, 2]
   >>> result["BattV_Min"]["warn_count"]
   2


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


.. py:function:: apply_persistence_flags(df, var_name, config)

   Flag rows where a variable shows no meaningful variation (flat line).

   Computes the rolling max-minus-min range over a backward-looking
   time window and flags rows where that range is at or below an
   epsilon threshold. A persistently flat sensor reading usually
   indicates a stuck analogue output, a disconnected probe, or a
   data-logger averaging artefact.

   Parameters
   ----------
   df : pd.DataFrame
       Time-indexed sensor data with a ``pd.DatetimeIndex`` (required
       for the time-based rolling window). Must contain at least the
       column ``var_name``. Non-numeric values are coerced to ``NaN``.
   var_name : str
       Name of the column in ``df`` to check
       (e.g. ``"CO2_C1"``, ``"SWC_C1_5cm"``).
   config : dict
       Variable config dict. Recognised key:

       ``"persistence"`` : dict, optional
           Sub-dict with:

           ``"window_hours"`` : float
               Rolling window length in hours. If missing the check is
               skipped and all flags return 0.
           ``"epsilon"`` : float, optional
               Maximum range (max - min) that is still considered flat.
               Default ``0.0`` (exact equality required). Set higher
               for noisy sensors, e.g. ``0.01`` for SWC.

   Returns
   -------
   pd.Series
       Integer flag series aligned to ``df.index``:

       - ``0`` — normal variation within the window (Good).
       - ``1`` — range within the window is <= epsilon (Suspect flat).

   Notes
   -----
   A row is flagged when the *entire backward-looking window ending at
   that row* had suspiciously low variation. This means the flag
   appears at the end of a flat sequence, not at its start.
   Short sequences at the beginning of a file that are shorter than
   ``window_hours`` use ``min_periods=1`` and may receive false positives
   if the variable genuinely does not change during the initial window.

   Examples
   --------
   >>> import pandas as pd
   >>> idx = pd.date_range("2024-01-01", periods=6, freq="30min")
   >>> vals = [400.0, 400.0, 400.0, 400.0, 400.0, 500.0]
   >>> df = pd.DataFrame({"CO2_C1": vals}, index=idx)
   >>> cfg = {"persistence": {"window_hours": 1.5, "epsilon": 0.01}}
   >>> flags = apply_persistence_flags(df, "CO2_C1", cfg)
   >>> flags.tolist()
   [1, 1, 1, 1, 1, 0]


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


.. py:function:: apply_rate_of_change_flags(df, var_name, config)

   Flag rows where consecutive-sample change exceeds a spike limit.

   Computes the absolute first-difference of the column and compares it
   against a configured ``rate_of_change.limit``. Accounts for time
   gaps (e.g. chamber open periods) by skipping the check at transitions
   where the elapsed time exceeds three times the typical sampling
   interval.

   Parameters
   ----------
   df : pd.DataFrame
       Time-indexed sensor data with a ``pd.DatetimeIndex`` (preferred).
       Must contain at least the column ``var_name``. Non-numeric values
       are coerced to ``NaN``.
   var_name : str
       Name of the column in ``df`` to check
       (e.g. ``"CO2_C1"``, ``"AirTC_Avg"``).
   config : dict
       Variable config dict. Recognised key:

       ``"rate_of_change"`` : dict, optional
           Sub-dict with:

           ``"limit"`` : float
               Maximum allowed absolute change between consecutive
               samples in native units. If missing, the check is
               skipped and all flags return 0.

   Returns
   -------
   pd.Series
       Integer flag series aligned to ``df.index``:

       - ``0`` — change within the allowed limit (Good).
       - ``1`` — change exceeds the limit (Suspect spike).

   Notes
   -----
   The gap-aware logic estimates the typical sampling interval as the
   median of all consecutive time differences. Differences larger than
   3 times that median are treated as legitimate data gaps rather than
   physical spikes and are excluded from flagging. For 4-second chamber
   data this means jumps across gaps longer than 12 seconds are never
   flagged as spikes; for 15-minute soil data the threshold is 45
   minutes.

   Examples
   --------
   >>> import pandas as pd
   >>> idx = pd.date_range("2024-01-01", periods=5, freq="4s")
   >>> df = pd.DataFrame({"CO2_C1": [400.0, 401.0, 500.0, 402.0, 403.0]}, index=idx)
   >>> cfg = {"rate_of_change": {"limit": 20.0}}
   >>> flags = apply_rate_of_change_flags(df, "CO2_C1", cfg)
   >>> flags.tolist()
   [0, 0, 1, 1, 0]


.. py:function:: apply_sensor_exclusion_flags(df, var_name, config_path=None)

   Flag rows that fall inside a sensor maintenance or swap-out window.

   Reads exclusion windows from ``config/sensor_exclusions.yaml`` and
   flags every row whose timestamp is inside any window defined for
   ``var_name``. This step is applied before other QC rules so that
   hardware-verified bad periods are always marked Bad (flag 2)
   regardless of what the IQR or physical-bounds checks produce.

   Parameters
   ----------
   df : pd.DataFrame
       DataFrame with a ``pd.DatetimeIndex``. Row timestamps are
       compared directly against window boundaries.
   var_name : str
       Column name to look up in the exclusion config
       (e.g. ``"CO2_C1"``).
   config_path : str or Path, optional
       Override path to ``sensor_exclusions.yaml``. If ``None``, the
       file is resolved relative to the package ``config/`` directory.

   Returns
   -------
   pd.Series
       Integer flag series aligned to ``df.index``:

       - ``0`` — no exclusion window applies.
       - ``1`` or ``2`` — per the ``flag`` field in the YAML config
         (most windows use ``2`` for Bad).

   Notes
   -----
   Exclusion windows are inclusive on both start and end dates (end date
   extended to 23:59:59 to cover sub-daily data). Within each window,
   flags are only ever elevated — existing higher flags are preserved.

   The YAML config structure for one variable::

       sensor_exclusions:
         CO2_C1:
           - start: "2024-03-10"
             end:   "2024-03-14"
             flag:  2
             reason: "Sensor removed for cleaning"
             source: "manual"

   Examples
   --------
   >>> import pandas as pd
   >>> import tempfile, os, textwrap
   >>> yaml_txt = textwrap.dedent('''
   ...     sensor_exclusions:
   ...       CO2_C1:
   ...         - start: "2024-01-02"
   ...           end:   "2024-01-02"
   ...           flag:  2
   ...           reason: "test"
   ...           source: "manual"
   ... ''')
   >>> with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
   ...     _ = f.write(yaml_txt)
   ...     tmp = f.name
   >>> idx = pd.date_range("2024-01-01", periods=3, freq="1D")
   >>> df = pd.DataFrame({"CO2_C1": [400.0, 500.0, 410.0]}, index=idx)
   >>> flags = apply_sensor_exclusion_flags(df, "CO2_C1", config_path=tmp)
       Exclusion: CO2_C1 2024-01-02 → 2024-01-02 (flag=2, 1 rows) — test
   >>> flags.tolist()
   [0, 2, 0]
   >>> os.unlink(tmp)


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


.. py:function:: generate_exclusion_recommendations(audit_path=None, config_path=None, agreement_threshold=0.3, write=False)

   Auto-detect exclusion windows from a cross-chamber agreement audit.

   Reads a regime-audit CSV that records per-regime cross-chamber
   agreement scores and drift-slope warnings. Identifies regimes where
   agreement is poor, merges contiguous bad regimes into date windows,
   and returns per-sensor exclusion recommendations. Optionally writes
   the merged recommendations to ``config/sensor_exclusions.yaml``
   while preserving any ``source: "manual"`` entries already there.

   Parameters
   ----------
   audit_path : str or Path, optional
       Path to the regime audit CSV
       (e.g. ``Data/Integrated_QC_Data/026_regime_audit.csv``).
       Auto-resolved relative to the package root if ``None``.
   config_path : str or Path, optional
       Path to ``sensor_exclusions.yaml`` for writing. Auto-resolved
       relative to the package root if ``None``.
   agreement_threshold : float, optional
       Regimes with ``agreement_score < threshold`` OR
       ``slope_warning=True`` are considered bad. Default ``0.3``.
   write : bool, optional
       If ``True``, write merged recommendations to the YAML config
       file (preserving ``source: "manual"`` entries). Default
       ``False`` (dry-run, returns dict only).

   Returns
   -------
   dict
       ``{sensor_col: [{"start": str, "end": str, "flag": 2,
       "reason": str, "regimes": list, "source": "026_regime_audit"},
       ...]}``

       Where ``sensor_col`` is the chamber column to exclude
       (e.g. ``"CO2_C2"``), ``"start"`` and ``"end"`` are
       ``"YYYY-MM-DD"`` strings covering the merged bad window, and
       ``"regimes"`` is a list of per-regime metadata dicts.

   Notes
   -----
   The regime audit CSV is expected to have at least these columns:
   ``agreement_score``, ``slope_warning``, ``start``, ``end``,
   ``variable``, ``reference``, ``regime``, ``slope``.

   The ``reference`` column indicates which chamber had the more
   reliable reading during that regime. The *other* chamber's column is
   the one recommended for exclusion.

   Contiguous regimes (gap <= 1 day) are merged into a single window to
   avoid fragmented exclusion entries.

   Examples
   --------
   >>> generate_exclusion_recommendations(
   ...     audit_path="/path/to/026_regime_audit.csv",
   ...     agreement_threshold=0.3,
   ...     write=False,
   ... )  # doctest: +SKIP
   {}


.. py:function:: generate_qc_summary(df, flag_column)

   Count and summarise flag levels for one QC flag column.

   Parameters
   ----------
   df : pd.DataFrame
       Data frame containing at least the column ``flag_column``.
   flag_column : str
       Name of the integer flag column to summarise
       (e.g. ``"CO2_C1_rule_flag"``).

   Returns
   -------
   dict
       Summary statistics with the following keys:

       ``"total_points"`` : int
           Total number of rows.
       ``"flag_0_count"`` : int
           Number of rows with flag 0 (Good).
       ``"flag_1_count"`` : int
           Number of rows with flag 1 (Suspect).
       ``"flag_2_count"`` : int
           Number of rows with flag 2 (Bad).
       ``"flag_0_percent"`` : float
           Percentage of rows with flag 0.
       ``"flag_1_percent"`` : float
           Percentage of rows with flag 1.
       ``"flag_2_percent"`` : float
           Percentage of rows with flag 2.

   Examples
   --------
   >>> import pandas as pd
   >>> df = pd.DataFrame({"CO2_rule_flag": [0, 0, 1, 2, 0]})
   >>> s = generate_qc_summary(df, "CO2_rule_flag")
   >>> s["total_points"], s["flag_0_count"], s["flag_1_count"], s["flag_2_count"]
   (5, 3, 1, 1)


.. py:function:: get_variable_config(var_name, var_config_dict)

   Look up the QC configuration for a specific variable column name.

   Handles both direct column-name matches (e.g. ``"CO2_C1"``) and
   prefix-pattern matches used for soil sensor arrays
   (e.g. ``"SWC_C1"`` matching columns like ``"SWC_C1_5cm"``).

   Parameters
   ----------
   var_name : str
       Variable column name to look up (e.g. ``"CO2_C1"``,
       ``"SWC_C1_30cm"``).
   var_config_dict : dict
       Variable configuration dictionary, typically loaded from
       ``variable_config.json``. Each entry is either:

       - A config with ``"columns": [...]`` — list of exact column names
         that share this config.
       - A config with ``"pattern": "<prefix>"`` — all columns whose
         name starts with ``"<prefix>_"`` share this config.

   Returns
   -------
   dict or None
       Configuration dict for the variable if found, otherwise ``None``.

   Notes
   -----
   Direct column matches are checked before pattern matches. If a
   variable matches both, the direct match wins.

   Examples
   --------
   >>> cfg_dict = {
   ...     "co2": {"columns": ["CO2_C1", "CO2_C2"], "hard": [0, 20000]},
   ...     "swc": {"pattern": "SWC_C1", "hard": [0.0, 0.8]},
   ... }
   >>> get_variable_config("CO2_C1", cfg_dict)
   {'columns': ['CO2_C1', 'CO2_C2'], 'hard': [0, 20000]}
   >>> get_variable_config("SWC_C1_30cm", cfg_dict)
   {'pattern': 'SWC_C1', 'hard': [0.0, 0.8]}
   >>> get_variable_config("Temp_air", cfg_dict) is None
   True


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


