palmwtc.io.paths
================

.. py:module:: palmwtc.io.paths

.. autoapi-nested-parse::

   Data-path helpers and QC-file resolution for palmwtc input files.

   This module provides utilities for locating QC output files produced by
   the palmwtc pipeline and for inspecting the column structure of those
   files before loading them into memory.

   The three public functions cover the most common file-access patterns:

   - :func:`find_latest_qc_file` — locate the correct QC output parquet or
     CSV for a given pipeline stage.
   - :func:`get_usecols` — determine which columns are worth loading from a
     QC file, avoiding unnecessary memory allocation.
   - :func:`data_integrity_report` — generate a one-row summary DataFrame
     describing the temporal coverage, duplicate rate, gap rate, missing
     value rates, and WPL-input validity of a loaded QC dataset.



Functions
---------

.. autoapisummary::

   palmwtc.io.paths.find_latest_qc_file
   palmwtc.io.paths.get_usecols
   palmwtc.io.paths.data_integrity_report


Module Contents
---------------

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


