palmwtc.flux.scaling
====================

.. py:module:: palmwtc.flux.scaling

.. autoapi-nested-parse::

   Leaf-area index (LAI) calculation and flux scaling to leaf basis.

   Converts ground-area-basis fluxes (µmol m⁻² ground s⁻¹) to
   leaf-area basis (µmol m⁻² leaf s⁻¹) using the estimated LAI
   for the tree footprint inside the chamber. Also provides PAR estimation
   from shortwave radiation for light-response analyses.

   Public API
   ----------
   - :func:`load_biophysical_data` — load leaf-count and canopy measurements
     from the PalmStudio biophysical spreadsheet.
   - :func:`estimate_leaf_area` — convert leaf count to total leaf area (m²)
     using age-appropriate area-per-leaf assumptions for chamber oil palms.
   - :func:`estimate_leaf_area_corley` — per-rank leaflet-level Corley/Hardon
     allometry from three measured rachis-length anchors (rank 1/3/9). Opt-in
     juvenile-aware estimator that takes per-rank rachis lengths + VPalm
     leaflet coefficients and returns total leaf area (m²) per palm.
   - :func:`per_rank_rachis_lengths_m` — build a per-rank rachis-length curve
     from three anchors (linear interpolation between, floored extrapolation
     past rank 9). Exposed for diagnostics.
   - :func:`juvenile_combined_leaflet_params` — convenience factory that
     halves ``leaflets_nb_max`` + the length/width slopes of a mature VPalm
     parameter dict, producing the juvenile-combined placeholder used by
     ``estimate_leaf_area_corley`` until a calibrated juvenile leaflet
     parameter survey is available.
   - :func:`calculate_lai_effective` — match biophysical measurements to flux
     dates by temporal proximity and compute LAI = leaf_area / floor_area.
   - :func:`scale_to_leaf_basis` — divide ground-area fluxes by LAI to obtain
     leaf-area fluxes.
   - :func:`estimate_par_from_radiation` — estimate PAR (µmol m⁻² s⁻¹) from
     global shortwave radiation (W m⁻²) using the McCree (1972) factor.
   - :func:`add_par_estimates` — add a PAR column to a flux DataFrame.



Attributes
----------

.. autoapisummary::

   palmwtc.flux.scaling.LEAFLET_SHAPE_FACTOR
   palmwtc.flux.scaling.MEAN_LEAFLET_FACTOR
   palmwtc.flux.scaling.MIN_RACHIS_LENGTH_M
   palmwtc.flux.scaling.MIN_RACHIS_FRACTION_OF_POS1
   palmwtc.flux.scaling._VPALM_LEAFLET_PARAM_KEYS


Functions
---------

.. autoapisummary::

   palmwtc.flux.scaling.load_biophysical_data
   palmwtc.flux.scaling.estimate_leaf_area
   palmwtc.flux.scaling.per_rank_rachis_lengths_m
   palmwtc.flux.scaling.juvenile_combined_leaflet_params
   palmwtc.flux.scaling.estimate_leaf_area_corley
   palmwtc.flux.scaling.calculate_lai_effective
   palmwtc.flux.scaling.scale_to_leaf_basis
   palmwtc.flux.scaling.estimate_par_from_radiation
   palmwtc.flux.scaling.add_par_estimates


Module Contents
---------------

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


.. py:data:: LEAFLET_SHAPE_FACTOR
   :value: 0.55


.. py:data:: MEAN_LEAFLET_FACTOR
   :value: 0.85


.. py:data:: MIN_RACHIS_LENGTH_M
   :value: 0.5


.. py:data:: MIN_RACHIS_FRACTION_OF_POS1
   :value: 0.5


.. py:data:: _VPALM_LEAFLET_PARAM_KEYS
   :value: ('leaflets_nb_max', 'leaflets_nb_slope', 'leaflets_nb_inflexion',...


.. py:function:: per_rank_rachis_lengths_m(n_leaves: int, rachis_length_by_rank: dict[int, float]) -> numpy.ndarray

   Build a per-rank rachis-length curve from three measured anchors.

   Returns an array of length ``n_leaves`` giving the rachis length (m) at
   each rank, with rank 1 = newest (top of canopy) and rank ``n_leaves`` =
   oldest.  Anchors are taken at ranks 1, 3, 9; values between anchors are
   linearly interpolated; ranks above 9 are linearly extrapolated using the
   rank-3 → rank-9 slope and floored at
   ``max(MIN_RACHIS_LENGTH_M, MIN_RACHIS_FRACTION_OF_POS1 * pos1)``.

   Parameters
   ----------
   n_leaves : int
       Total number of leaves (fronds) on the palm.  Must be ≥ 1.
   rachis_length_by_rank : dict[int, float]
       Mapping with at least key ``1`` (rachis length at rank 1, in metres).
       Keys ``3`` and ``9`` are optional; if missing or non-finite they
       fall back to the next-lower rank that is present (rank 9 → rank 3 →
       rank 1).  Extra keys are ignored.

   Returns
   -------
   np.ndarray
       1-D array of length ``n_leaves`` with the rachis length at each rank.

   Raises
   ------
   ValueError
       If *n_leaves* < 1, or if rank 1 is missing / non-finite.

   Notes
   -----
   The per-rank decay between measured anchors is a linear placeholder for
   the true (likely Gompertz / saturating) profile.  For palms with
   ``n_leaves`` much larger than 9 most fronds are in the extrapolated
   region; the floor prevents the curve from producing absurdly tiny
   rachis lengths at high rank.

   Examples
   --------
   >>> r = per_rank_rachis_lengths_m(5, {1: 1.4, 3: 1.2, 9: 0.9})
   >>> [round(float(v), 3) for v in r]
   [1.4, 1.3, 1.2, 1.15, 1.1]

   Past rank 9 the curve falls along the rank-3 → rank-9 slope, but is
   floored:

   >>> r = per_rank_rachis_lengths_m(12, {1: 1.4, 3: 1.2, 9: 0.9})
   >>> floor = max(0.5, 0.5 * 1.4)
   >>> round(float(r[-1]), 3) >= round(floor, 3)
   True


.. py:function:: juvenile_combined_leaflet_params(mature_params: dict) -> dict

   Return a juvenile-combined placeholder of a mature VPalm parameter dict.

   Halves ``leaflets_nb_max`` and the two leaflet length/width slopes,
   leaving the other coefficients unchanged.  This matches the
   ``juvenile_combined`` variant in the per-rank Corley LAI study v3 (the
   only variant that produced LAI inside the juvenile 0.5–4 target range
   for both LIBZ chamber palms).

   Parameters
   ----------
   mature_params : dict
       VPalm leaflet allometry coefficients.  Must contain at least the
       keys listed in :data:`_VPALM_LEAFLET_PARAM_KEYS`.

   Returns
   -------
   dict
       Shallow copy of *mature_params* with ``leaflets_nb_max``,
       ``leaflet_length_at_b_slope`` and ``leaflet_width_at_b_slope``
       halved.  All other keys are passed through unchanged.

   Notes
   -----
   This is a **placeholder** for a properly-calibrated juvenile leaflet
   parameter set (the eventual output of a juvenile leaflet-survey).
   Until that survey is available, the halved-mature placeholder is
   documented explicitly in the returned dict via the
   ``"_juvenile_placeholder"`` flag so downstream code can detect it.

   Examples
   --------
   >>> mature = {
   ...     "leaflets_nb_max": 170.0,
   ...     "leaflets_nb_slope": 0.25,
   ...     "leaflets_nb_inflexion": 2.3,
   ...     "leaflet_length_at_b_intercept": 0.61,
   ...     "leaflet_length_at_b_slope": 0.054,
   ...     "leaflet_width_at_b_intercept": 0.063,
   ...     "leaflet_width_at_b_slope": -0.004,
   ... }
   >>> juv = juvenile_combined_leaflet_params(mature)
   >>> juv["leaflets_nb_max"]
   85.0
   >>> juv["leaflet_length_at_b_slope"]
   0.027
   >>> juv["_juvenile_placeholder"]
   'juvenile_combined (halved leaflets_nb_max + length/width slopes)'


.. py:function:: estimate_leaf_area_corley(n_leaves: int, rachis_length_by_rank: dict[int, float], leaflet_params: dict) -> float

   Estimate total palm leaf area (m²) via per-rank leaflet-level allometry.

   Implements the Corley/Hardon leaflet-level integration on a per-rank
   rachis-length curve.  For each rank ``r = 1..n_leaves`` the rachis
   length is taken from :func:`per_rank_rachis_lengths_m`, the leaflet
   count is computed from a logistic of rachis length (VPalm), leaflet
   length and width at the B-point are linear functions of rachis
   length, and the per-leaflet area is

   .. math::

       A_{leaflet} = (0.85 \cdot L_{b})(0.85 \cdot W_{b}) \cdot 0.55

   The per-frond area is leaflet count × per-leaflet area, and the total
   palm leaf area is the sum across all ranks.

   This estimator is the **juvenile-aware opt-in** path landed in
   palmwtc 0.4.4 to address the 5–10× LAI over-estimate produced by the
   legacy ``estimate_leaf_area(method="conservative")`` (4 m² per leaf)
   on juvenile chamber palms.  Use :func:`juvenile_combined_leaflet_params`
   to halve a mature VPalm parameter dict for the placeholder
   juvenile parameter set; pass calibrated juvenile coefficients directly
   once a juvenile leaflet-survey is available.

   Parameters
   ----------
   n_leaves : int
       Total number of live fronds on the palm.  Must be ≥ 1.
   rachis_length_by_rank : dict[int, float]
       Per-rank rachis-length anchors in metres.  Must contain key ``1``
       (rachis length at rank 1, the newest frond); keys ``3`` and ``9``
       are optional and fall back to the next-lower rank if missing
       (rank 9 → rank 3 → rank 1).  Extra keys are ignored.
   leaflet_params : dict
       VPalm leaflet allometry coefficients.  Required keys:

       - ``leaflets_nb_max`` — logistic ceiling on leaflet count.
       - ``leaflets_nb_slope`` — logistic slope (m⁻¹).
       - ``leaflets_nb_inflexion`` — logistic inflexion (m).
       - ``leaflet_length_at_b_intercept`` — leaflet length intercept (m).
       - ``leaflet_length_at_b_slope`` — leaflet length slope (dimensionless).
       - ``leaflet_width_at_b_intercept`` — leaflet width intercept (m).
       - ``leaflet_width_at_b_slope`` — leaflet width slope (dimensionless).

   Returns
   -------
   float
       Total leaf area (m²) summed across all ranks.

   Raises
   ------
   ValueError
       If *n_leaves* < 1, if rank 1 is missing / non-finite, or if any
       required VPalm key is missing from *leaflet_params*.

   See Also
   --------
   estimate_leaf_area : Legacy area-per-leaf estimator (4 m² leaf⁻¹ at
       ``method="conservative"``).  Kept as the default for backward
       compatibility; over-estimates LAI by 5–10× on juvenile palms.
   juvenile_combined_leaflet_params : Convenience factory for the
       halved-mature placeholder juvenile parameter set.
   per_rank_rachis_lengths_m : Helper that builds the per-rank curve.

   References
   ----------
   Corley, R. H. V. & Tinker, P. B. (2016). *The Oil Palm*, 5th ed.
       Wiley-Blackwell.
   Hardon, J. J., Williams, C. N. & Watson, I. (1969). Leaf area and
       yield in the oil palm in Malaya. *Experimental Agriculture*,
       5(1), 25–32. https://doi.org/10.1017/S0014479700001514
   Henson, I. E. (1991). Limitations to gas exchange, growth and yield of
       young oil palm by soil water supply and atmospheric drought.
       *Transactions of the Malaysian Society of Plant Physiology*, 3,
       39–51.
   Perez, R. P. A., Dauzat, J., Pallas, B., Lamour, J., Verley, P.,
       Caliman, J.-P., Costes, E. & Faivre, R. (2016). Designing oil
       palm architectural ideotypes for optimal light interception and
       carbon assimilation through a sensitivity analysis of leaf traits.
       *Annals of Botany*, 118(7), 1213–1228.
       https://doi.org/10.1093/aob/mcw214

   Examples
   --------
   Hand-computable single-rank case (n_leaves=1, only rank 1 in play):

   >>> params = {
   ...     "leaflets_nb_max": 100.0,
   ...     "leaflets_nb_slope": 0.25,
   ...     "leaflets_nb_inflexion": 2.0,
   ...     "leaflet_length_at_b_intercept": 0.6,
   ...     "leaflet_length_at_b_slope": 0.05,
   ...     "leaflet_width_at_b_intercept": 0.06,
   ...     "leaflet_width_at_b_slope": 0.0,
   ... }
   >>> area = estimate_leaf_area_corley(1, {1: 2.0}, params)
   >>> round(area, 4)
   0.8345

   Three-anchor curve, juvenile-combined placeholder:

   >>> juv = juvenile_combined_leaflet_params(params)
   >>> area = estimate_leaf_area_corley(
   ...     20, {1: 1.45, 3: 1.30, 9: 1.05}, juv
   ... )
   >>> area > 0
   True


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


