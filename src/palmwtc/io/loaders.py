"""Data loaders for palmwtc.

This module reads the CSV and Excel files produced by the LIBZ automated
whole-tree chamber (WTC) deployment.  Three loaders cover the main entry
points:

- :func:`load_monthly_data` — reads the pre-integrated monthly CSV files
  (``Integrated_Data_YYYY-MM.csv``) and applies a first-pass hardware outlier
  filter (temperature, pressure, relative humidity, soil water potential).
- :func:`load_from_multiple_dirs` — concatenates raw TOA5 ``.dat`` files from
  one or more directories (e.g. a main archive plus incremental update folders),
  deduplicating by ``TIMESTAMP``.
- :func:`load_radiation_data` — reads global radiation from an AWS Excel
  export, normalising heterogeneous column names into a consistent
  ``Global_Radiation`` (W m⁻²) column.

Additional helpers :func:`integrate_temp_humidity_c2`,
:func:`export_monthly`, :func:`read_toa5_file`, and
:func:`load_data_in_range` support the full pre-processing pipeline but are
also available as standalone utilities.
"""

# ruff: noqa: F541, F841, UP037
# F541 — unused f-string prefix in some print() calls.
# F841 — `initial_count` is assigned but not used after the outlier block
#         (retained for future diagnostics).
# UP037 — quoted return-type annotation on load_from_multiple_dirs kept for
#          clarity at the call site; removing it is a separate commit.

from __future__ import annotations

import pathlib
from pathlib import Path

import numpy as np
import pandas as pd


def load_monthly_data(data_dir: Path, months: list[str] | None = None) -> pd.DataFrame:
    """Load pre-integrated monthly CSV files and apply hardware outlier filters.

    Reads all ``Integrated_Data_YYYY-MM.csv`` files found in *data_dir*, sorts
    them chronologically, concatenates them, and removes rows that violate the
    following first-pass physical bounds:

    - Atmospheric pressure < 50 kPa → likely sensor dropout.
    - Temperature (any channel) < -100 °C or > 100 °C → hardware error.
    - Relative humidity or vapour pressure < -100 → hardware error.
    - Soil water potential > 1000 kPa → hardware overflow.

    Parameters
    ----------
    data_dir : Path
        Directory that contains the ``Integrated_Data_*.csv`` files
        (the ``Integrated_Monthly`` folder in the standard export layout).
    months : list of str, optional
        Subset of YYYY-MM strings to load, e.g. ``["2024-10", "2024-11"]``.
        When *None* (default), all CSV files in *data_dir* are loaded.

    Returns
    -------
    pd.DataFrame
        Concatenated data with ``TIMESTAMP`` as the index (``DatetimeTzNaive``),
        sorted ascending.  Outlier rows are dropped in-place.

    Examples
    --------
    >>> from pathlib import Path
    >>> from palmwtc.io import load_monthly_data
    >>> df = load_monthly_data(Path("/data/Integrated_Monthly"))  # doctest: +SKIP
    >>> df.index.name  # doctest: +SKIP
    'TIMESTAMP'
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


def integrate_temp_humidity_c2(
    clim_df: pd.DataFrame | None,
    soil_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Merge Chamber 2 air temperature (°C) and relative humidity (%) from two sensors.

    Chamber 2 has two overlapping sources:

    - **Climate logger** — 4-second resolution; preferred when available.
    - **Soil sensor logger** — 15-minute resolution; linearly interpolated to 4 s
      and used to fill any gaps left by the climate logger.

    The output spans the full temporal union of both inputs at a 4-second
    cadence.  A ``*_source`` column records whether each value came from
    ``"climate"``, ``"soil_interpolated"``, or ``"missing"``.

    Parameters
    ----------
    clim_df : pd.DataFrame or None
        Climate logger data.  Must contain ``TIMESTAMP``, ``Temp_1_C2``
        (°C), and ``RH_1_C2`` (%).  Pass *None* or an empty frame to
        fall back entirely to the soil sensor.
    soil_df : pd.DataFrame or None
        Soil sensor logger data.  Must contain ``TIMESTAMP``,
        ``AirTC_Avg_Soil`` (°C), and ``RH_Avg_Soil`` (%).  Pass *None*
        or an empty frame if not available.

    Returns
    -------
    pd.DataFrame
        Columns: ``TIMESTAMP``, ``Temp_1_C2_final`` (°C),
        ``RH_1_C2_final`` (%),  ``Temp_1_C2_source``,
        ``RH_1_C2_source``, plus the four original source columns for
        reference.  Returns an empty DataFrame if both inputs are absent.

    Examples
    --------
    >>> import pandas as pd
    >>> from palmwtc.io import integrate_temp_humidity_c2
    >>> result = integrate_temp_humidity_c2(None, None)  # doctest: +SKIP
    >>> result.empty  # doctest: +SKIP
    True
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


def export_monthly(df: pd.DataFrame | None, output_dir: Path | str) -> None:
    """Split a DataFrame by calendar month and write one CSV per month.

    Each output file is named ``Integrated_Data_YYYY-MM.csv``.  A summary
    file ``Monthly_Export_Summary.csv`` is also written to *output_dir*.

    Parameters
    ----------
    df : pd.DataFrame or None
        Input data.  Must contain a ``TIMESTAMP`` column (datetime).
        Nothing is written when *df* is *None* or empty.
    output_dir : Path or str
        Destination directory.  Created automatically if it does not exist.

    Examples
    --------
    >>> import pandas as pd
    >>> from palmwtc.io import export_monthly
    >>> export_monthly(None, "/tmp/out")  # doctest: +SKIP
    No data to export.
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


def read_toa5_file(filepath: Path | str) -> pd.DataFrame | None:
    """Read a single TOA5 ``.dat`` file from a Campbell Scientific datalogger.

    TOA5 files have a four-row preamble: environment info (row 0), column
    names (row 1), units (row 2), and processing type (row 3).  This
    function uses row 1 as the header, drops rows 2-3, and coerces all
    non-``TIMESTAMP`` columns to numeric.

    Parameters
    ----------
    filepath : Path or str
        Path to the ``.dat`` file.

    Returns
    -------
    pd.DataFrame or None
        Cleaned DataFrame with ``TIMESTAMP`` parsed as ``datetime64``,
        or *None* if the file cannot be read or lacks a ``TIMESTAMP`` column.

    Examples
    --------
    >>> from palmwtc.io import read_toa5_file
    >>> df = read_toa5_file("/data/raw/CR1000_2024_10_01.dat")  # doctest: +SKIP
    >>> "TIMESTAMP" in df.columns  # doctest: +SKIP
    True
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
    base_dir: Path | str,
    start_date,
    end_date,
    is_flat_structure: bool = False,
    filename_pattern: str = "*.dat",
) -> pd.DataFrame | None:
    """Load and concatenate TOA5 ``.dat`` files that overlap a date range.

    Parameters
    ----------
    base_dir : Path or str
        Root directory to search.
    start_date : datetime-like or None
        Inclusive lower bound on ``TIMESTAMP``.  Pass *None* to load all
        records.
    end_date : datetime-like or None
        Inclusive upper bound on ``TIMESTAMP``.  Pass *None* to load all
        records.
    is_flat_structure : bool, default False
        When *True*, only files directly inside *base_dir* are matched
        (``glob``).  When *False*, the search recurses into subdirectories
        (``rglob``).
    filename_pattern : str, default ``"*.dat"``
        Glob pattern for matching data files.

    Returns
    -------
    pd.DataFrame or None
        Concatenated data sorted by ``TIMESTAMP`` with exact duplicates
        removed, or *None* when no matching records are found.

    Examples
    --------
    >>> from pathlib import Path
    >>> from palmwtc.io import load_data_in_range
    >>> df = load_data_in_range(Path("/data/raw/chamber_1"), None, None)  # doctest: +SKIP
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
    dir_entries: list[dict],
    start_date=None,
    end_date=None,
) -> "pd.DataFrame | None":
    """Load TOA5 data from several directories and merge into one DataFrame.

    Designed for deployments where a **main archive** directory is supplemented
    by one or more **update** directories (e.g. incremental SD-card downloads).
    Records are sorted by ``TIMESTAMP`` before deduplication so that, when a
    timestamp appears in both main and update, the update-folder version is
    kept (``keep="last"``).

    Parameters
    ----------
    dir_entries : list of dict
        Ordered list of source directories.  Each element must have:

        - ``"path"`` : :class:`pathlib.Path` — directory to scan.
        - ``"is_flat"`` : bool — ``True`` if files sit directly in the
          directory; ``False`` for a nested (monthly subfolder) layout.
    start_date : datetime-like, optional
        Inclusive lower bound on ``TIMESTAMP``.  *None* loads all records.
    end_date : datetime-like, optional
        Inclusive upper bound on ``TIMESTAMP``.  *None* loads all records.

    Returns
    -------
    pd.DataFrame or None
        Single DataFrame with unique ``TIMESTAMP`` rows in ascending order,
        or *None* when no data is found in any of the supplied directories.

    Examples
    --------
    >>> from pathlib import Path
    >>> from palmwtc.io import load_from_multiple_dirs
    >>> entries = [
    ...     {"path": Path("/data/main/chamber_1"), "is_flat": False},
    ...     {"path": Path("/data/update_240901/01_chamber1"), "is_flat": True},
    ... ]
    >>> df = load_from_multiple_dirs(entries)  # doctest: +SKIP
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


def load_radiation_data(aws_file_path: Path | str) -> pd.DataFrame | None:
    """Load global solar radiation (W m⁻²) from an automatic weather station Excel file.

    The AWS export format varies across logger versions.  This function
    normalises both the timestamp field (looking for ``TIMESTAMP``,
    ``Date``+``Time``, or any column containing "time"/"date" in its name)
    and the radiation column (looking for ``Global_Radiation``, or any
    column containing "radiation" or "solar"+"rad").

    Parameters
    ----------
    aws_file_path : Path or str
        Path to the AWS Excel file (``.xlsx`` or ``.xls``).

    Returns
    -------
    pd.DataFrame or None
        DataFrame sorted by ``TIMESTAMP`` with at least a ``TIMESTAMP``
        column (``datetime64``) and, when found, a ``Global_Radiation``
        column (W m⁻², ``float64``).  Returns *None* if the file does not
        exist or cannot be parsed.

    Notes
    -----
    The normalisation heuristic picks the **first** matching radiation column
    it finds.  If the AWS export contains multiple radiation channels, verify
    which column is selected.

    Examples
    --------
    >>> from pathlib import Path
    >>> from palmwtc.io import load_radiation_data
    >>> df = load_radiation_data(Path("/data/aws/AWS_2024.xlsx"))  # doctest: +SKIP
    >>> "Global_Radiation" in df.columns  # doctest: +SKIP
    True
    """
    aws_file_path = Path(aws_file_path)
    if not aws_file_path.exists():
        print(f"Warning: Radiation file not found at {aws_file_path}")
        return None

    try:
        # AWS sensor exports use "--" and "-" to mark missing/sensor-error
        # readings.  Parsing them as NaN keeps the resulting DataFrame's
        # dtypes numeric so downstream ``to_parquet`` writes don't fail
        # on object-dtype "Temp - °C" / "Hum - %" columns containing the
        # raw "--" string (palmwtc 0.4.1 fix; see CHANGELOG).
        df_rad = pd.read_excel(aws_file_path, na_values=["--", "-"])

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
