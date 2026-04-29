"""Characterization tests for palmwtc.io.loaders.

These tests lock in the original behaviour of the loader functions ported
from flux_chamber/src/data_utils.py. They run against the new location and
assert on shape/content identical to what the original would produce.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from palmwtc.io import (
    export_monthly,
    integrate_temp_humidity_c2,
    load_data_in_range,
    load_from_multiple_dirs,
    load_monthly_data,
    load_radiation_data,
    read_toa5_file,
)

# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------


def _write_toa5(filepath: Path, rows: list[dict]) -> None:
    """Write a minimal TOA5-format .dat file.

    TOA5 layout:
      Row 0: TOA5 header (ignored)
      Row 1: Column names
      Row 2: Units
      Row 3: Type
      Row 4+: Data
    """
    cols = list(rows[0].keys())
    lines = []
    # Row 0: TOA5 metadata
    lines.append('"TOA5","STATION","CR1000","SN","OS","PROG","SIG","TABLE"')
    # Row 1: Column names
    lines.append(",".join(f'"{c}"' for c in cols))
    # Row 2: Units
    lines.append(",".join(['""'] * len(cols)))
    # Row 3: Type
    lines.append(",".join(['""'] * len(cols)))
    # Row 4+: Data
    for row in rows:
        lines.append(",".join(str(row[c]) for c in cols))
    filepath.write_text("\n".join(lines) + "\n")


def _write_integrated_monthly_csv(filepath: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(filepath, index=False)


# ---------------------------------------------------------------------------
# read_toa5_file
# ---------------------------------------------------------------------------


def test_read_toa5_file_happy_path(tmp_path: Path) -> None:
    f = tmp_path / "data.dat"
    _write_toa5(
        f,
        [
            {"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": 420.1, "Temp_1_C1": 25.0},
            {"TIMESTAMP": "2024-01-01 00:00:04", "CO2_C1": 420.2, "Temp_1_C1": 25.1},
            {"TIMESTAMP": "2024-01-01 00:00:08", "CO2_C1": 420.3, "Temp_1_C1": 25.2},
        ],
    )
    df = read_toa5_file(f)

    assert df is not None
    assert len(df) == 3
    assert "TIMESTAMP" in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["TIMESTAMP"])
    assert pd.api.types.is_numeric_dtype(df["CO2_C1"])
    assert df["CO2_C1"].iloc[0] == pytest.approx(420.1)


def test_read_toa5_file_no_timestamp_column_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "bad.dat"
    # First line is TOA5 metadata, second line is column names — deliberately omit TIMESTAMP.
    f.write_text('"TOA5","S","CR1000","SN","OS","P","S","T"\n"A","B"\n"",""\n"",""\n1,2\n')
    assert read_toa5_file(f) is None


def test_read_toa5_file_nonexistent_returns_none(tmp_path: Path) -> None:
    # Reading a missing file should not raise — the function catches exceptions.
    missing = tmp_path / "nope.dat"
    assert read_toa5_file(missing) is None


def test_read_toa5_file_coerces_na_values(tmp_path: Path) -> None:
    f = tmp_path / "data.dat"
    _write_toa5(
        f,
        [
            {"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": "NAN", "Temp_1_C1": 25.0},
            {"TIMESTAMP": "2024-01-01 00:00:04", "CO2_C1": 420.2, "Temp_1_C1": "nan"},
        ],
    )
    df = read_toa5_file(f)
    assert df is not None
    assert pd.isna(df["CO2_C1"].iloc[0])
    assert pd.isna(df["Temp_1_C1"].iloc[1])


# ---------------------------------------------------------------------------
# load_data_in_range
# ---------------------------------------------------------------------------


def test_load_data_in_range_flat_structure(tmp_path: Path) -> None:
    _write_toa5(
        tmp_path / "a.dat",
        [
            {"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": 420.0},
            {"TIMESTAMP": "2024-01-02 00:00:00", "CO2_C1": 421.0},
        ],
    )
    _write_toa5(
        tmp_path / "b.dat",
        [
            {"TIMESTAMP": "2024-01-03 00:00:00", "CO2_C1": 422.0},
            {"TIMESTAMP": "2024-01-04 00:00:00", "CO2_C1": 423.0},
        ],
    )

    df = load_data_in_range(
        tmp_path,
        start_date=pd.Timestamp("2024-01-02"),
        end_date=pd.Timestamp("2024-01-03 12:00:00"),
        is_flat_structure=True,
    )

    assert df is not None
    assert len(df) == 2
    assert df["TIMESTAMP"].tolist() == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
    ]


def test_load_data_in_range_recursive_structure(tmp_path: Path) -> None:
    sub = tmp_path / "2024-01"
    sub.mkdir()
    _write_toa5(
        sub / "a.dat",
        [{"TIMESTAMP": "2024-01-05 00:00:00", "CO2_C1": 420.0}],
    )

    df = load_data_in_range(
        tmp_path,
        start_date=None,
        end_date=None,
        is_flat_structure=False,
    )

    assert df is not None
    assert len(df) == 1


def test_load_data_in_range_empty_dir_returns_none(tmp_path: Path) -> None:
    df = load_data_in_range(tmp_path, None, None, is_flat_structure=True)
    assert df is None


def test_load_data_in_range_dedupes_timestamps(tmp_path: Path) -> None:
    _write_toa5(
        tmp_path / "a.dat",
        [{"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": 420.0}],
    )
    _write_toa5(
        tmp_path / "b.dat",
        [{"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": 999.0}],
    )
    df = load_data_in_range(tmp_path, None, None, is_flat_structure=True)
    assert df is not None
    assert len(df) == 1


# ---------------------------------------------------------------------------
# load_from_multiple_dirs
# ---------------------------------------------------------------------------


def test_load_from_multiple_dirs_merges_and_dedupes(tmp_path: Path) -> None:
    main = tmp_path / "main"
    update = tmp_path / "update"
    main.mkdir()
    update.mkdir()
    _write_toa5(
        main / "a.dat",
        [
            {"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": 420.0},
            {"TIMESTAMP": "2024-01-02 00:00:00", "CO2_C1": 421.0},
        ],
    )
    _write_toa5(
        update / "b.dat",
        [
            # Duplicate timestamp — the update value should win (keep='last').
            {"TIMESTAMP": "2024-01-02 00:00:00", "CO2_C1": 999.0},
            {"TIMESTAMP": "2024-01-03 00:00:00", "CO2_C1": 422.0},
        ],
    )

    df = load_from_multiple_dirs(
        [
            {"path": main, "is_flat": True},
            {"path": update, "is_flat": True},
        ]
    )

    assert df is not None
    assert len(df) == 3
    # Update wins on duplicate
    jan2 = df.loc[df["TIMESTAMP"] == pd.Timestamp("2024-01-02"), "CO2_C1"].iloc[0]
    assert jan2 == pytest.approx(999.0)


def test_load_from_multiple_dirs_empty_returns_none(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = load_from_multiple_dirs([{"path": empty, "is_flat": True}])
    assert result is None


# ---------------------------------------------------------------------------
# load_monthly_data
# ---------------------------------------------------------------------------


def test_load_monthly_data_basic(tmp_path: Path) -> None:
    _write_integrated_monthly_csv(
        tmp_path / "Integrated_Data_2024-01.csv",
        [
            {"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": 420.0, "Temp_1_C1": 25.0},
            {"TIMESTAMP": "2024-01-02 00:00:00", "CO2_C1": 421.0, "Temp_1_C1": 26.0},
        ],
    )
    _write_integrated_monthly_csv(
        tmp_path / "Integrated_Data_2024-02.csv",
        [
            {"TIMESTAMP": "2024-02-01 00:00:00", "CO2_C1": 422.0, "Temp_1_C1": 27.0},
        ],
    )

    df = load_monthly_data(tmp_path)
    assert len(df) == 3
    assert df.index.name == "TIMESTAMP"
    assert pd.api.types.is_datetime64_any_dtype(df.index)
    assert df["CO2_C1"].tolist() == [420.0, 421.0, 422.0]


def test_load_monthly_data_month_filter(tmp_path: Path) -> None:
    _write_integrated_monthly_csv(
        tmp_path / "Integrated_Data_2024-01.csv",
        [{"TIMESTAMP": "2024-01-01 00:00:00", "CO2_C1": 420.0, "Temp_1_C1": 25.0}],
    )
    _write_integrated_monthly_csv(
        tmp_path / "Integrated_Data_2024-02.csv",
        [{"TIMESTAMP": "2024-02-01 00:00:00", "CO2_C1": 422.0, "Temp_1_C1": 27.0}],
    )

    df = load_monthly_data(tmp_path, months=["2024-01"])
    assert len(df) == 1
    assert df["CO2_C1"].iloc[0] == pytest.approx(420.0)


def test_load_monthly_data_outlier_filter(tmp_path: Path) -> None:
    # Temp > 100 triggers drop; Pressure < 50 triggers drop; good row stays.
    _write_integrated_monthly_csv(
        tmp_path / "Integrated_Data_2024-01.csv",
        [
            {
                "TIMESTAMP": "2024-01-01 00:00:00",
                "AtmosphericPressure_1_C1": 100.0,
                "Temp_1_C1": 25.0,
                "VaporPressure_1_C1": 2.0,
                "RH_1_C1": 70.0,
            },
            {
                "TIMESTAMP": "2024-01-02 00:00:00",
                "AtmosphericPressure_1_C1": 100.0,
                "Temp_1_C1": 150.0,  # > 100 → drop
                "VaporPressure_1_C1": 2.0,
                "RH_1_C1": 70.0,
            },
            {
                "TIMESTAMP": "2024-01-03 00:00:00",
                "AtmosphericPressure_1_C1": 10.0,  # < 50 → drop
                "Temp_1_C1": 25.0,
                "VaporPressure_1_C1": 2.0,
                "RH_1_C1": 70.0,
            },
            {
                "TIMESTAMP": "2024-01-04 00:00:00",
                "AtmosphericPressure_1_C1": 100.0,
                "Temp_1_C1": 25.0,
                "VaporPressure_1_C1": -200.0,  # < -100 → drop
                "RH_1_C1": 70.0,
            },
        ],
    )
    df = load_monthly_data(tmp_path)
    assert len(df) == 1
    assert df.index[0] == pd.Timestamp("2024-01-01")


# ---------------------------------------------------------------------------
# integrate_temp_humidity_c2
# ---------------------------------------------------------------------------


def test_integrate_temp_humidity_c2_basic() -> None:
    clim = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=3, freq="4s"),
            "Temp_1_C2": [25.0, np.nan, 25.2],
            "RH_1_C2": [70.0, np.nan, 72.0],
        }
    )
    soil = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=2, freq="15min"),
            "AirTC_Avg_Soil": [24.0, 24.5],
            "RH_Avg_Soil": [68.0, 69.0],
        }
    )

    out = integrate_temp_humidity_c2(clim, soil)

    assert "Temp_1_C2_final" in out.columns
    assert "RH_1_C2_final" in out.columns
    assert "Temp_1_C2_source" in out.columns
    # Row 0: climate value available
    assert out["Temp_1_C2_final"].iloc[0] == pytest.approx(25.0)
    assert out["Temp_1_C2_source"].iloc[0] == "climate"
    # Row 1: climate NaN → falls back to interpolated soil
    assert out["Temp_1_C2_source"].iloc[1] == "soil_interpolated"
    assert not pd.isna(out["Temp_1_C2_final"].iloc[1])


def test_integrate_temp_humidity_c2_empty_inputs() -> None:
    out = integrate_temp_humidity_c2(None, None)
    assert isinstance(out, pd.DataFrame)
    assert out.empty


def test_integrate_temp_humidity_c2_only_climate() -> None:
    clim = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=2, freq="4s"),
            "Temp_1_C2": [25.0, 25.1],
            "RH_1_C2": [70.0, 71.0],
        }
    )
    out = integrate_temp_humidity_c2(clim, None)
    assert len(out) == 2
    assert out["Temp_1_C2_source"].tolist() == ["climate", "climate"]


# ---------------------------------------------------------------------------
# export_monthly
# ---------------------------------------------------------------------------


def test_export_monthly_basic(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "TIMESTAMP": pd.to_datetime(
                [
                    "2024-01-15 00:00:00",
                    "2024-01-16 00:00:00",
                    "2024-02-15 00:00:00",
                ]
            ),
            "value": [1.0, 2.0, 3.0],
        }
    )
    out_dir = tmp_path / "exports"
    export_monthly(df, out_dir)

    jan = out_dir / "Integrated_Data_2024-01.csv"
    feb = out_dir / "Integrated_Data_2024-02.csv"
    summary = out_dir / "Monthly_Export_Summary.csv"

    assert jan.exists()
    assert feb.exists()
    assert summary.exists()

    jan_df = pd.read_csv(jan)
    assert len(jan_df) == 2
    assert "YearMonth" not in jan_df.columns


def test_export_monthly_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    export_monthly(pd.DataFrame(), tmp_path / "nope")
    out = capsys.readouterr().out
    assert "No data to export" in out


# ---------------------------------------------------------------------------
# load_radiation_data
# ---------------------------------------------------------------------------


def test_load_radiation_data_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_radiation_data(tmp_path / "nope.xlsx") is None


def test_load_radiation_data_with_timestamp_and_radiation(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    f = tmp_path / "rad.xlsx"
    pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=3, freq="h"),
            "Global_Radiation": [100.0, 200.0, 300.0],
        }
    ).to_excel(f, index=False)

    df = load_radiation_data(f)
    assert df is not None
    assert len(df) == 3
    assert "TIMESTAMP" in df.columns
    assert "Global_Radiation" in df.columns


def test_load_radiation_data_derives_timestamp_from_date_and_time(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    f = tmp_path / "rad.xlsx"
    pd.DataFrame(
        {
            "Date": ["2024-01-01", "2024-01-02"],
            "Time": ["00:00:00", "01:00:00"],
            "Solar_Radiation": [50.0, 150.0],
        }
    ).to_excel(f, index=False)

    df = load_radiation_data(f)
    assert df is not None
    assert "TIMESTAMP" in df.columns
    assert "Global_Radiation" in df.columns
    assert df["Global_Radiation"].tolist() == [50.0, 150.0]


def test_load_radiation_data_parses_dash_dash_as_nan(tmp_path: Path) -> None:
    """Regression for v0.4.1 — AWS exports use ``"--"`` and ``"-"`` to mark
    sensor errors / missing readings.  Previously these flowed through as
    Python strings on object-dtype columns (e.g. ``Temp - °C``), which
    broke any downstream ``to_parquet`` write that included them.

    The fix is to pass ``na_values=["--", "-"]`` to ``pd.read_excel`` so
    those markers become NaN at load time and the columns stay numeric.
    """
    pytest.importorskip("openpyxl")
    f = tmp_path / "rad_with_errors.xlsx"
    # Mimic the LIBZ AWS export: a few real readings, plus the two sensor-
    # error markers in both the Temp and Global_Radiation columns.
    pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=4, freq="h"),
            "Global_Radiation": [100.0, "--", 200.0, "-"],
            "Temp - °C": [25.0, "--", 26.5, "-"],
            "Hum - %": [80.0, 82.0, "--", 85.0],
        }
    ).to_excel(f, index=False)

    df = load_radiation_data(f)
    assert df is not None

    # Global_Radiation must be numeric with NaN where the markers were.
    assert pd.api.types.is_numeric_dtype(df["Global_Radiation"]), (
        f"Global_Radiation should be numeric after the fix, got {df['Global_Radiation'].dtype}"
    )
    assert df["Global_Radiation"].isna().sum() == 2
    assert df["Global_Radiation"].dropna().tolist() == [100.0, 200.0]

    # Other AWS columns must also be numeric so downstream ``to_parquet``
    # writes (which is what failed before the fix) succeed without an
    # ArrowInvalid.  We don't assert their exact values here — just dtype.
    assert pd.api.types.is_numeric_dtype(df["Temp - °C"]), (
        f"'Temp - °C' should be numeric after the fix, got {df['Temp - °C'].dtype}"
    )
    assert pd.api.types.is_numeric_dtype(df["Hum - %"]), (
        f"'Hum - %' should be numeric after the fix, got {df['Hum - %'].dtype}"
    )

    # Smoke check: the resulting frame must be writeable as parquet.
    # This is the contract that broke production downstream of
    # load_radiation_data.
    pytest.importorskip("pyarrow")
    parquet_path = tmp_path / "rad_round_trip.parquet"
    df.to_parquet(parquet_path)
    assert parquet_path.exists()
