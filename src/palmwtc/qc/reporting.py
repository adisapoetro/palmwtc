"""palmwtc.qc.reporting — QC summary export + field alert HTML report.

Behaviour-preserving port of ``flux_chamber/src/qc_reporting.py``. Only
``import`` statements were updated to point at the new package layout.

Public API (re-exported from :mod:`palmwtc.qc`):

- :func:`generate_qc_summary_from_results` — flatten per-variable QC dicts
  into a sorted ``pandas.DataFrame``.
- :func:`export_qc_data` — write a QC-flagged dataframe to Parquet (zstd)
  with optional CSV backup.
- :func:`build_field_alert_context` — build the Jinja2 context for the
  notebook-023 field alert HTML report.
- :func:`render_field_alert_html` — render the field alert template to a
  string for emailing or notebook display.
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader


def generate_qc_summary_from_results(qc_results: dict) -> pd.DataFrame:
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
):
    """
    Export data with QC flags to Parquet (primary) and optionally CSV (backup).

    Primary output: QC_Flagged_Data_latest.parquet (zstd, fixed name, overwrites each run)
    Fallback output: QC_Flagged_Data_latest.csv (when no Parquet engine is installed)
    Backup output:   QC_Flagged_Data_{timestamp}.csv (only when keep_csv_backup=True)

    Returns the path of the file that was written.
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
    """Build Jinja2 template context for the field alert HTML report.

    Parameters
    ----------
    df : pd.DataFrame
        QC-flagged dataframe (already filtered to the lookback window).
        Must contain ``{var}_rule_flag`` or ``{var}_qc_flag`` columns and
        optionally ``cv_*`` cross-variable columns.
    config : dict
        Notebook CONFIG dict with thresholds (healthy_threshold, etc.).
    priority_variables : list[str] | None
        Subset of variable names to report on.  If *None*, auto-detect from
        columns ending with ``_rule_flag`` or ``_qc_flag``.

    Returns
    -------
    dict
        Context dict ready to pass to :func:`render_field_alert_html`.
    """
    # Lazy imports so dashboard modules are only needed at call time.
    # Prefer the in-package location (Phase 6 will land
    # ``palmwtc.dashboard.core``); fall back to the legacy
    # ``flux_chamber/dashboard`` tree by walking up to the project root and
    # adding it to ``sys.path``. This preserves the original
    # ``sys.path.insert`` behaviour during the transition.
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
    """Render the field alert Jinja2 template to an HTML string.

    Parameters
    ----------
    context : dict
        Context dict from :func:`build_field_alert_context`.
    template_name : str
        Template filename inside *template_dir*.
    template_dir : Path | None
        Directory containing the Jinja2 template.  Defaults to
        ``dashboard/email_report/templates/`` relative to the project root.
    """
    if template_dir is None:
        template_dir = (
            Path(__file__).resolve().parent.parent / "dashboard" / "email_report" / "templates"
        )

    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(template_name)
    return template.render(**context)
