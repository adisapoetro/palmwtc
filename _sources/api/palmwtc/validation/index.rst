palmwtc.validation
==================

.. py:module:: palmwtc.validation

.. autoapi-nested-parse::

   palmwtc.validation — science validation against literature ecophysiology bounds.

   This subpackage compares per-cycle CO₂ and H₂O flux results against published
   ecophysiology values for tropical oil-palm canopies.  It is designed to be
   called after :mod:`palmwtc.windows` has selected high-confidence cycles.

   Main entry point
   ----------------
   :func:`~palmwtc.validation.science.run_science_validation`
       Run all four ecophysiology checks in one call and return a structured
       scorecard dict.  Each check returns ``"PASS"``, ``"BORDERLINE"``,
       ``"FAIL"``, or ``"N/A"`` (when data are insufficient).

   Checks performed
   ~~~~~~~~~~~~~~~~
   1. **Light response** — Amax and quantum yield (alpha) within whole-canopy
      bounds for tropical perennial crops (Lamade & Bouillet 2005).
   2. **Q10 temperature response** — respiration Q10 within 1.5–3.0.
   3. **Water use efficiency (WUE)** — median WUE in range and negative WUE–VPD
      correlation consistent with Medlyn stomatal optimality (Medlyn et al. 2011).
   4. **Inter-chamber agreement** — daytime Pearson r > 0.70 between the two
      automated whole-tree chambers.

   Helper
   ------
   :func:`~palmwtc.validation.science.derive_is_daytime`
       Classify cycles as day/night using global radiation, with hour-of-day
       as a fallback when radiation data are absent.

   Configuration
   -------------
   :data:`~palmwtc.validation.science.DEFAULT_CONFIG`
       Dict of all configurable column names and literature-cited thresholds.

   Typical usage::

       from palmwtc.validation import run_science_validation

       result = run_science_validation(cycles_df, label="cycle_conf=0.65")
       print(result["scorecard"])



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/validation/science/index


Attributes
----------

.. autoapisummary::

   palmwtc.validation.DEFAULT_CONFIG


Functions
---------

.. autoapisummary::

   palmwtc.validation.derive_is_daytime
   palmwtc.validation.run_science_validation


Package Contents
----------------

.. py:data:: DEFAULT_CONFIG
   :type:  dict[str, Any]

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


