palmwtc.io.loaders
==================

.. py:module:: palmwtc.io.loaders

.. autoapi-nested-parse::

   Data loaders for palmwtc.

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



Functions
---------

.. autoapisummary::

   palmwtc.io.loaders.load_monthly_data
   palmwtc.io.loaders.integrate_temp_humidity_c2
   palmwtc.io.loaders.export_monthly
   palmwtc.io.loaders.read_toa5_file
   palmwtc.io.loaders.load_data_in_range
   palmwtc.io.loaders.load_from_multiple_dirs
   palmwtc.io.loaders.load_radiation_data


Module Contents
---------------

.. py:function:: load_monthly_data(data_dir: pathlib.Path, months: list[str] | None = None) -> pandas.DataFrame

   Load pre-integrated monthly CSV files and apply hardware outlier filters.

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


.. py:function:: integrate_temp_humidity_c2(clim_df: pandas.DataFrame | None, soil_df: pandas.DataFrame | None) -> pandas.DataFrame

   Merge Chamber 2 air temperature (°C) and relative humidity (%) from two sensors.

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


.. py:function:: export_monthly(df: pandas.DataFrame | None, output_dir: pathlib.Path | str) -> None

   Split a DataFrame by calendar month and write one CSV per month.

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


.. py:function:: read_toa5_file(filepath: pathlib.Path | str) -> pandas.DataFrame | None

   Read a single TOA5 ``.dat`` file from a Campbell Scientific datalogger.

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


.. py:function:: load_data_in_range(base_dir: pathlib.Path | str, start_date, end_date, is_flat_structure: bool = False, filename_pattern: str = '*.dat') -> pandas.DataFrame | None

   Load and concatenate TOA5 ``.dat`` files that overlap a date range.

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


.. py:function:: load_from_multiple_dirs(dir_entries: list[dict], start_date=None, end_date=None) -> pandas.DataFrame | None

   Load TOA5 data from several directories and merge into one DataFrame.

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


.. py:function:: load_radiation_data(aws_file_path: pathlib.Path | str) -> pandas.DataFrame | None

   Load global solar radiation (W m⁻²) from an automatic weather station Excel file.

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


