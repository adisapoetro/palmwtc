#!/usr/bin/env python
# ruff: noqa: RUF001
"""Generate the bundled synthetic sample dataset shipped with palmwtc.

Produces ~5 MB of deterministic chamber + climate data in the *post-020 QC
parquet shape* (the stage that notebook 030 consumes). This skips the raw
TOA5 data-ingest layer, which is too site-specific to fake; instead, the
synthetic sample exercises the downstream flux + windows + validation
pipeline. Real users with real chamber outputs run the full pipeline
starting at notebook 010.

Generated assets (all under ``src/palmwtc/data/sample/synthetic/``):
- ``QC_Flagged_Data_synthetic.parquet`` — 1 week of 30-second chamber cycles
  for two chambers (C1 + C2), with QC flags and intentional edge cases.
- ``weather_30min.csv`` — 30-min aggregated weather (radiation, VPD, rainfall).
- ``tree_biophysics_events.csv`` — vigor + phenology events for both chambers.
- ``README.md`` — explains what's here and how it was generated.

Determinism: ``numpy.random.default_rng(seed=42)`` everywhere. Re-running this
script produces byte-identical output (modulo parquet metadata).

Edge cases injected:
- 1 NaN burst (45 min, chamber 1 CO2)
- 1 linear drift segment (3 days, chamber 2 CO2 baseline +0.5 ppm/day)
- 2 out-of-bounds spikes (one per chamber)
- 1 saturated H2O spike (chamber 1)

Usage::

    .venv/bin/python scripts/make_sample_data.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
DURATION_DAYS = 7
SAMPLING_SEC = 30
CYCLE_MINUTES = 30
CLOSED_MINUTES = 10
START = datetime(2026, 3, 1, 0, 0, 0)

OUT_DIR = (
    Path(__file__).resolve().parent.parent / "src" / "palmwtc" / "data" / "sample" / "synthetic"
)


def generate_cycles_one_chamber(
    chamber: int, ts: pd.DatetimeIndex, rng: np.random.Generator
) -> pd.DataFrame:
    """Synthetic CO2/H2O/Temp/RH/Pressure for one chamber over the full timeseries."""
    n = len(ts)
    cycle_seconds = CYCLE_MINUTES * 60
    closed_seconds = CLOSED_MINUTES * 60

    # Position within each cycle: 0 .. cycle_seconds-1.
    seconds_since_start = (ts - ts[0]).total_seconds().astype(int)
    cycle_pos = seconds_since_start % cycle_seconds
    is_closed = cycle_pos < closed_seconds

    # CO2 baseline ~ 410 ppm with diurnal swing. Closed-phase ramp adds ~+20 ppm.
    hour = ts.hour + ts.minute / 60.0
    diurnal_co2 = 10 * np.cos((hour - 14) / 24 * 2 * np.pi)  # cooler day, photosynthesis dip
    closed_ramp = np.where(
        is_closed,
        20 * (cycle_pos.values / closed_seconds),  # linear ramp 0 → 20 ppm during closed
        0.0,
    )
    co2 = 410.0 + diurnal_co2.values + closed_ramp + rng.normal(0, 0.4, n)

    # H2O baseline ~ 22 mmol/mol with similar cycle pattern (transpiration during closed).
    diurnal_h2o = 4 * np.sin((hour - 6) / 24 * 2 * np.pi)
    closed_h2o_ramp = np.where(is_closed, 6 * (cycle_pos.values / closed_seconds), 0.0)
    h2o = 22.0 + diurnal_h2o.values + closed_h2o_ramp + rng.normal(0, 0.15, n)

    # Met
    temp = 26.0 + 6 * np.sin((hour - 14) / 24 * 2 * np.pi).values + rng.normal(0, 0.3, n)
    rh = np.clip(
        75.0 - 25 * np.sin((hour - 14) / 24 * 2 * np.pi).values + rng.normal(0, 1.5, n), 30, 100
    )
    pressure = 1011.0 + rng.normal(0, 0.6, n)
    vapor_pressure = h2o * pressure / 1000.0  # rough proxy

    return pd.DataFrame(
        {
            f"CO2_C{chamber}": co2,
            f"H2O_C{chamber}": h2o,
            f"VaporPressure_1_C{chamber}": vapor_pressure,
            f"Temp_1_C{chamber}": temp,
            f"RH_1_C{chamber}": rh,
            f"AtmosphericPressure_1_C{chamber}": pressure,
            f"Batt_volt_Min_C{chamber}": 12.6 + rng.normal(0, 0.05, n),
        }
    )


def inject_edge_cases(df: pd.DataFrame, ts: pd.DatetimeIndex, rng: np.random.Generator) -> dict:
    """Inject realistic QC-relevant artefacts. Returns a dict logging what was injected."""
    log: dict = {}

    # 1) NaN burst, chamber 1 CO2, 45 min on day 2 around noon.
    nan_start = ts.searchsorted(ts[0] + timedelta(days=2, hours=12))
    nan_end = nan_start + (45 * 60 // SAMPLING_SEC)
    df.iloc[nan_start:nan_end, df.columns.get_loc("CO2_C1")] = np.nan
    log["nan_burst"] = {"variable": "CO2_C1", "start": str(ts[nan_start]), "minutes": 45}

    # 2) Linear drift, chamber 2 CO2 baseline, days 4..7 (+0.5 ppm/day).
    drift_start = ts.searchsorted(ts[0] + timedelta(days=4))
    drift_seconds = (ts[drift_start:] - ts[drift_start]).total_seconds().values
    drift_ppm = 0.5 * (drift_seconds / 86400)
    df.iloc[drift_start:, df.columns.get_loc("CO2_C2")] += drift_ppm
    log["drift"] = {"variable": "CO2_C2", "start": str(ts[drift_start]), "rate": "+0.5 ppm/day"}

    # 3) Out-of-bounds spike, chamber 1 CO2, day 5 at 10am: 800 ppm for 2 minutes.
    spike1_start = ts.searchsorted(ts[0] + timedelta(days=5, hours=10))
    spike1_end = spike1_start + (2 * 60 // SAMPLING_SEC)
    df.iloc[spike1_start:spike1_end, df.columns.get_loc("CO2_C1")] = 800.0
    log["spike_co2"] = {"variable": "CO2_C1", "start": str(ts[spike1_start]), "value": 800.0}

    # 4) Out-of-bounds spike, chamber 2 H2O, day 6 at 14:00: -5 mmol/mol for 1 min.
    spike2_start = ts.searchsorted(ts[0] + timedelta(days=6, hours=14))
    spike2_end = spike2_start + (60 // SAMPLING_SEC)
    df.iloc[spike2_start:spike2_end, df.columns.get_loc("H2O_C2")] = -5.0
    log["spike_h2o"] = {"variable": "H2O_C2", "start": str(ts[spike2_start]), "value": -5.0}

    # 5) Saturated H2O spike, chamber 1, day 3 at 03:00: 60 mmol/mol for 30 sec.
    sat_idx = ts.searchsorted(ts[0] + timedelta(days=3, hours=3))
    df.iloc[sat_idx : sat_idx + 1, df.columns.get_loc("H2O_C1")] = 60.0
    log["saturation"] = {"variable": "H2O_C1", "start": str(ts[sat_idx]), "value": 60.0}

    return log


def add_qc_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add minimal QC flag columns (zero = pass) so downstream code finds the columns it expects."""
    flag_columns = {
        "CO2_C1_qc_flag": (
            df["CO2_C1"].isna() | (df["CO2_C1"] < 300) | (df["CO2_C1"] > 600)
        ).astype(int),
        "CO2_C2_qc_flag": (
            df["CO2_C2"].isna() | (df["CO2_C2"] < 300) | (df["CO2_C2"] > 600)
        ).astype(int),
        "H2O_C1_qc_flag": (df["H2O_C1"].isna() | (df["H2O_C1"] < 0) | (df["H2O_C1"] > 50)).astype(
            int
        ),
        "H2O_C2_qc_flag": (df["H2O_C2"].isna() | (df["H2O_C2"] < 0) | (df["H2O_C2"] > 50)).astype(
            int
        ),
    }
    return df.assign(**flag_columns)


def generate_weather_30min(
    ts_start: datetime, ndays: int, rng: np.random.Generator
) -> pd.DataFrame:
    """30-min aggregated weather: radiation (PAR proxy), VPD, rainfall."""
    n = ndays * 48
    ts = pd.date_range(ts_start, periods=n, freq="30min")
    hour = ts.hour + ts.minute / 60.0
    sw_in = np.clip(900 * np.sin((hour - 6) / 12 * np.pi).values, 0, 900) + rng.normal(0, 20, n)
    sw_in = np.clip(sw_in, 0, None)
    air_temp = 26.0 + 6 * np.sin((hour - 14) / 24 * 2 * np.pi).values + rng.normal(0, 0.5, n)
    rh = np.clip(
        75.0 - 25 * np.sin((hour - 14) / 24 * 2 * np.pi).values + rng.normal(0, 2, n), 30, 100
    )
    es = 0.6108 * np.exp((17.27 * air_temp) / (air_temp + 237.3))
    vpd = es * (1 - rh / 100)
    rain = rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1.5], size=n) * rng.uniform(0.5, 3.0, n)
    return pd.DataFrame(
        {
            "TIMESTAMP": ts,
            "SW_IN_Avg": sw_in,
            "AirTC_Avg": air_temp,
            "RH_Avg": rh,
            "VPD_kPa": vpd,
            "Rain_mm_Tot": rain,
        }
    )


def generate_tree_biophysics(ts_start: datetime, ndays: int) -> pd.DataFrame:
    """Stub tree biophysics: 1 vigor measurement at start, 1 phenology event mid-week."""
    return pd.DataFrame(
        {
            "chamber": ["C1", "C2"],
            "date": [ts_start.date(), ts_start.date()],
            "trunk_height_cm": [180.0, 175.0],
            "leaf_area_m2": [12.0, 11.5],
            "vigor_index": [0.78, 0.82],
            "event": ["baseline_vigor_measurement", "baseline_vigor_measurement"],
        }
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    n_samples = DURATION_DAYS * 24 * 3600 // SAMPLING_SEC
    ts = pd.date_range(START, periods=n_samples, freq=f"{SAMPLING_SEC}s")
    print(f"[sample] {n_samples} rows over {DURATION_DAYS} days at {SAMPLING_SEC}s sampling")

    c1 = generate_cycles_one_chamber(1, ts, rng)
    c2 = generate_cycles_one_chamber(2, ts, rng)
    df = pd.concat([pd.DataFrame({"TIMESTAMP": ts}), c1, c2], axis=1)

    edge_log = inject_edge_cases(df, ts, rng)
    print(f"[sample] injected edge cases: {len(edge_log)}")
    df = add_qc_flags(df)

    parquet_path = OUT_DIR / "QC_Flagged_Data_synthetic.parquet"
    df.to_parquet(parquet_path, index=False)
    size_mb = parquet_path.stat().st_size / 1e6
    print(
        f"[sample] wrote {parquet_path.name} ({size_mb:.2f} MB, {df.shape[0]} rows × {df.shape[1]} cols)"
    )

    weather = generate_weather_30min(START, DURATION_DAYS, rng)
    weather_path = OUT_DIR / "weather_30min.csv"
    weather.to_csv(weather_path, index=False)
    print(f"[sample] wrote {weather_path.name} ({weather.shape[0]} rows)")

    bio = generate_tree_biophysics(START, DURATION_DAYS)
    bio_path = OUT_DIR / "tree_biophysics_events.csv"
    bio.to_csv(bio_path, index=False)
    print(f"[sample] wrote {bio_path.name} ({bio.shape[0]} rows)")

    readme = OUT_DIR / "README.md"
    readme.write_text(
        "# palmwtc bundled synthetic sample\n\n"
        f"Deterministic ({SEED=}) synthetic dataset for CI smoke + zero-config first-run.\n\n"
        f"- {DURATION_DAYS} days × {SAMPLING_SEC}s sampling = {df.shape[0]} chamber rows.\n"
        f"- 2 chambers (C1, C2), {CYCLE_MINUTES}-min cycles ({CLOSED_MINUTES} closed / "
        f"{CYCLE_MINUTES - CLOSED_MINUTES} open).\n"
        f"- 30-min weather, 2 baseline tree biophysics rows.\n\n"
        f"Edge cases injected: {edge_log}\n\n"
        "Regenerate with `python scripts/make_sample_data.py`.\n"
    )

    print(
        f"[sample] done — total {sum(p.stat().st_size for p in OUT_DIR.iterdir()) / 1e6:.2f} MB in {OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
