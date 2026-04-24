# ruff: noqa: RUF002, RUF003, SIM108
"""Leaf-area index (LAI) calculation and flux scaling to leaf basis.

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
- :func:`calculate_lai_effective` — match biophysical measurements to flux
  dates by temporal proximity and compute LAI = leaf_area / floor_area.
- :func:`scale_to_leaf_basis` — divide ground-area fluxes by LAI to obtain
  leaf-area fluxes.
- :func:`estimate_par_from_radiation` — estimate PAR (µmol m⁻² s⁻¹) from
  global shortwave radiation (W m⁻²) using the McCree (1972) factor.
- :func:`add_par_estimates` — add a PAR column to a flux DataFrame.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_biophysical_data(file_path: str | Path | None = None) -> pd.DataFrame:
    """Load oil-palm biophysical parameters from the PalmStudio spreadsheet.

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
    """
    if file_path is None:
        # Default location
        base_dir = Path(__file__).parent.parent
        file_path = base_dir / "Raw" / "BiophysicalParam" / "Vigor_Index_PalmStudio.xlsx"

    # Read with proper header (row 2)
    df = pd.read_excel(file_path, sheet_name=0, header=2)

    # Rename columns for clarity
    df_clean = pd.DataFrame(
        {
            "date": pd.to_datetime(df["Tanggal"]),
            "tree_code": df["Kode pohon"],
            "n_leaves": df["Total Pelepah"],
            "height_cm": df["Tinggi Pohon (cm)"],
            "r1_cm": df["R1 (cm)"],
            "r2_cm": df["R2 (cm)"],
            "vigor_index": df["Vigor Index"],
        }
    )

    # Map tree code to chamber
    # 2.2/EKA-1/2107 → Chamber 1
    # 2.4/EKA-2/2858 → Chamber 2
    chamber_map = {"2.2/EKA-1/2107": 1, "2.4/EKA-2/2858": 2}
    df_clean["chamber"] = df_clean["tree_code"].map(chamber_map)

    # Remove rows with missing critical data
    df_clean = df_clean.dropna(subset=["date", "chamber"])

    return df_clean


def estimate_leaf_area(
    n_leaves: float | np.ndarray,
    tree_code: str | None = None,
    method: str = "conservative",
) -> float | np.ndarray:
    """Estimate total leaf area (m²) from leaf count.

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
    """
    if method == "conservative":
        # Chamber-appropriate estimate (younger palms)
        area_per_leaf_m2 = 4.0  # m² per leaf (conservative for chamber palms)
        total_area = n_leaves * area_per_leaf_m2
    elif method == "literature_max":
        # Maximum literature value (mature field palms)
        area_per_leaf_m2 = 12.0  # m² per leaf
        total_area = n_leaves * area_per_leaf_m2
    elif method == "fixed":
        area_per_leaf_m2 = 6.0  # Middle ground
        total_area = n_leaves * area_per_leaf_m2
    else:
        raise ValueError(f"Unknown method: {method}")

    return total_area


def calculate_lai_effective(
    flux_df: pd.DataFrame,
    biophys_df: pd.DataFrame,
    chamber_floor_area: dict | None = None,
) -> pd.DataFrame:
    """Compute effective LAI for each flux cycle and attach it to the DataFrame.

    For each row in *flux_df* the function looks up the biophysical measurement
    that is closest in time (within 30 days) for the same chamber, estimates the
    total leaf area with :func:`estimate_leaf_area`, then divides by the chamber
    floor area to obtain LAI_effective.

    .. math::

        \\text{LAI}_{\\text{eff}} = \\frac{\\text{leaf\\_area\\_m2}}{\\text{chamber\\_floor\\_area\\_m2}}

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
    """
    # Create output dataframe
    result_df = flux_df.copy()

    # Initialize new columns
    result_df["n_leaves"] = np.nan
    result_df["leaf_area_m2"] = np.nan
    result_df["chamber_floor_area_m2"] = np.nan
    result_df["lai_effective"] = np.nan

    # Map chamber names to numbers
    chamber_name_map = {"Chamber 1": 1, "Chamber 2": 2}

    for idx, row in result_df.iterrows():
        flux_date = row["flux_date"]
        chamber_name = row["Source_Chamber"]
        chamber_num = chamber_name_map.get(chamber_name)

        if chamber_num is None:
            continue

        # Get floor area for this date
        if chamber_floor_area is not None and flux_date in chamber_floor_area:
            floor_area = chamber_floor_area[flux_date].get(chamber_num, 4.0)
        else:
            # Default based on date
            cutoff_date = pd.Timestamp("2025-07-01")
            if flux_date < cutoff_date:
                floor_area = 4.0  # 2m × 2m
            else:
                floor_area = 16.0  # 4m × 4m

        # Find closest biophysical measurement (temporal interpolation)
        chamber_biophys = biophys_df[biophys_df["chamber"] == chamber_num]
        if chamber_biophys.empty:
            continue

        # Find measurement closest to flux date
        time_diffs = (chamber_biophys["date"] - flux_date).abs()
        closest_idx = time_diffs.idxmin()
        closest_measurement = chamber_biophys.loc[closest_idx]

        # Only use if within 30 days
        if time_diffs.loc[closest_idx] > pd.Timedelta(days=30):
            continue

        # Get leaf count and estimate area
        n_leaves = closest_measurement["n_leaves"]
        leaf_area = estimate_leaf_area(n_leaves)

        # Calculate LAI_effective
        lai_eff = leaf_area / floor_area

        # Update result
        result_df.at[idx, "n_leaves"] = n_leaves
        result_df.at[idx, "leaf_area_m2"] = leaf_area
        result_df.at[idx, "chamber_floor_area_m2"] = floor_area
        result_df.at[idx, "lai_effective"] = lai_eff

    return result_df


def scale_to_leaf_basis(
    flux_df: pd.DataFrame,
    lai_column: str = "lai_effective",
) -> pd.DataFrame:
    """Scale ground-area fluxes to leaf-area basis by dividing by LAI.

    .. math::

        F_{\\text{leaf}} = \\frac{F_{\\text{ground}}}{\\text{LAI}_{\\text{eff}}}

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
    """
    result_df = flux_df.copy()

    # Scale flux
    result_df["flux_absolute_leaf"] = np.nan

    mask = result_df[lai_column].notna() & (result_df[lai_column] > 0)
    result_df.loc[mask, "flux_absolute_leaf"] = (
        result_df.loc[mask, "flux_absolute"] / result_df.loc[mask, lai_column]
    )

    return result_df


def estimate_par_from_radiation(
    radiation_w_m2: float | np.ndarray,
    conversion_factor: float = 0.45,
) -> float | np.ndarray:
    """Estimate PAR from global shortwave radiation using the McCree factor.

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
    """
    umol_per_W = 4.57  # Conversion factor for PAR
    par = radiation_w_m2 * conversion_factor * umol_per_W
    return par


def add_par_estimates(
    flux_df: pd.DataFrame,
    radiation_column: str = "GlobalRadiation_Avg",
    par_column: str = "PAR_estimated",
) -> pd.DataFrame:
    """Add an estimated PAR column to a flux DataFrame.

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
    """
    result_df = flux_df.copy()

    if radiation_column in result_df.columns:
        result_df[par_column] = estimate_par_from_radiation(result_df[radiation_column])
    else:
        print(f"Warning: {radiation_column} not found in dataframe")
        result_df[par_column] = np.nan

    return result_df
