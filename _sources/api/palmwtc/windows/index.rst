palmwtc.windows
===============

.. py:module:: palmwtc.windows

.. autoapi-nested-parse::

   palmwtc.windows — high-confidence calibration window selection.

   This subpackage selects contiguous date ranges ("windows") of oil-palm
   chamber cycles whose per-cycle quality scores are high enough to use as
   training data for the XPalm digital-twin model.

   Main entry point
   ----------------
   :class:`~palmwtc.windows.selector.WindowSelector`
       Multi-criteria selector that scores cycles, detects instrument drift,
       and packages qualifying windows as a cycle CSV and JSON manifest.

   Module-level helper
   -------------------
   :func:`~palmwtc.windows.selector.merge_sensor_qc_onto_cycles`
       Vectorized interval-join that appends per-cycle mean CO₂/H₂O sensor
       QC flags from the high-frequency 021 parquet onto the cycle DataFrame.

   Configuration
   -------------
   :data:`~palmwtc.windows.selector.DEFAULT_CONFIG`
       Dict of all tunable thresholds with documented physical meaning.
       Pass ``config={"key": value}`` to :class:`WindowSelector` to override
       individual keys.

   Typical usage::

       from palmwtc.windows import WindowSelector

       ws = WindowSelector(cycles_df, config={"min_window_days": 7})
       ws.detect_drift()
       ws.score_cycles()
       ws.identify_windows()
       filtered_df, manifest = ws.export()



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/windows/selector/index


Attributes
----------

.. autoapisummary::

   palmwtc.windows.DEFAULT_CONFIG


Classes
-------

.. autoapisummary::

   palmwtc.windows.WindowSelector


Functions
---------

.. autoapisummary::

   palmwtc.windows.merge_sensor_qc_onto_cycles


Package Contents
----------------

.. py:data:: DEFAULT_CONFIG
   :type:  dict

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


