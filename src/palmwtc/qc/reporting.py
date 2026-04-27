"""QC summary export and daily field-alert HTML report for chamber sensors.

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
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader


def generate_qc_summary_from_results(qc_results: dict) -> pd.DataFrame:
    """Flatten per-variable QC result dicts into a sorted summary DataFrame.

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
    """
    summary_data = []

    for var_name, res in qc_results.items():
        # Extract usage stats from result summary
        # Handle cases where qc_results directly contains the summary (V2 optimization)
        s = res.get("summary", res)
        row = {
            "Variable": var_name,
            "Total_Records": s["total_points"],
            "Flag_0_Good": s["flag_0_count"],
            "Flag_0_Pct": s["flag_0_percent"],
            "Flag_1_Suspect": s["flag_1_count"],
            "Flag_1_Pct": s["flag_1_percent"],
            "Flag_2_Bad": s["flag_2_count"],
            "Flag_2_Pct": s["flag_2_percent"],
        }

        # Add detailed breakdown if available in result flags
        if "bounds_flags" in res:
            row["Bounds_Failures"] = (res["bounds_flags"] > 0).sum()
        if "iqr_flags" in res:
            row["IQR_Outliers"] = (res["iqr_flags"] > 0).sum()
        summary_data.append(row)

    return pd.DataFrame(summary_data).sort_values("Flag_0_Pct", ascending=False)


def export_qc_data(
    df: pd.DataFrame,
    output_dir: str = "../Data/QC_Reports",
    keep_csv_backup: bool = False,
) -> Path:
    """Write a QC-flagged dataframe to Parquet and optionally a CSV backup.

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
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # TIMESTAMP is typically the index at this stage — reset so it becomes a column in Parquet
    _df_export = df.reset_index() if df.index.name == "TIMESTAMP" else df.copy()

    parquet_path = output_dir / "QC_Flagged_Data_latest.parquet"
    print(f"Exporting data to {parquet_path} (zstd)...")
    try:
        _df_export.to_parquet(parquet_path, compression="zstd", index=False)
        export_path = parquet_path
        print(f"Export complete. ({parquet_path.stat().st_size / 1e6:.1f} MB)")
    except ImportError as err:
        csv_fallback_path = output_dir / "QC_Flagged_Data_latest.csv"
        warnings.warn(
            "Parquet export skipped because no usable parquet engine is installed. "
            f"Writing CSV fallback instead. Original error: {err}",
            stacklevel=2,
        )
        print(f"Writing CSV fallback to {csv_fallback_path}...")
        _df_export.to_csv(csv_fallback_path, index=False)
        export_path = csv_fallback_path
        print(f"CSV fallback complete. ({csv_fallback_path.stat().st_size / 1e6:.1f} MB)")

    if keep_csv_backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = output_dir / f"QC_Flagged_Data_{timestamp}.csv"
        print(f"Writing CSV backup to {csv_path}...")
        _df_export.to_csv(csv_path, index=False)
        print("CSV backup complete.")

    return export_path


# ---------------------------------------------------------------------------
# Field alert report helpers (notebook 023)
# ---------------------------------------------------------------------------

_COLOR_HEX = {"green": "#2ecc71", "orange": "#f39c12", "red": "#e74c3c"}


def _prettify_chemical(text: str) -> str:
    """Convert known chemical formulas to HTML with proper subscripts.

    CO2 → CO<sub>2</sub>, H2O → H<sub>2</sub>O, CH4 → CH<sub>4</sub>, N2O → N<sub>2</sub>O.
    Only targets known formulas to avoid mangling sensor IDs like C1, C2.
    """
    _FORMULAS = {
        "CO2": "CO<sub>2</sub>",
        "Co2": "CO<sub>2</sub>",
        "co2": "CO<sub>2</sub>",
        "H2O": "H<sub>2</sub>O",
        "h2o": "H<sub>2</sub>O",
        "CH4": "CH<sub>4</sub>",
        "N2O": "N<sub>2</sub>O",
    }
    for plain, pretty in _FORMULAS.items():
        text = text.replace(plain, pretty)
    return text


def build_field_alert_context(
    df: pd.DataFrame,
    config: dict,
    priority_variables: list[str] | None = None,
) -> dict:
    """Build the Jinja2 template context for the daily field-alert HTML report.

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
    """
    # Lazy imports so dashboard modules are only needed at call time.
    # Prefer the in-package location; fall back to the ``dashboard`` package
    # found next to the palmwtc package root (research-repo companion path).
    try:
        from palmwtc.dashboard.core.health_scoring import compute_sensor_health_score
        from palmwtc.dashboard.core.recommendations import generate_recommendations
    except ImportError:
        _project_root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(_project_root))
        from dashboard.core.health_scoring import compute_sensor_health_score
        from dashboard.core.recommendations import generate_recommendations

    # --- Discover variables and their flag columns ---
    if priority_variables is None:
        priority_variables = sorted(
            {
                c.replace("_rule_flag", "").replace("_qc_flag", "")
                for c in df.columns
                if c.endswith("_rule_flag") or c.endswith("_qc_flag")
            }
        )

    # --- Compute per-variable QC summary + health scores ---
    qc_results: dict[str, dict] = {}
    health_rows: list[dict] = []

    for var in priority_variables:
        # Find the best flag column
        flag_col = None
        for suffix in ("_rule_flag", "_qc_flag"):
            if f"{var}{suffix}" in df.columns:
                flag_col = f"{var}{suffix}"
                break
        if flag_col is None:
            continue

        flags = df[flag_col].dropna()
        total = len(flags)
        if total == 0:
            continue

        f0 = (flags == 0).sum()
        f1 = (flags == 1).sum()
        f2 = (flags == 2).sum()

        summary = {
            "total_points": total,
            "flag_0_count": int(f0),
            "flag_0_percent": round(f0 / total * 100, 2),
            "flag_1_count": int(f1),
            "flag_1_percent": round(f1 / total * 100, 2),
            "flag_2_count": int(f2),
            "flag_2_percent": round(f2 / total * 100, 2),
        }
        qc_results[var] = {"summary": summary}

        health = compute_sensor_health_score(summary)
        health["variable"] = var
        health["color_hex"] = _COLOR_HEX.get(health["color"], "#95a5a6")
        health_rows.append(health)

    # Sort worst-first
    health_rows.sort(key=lambda h: h["score"])

    health_df = pd.DataFrame(health_rows)
    avg_score = health_df["score"].mean() if not health_df.empty else 0

    # --- Recommendations ---
    recommendations = generate_recommendations(
        health_scores=health_df,
        qc_results=qc_results,
        config=config,
    )
    critical_recs = [r for r in recommendations if r["severity"] == "critical"]
    warning_recs = [r for r in recommendations if r["severity"] == "warning"]

    # --- Cross-variable consistency ---
    cv_issues: list[dict] = []
    cv_cols = [c for c in df.columns if c.startswith("cv_") and c != "cv_any_flag"]
    for cv_col in sorted(cv_cols):
        flagged_pct = (df[cv_col] > 0).mean() * 100 if cv_col in df.columns else 0
        cv_issues.append(
            {
                "name": cv_col.replace("cv_", "").replace("_", " ").title(),
                "pct": round(flagged_pct, 2),
            }
        )

    # --- Status badge ---
    if avg_score >= config.get("healthy_threshold", 80):
        system_status, status_color = "HEALTHY", "#2ecc71"
    elif avg_score >= config.get("warning_threshold", 50):
        system_status, status_color = "WARNING", "#f39c12"
    else:
        system_status, status_color = "CRITICAL", "#e74c3c"

    # --- Timestamps ---
    ts_col = "TIMESTAMP" if "TIMESTAMP" in df.columns else df.index.name
    if ts_col and ts_col in df.columns:
        window_start = df[ts_col].min().strftime("%Y-%m-%d %H:%M")
        window_end = df[ts_col].max().strftime("%Y-%m-%d %H:%M")
    elif hasattr(df.index, "min"):
        window_start = df.index.min().strftime("%Y-%m-%d %H:%M")
        window_end = df.index.max().strftime("%Y-%m-%d %H:%M")
    else:
        window_start = window_end = "unknown"

    healthy_count = sum(1 for h in health_rows if h["status"] == "Healthy")

    # Prettify chemical formulas (CO2 → CO<sub>2</sub>, H2O → H<sub>2</sub>O)
    for h in health_rows:
        h["variable"] = _prettify_chemical(h["variable"])
    for rec in recommendations:
        rec["sensor"] = _prettify_chemical(rec["sensor"])
        rec["message"] = _prettify_chemical(rec["message"])
    for issue in cv_issues:
        issue["name"] = _prettify_chemical(issue["name"])

    return {
        "report_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "lookback_days": config.get("lookback_days", 7),
        "window_start": window_start,
        "window_end": window_end,
        "system_status": system_status,
        "status_color": status_color,
        "avg_score": f"{avg_score:.0f}",
        "total_sensors": len(health_rows),
        "healthy_count": healthy_count,
        "attention_sensors": [
            h for h in health_rows if h["score"] < config.get("healthy_threshold", 80)
        ],
        "critical_recs": critical_recs,
        "warning_recs": warning_recs,
        "cv_issues": [i for i in cv_issues if i["pct"] > 0],
        "qc_source": config.get("qc_source", "020"),
        # Pass-through for notebook use
        "health_rows": health_rows,
        "recommendations": recommendations,
    }


def render_field_alert_html(
    context: dict,
    template_name: str = "field_alert.html",
    template_dir: Path | None = None,
) -> str:
    """Render the field-alert Jinja2 template to an HTML string.

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
    """
    if template_dir is None:
        # Templates live alongside the qc/reporting.py module since v0.2.8.
        # The previous default pointed at palmwtc.dashboard which was removed
        # in v0.2.0 — the template was orphaned, leaving render_field_alert_html
        # silently broken until the caller passed an explicit template_dir.
        template_dir = Path(__file__).resolve().parent / "templates"

    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(template_name)
    return template.render(**context)
