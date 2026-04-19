"""Path resolution & data-integrity helpers for the palmwtc package.

Ported verbatim from ``flux_chamber/src/data_utils.py`` (Phase 2).
Behaviour preservation is the prime directive.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# QC Data Loading Helpers
# ---------------------------------------------------------------------------


def find_latest_qc_file(qc_dir, pattern="QC_Flagged_Data_*.csv", source="020"):
    """Find a QC output file in *qc_dir* by upstream notebook source.

    Parameters
    ----------
    source : str
        Which upstream notebook's output to load:
        "020" → 020_rule_qc_output.parquet  (rule-based QC)
        "022" → 022_ml_qc_output.parquet    (rule + ML QC)
        "025" → 025_cross_chamber_corrected.parquet
        "026" → 026_segmented_bias_corrected.parquet

    Falls back to legacy QC_Flagged_Data_latest.parquet / CSV if named file not found.
    """
    qc_dir = Path(qc_dir)
    _file_map = {
        "020": "020_rule_qc_output.parquet",
        "022": "022_ml_qc_output.parquet",
        "025": "025_cross_chamber_corrected.parquet",
        "026": "026_segmented_bias_corrected.parquet",
    }
    # Try named file first
    if source in _file_map:
        named = qc_dir / _file_map[source]
        if named.exists():
            return named
    # Legacy fallback
    fixed = qc_dir / "QC_Flagged_Data_latest.parquet"
    if fixed.exists():
        return fixed
    parquets = sorted(qc_dir.glob("QC_Flagged_Data_*.parquet"), reverse=True)
    if parquets:
        return parquets[0]
    csvs = sorted(qc_dir.glob(pattern), reverse=True)
    return csvs[0] if csvs else None


def get_usecols(path):
    """Determine which columns to load from a QC file (Parquet or CSV) to reduce memory."""
    path = Path(path)
    want = {
        "TIMESTAMP",
        "CO2_C1",
        "CO2_C2",
        "Temp_1_C1",
        "Temp_1_C2",
        "CO2_C1_qc_flag",
        "CO2_C2_qc_flag",
        "H2O_C1",
        "H2O_C2",
        "H2O_C1_qc_flag",
        "H2O_C2_qc_flag",
        "H2O_C1_corrected",
        "H2O_C2_corrected",
    }
    optional = {"RH_1_C1", "RH_1_C2"}
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        all_cols = pq.read_schema(path).names  # reads footer only — fast
    else:
        all_cols = pd.read_csv(path, nrows=0).columns
    return [c for c in all_cols if c in want or c in optional]


def data_integrity_report(data, cycle_gap_sec=300, h2o_valid_range=(0.0, 60.0)):
    """
    Generate a one-row DataFrame summarising data integrity.

    Checks: row count, time range, median delta-t, duplicate percentage,
    gap percentage, per-column missing rates, and WPL input validity.
    """
    report = {}
    report["rows"] = len(data)
    report["start"] = data["TIMESTAMP"].min()
    report["end"] = data["TIMESTAMP"].max()

    delta = data["TIMESTAMP"].diff().dt.total_seconds()
    report["median_dt_sec"] = float(delta.median()) if delta.notna().any() else np.nan
    report["pct_duplicates"] = float(data["TIMESTAMP"].duplicated().mean() * 100.0)
    report["gaps_over_cycle_pct"] = float((delta > cycle_gap_sec).mean() * 100.0)

    tracked_cols = [
        "CO2_C1",
        "CO2_C2",
        "Temp_1_C1",
        "Temp_1_C2",
        "H2O_C1",
        "H2O_C2",
        "H2O_C1_corrected",
        "H2O_C2_corrected",
    ]
    for col in tracked_cols:
        if col in data.columns:
            report[f"missing_{col}"] = float(data[col].isna().mean() * 100.0)
        else:
            report[f"missing_{col}"] = np.nan

    lo, hi = h2o_valid_range
    for suffix in ["C1", "C2"]:
        h2o_candidates = [f"H2O_{suffix}_corrected", f"H2O_{suffix}"]
        h2o_col = next((c for c in h2o_candidates if c in data.columns), None)

        if h2o_col is None:
            report[f"wpl_input_valid_pct_{suffix}"] = np.nan
            continue

        h2o = pd.to_numeric(data[h2o_col], errors="coerce")
        denom = 1000.0 - h2o
        valid = h2o.notna() & (h2o >= lo) & (h2o <= hi) & denom.gt(0)
        report[f"wpl_input_valid_pct_{suffix}"] = float(valid.mean() * 100.0)

    return pd.DataFrame([report])
