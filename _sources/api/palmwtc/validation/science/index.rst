palmwtc.validation.science
==========================

.. py:module:: palmwtc.validation.science

.. autoapi-nested-parse::

   Science validation: compare flux results against literature ecophysiology bounds.

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



Attributes
----------

.. autoapisummary::

   palmwtc.validation.science.DEFAULT_CONFIG


Functions
---------

.. autoapisummary::

   palmwtc.validation.science._light_response
   palmwtc.validation.science._status_inrange
   palmwtc.validation.science._status_atleast
   palmwtc.validation.science.derive_is_daytime
   palmwtc.validation.science.test_light_response
   palmwtc.validation.science.test_q10
   palmwtc.validation.science.test_wue
   palmwtc.validation.science.test_inter_chamber
   palmwtc.validation.science.run_science_validation


Module Contents
---------------

.. py:data:: DEFAULT_CONFIG
   :type:  dict[str, Any]

.. py:function:: _light_response(par: numpy.ndarray, alpha: float, Amax: float, Rd: float) -> numpy.ndarray

   Rectangular hyperbola (Michaelis-Menten) light response.


.. py:function:: _status_inrange(val: float, lo: float, hi: float) -> str

.. py:function:: _status_atleast(val: float, threshold: float, flip: bool = False) -> str

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


.. py:function:: test_light_response(cycles: pandas.DataFrame, config: dict[str, Any]) -> dict[str, dict]

   Fit a rectangular-hyperbola light response per chamber.

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


.. py:function:: test_q10(cycles: pandas.DataFrame, config: dict[str, Any]) -> dict[str, dict]

   Van't Hoff Q10 fit on nighttime respiration vs temperature per chamber.

   Returns ``status="N/A"`` when the chamber's nighttime temperature range is
   too narrow to support a defensible fit. Audit 2026-04-15 found nighttime
   T IQR ~1.7 C at LIBZ — far below the 5-10 C typically required for Q10
   identifiability — so reporting any Q10 value here would be
   indistinguishable from fitting noise. Tightened R2 gate as well: a fit
   with r2 < Q10_r2_min now returns FAIL (not BORDERLINE) on the r2 axis.


.. py:function:: test_wue(cycles: pandas.DataFrame, config: dict[str, Any]) -> dict[str, Any]

   Compute median WUE and WUE–VPD correlation across daytime uptake cycles.

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


.. py:function:: test_inter_chamber(cycles: pandas.DataFrame, config: dict[str, Any]) -> dict[str, Any]

   Compute daytime and nighttime Pearson r between the two chamber CO₂ fluxes.

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


