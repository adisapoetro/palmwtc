palmwtc.flux.advanced_outlier
=============================

.. py:module:: palmwtc.flux.advanced_outlier

.. autoapi-nested-parse::

   Advanced outlier-detection helpers used by the chamber flux pipeline.

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



Attributes
----------

.. autoapisummary::

   palmwtc.flux.advanced_outlier.DEFAULT_ADVANCED_OUTLIER_CONFIG


Functions
---------

.. autoapisummary::

   palmwtc.flux.advanced_outlier.compute_stl_residual_scores
   palmwtc.flux.advanced_outlier.compute_rolling_zscore
   palmwtc.flux.advanced_outlier.compute_ensemble_score


Module Contents
---------------

.. py:data:: DEFAULT_ADVANCED_OUTLIER_CONFIG
   :type:  dict[str, Any]

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


