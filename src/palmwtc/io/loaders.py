"""Data loaders for the palmwtc package.

Ported verbatim from ``flux_chamber/src/data_utils.py`` (Phase 2).
Behaviour preservation is the prime directive: function signatures and
bodies match the original to 1e-12. Internal cross-module references now
resolve via ``palmwtc.io.*``.
"""

# ruff: noqa: F541, F841, UP037
# Above ignores cover quirks carried verbatim from the original
# ``flux_chamber/src/data_utils.py`` to honour the Phase 2 "behaviour
# preservation" rule: F541 unused f-prefixes in print() calls, F841 unused
# `initial_count` local in load_monthly_data, RUF013 implicit Optional in
# ``months: list = None``, and UP037 quoted return-type on
# ``load_from_multiple_dirs``. Bug fixes are deferred to a later commit.

from __future__ import annotations

import pathlib
from pathlib import Path

import numpy as np
import pandas as pd


def load_monthly_data(data_dir: Path, months: list | None = None) -> pd.DataFrame:
    """
    Load integrated monthly CSV files.

    Args:
        data_dir: Path to Integrated_Monthly directory
        months: Optional list of months to load (e.g., ['2024-10', '2024-11'])
                If None, loads all available files.

    Returns:
        Combined DataFrame with TIMESTAMP as index
    """
    csv_files = sorted(data_dir.glob("Integrated_Data_*.csv"))

    if months:
        csv_files = [f for f in csv_files if any(m in f.name for m in months)]

    print(f"Loading {len(csv_files)} monthly file(s)...")

    dfs = []
    for f in csv_files:
        df = pd.read_csv(f, parse_dates=["TIMESTAMP"])
        dfs.append(df)
        print(f"  {f.name}: {len(df):,} rows ({df['TIMESTAMP'].min()} to {df['TIMESTAMP'].max()})")

    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.sort_values("TIMESTAMP").reset_index(drop=True)
    combined = combined.set_index("TIMESTAMP")

    # --- Filtering Outliers based on User Logic ---
    initial_count = len(combined)
    drop_mask = pd.Series(False, index=combined.index)

    # Identify variable groups
    check_cols_neg100 = ["AtmosphericPressure_1_C1", "Temp_1_C1", "VaporPressure_1_C1", "RH_1_C1"]
    temp_cols = [c for c in combined.columns if "Temp" in c]
    wp_cols = [c for c in combined.columns if "WP" in c and "Soil" in c]
    pressure_cols = [c for c in combined.columns if "AtmosphericPressure" in c]

    # Ensure all target columns are numeric before comparison to avoid TypeError
    cols_to_check = set(check_cols_neg100 + temp_cols + wp_cols + pressure_cols)
    for col in cols_to_check:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    # 1. Specific checks: Value < -100 for specific variables
    for col in check_cols_neg100:
        if col in combined.columns:
            drop_mask |= combined[col] < -100

    # 2. Temperature checks: < -100 or > 100 for ALL Temp columns
    for col in temp_cols:
        drop_mask |= (combined[col] < -100) | (combined[col] > 100)

    # 3. WP Soil checks: > 1000
    for col in wp_cols:
        drop_mask |= combined[col] > 1000

    # 4. Atmospheric Pressure checks: < 50
    for col in pressure_cols:
        drop_mask |= combined[col] < 50

    if drop_mask.sum() > 0:
        print(
            f"Removing {drop_mask.sum():,} rows containing outliers (Temp/Pres/RH < -100, Temp > 100, WP > 1000, Pres < 50)."
        )
        combined = combined[~drop_mask]
    else:
        print("No rows removed based on outlier criteria.")

    print(f"\nTotal: {len(combined):,} rows")
    print(f"Date range: {combined.index.min()} to {combined.index.max()}")

    return combined


def integrate_temp_humidity_c2(clim_df, soil_df):
    """
    Integrates temperature and humidity data for Chamber 2 by prioritizing
    high-frequency Climate data (4-second interval) and filling gaps with
    interpolated Soil Sensor data (15-minute interval).

    Args:
        clim_df: DataFrame with Climate data containing 'TIMESTAMP', 'Temp_1_C2', 'RH_1_C2'
        soil_df: DataFrame with Soil Sensor data containing 'TIMESTAMP', 'AirTC_Avg_Soil', 'RH_Avg_Soil'

    Returns:
        pd.DataFrame with integrated temperature and humidity data at 4-second intervals
        Columns: TIMESTAMP, Temp_1_C2_final, RH_1_C2_final, Temp_1_C2_source, RH_1_C2_source
    """

    # Validate inputs
    if clim_df is None or clim_df.empty:
        print("Warning: No Climate data provided")
        clim_df = pd.DataFrame(columns=["TIMESTAMP", "Temp_1_C2", "RH_1_C2"])

    if soil_df is None or soil_df.empty:
        print("Warning: No Soil Sensor data provided")
        soil_df = pd.DataFrame(columns=["TIMESTAMP", "AirTC_Avg_Soil", "RH_Avg_Soil"])

    # Ensure TIMESTAMP is datetime
    if not clim_df.empty:
        clim_df = clim_df.copy()
        clim_df["TIMESTAMP"] = pd.to_datetime(clim_df["TIMESTAMP"])
        clim_df = clim_df.sort_values("TIMESTAMP")

    if not soil_df.empty:
        soil_df = soil_df.copy()
        soil_df["TIMESTAMP"] = pd.to_datetime(soil_df["TIMESTAMP"])
        soil_df = soil_df.sort_values("TIMESTAMP")

    # Determine the full date range
    if not clim_df.empty and not soil_df.empty:
        start_time = min(clim_df["TIMESTAMP"].min(), soil_df["TIMESTAMP"].min())
        end_time = max(clim_df["TIMESTAMP"].max(), soil_df["TIMESTAMP"].max())
    elif not clim_df.empty:
        start_time = clim_df["TIMESTAMP"].min()
        end_time = clim_df["TIMESTAMP"].max()
    elif not soil_df.empty:
        start_time = soil_df["TIMESTAMP"].min()
        end_time = soil_df["TIMESTAMP"].max()
    else:
        print("Error: No data available for integration")
        return pd.DataFrame()

    # Create complete 4-second timeline
    timeline = pd.date_range(start=start_time, end=end_time, freq="4s")
    integrated_df = pd.DataFrame({"TIMESTAMP": timeline})

    print(f"Created timeline from {start_time} to {end_time}")
    print(f"Total records at 4-second intervals: {len(integrated_df)}")

    # Step 1: Merge Climate data (exact match on TIMESTAMP)
    if not clim_df.empty:
        # Select only needed columns
        clim_subset = clim_df[["TIMESTAMP", "Temp_1_C2", "RH_1_C2"]].copy()
        integrated_df = integrated_df.merge(clim_subset, on="TIMESTAMP", how="left")
        print(
            f"Merged Climate data: {clim_subset['Temp_1_C2'].notna().sum()} temperature records, {clim_subset['RH_1_C2'].notna().sum()} RH records"
        )
    else:
        integrated_df["Temp_1_C2"] = np.nan
        integrated_df["RH_1_C2"] = np.nan

    # Step 2: Interpolate Soil Sensor data to 4-second intervals
    if not soil_df.empty:
        # Select only needed columns
        soil_subset = soil_df[["TIMESTAMP", "AirTC_Avg_Soil", "RH_Avg_Soil"]].copy()

        # Set TIMESTAMP as index for resampling
        soil_subset = soil_subset.set_index("TIMESTAMP")

        # Resample to 4-second intervals with linear interpolation
        soil_resampled = soil_subset.resample("4s").asfreq()
        soil_interpolated = soil_resampled.interpolate(method="linear", limit_direction="both")

        # Reset index to merge
        soil_interpolated = soil_interpolated.reset_index()

        # Merge interpolated soil data
        integrated_df = integrated_df.merge(
            soil_interpolated[["TIMESTAMP", "AirTC_Avg_Soil", "RH_Avg_Soil"]],
            on="TIMESTAMP",
            how="left",
        )
        print(
            f"Interpolated Soil Sensor data: {soil_interpolated['AirTC_Avg_Soil'].notna().sum()} temperature records, {soil_interpolated['RH_Avg_Soil'].notna().sum()} RH records"
        )
    else:
        integrated_df["AirTC_Avg_Soil"] = np.nan
        integrated_df["RH_Avg_Soil"] = np.nan

    # Step 3: Create final columns with priority logic
    # Temperature: Use Climate if available, otherwise use interpolated Soil Sensor
    integrated_df["Temp_1_C2_final"] = integrated_df["Temp_1_C2"].fillna(
        integrated_df["AirTC_Avg_Soil"]
    )

    # Relative Humidity: Use Climate if available, otherwise use interpolated Soil Sensor
    integrated_df["RH_1_C2_final"] = integrated_df["RH_1_C2"].fillna(integrated_df["RH_Avg_Soil"])

    # Step 4: Add source metadata columns (np.where avoids pandas 3.0 CoW issues)
    integrated_df["Temp_1_C2_source"] = np.where(
        integrated_df["Temp_1_C2"].notna(),
        "climate",
        np.where(integrated_df["AirTC_Avg_Soil"].notna(), "soil_interpolated", "missing"),
    )
    integrated_df["RH_1_C2_source"] = np.where(
        integrated_df["RH_1_C2"].notna(),
        "climate",
        np.where(integrated_df["RH_Avg_Soil"].notna(), "soil_interpolated", "missing"),
    )

    # Print summary statistics
    print("\\n=== Integration Summary ===")
    print(f"Total records: {len(integrated_df)}")
    print(f"\\nTemperature sources:")
    print(
        f"  Climate: {(integrated_df['Temp_1_C2_source'] == 'climate').sum()} ({(integrated_df['Temp_1_C2_source'] == 'climate').sum() / len(integrated_df) * 100:.2f}%)"
    )
    print(
        f"  Soil (interpolated): {(integrated_df['Temp_1_C2_source'] == 'soil_interpolated').sum()} ({(integrated_df['Temp_1_C2_source'] == 'soil_interpolated').sum() / len(integrated_df) * 100:.2f}%)"
    )
    print(
        f"  Missing: {(integrated_df['Temp_1_C2_source'] == 'missing').sum()} ({(integrated_df['Temp_1_C2_source'] == 'missing').sum() / len(integrated_df) * 100:.2f}%)"
    )

    print(f"\\nRelative Humidity sources:")
    print(
        f"  Climate: {(integrated_df['RH_1_C2_source'] == 'climate').sum()} ({(integrated_df['RH_1_C2_source'] == 'climate').sum() / len(integrated_df) * 100:.2f}%)"
    )
    print(
        f"  Soil (interpolated): {(integrated_df['RH_1_C2_source'] == 'soil_interpolated').sum()} ({(integrated_df['RH_1_C2_source'] == 'soil_interpolated').sum() / len(integrated_df) * 100:.2f}%)"
    )
    print(
        f"  Missing: {(integrated_df['RH_1_C2_source'] == 'missing').sum()} ({(integrated_df['RH_1_C2_source'] == 'missing').sum() / len(integrated_df) * 100:.2f}%)"
    )

    # Keep only final columns
    final_columns = [
        "TIMESTAMP",
        "Temp_1_C2_final",
        "RH_1_C2_final",
        "Temp_1_C2_source",
        "RH_1_C2_source",
        # Keep original columns for reference/debugging
        "Temp_1_C2",
        "RH_1_C2",
        "AirTC_Avg_Soil",
        "RH_Avg_Soil",
    ]

    return integrated_df[final_columns]


def export_monthly(df, output_dir):
    """
    Splits dataframe by Year-Month and saves to CSV.

    Args:
        df: DataFrame with TIMESTAMP column
        output_dir: Directory path for output files
    """
    if df is None or df.empty:
        print("No data to export.")
        return

    # Create output directory if it doesn't exist
    output_path = pathlib.Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Create year-month period
    df["YearMonth"] = df["TIMESTAMP"].dt.to_period("M")

    print(f"\\nExporting data to monthly files...")
    print("=" * 80)

    monthly_summary = []

    for period, group in df.groupby("YearMonth"):
        filename = f"Integrated_Data_{period}.csv"
        file_path = output_path / filename

        # Drop the helper column before saving
        group_to_save = group.drop(columns=["YearMonth"])
        if "Date" in group_to_save.columns:
            group_to_save = group_to_save.drop(columns=["Date"])

        group_to_save.to_csv(file_path, index=False)

        file_size_mb = file_path.stat().st_size / (1024 * 1024)

        monthly_summary.append(
            {
                "Month": str(period),
                "Records": len(group),
                "File_Size_MB": round(file_size_mb, 2),
                "Filename": filename,
            }
        )

        print(f"  ✓ {filename}: {len(group):,} records ({file_size_mb:.2f} MB)")

    # Create summary DataFrame (most recent first)
    summary_df = (
        pd.DataFrame(monthly_summary).sort_values("Month", ascending=False).reset_index(drop=True)
    )

    print("\\n" + "=" * 80)
    print("Monthly Export Summary:")
    print("=" * 80)
    print(summary_df)
    print(f"\\nTotal files created: {len(summary_df)}")
    print(f"Total size: {summary_df['File_Size_MB'].sum():.2f} MB")
    print(f"\\nAll files saved to: {output_path}")

    # Save summary to CSV
    summary_path = output_path / "Monthly_Export_Summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"Summary saved to: {summary_path}")


# ---------------------------------------------------------------------------
# TOA5 File I/O (internal helpers used by load_from_multiple_dirs)
# ---------------------------------------------------------------------------


def read_toa5_file(filepath):
    """
    Reads a TOA5 .dat file, handling the specific header structure.

    Returns:
        pd.DataFrame or None if reading fails
    """
    try:
        # Read the file using Row 1 (0-indexed) as header
        df = pd.read_csv(filepath, header=1, low_memory=False, na_values=["NAN", "nan"])

        # Verify TIMESTAMP column exists
        if "TIMESTAMP" not in df.columns:
            print(f"Warning: No TIMESTAMP column in {filepath}")
            return None

        # Check if we have enough rows
        if len(df) < 2:
            return None

        # Drop the first two rows (Units and Type metadata)
        df_clean = df.iloc[2:].copy()

        # Parse TIMESTAMP
        df_clean["TIMESTAMP"] = pd.to_datetime(df_clean["TIMESTAMP"], errors="coerce")

        # Drop rows where TIMESTAMP is NaT
        df_clean = df_clean.dropna(subset=["TIMESTAMP"])

        # Convert numeric columns
        for col in df_clean.columns:
            if col != "TIMESTAMP":
                df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")

        return df_clean
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None


def load_data_in_range(
    base_dir, start_date, end_date, is_flat_structure=False, filename_pattern="*.dat"
):
    """
    Loads and concatenates .dat files within a date range.

    Args:
        base_dir: Path to the data directory
        start_date: datetime object for start of range
        end_date: datetime object for end of range
        is_flat_structure: True if files are directly in base_dir, False if in subdirectories
        filename_pattern: Glob pattern for matching files

    Returns:
        pd.DataFrame or None
    """
    base_path = pathlib.Path(base_dir)

    if is_flat_structure:
        all_files = list(base_path.glob(filename_pattern))
    else:
        all_files = list(base_path.rglob(filename_pattern))

    print(f"  Found {len(all_files)} files in {base_dir}")

    data_frames = []

    for file in all_files:
        df = read_toa5_file(file)

        if df is not None and "TIMESTAMP" in df.columns:
            if (
                start_date is not None
                and end_date is not None
                and not pd.isna(start_date)
                and not pd.isna(end_date)
            ):
                mask = (df["TIMESTAMP"] >= start_date) & (df["TIMESTAMP"] <= end_date)
                filtered_df = df.loc[mask]
            else:
                filtered_df = df

            if not filtered_df.empty:
                data_frames.append(filtered_df)

    if data_frames:
        full_df = pd.concat(data_frames, ignore_index=True)
        full_df = full_df.sort_values("TIMESTAMP").drop_duplicates(subset=["TIMESTAMP"])
        print(f"  Loaded {len(full_df)} records")
        return full_df
    else:
        print(f"  No data found in date range")
        return None


def load_from_multiple_dirs(
    dir_entries: list, start_date=None, end_date=None
) -> "pd.DataFrame | None":
    """
    Load and merge data from multiple directories, deduplicating by TIMESTAMP.

    Parameters
    ----------
    dir_entries : list of dict
        Each dict must have keys ``"path"`` (Path) and ``"is_flat"`` (bool).
    start_date : datetime-like, optional
    end_date   : datetime-like, optional

    Returns
    -------
    pd.DataFrame or None
    """
    frames = []
    for entry in dir_entries:
        df = load_data_in_range(
            entry["path"],
            start_date,
            end_date,
            is_flat_structure=entry["is_flat"],
        )
        if df is not None:
            frames.append(df)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    # Sort so that chronologically later records (from update dirs) appear last;
    # keep='last' means update folder data wins when timestamps duplicate Main.
    combined = (
        combined.sort_values("TIMESTAMP")
        .drop_duplicates(subset=["TIMESTAMP"], keep="last")
        .reset_index(drop=True)
    )
    print(f"  Combined: {len(combined):,} unique records from {len(frames)} source(s)")
    return combined


def load_radiation_data(aws_file_path):
    """
    Load AWS radiation data from an Excel file.

    Handles various timestamp and radiation column name formats.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with TIMESTAMP and Global_Radiation columns, or None on failure.
    """
    aws_file_path = Path(aws_file_path)
    if not aws_file_path.exists():
        print(f"Warning: Radiation file not found at {aws_file_path}")
        return None

    try:
        df_rad = pd.read_excel(aws_file_path)

        # Normalize timestamp field
        if "TIMESTAMP" not in df_rad.columns:
            if {"Date", "Time"}.issubset(df_rad.columns):
                df_rad["TIMESTAMP"] = pd.to_datetime(
                    df_rad["Date"].astype(str).str.strip()
                    + " "
                    + df_rad["Time"].astype(str).str.strip(),
                    errors="coerce",
                )
            elif "Date" in df_rad.columns:
                df_rad["TIMESTAMP"] = pd.to_datetime(df_rad["Date"], errors="coerce")
            else:
                dt_candidate = next(
                    (
                        c
                        for c in df_rad.columns
                        if "time" in str(c).lower() or "date" in str(c).lower()
                    ),
                    None,
                )
                if dt_candidate is not None:
                    df_rad["TIMESTAMP"] = pd.to_datetime(df_rad[dt_candidate], errors="coerce")

        # Normalize radiation field
        if "Global_Radiation" not in df_rad.columns:
            rad_candidates = [
                c
                for c in df_rad.columns
                if ("radiation" in str(c).lower())
                or ("solar" in str(c).lower() and "rad" in str(c).lower())
            ]
            if rad_candidates:
                df_rad["Global_Radiation"] = pd.to_numeric(
                    df_rad[rad_candidates[0]], errors="coerce"
                )

        if "TIMESTAMP" in df_rad.columns:
            df_rad["TIMESTAMP"] = pd.to_datetime(df_rad["TIMESTAMP"], errors="coerce")
            df_rad = (
                df_rad.dropna(subset=["TIMESTAMP"]).sort_values("TIMESTAMP").reset_index(drop=True)
            )

        if "Global_Radiation" in df_rad.columns:
            df_rad["Global_Radiation"] = pd.to_numeric(df_rad["Global_Radiation"], errors="coerce")

        print(f"Radiation data loaded: {len(df_rad)} rows")
        if "Global_Radiation" in df_rad.columns:
            print(f"Global_Radiation available. NaNs: {df_rad['Global_Radiation'].isna().sum()}")
        else:
            print("Warning: could not derive Global_Radiation from radiation file columns")
        return df_rad

    except Exception as e:
        print(f"Error loading radiation data: {e}")
        return None
