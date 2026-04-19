"""Characterization tests for palmwtc.flux.absolute.

Functions ported from flux_chamber/src/flux_analysis.py:
    - calculate_absolute_flux
    - calculate_h2o_absolute_flux
    - calculate_flux_for_chamber

Includes:
    1. Standalone behaviour tests (always run) — anchor numeric semantics
       on synthetic inputs.
    2. Parity tests against the original module (skip if source not on disk)
       — assert numeric equality to 1e-12.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from palmwtc.flux.absolute import (
    calculate_absolute_flux,
    calculate_flux_for_chamber,
    calculate_h2o_absolute_flux,
)

FLUX_CHAMBER_SRC = Path("/Users/adisapoetro/flux_chamber/src/flux_analysis.py")


def _load_original() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_flux_chamber_flux_analysis_orig", FLUX_CHAMBER_SRC
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PARITY_SKIP = pytest.mark.skipif(
    not FLUX_CHAMBER_SRC.exists(),
    reason="flux_chamber source not available at expected path",
)


# ---------------------------------------------------------------------------
# calculate_absolute_flux — standalone
# ---------------------------------------------------------------------------


def _make_row(
    flux_slope: float = 0.05,
    mean_temp: float | None = 25.0,
    flux_date: pd.Timestamp = pd.Timestamp("2025-01-15"),
    tree_volume: float | None = 0.0,
) -> pd.Series:
    data: dict = {
        "flux_slope": flux_slope,
        "flux_date": flux_date,
    }
    if mean_temp is not None:
        data["mean_temp"] = mean_temp
    if tree_volume is not None:
        data["tree_volume"] = tree_volume
    return pd.Series(data)


def test_calculate_absolute_flux_pre_cutoff_known_values() -> None:
    """Pre-July-2025 chamber: V=8, A=4, h_eff=2 m at 25 C, slope=0.05 ppm/s."""
    row = _make_row(
        flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-01-15"), tree_volume=0.0
    )
    # rho_air = 101325 / (8.314 * 298.15) = 40.873... mol/m³
    R = 8.314
    P_std = 101325
    rho_air = P_std / (R * (25.0 + 273.15))
    expected = 0.05 * rho_air * 2.0
    result = calculate_absolute_flux(row)
    assert result == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_post_cutoff_known_values() -> None:
    """Post-July-2025 chamber: V=96, A=16, h_eff=6 m at 25 C, slope=0.05 ppm/s."""
    row = _make_row(
        flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-08-15"), tree_volume=0.0
    )
    R = 8.314
    P_std = 101325
    rho_air = P_std / (R * (25.0 + 273.15))
    expected = 0.05 * rho_air * 6.0
    result = calculate_absolute_flux(row)
    assert result == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_defaults_to_25c_when_temp_missing() -> None:
    row = _make_row(
        flux_slope=0.05, mean_temp=None, flux_date=pd.Timestamp("2025-01-15"), tree_volume=0.0
    )
    expected = calculate_absolute_flux(
        _make_row(flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-01-15"))
    )
    assert calculate_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_handles_nan_mean_temp() -> None:
    row = pd.Series(
        {
            "flux_slope": 0.05,
            "flux_date": pd.Timestamp("2025-01-15"),
            "mean_temp": np.nan,
            "tree_volume": 0.0,
        }
    )
    expected = calculate_absolute_flux(
        _make_row(flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-01-15"))
    )
    assert calculate_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_returns_nan_when_flux_date_missing() -> None:
    row = pd.Series({"flux_slope": 0.05, "mean_temp": 25.0, "tree_volume": 0.0})
    assert math.isnan(calculate_absolute_flux(row))


def test_calculate_absolute_flux_treats_missing_tree_volume_as_zero() -> None:
    row = pd.Series(
        {
            "flux_slope": 0.05,
            "flux_date": pd.Timestamp("2025-01-15"),
            "mean_temp": 25.0,
        }
    )
    # No tree_volume key at all → defaults to 0.0
    expected = calculate_absolute_flux(
        _make_row(
            flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-01-15"), tree_volume=0.0
        )
    )
    assert calculate_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_treats_nan_tree_volume_as_zero() -> None:
    row = _make_row(
        flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-01-15"), tree_volume=np.nan
    )
    expected = calculate_absolute_flux(
        _make_row(
            flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-01-15"), tree_volume=0.0
        )
    )
    assert calculate_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_clamps_net_volume_to_min_0p1() -> None:
    """Tree volume larger than chamber → net_vol clamped to 0.1 m³."""
    row = _make_row(
        flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-01-15"), tree_volume=100.0
    )
    R = 8.314
    P_std = 101325
    rho_air = P_std / (R * (25.0 + 273.15))
    expected = 0.05 * rho_air * (0.1 / 4.0)
    assert calculate_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_subtracts_tree_volume() -> None:
    row = _make_row(
        flux_slope=0.05, mean_temp=25.0, flux_date=pd.Timestamp("2025-08-15"), tree_volume=20.0
    )
    R = 8.314
    P_std = 101325
    rho_air = P_std / (R * (25.0 + 273.15))
    expected = 0.05 * rho_air * ((96.0 - 20.0) / 16.0)
    assert calculate_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_absolute_flux_negative_slope_yields_negative_flux() -> None:
    row = _make_row(
        flux_slope=-0.10, mean_temp=25.0, flux_date=pd.Timestamp("2025-08-15"), tree_volume=0.0
    )
    result = calculate_absolute_flux(row)
    assert result < 0


# ---------------------------------------------------------------------------
# calculate_h2o_absolute_flux — standalone
# ---------------------------------------------------------------------------


def test_calculate_h2o_absolute_flux_pre_cutoff_known() -> None:
    row = pd.Series(
        {
            "h2o_slope": 0.5,
            "flux_date": pd.Timestamp("2025-01-15"),
            "mean_temp": 25.0,
            "tree_volume": 0.0,
        }
    )
    R = 8.314
    P_std = 101325
    rho_air = P_std / (R * (25.0 + 273.15))
    expected = 0.5 * rho_air * 2.0
    assert calculate_h2o_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_h2o_absolute_flux_post_cutoff_known() -> None:
    row = pd.Series(
        {
            "h2o_slope": 0.5,
            "flux_date": pd.Timestamp("2025-08-15"),
            "mean_temp": 25.0,
            "tree_volume": 0.0,
        }
    )
    R = 8.314
    P_std = 101325
    rho_air = P_std / (R * (25.0 + 273.15))
    expected = 0.5 * rho_air * 6.0
    assert calculate_h2o_absolute_flux(row) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_calculate_h2o_absolute_flux_returns_nan_when_h2o_slope_missing() -> None:
    row = pd.Series(
        {
            "flux_date": pd.Timestamp("2025-08-15"),
            "mean_temp": 25.0,
            "tree_volume": 0.0,
        }
    )
    assert math.isnan(calculate_h2o_absolute_flux(row))


def test_calculate_h2o_absolute_flux_returns_nan_when_h2o_slope_nan() -> None:
    row = pd.Series(
        {
            "h2o_slope": np.nan,
            "flux_date": pd.Timestamp("2025-08-15"),
            "mean_temp": 25.0,
            "tree_volume": 0.0,
        }
    )
    assert math.isnan(calculate_h2o_absolute_flux(row))


def test_calculate_h2o_absolute_flux_returns_nan_when_flux_date_missing() -> None:
    row = pd.Series({"h2o_slope": 0.5, "mean_temp": 25.0, "tree_volume": 0.0})
    assert math.isnan(calculate_h2o_absolute_flux(row))


# ---------------------------------------------------------------------------
# calculate_flux_for_chamber — standalone
# ---------------------------------------------------------------------------


@pytest.fixture
def _passthrough_tqdm(monkeypatch):
    """Replace tqdm.notebook in absolute.py with a no-op passthrough.

    The ported (and original) ``calculate_flux_for_chamber`` uses
    ``from tqdm.notebook import tqdm``, which requires ipywidgets/IProgress
    in the runtime environment — not available in headless pytest. The
    callable contract is identical (iterable in, iterable out), so a
    passthrough preserves behaviour without depending on Jupyter widgets.
    """

    def _passthrough(iterable, *_args, **_kwargs):
        return iterable

    monkeypatch.setattr("palmwtc.flux.absolute.tqdm", _passthrough)


def _build_synthetic_chamber_df(seed: int = 42) -> pd.DataFrame:
    """Two cycles of CO2 measurements, ~1 Hz, separated by a 600 s gap."""
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2025-01-15 08:00:00")

    # Cycle 1: 200 samples at 1 s spacing, slope = 0.05 ppm/s
    t1 = pd.date_range(base, periods=200, freq="1s")
    co2_1 = 400.0 + 0.05 * np.arange(200) + rng.normal(0, 0.1, 200)

    # Gap
    base2 = base + pd.Timedelta(seconds=200 + 600)

    # Cycle 2: 150 samples, slope = -0.10 ppm/s (uptake)
    t2 = pd.date_range(base2, periods=150, freq="1s")
    co2_2 = 410.0 - 0.10 * np.arange(150) + rng.normal(0, 0.1, 150)

    return pd.DataFrame(
        {
            "TIMESTAMP": list(t1) + list(t2),
            "CO2": list(co2_1) + list(co2_2),
            "Temp": [25.0] * 200 + [26.0] * 150,
            "Flag": [0] * 200 + [1] * 150,
        }
    )


def test_calculate_flux_for_chamber_returns_two_cycles(_passthrough_tqdm) -> None:
    df = _build_synthetic_chamber_df()
    out = calculate_flux_for_chamber(df, "Chamber 1")
    assert len(out) == 2
    assert set(out.columns) >= {
        "Source_Chamber",
        "cycle_id",
        "flux_date",
        "flux_slope",
        "r_squared",
        "mean_temp",
        "qc_flag",
        "n_points",
        "duration_sec",
        "flux_absolute",
    }


def test_calculate_flux_for_chamber_slopes_are_close_to_synthetic(
    _passthrough_tqdm,
) -> None:
    df = _build_synthetic_chamber_df()
    out = calculate_flux_for_chamber(df, "Chamber 1")
    out = out.sort_values("cycle_id").reset_index(drop=True)
    # Cycle 1 slope ~ +0.05; cycle 2 slope ~ -0.10
    assert out.loc[0, "flux_slope"] == pytest.approx(0.05, abs=5e-3)
    assert out.loc[1, "flux_slope"] == pytest.approx(-0.10, abs=5e-3)


def test_calculate_flux_for_chamber_empty_df_returns_empty() -> None:
    out = calculate_flux_for_chamber(pd.DataFrame({"TIMESTAMP": [], "CO2": []}), "Chamber 1")
    assert out.empty


def test_calculate_flux_for_chamber_min_r2_filter_drops_noise(
    _passthrough_tqdm,
) -> None:
    """All-noise series → R² is tiny → with min_r2=0.9 nothing survives."""
    rng = np.random.default_rng(0)
    base = pd.Timestamp("2025-01-15 08:00:00")
    t = pd.date_range(base, periods=200, freq="1s")
    co2 = 400.0 + rng.normal(0, 5.0, 200)
    df = pd.DataFrame({"TIMESTAMP": t, "CO2": co2, "Temp": 25.0, "Flag": 0})
    out = calculate_flux_for_chamber(df, "Chamber 1", min_r2=0.9)
    assert out.empty


# ---------------------------------------------------------------------------
# Parity tests vs. the original flux_chamber/src/flux_analysis.py
# ---------------------------------------------------------------------------


@_PARITY_SKIP
def test_calculate_absolute_flux_parity_pre_cutoff() -> None:
    orig = _load_original()
    rows = [
        _make_row(0.05, 25.0, pd.Timestamp("2025-01-15"), 0.0),
        _make_row(-0.10, 30.0, pd.Timestamp("2025-06-30"), 1.5),
        _make_row(0.0, 20.0, pd.Timestamp("2025-04-01"), np.nan),
    ]
    for r in rows:
        port = calculate_absolute_flux(r)
        ref = orig.calculate_absolute_flux(r)
        if math.isnan(ref):
            assert math.isnan(port)
        else:
            assert port == pytest.approx(ref, abs=1e-12, rel=1e-12)


@_PARITY_SKIP
def test_calculate_absolute_flux_parity_post_cutoff() -> None:
    orig = _load_original()
    rows = [
        _make_row(0.05, 25.0, pd.Timestamp("2025-08-15"), 0.0),
        _make_row(-0.20, 28.0, pd.Timestamp("2025-09-01"), 30.0),
        _make_row(0.10, 22.0, pd.Timestamp("2026-01-01"), 200.0),  # net_vol clamp
    ]
    for r in rows:
        port = calculate_absolute_flux(r)
        ref = orig.calculate_absolute_flux(r)
        assert port == pytest.approx(ref, abs=1e-12, rel=1e-12)


@_PARITY_SKIP
def test_calculate_absolute_flux_parity_missing_flux_date() -> None:
    orig = _load_original()
    row = pd.Series({"flux_slope": 0.05, "mean_temp": 25.0, "tree_volume": 0.0})
    port = calculate_absolute_flux(row)
    ref = orig.calculate_absolute_flux(row)
    assert math.isnan(port) and math.isnan(ref)


@_PARITY_SKIP
def test_calculate_h2o_absolute_flux_parity() -> None:
    orig = _load_original()
    rows = [
        pd.Series(
            {
                "h2o_slope": 0.5,
                "flux_date": pd.Timestamp("2025-01-15"),
                "mean_temp": 25.0,
                "tree_volume": 0.0,
            }
        ),
        pd.Series(
            {
                "h2o_slope": 1.2,
                "flux_date": pd.Timestamp("2025-08-15"),
                "mean_temp": 30.0,
                "tree_volume": 25.0,
            }
        ),
        pd.Series(
            {
                "h2o_slope": np.nan,
                "flux_date": pd.Timestamp("2025-08-15"),
                "mean_temp": 25.0,
                "tree_volume": 0.0,
            }
        ),
    ]
    for r in rows:
        port = calculate_h2o_absolute_flux(r)
        ref = orig.calculate_h2o_absolute_flux(r)
        if pd.isna(ref):
            assert pd.isna(port)
        else:
            assert port == pytest.approx(ref, abs=1e-12, rel=1e-12)


@_PARITY_SKIP
def test_calculate_flux_for_chamber_parity(monkeypatch, _passthrough_tqdm) -> None:
    orig = _load_original()

    # Patch the original module's tqdm too, for the same headless reason.
    def _passthrough(iterable, *_args, **_kwargs):
        return iterable

    monkeypatch.setattr(orig, "tqdm", _passthrough, raising=True)

    df = _build_synthetic_chamber_df()
    port_out = calculate_flux_for_chamber(df.copy(), "Chamber 1")
    ref_out = orig.calculate_flux_for_chamber(df.copy(), "Chamber 1")

    # Compare schemas
    assert list(port_out.columns) == list(ref_out.columns)
    assert len(port_out) == len(ref_out)

    # Compare numeric columns to 1e-12
    numeric_cols = [
        "flux_slope",
        "r_squared",
        "mean_temp",
        "n_points",
        "duration_sec",
        "flux_absolute",
        "qc_flag",
        "cycle_id",
    ]
    for col in numeric_cols:
        if col in port_out.columns:
            pd.testing.assert_series_equal(
                port_out[col].reset_index(drop=True),
                ref_out[col].reset_index(drop=True),
                check_names=False,
                check_exact=False,
                rtol=1e-12,
                atol=1e-12,
            )
    # Compare datetime + categorical
    pd.testing.assert_series_equal(
        port_out["flux_date"].reset_index(drop=True),
        ref_out["flux_date"].reset_index(drop=True),
        check_names=False,
    )
    assert (port_out["Source_Chamber"] == ref_out["Source_Chamber"]).all()
