palmwtc.io
==========

.. py:module:: palmwtc.io

.. autoapi-nested-parse::

   palmwtc.io — data loading, path resolution, and cloud-mount adapters.

   This subpackage handles everything between raw logger files on disk and a
   clean :class:`pandas.DataFrame` ready for the QC and flux pipelines.  Three
   modules cover distinct concerns:

   - :mod:`palmwtc.io.loaders` — reads the pre-integrated monthly CSV files
     (``Integrated_Data_YYYY-MM.csv``) and raw TOA5 ``.dat`` files from one
     or more directories.  Also writes monthly export CSVs.
   - :mod:`palmwtc.io.paths` — resolves QC-file paths given a data directory,
     and produces a :func:`~palmwtc.io.paths.data_integrity_report` summary.
   - :mod:`palmwtc.io.cloud` — walks the Google Drive mount layout used by the
     LIBZ deployment to discover all raw-data directories for each sensor type.

   All public helpers are re-exported here.  Callers can write::

       from palmwtc.io import load_monthly_data, get_cloud_sensor_dirs

   without needing to know which sub-module each function lives in.



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/io/cloud/index
   /api/palmwtc/io/loaders/index
   /api/palmwtc/io/paths/index


Functions
---------

.. autoapisummary::

   palmwtc.io.get_cloud_sensor_dirs
   palmwtc.io.export_monthly
   palmwtc.io.integrate_temp_humidity_c2
   palmwtc.io.load_data_in_range
   palmwtc.io.load_from_multiple_dirs
   palmwtc.io.load_monthly_data
   palmwtc.io.load_radiation_data
   palmwtc.io.read_toa5_file
   palmwtc.io.data_integrity_report
   palmwtc.io.find_latest_qc_file
   palmwtc.io.get_usecols


Package Contents
----------------

.. py:function:: get_cloud_sensor_dirs(chamber_base: pathlib.Path | str) -> dict[str, list[dict]]

   Discover all raw-data directories for each sensor type under the cloud chamber base.

   Walks the Google Drive mount layout used by the LIBZ deployment.  The
   result is a dict of directory entries ready for
   :func:`~palmwtc.io.load_from_multiple_dirs`.

   Search order (determines deduplication priority in
   :func:`~palmwtc.io.load_from_multiple_dirs`):

   1. ``<chamber_base>/main/<sensor>/`` — primary archive; chamber
      subdirectories have monthly sub-folders (``is_flat=False``); climate
      and soil-sensor subdirectories are flat (``is_flat=True``).
   2. ``<chamber_base>/update_YYMMDD/<MM_sensortype>/`` — incremental update
      folders, sorted chronologically.  All are flat (``is_flat=True``).

   Sensor-type detection uses case-insensitive substring matching against
   the subdirectory name:

   - ``"chamber_1"`` — names containing ``"chamber1"`` or ``"chamber_1"``.
   - ``"chamber_2"`` — names containing ``"chamber2"`` or ``"chamber_2"``.
   - ``"climate"``   — names containing ``"climate"``.
   - ``"soil_sensor"`` — names containing ``"soil"``.

   Parameters
   ----------
   chamber_base : Path or str
       Root of the mounted Google Drive share for one chamber site
       (e.g. the local path of the shared drive folder).

   Returns
   -------
   dict[str, list[dict]]
       Keys are ``"chamber_1"``, ``"chamber_2"``, ``"climate"``, and
       ``"soil_sensor"``.  Each value is a list of ``{"path": Path,
       "is_flat": bool}`` dicts, suitable as the *dir_entries* argument of
       :func:`~palmwtc.io.load_from_multiple_dirs`.  Missing sensor types
       have an empty list.

   Examples
   --------
   >>> from pathlib import Path
   >>> from palmwtc.io import get_cloud_sensor_dirs
   >>> dirs = get_cloud_sensor_dirs(Path("/mnt/gdrive/LIBZ_Chamber"))  # doctest: +SKIP
   >>> list(dirs.keys())  # doctest: +SKIP
   ['chamber_1', 'chamber_2', 'climate', 'soil_sensor']


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


.. py:function:: data_integrity_report(data: pandas.DataFrame, cycle_gap_sec: float = 300, h2o_valid_range: tuple[float, float] = (0.0, 60.0)) -> pandas.DataFrame

   Generate a one-row DataFrame summarising data integrity metrics.

   Computes coverage, timing regularity, duplicate rate, gap rate,
   per-column missing-value rates, and the fraction of rows that
   provide valid WPL (Webb-Pearman-Leuning) inputs.

   Parameters
   ----------
   data : pandas.DataFrame
       QC output table.  Must contain a ``"TIMESTAMP"`` column of
       :class:`pandas.Timestamp` (or datetime-like) values.
   cycle_gap_sec : float, optional
       Threshold in seconds above which a consecutive-timestamp gap is
       classified as a data gap.  Default: ``300`` (5 minutes).
   h2o_valid_range : tuple of (float, float), optional
       ``(low, high)`` bounds (inclusive) for H₂O concentration in
       mmol mol⁻¹.  Rows outside this range are counted as invalid WPL
       inputs.  Default: ``(0.0, 60.0)``.

   Returns
   -------
   pandas.DataFrame
       Single-row DataFrame with the following columns:

       ``rows``
           Total number of rows in *data*.
       ``start``
           Earliest ``TIMESTAMP`` value.
       ``end``
           Latest ``TIMESTAMP`` value.
       ``median_dt_sec``
           Median inter-row interval in seconds.  ``NaN`` if fewer
           than two rows.
       ``pct_duplicates``
           Percentage of rows with a duplicated ``TIMESTAMP``.
       ``gaps_over_cycle_pct``
           Percentage of consecutive intervals exceeding
           *cycle_gap_sec*.
       ``missing_<col>``
           Percentage of ``NaN`` values for each tracked column
           (``CO2_C1``, ``CO2_C2``, ``Temp_1_C1``, ``Temp_1_C2``,
           ``H2O_C1``, ``H2O_C2``, ``H2O_C1_corrected``,
           ``H2O_C2_corrected``).  ``NaN`` when the column is absent.
       ``wpl_input_valid_pct_C1``
           Percentage of rows where H₂O for chamber 1 is finite and
           within *h2o_valid_range* and ``1000 - H2O > 0``.
           Prefers ``H2O_C1_corrected`` over ``H2O_C1``.
           ``NaN`` when neither column is present.
       ``wpl_input_valid_pct_C2``
           Same as above for chamber 2.

   Examples
   --------
   >>> import pandas as pd, numpy as np
   >>> ts = pd.date_range("2024-01-01", periods=4, freq="30s")
   >>> df = pd.DataFrame({
   ...     "TIMESTAMP": ts,
   ...     "CO2_C1": [410.0, 411.0, 412.0, 413.0],
   ...     "H2O_C1": [15.0, 16.0, 17.0, 18.0],
   ... })
   >>> report = data_integrity_report(df)
   >>> int(report["rows"].iloc[0])
   4
   >>> float(report["median_dt_sec"].iloc[0])
   30.0
   >>> float(report["pct_duplicates"].iloc[0])
   0.0


.. py:function:: find_latest_qc_file(qc_dir: str | pathlib.Path, pattern: str = 'QC_Flagged_Data_*.csv', source: str = '020') -> pathlib.Path | None

   Find a QC output file in *qc_dir* by upstream pipeline stage.

   Searches for the canonical output file for a given pipeline stage.
   When the named file does not exist, falls back through a hierarchy
   of legacy filenames before returning ``None``.

   Lookup order
   ------------
   1. Named stage file (e.g. ``020_rule_qc_output.parquet``).
   2. ``QC_Flagged_Data_latest.parquet`` (legacy fixed name).
   3. Newest ``QC_Flagged_Data_*.parquet`` (legacy timestamped).
   4. Newest file matching *pattern* (CSV glob, newest-first).
   5. ``None`` if nothing matches.

   Parameters
   ----------
   qc_dir : str or pathlib.Path
       Directory to search for QC output files.
   pattern : str, optional
       Glob pattern used for the final CSV fallback.
       Default: ``"QC_Flagged_Data_*.csv"``.
   source : {"020", "022", "025", "026"}, optional
       Which pipeline stage's output to look for:

       - ``"020"`` → ``020_rule_qc_output.parquet``
       - ``"022"`` → ``022_ml_qc_output.parquet``
       - ``"025"`` → ``025_cross_chamber_corrected.parquet``
       - ``"026"`` → ``026_segmented_bias_corrected.parquet``

       Default: ``"020"``.

   Returns
   -------
   pathlib.Path or None
       Absolute path to the best-matching file, or ``None`` if no
       file was found.

   Examples
   --------
   Create a directory with a stage-020 output and resolve it:

   >>> import tempfile, pathlib
   >>> with tempfile.TemporaryDirectory() as d:
   ...     p = pathlib.Path(d)
   ...     _ = (p / "020_rule_qc_output.parquet").touch()
   ...     result = find_latest_qc_file(p, source="020")
   ...     result.name
   '020_rule_qc_output.parquet'

   When the named file is absent the function returns ``None``:

   >>> import tempfile, pathlib
   >>> with tempfile.TemporaryDirectory() as d:
   ...     find_latest_qc_file(pathlib.Path(d), source="020") is None
   True


.. py:function:: get_usecols(path: str | pathlib.Path) -> list[str]

   Return the columns worth loading from a QC output file.

   Reads only the schema or header of the file (not the data rows) and
   returns the subset of columns that are needed for flux calculations
   and WPL corrections. Irrelevant columns are excluded to limit memory
   use when calling :func:`pandas.read_parquet` or
   :func:`pandas.read_csv`.

   The *required* set is::

       TIMESTAMP, CO2_C1, CO2_C2, Temp_1_C1, Temp_1_C2,
       CO2_C1_qc_flag, CO2_C2_qc_flag,
       H2O_C1, H2O_C2, H2O_C1_qc_flag, H2O_C2_qc_flag,
       H2O_C1_corrected, H2O_C2_corrected

   The *optional* set (included when present) is::

       RH_1_C1, RH_1_C2

   Parameters
   ----------
   path : str or pathlib.Path
       Path to a QC output file. Suffix determines the read strategy:
       ``".parquet"`` reads only the Parquet footer (fast, no data
       rows); any other extension reads the first row of a CSV header.

   Returns
   -------
   list of str
       Column names present in the file that belong to the required or
       optional sets, in the order they appear in the file schema.

   Examples
   --------
   >>> import tempfile, pathlib
   >>> import pandas as pd
   >>> with tempfile.TemporaryDirectory() as d:
   ...     f = pathlib.Path(d) / "qc.csv"
   ...     pd.DataFrame(columns=["TIMESTAMP", "CO2_C1", "junk"]).to_csv(f, index=False)
   ...     cols = get_usecols(f)
   ...     "TIMESTAMP" in cols and "CO2_C1" in cols and "junk" not in cols
   True


