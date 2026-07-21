palmwtc.qc.drift
================

.. py:module:: palmwtc.qc.drift

.. autoapi-nested-parse::

   Sensor-drift detection and piecewise drift correction.

   *Drift* is a gradual offset that builds up over days to weeks — for example,
   a CO₂ sensor whose zero point shifts slowly as the optical path ages or
   humidity changes the absorption coefficient.  Drift is distinct from a
   *breakpoint* (see :mod:`palmwtc.qc.breakpoints`), which is an instantaneous
   step change caused by a sensor swap or re-calibration.

   This module contains two functions:

   - :func:`detect_drift_windstats` — rolling Z-score method that computes how
     far the local mean strays from the global mean, normalised by the global
     standard deviation.  High absolute scores flag periods of persistent drift.
   - :func:`apply_drift_correction` — piecewise mean-shift correction that
     aligns each segment to a reference baseline, using breakpoints previously
     detected by :func:`~palmwtc.qc.breakpoints.detect_breakpoints_ruptures`.



Functions
---------

.. autoapisummary::

   palmwtc.qc.drift.detect_drift_windstats
   palmwtc.qc.drift.apply_drift_correction


Module Contents
---------------

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


