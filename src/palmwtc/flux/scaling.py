# ruff: noqa: RUF002, RUF003, SIM108
"""LAI / leaf-basis scaling helpers (Digital Twin Phase 1).

Behaviour-preserving port of the LAI + scaling helpers from
``flux_chamber/src/flux_analysis.py``. Function bodies are byte-equivalent;
only ``import`` statements and module location have changed.

Public API:
    - ``load_biophysical_data(file_path=None)``
    - ``estimate_leaf_area(n_leaves, tree_code=None, method='conservative')``
    - ``calculate_lai_effective(flux_df, biophys_df, chamber_floor_area=None)``
    - ``scale_to_leaf_basis(flux_df, lai_column='lai_effective')``
    - ``estimate_par_from_radiation(radiation_w_m2, conversion_factor=0.45)``
    - ``add_par_estimates(flux_df, radiation_column='GlobalRadiation_Avg', par_column='PAR_estimated')``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ==============================================================================
# LAI CALCULATION AND SCALING FUNCTIONS (Added for Digital Twin - Phase 1)
# ==============================================================================


def load_biophysical_data(file_path=None):
    """
    Load tree biophysical data (height, width, vigor index, leaf count).

    Args:
        file_path (str): Path to Vigor_Index_PalmStudio.xlsx file.
                        If None, uses default location.

    Returns:
        pd.DataFrame: Biophysical data with columns:
            - date: Measurement date
            - chamber: Chamber identifier (1 or 2)
            - tree_code: Original tree code
            - height_cm: Tree height (cm)
            - r1_cm, r2_cm: Canopy radii (cm)
            - n_leaves: Number of leaves
            - vigor_index: Vigor index (m³)
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


def estimate_leaf_area(n_leaves, tree_code=None, method="conservative"):
    """
    Estimate total leaf area from number of leaves.

    Args:
        n_leaves (int or array): Number of leaves
        tree_code (str, optional): Tree code for species-specific parameters
        method (str): Method for estimation
            - 'conservative': Use chamber-appropriate estimate (default)
            - 'literature_max': Use max literature value
            - 'fixed': Use fixed area per leaf

    Returns:
        float or array: Total leaf area (m²)

    Notes:
        Oil palm leaf area varies by position and tree age.
        Literature values for MATURE field palms:
        - Mature productive leaves: 8-15 m² per leaf (avg 12 m²)
        - Young chamber palms: 3-6 m² per leaf

        CRITICAL: Chamber palms are younger/smaller than mature field palms.
        For LAI calculation, we use conservative estimates to avoid over-scaling:
        - Conservative (chamber-appropriate): 4 m² per leaf average
        - This accounts for:
            * Young leaves (spear, rank 1-3): ~2 m²
            * Productive leaves (rank 4-15): ~5 m²
            * Old leaves (rank 16+): ~3 m²
            * Weighted average ≈ 4 m²

        Target LAI range: 2-6 (realistic for oil palm)
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


def calculate_lai_effective(flux_df, biophys_df, chamber_floor_area=None):
    """
    Calculate effective LAI (Leaf Area Index) for chamber flux scaling.

    LAI_effective = Total_Leaf_Area / Chamber_Floor_Area

    Args:
        flux_df (pd.DataFrame): Flux data with 'flux_date' and 'Source_Chamber'
        biophys_df (pd.DataFrame): Biophysical data from load_biophysical_data()
        chamber_floor_area (dict, optional): Floor area by date
            {date: {1: area_m2, 2: area_m2}}
            If None, uses standard dimensions:
            - Before 2025-07-01: 4 m² (2m × 2m)
            - After 2025-07-01: 16 m² (4m × 4m)

    Returns:
        pd.DataFrame: flux_df with added columns:
            - n_leaves: Number of leaves
            - leaf_area_m2: Total leaf area (m²)
            - chamber_floor_area_m2: Chamber floor area (m²)
            - lai_effective: LAI (dimensionless)
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


def scale_to_leaf_basis(flux_df, lai_column="lai_effective"):
    """
    Scale chamber flux from ground area basis to leaf area basis.

    flux_leaf_basis = flux_ground_basis / LAI_effective

    Args:
        flux_df (pd.DataFrame): Flux data with LAI_effective column
        lai_column (str): Name of LAI column

    Returns:
        pd.DataFrame: flux_df with added columns:
            - flux_absolute_leaf: Flux per leaf area (umol m⁻² s⁻¹ leaf area)

    Notes:
        Typical oil palm chamber flux (ground area):
        - Daytime uptake: -5 to -15 umol m⁻² s⁻¹ (negative = uptake)
        - Nighttime respiration: +1 to +4 umol m⁻² s⁻¹

        After scaling to leaf area with LAI=3:
        - Daytime: -1.7 to -5 umol m⁻² s⁻¹ leaf area
        - Nighttime: +0.3 to +1.3 umol m⁻² s⁻¹ leaf area

        Literature range for oil palm leaf: 10-25 umol m⁻² s⁻¹ (gross photosynthesis)
    """
    result_df = flux_df.copy()

    # Scale flux
    result_df["flux_absolute_leaf"] = np.nan

    mask = result_df[lai_column].notna() & (result_df[lai_column] > 0)
    result_df.loc[mask, "flux_absolute_leaf"] = (
        result_df.loc[mask, "flux_absolute"] / result_df.loc[mask, lai_column]
    )

    return result_df


def estimate_par_from_radiation(radiation_w_m2, conversion_factor=0.45):
    """
    Estimate PAR (Photosynthetically Active Radiation) from global radiation.

    Args:
        radiation_w_m2 (float or array): Global radiation (W m⁻²)
        conversion_factor (float): Fraction of global radiation that is PAR
            Typical values: 0.45-0.50 for cloudless sky

    Returns:
        float or array: PAR in umol m⁻² s⁻¹

    Notes:
        Conversion:
        1 W m⁻² ≈ 4.57 umol m⁻² s⁻¹ for PAR wavelengths (400-700 nm)

        PAR ≈ 0.45 × Global Radiation (W m⁻²) × 4.57 (umol m⁻² s⁻¹ per W m⁻²)

        Typical values:
        - Full sunlight: ~2000 umol m⁻² s⁻¹
        - Cloudy day: ~500 umol m⁻² s⁻¹
        - Dawn/dusk: ~200 umol m⁻² s⁻¹
    """
    umol_per_W = 4.57  # Conversion factor for PAR
    par = radiation_w_m2 * conversion_factor * umol_per_W
    return par


def add_par_estimates(flux_df, radiation_column="GlobalRadiation_Avg", par_column="PAR_estimated"):
    """
    Add estimated PAR to flux dataframe from global radiation measurements.

    Args:
        flux_df (pd.DataFrame): Flux data
        radiation_column (str): Column name for global radiation (W m⁻²)
        par_column (str): Name for new PAR column

    Returns:
        pd.DataFrame: flux_df with added PAR_estimated column
    """
    result_df = flux_df.copy()

    if radiation_column in result_df.columns:
        result_df[par_column] = estimate_par_from_radiation(result_df[radiation_column])
    else:
        print(f"Warning: {radiation_column} not found in dataframe")
        result_df[par_column] = np.nan

    return result_df


# ==============================================================================
# END OF LAI AND SCALING FUNCTIONS
# ==============================================================================
