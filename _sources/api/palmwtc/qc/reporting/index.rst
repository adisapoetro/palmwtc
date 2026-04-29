palmwtc.qc.reporting
====================

.. py:module:: palmwtc.qc.reporting

.. autoapi-nested-parse::

   QC summary export and daily field-alert HTML report for chamber sensors.

   This module provides two groups of helpers:

   **Export helpers** turn the per-variable QC result dicts produced by
   :func:`~palmwtc.qc.rules.process_variable_qc` into shareable artefacts:

   - :func:`generate_qc_summary_from_results` — flatten the result dicts into a
     single ``pandas.DataFrame`` sorted by data-quality percentage.
   - :func:`export_qc_data` — write the QC-flagged dataframe to a Parquet file
     (zstd compression) with an optional timestamped CSV backup.

   **Field-alert report helpers** build and render an HTML email report that is
   sent automatically every morning by the daily cron job (notebook 023):

   - :func:`build_field_alert_context` — compute per-sensor health scores,
     generate maintenance recommendations, and assemble a Jinja2 template
     context dict from a QC-flagged dataframe.
   - :func:`render_field_alert_html` — render a Jinja2 template using the
     context dict produced by :func:`build_field_alert_context`.

   All functions are re-exported from :mod:`palmwtc.qc` so callers can write
   ``from palmwtc.qc import render_field_alert_html`` without knowing the
   sub-module layout.



Attributes
----------

.. autoapisummary::

   palmwtc.qc.reporting._COLOR_HEX


Functions
---------

.. autoapisummary::

   palmwtc.qc.reporting.generate_qc_summary_from_results
   palmwtc.qc.reporting.export_qc_data
   palmwtc.qc.reporting._prettify_chemical
   palmwtc.qc.reporting.build_field_alert_context
   palmwtc.qc.reporting.render_field_alert_html


Module Contents
---------------

.. py:function:: generate_qc_summary_from_results(qc_results: dict) -> pandas.DataFrame

   Flatten per-variable QC result dicts into a sorted summary DataFrame.

   Iterates over the output of
   :func:`~palmwtc.qc.rules.process_variable_qc` (one entry per variable)
   and assembles a single table with flag counts, flag percentages, and
   optional breakdown columns. The table is sorted descending by
   ``Flag_0_Pct`` so the healthiest variables appear first.

   Parameters
   ----------
   qc_results : dict
       Mapping of variable name (str) to the result dict returned by
       :func:`~palmwtc.qc.rules.process_variable_qc`. Each result dict
       must contain either a ``"summary"`` sub-dict or the summary keys
       directly (the *V2 optimization* short-circuit path).  The summary
       sub-dict must have the keys:

       ``"total_points"`` : int
           Total number of records.
       ``"flag_0_count"`` : int
           Number of records with flag 0 (good).
       ``"flag_0_percent"`` : float
           Fraction of records with flag 0, as a percentage (0-100).
       ``"flag_1_count"`` : int
           Number of records with flag 1 (suspect).
       ``"flag_1_percent"`` : float
           Fraction of records with flag 1, as a percentage (0-100).
       ``"flag_2_count"`` : int
           Number of records with flag 2 (bad).
       ``"flag_2_percent"`` : float
           Fraction of records with flag 2, as a percentage (0-100).

       Optional top-level keys that add extra columns when present:

       ``"bounds_flags"`` : pd.Series
           Raw physical-bounds flags; adds ``"Bounds_Failures"`` column.
       ``"iqr_flags"`` : pd.Series
           Raw IQR outlier flags; adds ``"IQR_Outliers"`` column.

   Returns
   -------
   pd.DataFrame
       One row per variable, sorted descending by ``Flag_0_Pct``.
       Always-present columns:

       ``"Variable"``, ``"Total_Records"``,
       ``"Flag_0_Good"``, ``"Flag_0_Pct"``,
       ``"Flag_1_Suspect"``, ``"Flag_1_Pct"``,
       ``"Flag_2_Bad"``, ``"Flag_2_Pct"``.

       Optional columns (only present when the corresponding raw flags
       exist in the input):
       ``"Bounds_Failures"``, ``"IQR_Outliers"``.

   Examples
   --------
   >>> import pandas as pd
   >>> import numpy as np
   >>> from palmwtc.qc.reporting import generate_qc_summary_from_results
   >>> results = {
   ...     "CO2_LI850": {
   ...         "summary": {
   ...             "total_points": 100,
   ...             "flag_0_count": 90, "flag_0_percent": 90.0,
   ...             "flag_1_count": 7,  "flag_1_percent": 7.0,
   ...             "flag_2_count": 3,  "flag_2_percent": 3.0,
   ...         }
   ...     },
   ...     "H2O_LI850": {
   ...         "summary": {
   ...             "total_points": 100,
   ...             "flag_0_count": 95, "flag_0_percent": 95.0,
   ...             "flag_1_count": 4,  "flag_1_percent": 4.0,
   ...             "flag_2_count": 1,  "flag_2_percent": 1.0,
   ...         }
   ...     },
   ... }
   >>> df = generate_qc_summary_from_results(results)
   >>> list(df["Variable"])  # sorted best first
   ['H2O_LI850', 'CO2_LI850']
   >>> df.shape
   (2, 8)


.. py:function:: export_qc_data(df: pandas.DataFrame, output_dir: str = '../Data/QC_Reports', keep_csv_backup: bool = False) -> pathlib.Path

   Write a QC-flagged dataframe to Parquet and optionally a CSV backup.

   The primary output file is always ``QC_Flagged_Data_latest.parquet``
   (zstd compression, overwrites on every call). If no Parquet engine is
   installed a CSV fallback is written instead and a warning is issued.
   When *keep_csv_backup* is ``True`` a timestamped CSV copy is also written
   alongside the primary output.

   If the dataframe index is named ``"TIMESTAMP"`` it is reset to become a
   regular column in the output file (Parquet does not preserve named
   indexes well across tools).

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged dataframe to export.  Must contain the flag columns
       produced by :class:`~palmwtc.qc.processor.QCProcessor` or
       :func:`~palmwtc.qc.rules.process_variable_qc`.
   output_dir : str, default ``"../Data/QC_Reports"``
       Directory where output files are written. Created if it does not
       exist.
   keep_csv_backup : bool, default False
       If ``True``, write an additional timestamped CSV file named
       ``QC_Flagged_Data_YYYYMMDD_HHMMSS.csv`` next to the primary output.

   Returns
   -------
   pathlib.Path
       Absolute path to the primary file that was written (the Parquet
       file, or the CSV fallback if Parquet is unavailable).

   Warns
   -----
   UserWarning
       Emitted when no Parquet engine is installed and the CSV fallback
       is used.

   Examples
   --------
   Write a tiny flagged dataframe to a temporary directory:

   >>> import tempfile, pandas as pd
   >>> from palmwtc.qc.reporting import export_qc_data
   >>> df = pd.DataFrame({"CO2_LI850": [400.0, 401.0], "CO2_LI850_qc_flag": [0, 0]})
   >>> with tempfile.TemporaryDirectory() as tmp:
   ...     p = export_qc_data(df, output_dir=tmp)
   ...     p.name  # doctest: +SKIP
   'QC_Flagged_Data_latest.parquet'


.. py:data:: _COLOR_HEX

.. py:function:: _prettify_chemical(text: str) -> str

   Convert known chemical formulas to HTML with proper subscripts.

   CO2 → CO<sub>2</sub>, H2O → H<sub>2</sub>O, CH4 → CH<sub>4</sub>, N2O → N<sub>2</sub>O.
   Only targets known formulas to avoid mangling sensor IDs like C1, C2.


.. py:function:: build_field_alert_context(df: pandas.DataFrame, config: dict, priority_variables: list[str] | None = None) -> dict

   Build the Jinja2 template context for the daily field-alert HTML report.

   Computes per-sensor health scores, assembles maintenance recommendations,
   detects cross-variable consistency issues, and packages everything into a
   flat dict that can be passed directly to :func:`render_field_alert_html`.

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged dataframe, **already filtered to the desired lookback
       window** (e.g. the last 7 days). The function reads flag columns
       whose names match ``{var}_rule_flag`` or ``{var}_qc_flag``, and
       optionally reads ``cv_*`` cross-variable consistency columns. The
       timestamp may be in the index or in a column named ``"TIMESTAMP"``.
   config : dict
       Run configuration with at least the following keys:

       ``"healthy_threshold"`` : float
           Minimum health score (0-100) to label a sensor *Healthy*.
           Default used when absent: 80.
       ``"warning_threshold"`` : float
           Minimum health score (0-100) to label a sensor *Warning*
           (below this is *Critical*). Default: 50.
       ``"lookback_days"`` : int
           Number of days the dataframe covers (used for display only).
           Default: 7.
       ``"qc_source"`` : str
           Notebook number or identifier that produced the QC flags
           (e.g. ``"020"``). Default: ``"020"``.

   priority_variables : list of str or None, optional
       Explicit list of variable column names to include in the report.
       If ``None`` (the default), all variables are auto-detected from
       columns whose names end with ``_rule_flag`` or ``_qc_flag``.

   Returns
   -------
   dict
       Context dict ready to pass to :func:`render_field_alert_html`.
       Keys include:

       ``"report_date"`` : str
           ISO datetime string of when the context was built.
       ``"lookback_days"`` : int
           Value from *config* (or the default 7).
       ``"window_start"`` : str
           Earliest timestamp in the dataframe window (``"YYYY-MM-DD HH:MM"``).
       ``"window_end"`` : str
           Latest timestamp in the dataframe window.
       ``"system_status"`` : str
           One of ``"HEALTHY"``, ``"WARNING"``, or ``"CRITICAL"``.
       ``"status_color"`` : str
           CSS hex colour corresponding to *system_status*.
       ``"avg_score"`` : str
           Average health score across all sensors, formatted as an integer
           string (e.g. ``"87"``).
       ``"total_sensors"`` : int
           Number of sensor variables included in the report.
       ``"healthy_count"`` : int
           Number of sensors whose status is ``"Healthy"``.
       ``"attention_sensors"`` : list of dict
           Sensors below *healthy_threshold*, sorted worst-first. Each dict
           has keys ``"variable"``, ``"score"``, ``"status"``,
           ``"color_hex"``.
       ``"critical_recs"`` : list of dict
           Maintenance recommendations with severity ``"critical"``. Each
           dict has keys ``"sensor"``, ``"message"``, ``"severity"``.
       ``"warning_recs"`` : list of dict
           Maintenance recommendations with severity ``"warning"``.
       ``"cv_issues"`` : list of dict
           Cross-variable consistency issues where the flagged fraction is
           greater than zero. Each dict has keys ``"name"`` and ``"pct"``.
       ``"health_rows"`` : list of dict
           All sensors (healthy and unhealthy), sorted worst-first.
       ``"recommendations"`` : list of dict
           All recommendations (critical + warning combined).
       ``"qc_source"`` : str
           Pass-through of ``config["qc_source"]``.

   Notes
   -----
   Health scores are computed by
   ``palmwtc.dashboard.core.health_scoring.compute_sensor_health_score``.
   Recommendations are generated by
   ``palmwtc.dashboard.core.recommendations.generate_recommendations``.
   Both are loaded lazily; if ``palmwtc.dashboard`` is not installed, the
   function falls back to the ``dashboard`` package found relative to the
   package root.

   Chemical formula strings in variable names, sensor labels, and
   recommendation messages are prettified to HTML subscripts before the
   context is returned (e.g. ``"CO2"`` becomes ``"CO<sub>2</sub>"``).

   Examples
   --------
   Requires ``palmwtc.dashboard.core`` (or the ``dashboard`` fallback) to
   be importable; skip in environments without it:

   >>> context = build_field_alert_context(None, config={})  # doctest: +SKIP
   >>> context["system_status"] in {"HEALTHY", "WARNING", "CRITICAL"}  # doctest: +SKIP
   True


.. py:function:: render_field_alert_html(context: dict, template_name: str = 'field_alert.html', template_dir: pathlib.Path | None = None) -> str

   Render the field-alert Jinja2 template to an HTML string.

   Loads the Jinja2 template from *template_dir* and renders it with the
   context dict produced by :func:`build_field_alert_context`.  The
   resulting HTML string can be written to a file, displayed in a notebook
   with ``IPython.display.HTML``, or sent as the body of a field-alert
   email.

   Parameters
   ----------
   context : dict
       Context dict from :func:`build_field_alert_context`.
       Required keys:

       ``"report_date"`` : str
           ISO datetime string shown in the report header.
       ``"lookback_days"`` : int
           Number of days covered by the report window.
       ``"window_start"`` : str
           Start of the data window (``"YYYY-MM-DD HH:MM"``).
       ``"window_end"`` : str
           End of the data window (``"YYYY-MM-DD HH:MM"``).
       ``"system_status"`` : str
           One of ``"HEALTHY"``, ``"WARNING"``, or ``"CRITICAL"``.
       ``"status_color"`` : str
           CSS hex colour (e.g. ``"#2ecc71"``).
       ``"avg_score"`` : str
           Average health score as an integer string (e.g. ``"87"``).
       ``"total_sensors"`` : int
           Total number of sensors in the report.
       ``"healthy_count"`` : int
           Number of sensors with status ``"Healthy"``.
       ``"attention_sensors"`` : list of dict
           Sensors below the healthy threshold; each dict has
           ``"variable"``, ``"score"``, ``"status"``, ``"color_hex"``.
       ``"critical_recs"`` : list of dict
           Critical maintenance recommendations; each dict has
           ``"sensor"``, ``"message"``, ``"severity"``.
       ``"warning_recs"`` : list of dict
           Warning-level maintenance recommendations.
       ``"cv_issues"`` : list of dict
           Cross-variable consistency issues with ``"name"`` and ``"pct"``.
       ``"health_rows"`` : list of dict
           All sensor rows (used for the full table in the template).
       ``"recommendations"`` : list of dict
           All recommendations (critical + warning combined).
       ``"qc_source"`` : str
           Notebook identifier for the QC source (e.g. ``"020"``).

   template_name : str, default ``"field_alert.html"``
       Filename of the Jinja2 template inside *template_dir*.
   template_dir : pathlib.Path or None, optional
       Directory that contains the Jinja2 template.  When ``None`` (the
       default) the function looks for the template at
       ``<package_root>/dashboard/email_report/templates/``.

   Returns
   -------
   str
       Rendered HTML string.

   Raises
   ------
   jinja2.TemplateNotFound
       If *template_name* does not exist inside *template_dir*.

   Examples
   --------
   Requires the ``field_alert.html`` Jinja2 template on disk at the
   default template location; skip in environments without it:

   >>> html = render_field_alert_html({})  # doctest: +SKIP
   >>> html.startswith("<!DOCTYPE html") or "<html" in html  # doctest: +SKIP
   True


