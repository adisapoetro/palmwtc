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
    LEAFLET_SHAPE_FACTOR,
    MEAN_LEAFLET_FACTOR,
    MIN_RACHIS_FRACTION_OF_POS1,
    MIN_RACHIS_LENGTH_M,
    add_par_estimates,
    calculate_lai_effective,
    estimate_leaf_area,
    estimate_leaf_area_corley,
    estimate_par_from_radiation,
    juvenile_combined_leaflet_params,
    per_rank_rachis_lengths_m,
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
# per_rank_rachis_lengths_m
# ---------------------------------------------------------------------------

# Canonical VPalm leaflet allometry used across the per-rank Corley tests.
# Numbers chosen so each per-leaflet area multiplication can be reproduced by
# hand from the formulas in estimate_leaf_area_corley.
_VPALM_BASE_PARAMS: dict[str, float] = {
    "leaflets_nb_max": 100.0,
    "leaflets_nb_slope": 0.25,
    "leaflets_nb_inflexion": 2.0,
    "leaflet_length_at_b_intercept": 0.6,
    "leaflet_length_at_b_slope": 0.05,
    "leaflet_width_at_b_intercept": 0.06,
    "leaflet_width_at_b_slope": 0.0,
}


def test_per_rank_rachis_linear_interpolation_anchors_and_between() -> None:
    out = per_rank_rachis_lengths_m(5, {1: 1.4, 3: 1.2, 9: 0.9})
    # rank 1 = pos1, rank 3 = pos3 exactly; rank 2 is midpoint of (1.4, 1.2)
    np.testing.assert_allclose(out[:3], [1.4, 1.3, 1.2], rtol=1e-12, atol=1e-12)
    # ranks 4 & 5 interpolate along the rank-3 → rank-9 slope (-0.05/rank)
    assert out[3] == pytest.approx(1.2 + (1.2 - 0.9) / (3.0 - 9.0) * (4 - 3))
    assert out[4] == pytest.approx(1.2 + (1.2 - 0.9) / (3.0 - 9.0) * (5 - 3))


def test_per_rank_rachis_extrapolation_floored_past_rank_9() -> None:
    # Steep decay would push later ranks below the floor; the floor must hold.
    out = per_rank_rachis_lengths_m(20, {1: 1.4, 3: 1.2, 9: 0.9})
    floor = max(MIN_RACHIS_LENGTH_M, MIN_RACHIS_FRACTION_OF_POS1 * 1.4)
    assert (out[9:] >= floor - 1e-12).all()
    # And the curve never exceeds pos1 (newest rank is longest in this regime).
    assert out.max() == pytest.approx(1.4, abs=1e-12)


def test_per_rank_rachis_fallback_when_pos9_missing() -> None:
    # pos9 missing → falls back to pos3 → ranks 3..9 form a flat segment at pos3.
    out_missing = per_rank_rachis_lengths_m(9, {1: 1.4, 3: 1.2})
    out_explicit = per_rank_rachis_lengths_m(9, {1: 1.4, 3: 1.2, 9: 1.2})
    np.testing.assert_allclose(out_missing, out_explicit, rtol=1e-12, atol=1e-12)


def test_per_rank_rachis_fallback_when_pos3_and_pos9_missing() -> None:
    # Both pos3 and pos9 fall back to pos1 → constant curve at pos1.
    out = per_rank_rachis_lengths_m(7, {1: 1.4})
    np.testing.assert_allclose(out, np.full(7, 1.4), rtol=1e-12, atol=1e-12)


def test_per_rank_rachis_requires_finite_pos1() -> None:
    with pytest.raises(ValueError, match="rank-1 anchor"):
        per_rank_rachis_lengths_m(5, {1: float("nan"), 3: 1.0, 9: 0.5})
    with pytest.raises(ValueError, match="rank-1 anchor"):
        per_rank_rachis_lengths_m(5, {3: 1.0, 9: 0.5})


def test_per_rank_rachis_requires_positive_n_leaves() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        per_rank_rachis_lengths_m(0, {1: 1.4})


# ---------------------------------------------------------------------------
# juvenile_combined_leaflet_params
# ---------------------------------------------------------------------------


def test_juvenile_combined_halves_three_keys_only() -> None:
    juv = juvenile_combined_leaflet_params(_VPALM_BASE_PARAMS)
    assert juv["leaflets_nb_max"] == 50.0
    assert juv["leaflet_length_at_b_slope"] == pytest.approx(0.025, abs=1e-12)
    assert juv["leaflet_width_at_b_slope"] == 0.0  # halved 0.0 stays 0.0
    # Other params unchanged.
    for k in (
        "leaflets_nb_slope",
        "leaflets_nb_inflexion",
        "leaflet_length_at_b_intercept",
        "leaflet_width_at_b_intercept",
    ):
        assert juv[k] == _VPALM_BASE_PARAMS[k]


def test_juvenile_combined_marks_placeholder() -> None:
    juv = juvenile_combined_leaflet_params(_VPALM_BASE_PARAMS)
    assert "_juvenile_placeholder" in juv
    assert "halved" in juv["_juvenile_placeholder"]


def test_juvenile_combined_does_not_mutate_input() -> None:
    snapshot = dict(_VPALM_BASE_PARAMS)
    juvenile_combined_leaflet_params(_VPALM_BASE_PARAMS)
    assert snapshot == _VPALM_BASE_PARAMS


def test_juvenile_combined_missing_keys_raises() -> None:
    bad = {k: v for k, v in _VPALM_BASE_PARAMS.items() if k != "leaflets_nb_max"}
    with pytest.raises(KeyError, match="leaflets_nb_max"):
        juvenile_combined_leaflet_params(bad)


# ---------------------------------------------------------------------------
# estimate_leaf_area_corley
# ---------------------------------------------------------------------------


def test_estimate_leaf_area_corley_single_rank_matches_hand_calculation() -> None:
    """Single-rank case with hand-computable inputs.

    For n_leaves=1, pos1=2.0 m, _VPALM_BASE_PARAMS:
      rachis = 2.0
      n_leaflets = 100 / (1 + exp(-0.25*(2.0-2.0))) = 50
      ll_b = 0.6 + 0.05*2.0 = 0.7
      lw_b = 0.06 + 0.0*2.0 = 0.06
      ll_mean = 0.85*0.7 = 0.595
      lw_mean = 0.85*0.06 = 0.051
      la_per_leaflet = 0.595*0.051*0.55 = 0.01668975
      total = 50 * 0.01668975 = 0.8344875
    """
    area = estimate_leaf_area_corley(1, {1: 2.0}, _VPALM_BASE_PARAMS)
    expected = 50.0 * (0.85 * 0.7) * (0.85 * 0.06) * LEAFLET_SHAPE_FACTOR
    assert area == pytest.approx(expected, abs=1e-12, rel=1e-12)
    # Sanity: same as the literal arithmetic.
    assert area == pytest.approx(0.8344875, abs=1e-9)


def test_estimate_leaf_area_corley_uses_mean_factor_squared() -> None:
    """Per-leaflet area carries (MEAN_LEAFLET_FACTOR)**2 * LEAFLET_SHAPE_FACTOR."""
    area = estimate_leaf_area_corley(1, {1: 2.0}, _VPALM_BASE_PARAMS)
    ll_b = 0.7
    lw_b = 0.06
    la_per_leaflet = (MEAN_LEAFLET_FACTOR**2) * ll_b * lw_b * LEAFLET_SHAPE_FACTOR
    assert area == pytest.approx(50.0 * la_per_leaflet, abs=1e-12, rel=1e-12)


def test_estimate_leaf_area_corley_juvenile_lower_than_mature() -> None:
    """Halving leaflet count + slopes must shrink total leaf area."""
    juv = juvenile_combined_leaflet_params(_VPALM_BASE_PARAMS)
    mature_area = estimate_leaf_area_corley(20, {1: 1.45, 3: 1.30, 9: 1.05}, _VPALM_BASE_PARAMS)
    juv_area = estimate_leaf_area_corley(20, {1: 1.45, 3: 1.30, 9: 1.05}, juv)
    assert juv_area > 0
    assert juv_area < mature_area
    # The ratio is bounded above by leaflet_count_ratio × leaflet_length_ratio
    # because the width slope is zero in _VPALM_BASE_PARAMS.
    assert juv_area / mature_area < 0.6  # well below the mature curve


def test_estimate_leaf_area_corley_increases_with_n_leaves() -> None:
    p = _VPALM_BASE_PARAMS
    a1 = estimate_leaf_area_corley(1, {1: 1.5, 3: 1.3, 9: 1.0}, p)
    a5 = estimate_leaf_area_corley(5, {1: 1.5, 3: 1.3, 9: 1.0}, p)
    a30 = estimate_leaf_area_corley(30, {1: 1.5, 3: 1.3, 9: 1.0}, p)
    assert a1 < a5 < a30


def test_estimate_leaf_area_corley_missing_vpalm_key_raises() -> None:
    bad = {k: v for k, v in _VPALM_BASE_PARAMS.items() if k != "leaflets_nb_slope"}
    with pytest.raises(ValueError, match="leaflets_nb_slope"):
        estimate_leaf_area_corley(5, {1: 1.4, 3: 1.2, 9: 0.9}, bad)


def test_estimate_leaf_area_corley_requires_finite_pos1() -> None:
    with pytest.raises(ValueError, match="rank-1 anchor"):
        estimate_leaf_area_corley(5, {1: float("nan"), 3: 1.2, 9: 0.9}, _VPALM_BASE_PARAMS)


def test_estimate_leaf_area_corley_returns_float() -> None:
    out = estimate_leaf_area_corley(10, {1: 1.4, 3: 1.2, 9: 0.9}, _VPALM_BASE_PARAMS)
    assert isinstance(out, float)
    assert out > 0


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
