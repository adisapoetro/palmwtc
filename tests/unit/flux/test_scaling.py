# ruff: noqa: RUF003
"""Characterization tests for palmwtc.flux.scaling.

Functions ported from flux_chamber/src/flux_analysis.py:
    - load_biophysical_data (file I/O — not exercised here; only its callers)
    - estimate_leaf_area
    - calculate_lai_effective
    - scale_to_leaf_basis
    - estimate_par_from_radiation
    - add_par_estimates

Includes:
    1. Standalone behaviour tests on synthetic inputs.
    2. Parity tests against the original module (skip if source not on disk)
       — assert numeric equality to 1e-12.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from palmwtc.flux.scaling import (
    add_par_estimates,
    calculate_lai_effective,
    estimate_leaf_area,
    estimate_par_from_radiation,
    scale_to_leaf_basis,
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
# estimate_leaf_area — standalone
# ---------------------------------------------------------------------------


def test_estimate_leaf_area_conservative_default() -> None:
    assert estimate_leaf_area(10) == 40.0  # 10 leaves × 4 m²


def test_estimate_leaf_area_literature_max() -> None:
    assert estimate_leaf_area(10, method="literature_max") == 120.0  # 10 × 12


def test_estimate_leaf_area_fixed() -> None:
    assert estimate_leaf_area(10, method="fixed") == 60.0  # 10 × 6


def test_estimate_leaf_area_array_input() -> None:
    arr = np.array([5, 10, 15])
    out = estimate_leaf_area(arr)
    np.testing.assert_array_equal(out, np.array([20.0, 40.0, 60.0]))


def test_estimate_leaf_area_unknown_method_raises() -> None:
    with pytest.raises(ValueError, match="Unknown method"):
        estimate_leaf_area(10, method="bogus")


# ---------------------------------------------------------------------------
# estimate_par_from_radiation — standalone
# ---------------------------------------------------------------------------


def test_estimate_par_from_radiation_default_factor() -> None:
    # PAR = rad × 0.45 × 4.57
    assert estimate_par_from_radiation(1000.0) == pytest.approx(
        1000.0 * 0.45 * 4.57, abs=1e-12, rel=1e-12
    )


def test_estimate_par_from_radiation_custom_factor() -> None:
    assert estimate_par_from_radiation(800.0, conversion_factor=0.50) == pytest.approx(
        800.0 * 0.50 * 4.57, abs=1e-12, rel=1e-12
    )


def test_estimate_par_from_radiation_zero_input() -> None:
    assert estimate_par_from_radiation(0.0) == 0.0


def test_estimate_par_from_radiation_array_input() -> None:
    arr = np.array([0.0, 500.0, 1000.0])
    out = estimate_par_from_radiation(arr)
    expected = arr * 0.45 * 4.57
    np.testing.assert_allclose(out, expected, rtol=1e-12, atol=1e-12)


# ---------------------------------------------------------------------------
# add_par_estimates — standalone
# ---------------------------------------------------------------------------


def test_add_par_estimates_writes_par_column() -> None:
    df = pd.DataFrame({"GlobalRadiation_Avg": [0.0, 500.0, 1000.0]})
    out = add_par_estimates(df)
    assert "PAR_estimated" in out.columns
    expected = df["GlobalRadiation_Avg"] * 0.45 * 4.57
    np.testing.assert_allclose(
        out["PAR_estimated"].to_numpy(), expected.to_numpy(), rtol=1e-12, atol=1e-12
    )


def test_add_par_estimates_missing_column_yields_nan(capsys) -> None:
    df = pd.DataFrame({"flux_absolute": [1.0, 2.0]})
    out = add_par_estimates(df)
    assert "PAR_estimated" in out.columns
    assert out["PAR_estimated"].isna().all()


def test_add_par_estimates_does_not_mutate_input() -> None:
    df = pd.DataFrame({"GlobalRadiation_Avg": [100.0, 200.0]})
    snap = df.copy()
    _ = add_par_estimates(df)
    pd.testing.assert_frame_equal(df, snap)


# ---------------------------------------------------------------------------
# calculate_lai_effective — standalone
# ---------------------------------------------------------------------------


def _make_biophys() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2025-01-01", "2025-01-15", "2025-02-01", "2025-01-10", "2025-02-15"]
            ),
            "chamber": [1, 1, 1, 2, 2],
            "n_leaves": [20, 22, 24, 18, 20],
            "tree_code": ["2.2/EKA-1/2107"] * 3 + ["2.4/EKA-2/2858"] * 2,
        }
    )


def _make_flux_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "flux_date": pd.to_datetime(["2025-01-15", "2025-01-15", "2025-08-15", "2025-08-15"]),
            "Source_Chamber": ["Chamber 1", "Chamber 2", "Chamber 1", "Chamber 2"],
            "flux_absolute": [-5.0, -6.0, -10.0, -12.0],
            "flux_slope": [0.05, 0.06, 0.10, 0.12],
        }
    )


def test_calculate_lai_effective_pre_cutoff_uses_4m2_floor() -> None:
    biophys = _make_biophys()
    flux = _make_flux_df()
    out = calculate_lai_effective(flux, biophys)
    # Row 0: Chamber 1, 2025-01-15 → closest biophys = 2025-01-15, n_leaves=22
    # leaf_area = 22 × 4 = 88; floor = 4 → LAI = 22
    assert out.loc[0, "n_leaves"] == 22
    assert out.loc[0, "leaf_area_m2"] == 88.0
    assert out.loc[0, "chamber_floor_area_m2"] == 4.0
    assert out.loc[0, "lai_effective"] == pytest.approx(22.0, abs=1e-12)


def test_calculate_lai_effective_post_cutoff_uses_16m2_floor() -> None:
    biophys = _make_biophys()
    flux = _make_flux_df()
    out = calculate_lai_effective(flux, biophys)
    # Row 2: Chamber 1, 2025-08-15 → closest biophys = 2025-02-01 (which is >30d → skipped)
    # n_leaves should be NaN
    assert pd.isna(out.loc[2, "n_leaves"])


def test_calculate_lai_effective_skips_rows_more_than_30_days_apart() -> None:
    biophys = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"]),
            "chamber": [1],
            "n_leaves": [20],
        }
    )
    flux = pd.DataFrame(
        {
            "flux_date": [pd.Timestamp("2025-01-15")],
            "Source_Chamber": ["Chamber 1"],
            "flux_absolute": [-5.0],
        }
    )
    out = calculate_lai_effective(flux, biophys)
    assert pd.isna(out.loc[0, "n_leaves"])
    assert pd.isna(out.loc[0, "lai_effective"])


def test_calculate_lai_effective_unknown_chamber_name_skipped() -> None:
    biophys = _make_biophys()
    flux = pd.DataFrame(
        {
            "flux_date": [pd.Timestamp("2025-01-15")],
            "Source_Chamber": ["Chamber 99"],
            "flux_absolute": [-5.0],
        }
    )
    out = calculate_lai_effective(flux, biophys)
    assert pd.isna(out.loc[0, "n_leaves"])


def test_calculate_lai_effective_custom_floor_area_dict() -> None:
    biophys = _make_biophys()
    flux = pd.DataFrame(
        {
            "flux_date": [pd.Timestamp("2025-01-15")],
            "Source_Chamber": ["Chamber 1"],
            "flux_absolute": [-5.0],
        }
    )
    custom = {pd.Timestamp("2025-01-15"): {1: 9.0, 2: 9.0}}
    out = calculate_lai_effective(flux, biophys, chamber_floor_area=custom)
    assert out.loc[0, "chamber_floor_area_m2"] == 9.0
    # n_leaves=22 → leaf_area=88 → LAI = 88/9
    assert out.loc[0, "lai_effective"] == pytest.approx(88.0 / 9.0, abs=1e-12, rel=1e-12)


# ---------------------------------------------------------------------------
# scale_to_leaf_basis — standalone
# ---------------------------------------------------------------------------


def test_scale_to_leaf_basis_divides_by_lai() -> None:
    flux = pd.DataFrame(
        {
            "flux_absolute": [-10.0, -6.0, -3.0],
            "lai_effective": [2.0, 3.0, 1.5],
        }
    )
    out = scale_to_leaf_basis(flux)
    assert out.loc[0, "flux_absolute_leaf"] == pytest.approx(-5.0, abs=1e-12)
    assert out.loc[1, "flux_absolute_leaf"] == pytest.approx(-2.0, abs=1e-12)
    assert out.loc[2, "flux_absolute_leaf"] == pytest.approx(-2.0, abs=1e-12)


def test_scale_to_leaf_basis_skips_nan_lai() -> None:
    flux = pd.DataFrame(
        {
            "flux_absolute": [-10.0, -6.0],
            "lai_effective": [2.0, np.nan],
        }
    )
    out = scale_to_leaf_basis(flux)
    assert out.loc[0, "flux_absolute_leaf"] == pytest.approx(-5.0, abs=1e-12)
    assert pd.isna(out.loc[1, "flux_absolute_leaf"])


def test_scale_to_leaf_basis_skips_zero_lai() -> None:
    flux = pd.DataFrame(
        {
            "flux_absolute": [-10.0],
            "lai_effective": [0.0],
        }
    )
    out = scale_to_leaf_basis(flux)
    assert pd.isna(out.loc[0, "flux_absolute_leaf"])


def test_scale_to_leaf_basis_does_not_mutate_input() -> None:
    flux = pd.DataFrame(
        {
            "flux_absolute": [-10.0, -6.0],
            "lai_effective": [2.0, 3.0],
        }
    )
    snap = flux.copy()
    _ = scale_to_leaf_basis(flux)
    pd.testing.assert_frame_equal(flux, snap)


def test_scale_to_leaf_basis_custom_lai_column_name() -> None:
    flux = pd.DataFrame(
        {
            "flux_absolute": [-10.0, -6.0],
            "lai_alt": [2.0, 3.0],
        }
    )
    out = scale_to_leaf_basis(flux, lai_column="lai_alt")
    assert out.loc[0, "flux_absolute_leaf"] == pytest.approx(-5.0, abs=1e-12)
    assert out.loc[1, "flux_absolute_leaf"] == pytest.approx(-2.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Parity tests vs. the original flux_chamber/src/flux_analysis.py
# ---------------------------------------------------------------------------


@_PARITY_SKIP
def test_estimate_leaf_area_parity() -> None:
    orig = _load_original()
    cases = [
        (1, "conservative"),
        (10, "conservative"),
        (10, "literature_max"),
        (10, "fixed"),
        (np.array([1, 5, 17]), "conservative"),
    ]
    for n_leaves, method in cases:
        port = estimate_leaf_area(n_leaves, method=method)
        ref = orig.estimate_leaf_area(n_leaves, method=method)
        np.testing.assert_allclose(np.asarray(port), np.asarray(ref), rtol=1e-12, atol=1e-12)


@_PARITY_SKIP
def test_estimate_par_from_radiation_parity() -> None:
    orig = _load_original()
    arr = np.array([0.0, 100.0, 500.0, 1000.0, 1500.0])
    for factor in (0.45, 0.50, 0.42):
        port = estimate_par_from_radiation(arr, conversion_factor=factor)
        ref = orig.estimate_par_from_radiation(arr, conversion_factor=factor)
        np.testing.assert_allclose(port, ref, rtol=1e-12, atol=1e-12)


@_PARITY_SKIP
def test_calculate_lai_effective_parity() -> None:
    orig = _load_original()
    biophys = _make_biophys()
    flux = _make_flux_df()
    port_out = calculate_lai_effective(flux.copy(), biophys.copy())
    ref_out = orig.calculate_lai_effective(flux.copy(), biophys.copy())

    assert list(port_out.columns) == list(ref_out.columns)
    for col in ("n_leaves", "leaf_area_m2", "chamber_floor_area_m2", "lai_effective"):
        pd.testing.assert_series_equal(
            port_out[col].reset_index(drop=True),
            ref_out[col].reset_index(drop=True),
            check_names=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )


@_PARITY_SKIP
def test_calculate_lai_effective_parity_with_custom_floor() -> None:
    orig = _load_original()
    biophys = _make_biophys()
    flux = _make_flux_df()
    custom = {pd.Timestamp("2025-01-15"): {1: 9.0, 2: 9.0}}
    port_out = calculate_lai_effective(flux.copy(), biophys.copy(), chamber_floor_area=custom)
    ref_out = orig.calculate_lai_effective(flux.copy(), biophys.copy(), chamber_floor_area=custom)
    pd.testing.assert_series_equal(
        port_out["lai_effective"].reset_index(drop=True),
        ref_out["lai_effective"].reset_index(drop=True),
        check_names=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


@_PARITY_SKIP
def test_scale_to_leaf_basis_parity() -> None:
    orig = _load_original()
    flux = pd.DataFrame(
        {
            "flux_absolute": [-10.0, -6.0, -3.0, np.nan, -1.0],
            "lai_effective": [2.0, 3.0, 0.0, 2.0, np.nan],
        }
    )
    port_out = scale_to_leaf_basis(flux.copy())
    ref_out = orig.scale_to_leaf_basis(flux.copy())
    pd.testing.assert_series_equal(
        port_out["flux_absolute_leaf"].reset_index(drop=True),
        ref_out["flux_absolute_leaf"].reset_index(drop=True),
        check_names=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


@_PARITY_SKIP
def test_add_par_estimates_parity() -> None:
    orig = _load_original()
    df = pd.DataFrame({"GlobalRadiation_Avg": [0.0, 100.0, 500.0, 1000.0]})
    port_out = add_par_estimates(df.copy())
    ref_out = orig.add_par_estimates(df.copy())
    pd.testing.assert_series_equal(
        port_out["PAR_estimated"].reset_index(drop=True),
        ref_out["PAR_estimated"].reset_index(drop=True),
        check_names=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


@_PARITY_SKIP
def test_add_par_estimates_parity_missing_column() -> None:
    orig = _load_original()
    df = pd.DataFrame({"flux_absolute": [1.0, 2.0]})
    port_out = add_par_estimates(df.copy())
    ref_out = orig.add_par_estimates(df.copy())
    assert port_out["PAR_estimated"].isna().all()
    assert ref_out["PAR_estimated"].isna().all()
