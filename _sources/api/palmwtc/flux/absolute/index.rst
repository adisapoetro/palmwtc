palmwtc.flux.absolute
=====================

.. py:module:: palmwtc.flux.absolute

.. autoapi-nested-parse::

   Absolute CO₂ and H₂O fluxes from whole-tree chamber cycles.

   Converts chamber-internal concentration slopes (ppm s⁻¹ for CO₂,
   mmol mol⁻¹ s⁻¹ for H₂O) into absolute fluxes (µmol m⁻² s⁻¹ for CO₂,
   mmol m⁻² s⁻¹ for H₂O) at the tree's ground-footprint basis.

   The conversion uses the ideal gas law ``n/V = P/(RT)`` to find the
   molar air density (mol m⁻³), then multiplies by the effective chamber
   height (volume / ground area) and the measured concentration slope:

       flux = slope × (P / RT) × (V_net / A)

   with:

   - ``P`` = standard atmospheric pressure, 101 325 Pa (constant; not
     read from the row).
   - ``T`` = chamber air temperature during the cycle (``mean_temp``
     column, °C → K). Defaults to 25 °C when the column is absent or NaN.
   - ``R`` = universal gas constant, 8.314 J mol⁻¹ K⁻¹.
   - ``V_net`` = net chamber volume after subtracting the optional tree
     volume correction (m³).
   - ``A`` = chamber ground-footprint area (m²).

   **Chamber resize schedule** (palms grew, chambers were enlarged):

   - Before 2025-07-01: 2 × 2 × 2 m → V = 8 m³, A = 4 m², h = 2 m.
   - From 2025-07-01 onward: 6 × 4 × 4 m → V = 96 m³, A = 16 m², h = 6 m.

   **Optional tree-volume correction**: when ``tree_volume`` is present in
   the row, it is subtracted from the base chamber volume before computing
   the flux. This gives the scientifically correct air-volume estimate
   (palm trunk and fronds displace some of the enclosed air). The column
   defaults to 0 when absent or NaN, keeping output bit-equivalent with the
   pre-correction baseline.

   Public API
   ----------
   calculate_absolute_flux : CO₂ flux (µmol m⁻² s⁻¹).
   calculate_h2o_absolute_flux : H₂O flux (mmol m⁻² s⁻¹).
   calculate_flux_for_chamber : Identify cycles, fit slopes, and apply
       ``calculate_absolute_flux`` for a single chamber DataFrame (legacy
       helper; not used by the active 030/033/080 pipeline but retained
       for API compatibility).



Functions
---------

.. autoapisummary::

   palmwtc.flux.absolute.calculate_absolute_flux
   palmwtc.flux.absolute.calculate_h2o_absolute_flux
   palmwtc.flux.absolute.calculate_flux_for_chamber


Module Contents
---------------

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


