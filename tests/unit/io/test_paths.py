"""Characterization tests for palmwtc.io.paths.

Functions ported from flux_chamber/src/data_utils.py: find_latest_qc_file,
get_usecols, data_integrity_report.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from palmwtc.io import data_integrity_report, find_latest_qc_file, get_usecols

# ---------------------------------------------------------------------------
# find_latest_qc_file
# ---------------------------------------------------------------------------


def test_find_latest_qc_file_named_source_020(tmp_path: Path) -> None:
    (tmp_path / "020_rule_qc_output.parquet").touch()
    (tmp_path / "022_ml_qc_output.parquet").touch()
    result = find_latest_qc_file(tmp_path, source="020")
    assert result == tmp_path / "020_rule_qc_output.parquet"


def test_find_latest_qc_file_named_source_022(tmp_path: Path) -> None:
    (tmp_path / "022_ml_qc_output.parquet").touch()
    result = find_latest_qc_file(tmp_path, source="022")
    assert result == tmp_path / "022_ml_qc_output.parquet"


def test_find_latest_qc_file_falls_back_to_legacy_parquet(tmp_path: Path) -> None:
    (tmp_path / "QC_Flagged_Data_latest.parquet").touch()
    result = find_latest_qc_file(tmp_path, source="025")
    assert result == tmp_path / "QC_Flagged_Data_latest.parquet"


def test_find_latest_qc_file_falls_back_to_timestamped_parquet(tmp_path: Path) -> None:
    (tmp_path / "QC_Flagged_Data_2024-01.parquet").touch()
    (tmp_path / "QC_Flagged_Data_2024-02.parquet").touch()
    result = find_latest_qc_file(tmp_path, source="025")
    # sorted reverse, so 02 > 01
    assert result == tmp_path / "QC_Flagged_Data_2024-02.parquet"


def test_find_latest_qc_file_falls_back_to_csv(tmp_path: Path) -> None:
    (tmp_path / "QC_Flagged_Data_2024-01.csv").touch()
    result = find_latest_qc_file(tmp_path, source="025")
    assert result == tmp_path / "QC_Flagged_Data_2024-01.csv"


def test_find_latest_qc_file_no_matches_returns_none(tmp_path: Path) -> None:
    assert find_latest_qc_file(tmp_path, source="020") is None


def test_find_latest_qc_file_accepts_string_dir(tmp_path: Path) -> None:
    (tmp_path / "020_rule_qc_output.parquet").touch()
    result = find_latest_qc_file(str(tmp_path), source="020")
    assert result == tmp_path / "020_rule_qc_output.parquet"


# ---------------------------------------------------------------------------
# get_usecols
# ---------------------------------------------------------------------------


def test_get_usecols_csv(tmp_path: Path) -> None:
    f = tmp_path / "qc.csv"
    pd.DataFrame(
        columns=[
            "TIMESTAMP",
            "CO2_C1",
            "CO2_C2",
            "Temp_1_C1",
            "Temp_1_C2",
            "RH_1_C1",
            "nonsense_col",
            "H2O_C1_qc_flag",
        ]
    ).to_csv(f, index=False)

    cols = get_usecols(f)
    # Should include things in "want" and "optional"
    assert "TIMESTAMP" in cols
    assert "CO2_C1" in cols
    assert "CO2_C2" in cols
    assert "Temp_1_C1" in cols
    assert "RH_1_C1" in cols
    assert "H2O_C1_qc_flag" in cols
    assert "nonsense_col" not in cols


def test_get_usecols_parquet(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    f = tmp_path / "qc.parquet"
    pd.DataFrame(
        {
            "TIMESTAMP": pd.to_datetime(["2024-01-01"]),
            "CO2_C1": [420.0],
            "CO2_C2": [421.0],
            "Temp_1_C1": [25.0],
            "Temp_1_C2": [25.1],
            "H2O_C1": [15.0],
            "H2O_C2": [16.0],
            "irrelevant": [1],
        }
    ).to_parquet(f)

    cols = get_usecols(f)
    assert "TIMESTAMP" in cols
    assert "CO2_C1" in cols
    assert "H2O_C1" in cols
    assert "irrelevant" not in cols


# ---------------------------------------------------------------------------
# data_integrity_report
# ---------------------------------------------------------------------------


def test_data_integrity_report_basic_shape() -> None:
    ts = pd.date_range("2024-01-01", periods=10, freq="4s")
    df = pd.DataFrame(
        {
            "TIMESTAMP": ts,
            "CO2_C1": np.arange(10, dtype=float),
            "CO2_C2": np.arange(10, dtype=float),
            "Temp_1_C1": np.arange(10, dtype=float),
            "Temp_1_C2": np.arange(10, dtype=float),
            "H2O_C1": np.full(10, 15.0),
            "H2O_C2": np.full(10, 16.0),
        }
    )

    report = data_integrity_report(df)
    assert isinstance(report, pd.DataFrame)
    assert len(report) == 1
    assert report["rows"].iloc[0] == 10
    assert report["start"].iloc[0] == ts.min()
    assert report["end"].iloc[0] == ts.max()
    assert report["median_dt_sec"].iloc[0] == pytest.approx(4.0)
    assert report["pct_duplicates"].iloc[0] == pytest.approx(0.0)
    # wpl_input_valid_pct_C1 — all H2O are 15.0 which is in [0, 60], so 100%
    assert report["wpl_input_valid_pct_C1"].iloc[0] == pytest.approx(100.0)


def test_data_integrity_report_missing_columns_are_nan() -> None:
    ts = pd.date_range("2024-01-01", periods=3, freq="4s")
    df = pd.DataFrame({"TIMESTAMP": ts, "CO2_C1": [1.0, 2.0, 3.0]})
    report = data_integrity_report(df)
    assert pd.isna(report["missing_CO2_C2"].iloc[0])
    assert pd.isna(report["missing_Temp_1_C1"].iloc[0])
    # No H2O columns → wpl_input_valid_pct_C1/C2 NaN
    assert pd.isna(report["wpl_input_valid_pct_C1"].iloc[0])
    assert pd.isna(report["wpl_input_valid_pct_C2"].iloc[0])


def test_data_integrity_report_detects_duplicates() -> None:
    ts = pd.to_datetime(
        [
            "2024-01-01 00:00:00",
            "2024-01-01 00:00:00",
            "2024-01-01 00:00:04",
            "2024-01-01 00:00:08",
        ]
    )
    df = pd.DataFrame({"TIMESTAMP": ts, "CO2_C1": [1.0, 2.0, 3.0, 4.0]})
    report = data_integrity_report(df)
    assert report["pct_duplicates"].iloc[0] == pytest.approx(25.0)


def test_data_integrity_report_prefers_corrected_h2o() -> None:
    ts = pd.date_range("2024-01-01", periods=3, freq="4s")
    df = pd.DataFrame(
        {
            "TIMESTAMP": ts,
            # corrected out of range so count should be 0%
            "H2O_C1": [15.0, 15.0, 15.0],
            "H2O_C1_corrected": [100.0, 100.0, 100.0],
        }
    )
    report = data_integrity_report(df)
    # Prefers corrected column, which has values > 60 → invalid → 0%
    assert report["wpl_input_valid_pct_C1"].iloc[0] == pytest.approx(0.0)
