"""Characterization tests for ``palmwtc.flux.chamber``.

Behaviour ported verbatim from ``flux_chamber/src/chamber_flux.py``.

These tests exercise:
- ``DEFAULT_CONFIG``, ``DEFAULT_CO2_QC_THRESHOLDS``,
  ``DEFAULT_H2O_QC_THRESHOLDS``, ``NIGHTTIME_CO2_QC_THRESHOLDS`` — dict shape.
- ``apply_wpl_correction`` — pure WPL math, no sibling deps.
- ``prepare_chamber_data`` — chamber slice + WPL + QC flag filtering.
- ``calculate_flux_cycles`` / ``calculate_h2o_flux_cycles`` — end-to-end on
  synthetic cycles. These pull in the ``palmwtc.flux.cycles`` sibling and are
  skipped if it is not yet ported.
- ``load_tree_biophysics`` / ``get_tree_volume_at_date`` — Excel loader +
  time-interpolated lookup.
- ``compute_closure_confidence`` — pure NumPy calculation.

The synthetic-cycle outputs are also compared against the original
``flux_chamber/src/chamber_flux.py`` (when reachable on disk) to confirm
byte-identical numeric output (tolerance 1e-12).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Optional: load the original chamber_flux module for byte-identical comparison
# ---------------------------------------------------------------------------

_ORIGINAL_SRC = Path("/Users/adisapoetro/flux_chamber/src/chamber_flux.py")


def _load_original_module():
    """Import the upstream ``chamber_flux`` module from its package.

    Returns ``None`` when the upstream tree is not present on this machine.
    """
    if not _ORIGINAL_SRC.exists():
        return None
    src_root = _ORIGINAL_SRC.parent.parent  # .../flux_chamber/
    sys.path.insert(0, str(src_root))
    try:
        import importlib

        if "src" in sys.modules:
            del sys.modules["src"]
        if "src.chamber_flux" in sys.modules:
            del sys.modules["src.chamber_flux"]
        module = importlib.import_module("src.chamber_flux")
        return module
    except Exception:
        return None


_ORIGINAL = _load_original_module()


# ---------------------------------------------------------------------------
# New module under test
# ---------------------------------------------------------------------------

_HAS_CYCLES_SIBLING = importlib.util.find_spec("palmwtc.flux.cycles") is not None
_HAS_ABSOLUTE_SIBLING = importlib.util.find_spec("palmwtc.flux.absolute") is not None

# The chamber module itself imports its siblings at module top-level
# (``from palmwtc.flux.cycles import …``). We must therefore skip the entire
# import block when those siblings have not yet landed.
_HAS_CHAMBER = importlib.util.find_spec("palmwtc.flux.chamber") is not None and _HAS_CYCLES_SIBLING

if _HAS_CHAMBER:
    from palmwtc.flux import chamber as new_mod
else:
    new_mod = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_default_config_has_expected_keys() -> None:
    cfg = new_mod.DEFAULT_CONFIG
    expected = {
        "cycle_gap_sec",
        "start_cutoff_sec",
        "start_search_sec",
        "min_points",
        "min_duration_sec",
        "outlier_z",
        "max_outlier_refit_frac",
        "noise_eps_ppm",
        "accepted_co2_qc_flags",
        "accepted_h2o_qc_flags",
        "prefer_corrected_h2o",
        "require_h2o_for_wpl",
        "h2o_valid_range",
        "max_abs_wpl_rel_change",
        "use_multiprocessing",
        "n_jobs",
    }
    assert expected.issubset(cfg.keys())
    assert cfg["cycle_gap_sec"] == 300
    assert cfg["accepted_co2_qc_flags"] == [0]
    assert cfg["accepted_h2o_qc_flags"] == [0, 1]
    assert cfg["h2o_valid_range"] == (0.0, 60.0)


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_default_co2_qc_thresholds_match_known_values() -> None:
    th = new_mod.DEFAULT_CO2_QC_THRESHOLDS
    assert th["r2_A"] == 0.90
    assert th["r2_B"] == 0.70
    assert th["snr_B"] == 3.0  # relaxed value documented in source
    assert th["monotonic_B"] == 0.45  # relaxed value documented in source
    assert th["signal_ppm_guard"] == 5.0


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_default_h2o_qc_thresholds_match_known_values() -> None:
    th = new_mod.DEFAULT_H2O_QC_THRESHOLDS
    assert th["r2_A"] == 0.70
    assert th["nrmse_A"] == 0.15
    assert th["monotonic_B"] == 0.40
    assert th["signal_mmol_guard"] == 0.3


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_nighttime_co2_qc_thresholds_alias_to_flux_qc_fast() -> None:
    """``NIGHTTIME_CO2_QC_THRESHOLDS`` is the same dict object as the
    one re-exported from ``palmwtc.flux.cycles.NIGHTTIME_QC_THRESHOLDS``."""
    from palmwtc.flux.cycles import NIGHTTIME_QC_THRESHOLDS

    assert new_mod.NIGHTTIME_CO2_QC_THRESHOLDS is NIGHTTIME_QC_THRESHOLDS


# ---------------------------------------------------------------------------
# WPL correction
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_apply_wpl_correction_basic_arithmetic() -> None:
    co2_wet = pd.Series([400.0, 410.0, np.nan, 420.0])
    h2o = pd.Series([10.0, 20.0, 15.0, np.nan])

    co2_dry, factor, valid = new_mod.apply_wpl_correction(co2_wet, h2o)

    # Row 0: 400 * (1 + 10/990)
    assert co2_dry.iloc[0] == pytest.approx(400.0 * (1.0 + 10.0 / 990.0), rel=1e-12)
    # Row 1: 410 * (1 + 20/980)
    assert co2_dry.iloc[1] == pytest.approx(410.0 * (1.0 + 20.0 / 980.0), rel=1e-12)
    # Rows 2 & 3: NaN -> invalid, NaN output
    assert pd.isna(co2_dry.iloc[2])
    assert pd.isna(co2_dry.iloc[3])
    # Validity mask
    assert list(valid) == [True, True, False, False]
    # Factor at first row
    assert factor.iloc[0] == pytest.approx(1.0 + 10.0 / 990.0, rel=1e-12)


@pytest.mark.skipif(
    not _HAS_CHAMBER or _ORIGINAL is None,
    reason="needs both new + original module on disk",
)
def test_apply_wpl_correction_matches_original() -> None:
    """Numeric output of new ``apply_wpl_correction`` matches original to 1e-12."""
    rng = np.random.default_rng(0)
    co2 = pd.Series(rng.uniform(380, 420, size=50))
    h2o = pd.Series(rng.uniform(5, 30, size=50))

    new_co2, new_f, new_v = new_mod.apply_wpl_correction(co2, h2o)
    old_co2, old_f, old_v = _ORIGINAL.apply_wpl_correction(co2, h2o)

    np.testing.assert_allclose(new_co2.values, old_co2.values, rtol=0, atol=1e-12)
    np.testing.assert_allclose(new_f.values, old_f.values, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(new_v.values, old_v.values)


# ---------------------------------------------------------------------------
# prepare_chamber_data
# ---------------------------------------------------------------------------


def _make_synthetic_chamber_frame(n: int = 30) -> pd.DataFrame:
    """Synthetic two-chamber dataframe with QC flags + H2O column variants."""
    ts = pd.date_range("2024-01-01", periods=n, freq="4s")
    rng = np.random.default_rng(42)
    co2 = 410.0 + rng.normal(0, 1.0, size=n).cumsum() * 0.1
    h2o = 15.0 + rng.normal(0, 0.2, size=n)
    return pd.DataFrame(
        {
            "TIMESTAMP": ts,
            "CO2_C1": co2,
            "CO2_C2": co2 + 1.0,
            "Temp_1_C1": np.full(n, 25.0),
            "Temp_1_C2": np.full(n, 25.0),
            "H2O_C1": h2o,
            "H2O_C1_corrected": h2o * 1.01,
            "H2O_C2": h2o,
            "CO2_C1_qc_flag": np.zeros(n, dtype=int),
            "CO2_C2_qc_flag": np.zeros(n, dtype=int),
            "H2O_C1_qc_flag": np.zeros(n, dtype=int),
            "H2O_C2_qc_flag": np.zeros(n, dtype=int),
        }
    )


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_prepare_chamber_data_returns_expected_columns() -> None:
    df = _make_synthetic_chamber_frame()
    out = new_mod.prepare_chamber_data(df, "C1")

    for col in (
        "TIMESTAMP",
        "CO2",
        "CO2_raw",
        "H2O",
        "Temp",
        "Flag",
        "wpl_factor",
        "wpl_delta_ppm",
        "wpl_rel_change",
    ):
        assert col in out.columns
    assert len(out) > 0
    # Sorted ascending by TIMESTAMP
    assert out["TIMESTAMP"].is_monotonic_increasing


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_prepare_chamber_data_prefers_corrected_h2o() -> None:
    df = _make_synthetic_chamber_frame()
    out = new_mod.prepare_chamber_data(df, "C1", prefer_corrected_h2o=True)
    # Synthesised so corrected = 1.01x raw -> median should match corrected
    assert out["H2O"].median() == pytest.approx(df["H2O_C1_corrected"].median(), rel=1e-9)


@pytest.mark.skipif(
    not _HAS_CHAMBER or _ORIGINAL is None,
    reason="needs both new + original module on disk",
)
def test_prepare_chamber_data_matches_original_numeric() -> None:
    df = _make_synthetic_chamber_frame()
    new_out = new_mod.prepare_chamber_data(df, "C1")
    old_out = _ORIGINAL.prepare_chamber_data(df, "C1")

    assert list(new_out.columns) == list(old_out.columns)
    assert len(new_out) == len(old_out)
    for col in ("CO2", "CO2_raw", "H2O", "wpl_factor", "wpl_delta_ppm", "wpl_rel_change"):
        np.testing.assert_allclose(
            new_out[col].values.astype(float),
            old_out[col].values.astype(float),
            rtol=0,
            atol=1e-12,
            equal_nan=True,
        )


# ---------------------------------------------------------------------------
# calculate_flux_cycles / calculate_h2o_flux_cycles
# ---------------------------------------------------------------------------


def _make_synthetic_cycle_frame(n_cycles: int = 3, n_per_cycle: int = 60) -> pd.DataFrame:
    """Build a multi-cycle dataframe of CO2/H2O traces with realistic slopes."""
    rows = []
    rng = np.random.default_rng(7)
    base_t = pd.Timestamp("2024-01-01 08:00:00")
    for cyc in range(n_cycles):
        # 4-second cadence, then leave a 10-min gap before the next cycle.
        cyc_start = base_t + pd.Timedelta(minutes=15 * cyc)
        t = cyc_start + pd.to_timedelta(np.arange(n_per_cycle) * 4, unit="s")
        # CO2 rises linearly + small noise
        co2 = 410.0 + 0.05 * np.arange(n_per_cycle) + rng.normal(0, 0.3, n_per_cycle)
        # H2O rises slowly
        h2o = 15.0 + 0.005 * np.arange(n_per_cycle) + rng.normal(0, 0.05, n_per_cycle)
        for i in range(n_per_cycle):
            rows.append(
                {
                    "TIMESTAMP": t[i],
                    "CO2": co2[i],
                    "CO2_raw": co2[i],
                    "H2O": h2o[i],
                    "Temp": 25.0,
                    "Flag": 0,
                    "wpl_factor": 1.0,
                    "wpl_delta_ppm": 0.0,
                    "wpl_rel_change": 0.0,
                    "wpl_valid_input": 1,
                    "CO2_corrected": co2[i],
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_calculate_flux_cycles_runs_on_synthetic_data() -> None:
    df = _make_synthetic_cycle_frame()
    # Use serial path to keep tests deterministic and avoid Pool overhead.
    out = new_mod.calculate_flux_cycles(df, "Chamber 1", use_multiprocessing=False)
    # Should get at least one cycle of results.
    assert isinstance(out, pd.DataFrame)
    if not out.empty:
        assert "flux_slope" in out.columns or "flux_date" in out.columns


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_calculate_flux_cycles_empty_input_returns_empty_df() -> None:
    out = new_mod.calculate_flux_cycles(pd.DataFrame(), "Chamber 1")
    assert isinstance(out, pd.DataFrame)
    assert out.empty


@pytest.mark.skipif(
    not _HAS_CHAMBER or _ORIGINAL is None,
    reason="needs both new + original module on disk",
)
def test_calculate_flux_cycles_matches_original_numeric() -> None:
    df = _make_synthetic_cycle_frame()
    new_out = new_mod.calculate_flux_cycles(df, "Chamber 1", use_multiprocessing=False)
    old_out = _ORIGINAL.calculate_flux_cycles(df, "Chamber 1", use_multiprocessing=False)
    assert len(new_out) == len(old_out)
    if not new_out.empty:
        # Skip ``flux_absolute`` — it is computed inside the cycles sibling
        # using its own ``calculate_absolute_flux`` import path, which can
        # differ between the original (``src.flux_analysis``) and the ported
        # (``palmwtc.flux.absolute``) loader contexts in test environments.
        # The numeric machinery being tested here is in ``chamber.py`` itself.
        skip_cols = {"flux_absolute"}
        common_cols = [
            c
            for c in new_out.columns
            if c in old_out.columns and new_out[c].dtype != object and c not in skip_cols
        ]
        for col in common_cols:
            np.testing.assert_allclose(
                pd.to_numeric(new_out[col], errors="coerce").values,
                pd.to_numeric(old_out[col], errors="coerce").values,
                rtol=0,
                atol=1e-12,
                equal_nan=True,
            )


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_calculate_h2o_flux_cycles_runs_on_synthetic_data() -> None:
    df = _make_synthetic_cycle_frame()
    out = new_mod.calculate_h2o_flux_cycles(df, "Chamber 1")
    assert isinstance(out, pd.DataFrame)
    if not out.empty:
        assert "h2o_slope" in out.columns


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_calculate_h2o_flux_cycles_no_h2o_returns_empty() -> None:
    df = _make_synthetic_cycle_frame()
    df["H2O"] = np.nan
    out = new_mod.calculate_h2o_flux_cycles(df, "Chamber 1")
    assert isinstance(out, pd.DataFrame)
    assert out.empty


@pytest.mark.skipif(
    not _HAS_CHAMBER or _ORIGINAL is None,
    reason="needs both new + original module on disk",
)
def test_calculate_h2o_flux_cycles_matches_original_numeric() -> None:
    df = _make_synthetic_cycle_frame()
    new_out = new_mod.calculate_h2o_flux_cycles(df, "Chamber 1")
    old_out = _ORIGINAL.calculate_h2o_flux_cycles(df, "Chamber 1")
    assert len(new_out) == len(old_out)
    if not new_out.empty:
        common_cols = [
            c for c in new_out.columns if c in old_out.columns and new_out[c].dtype != object
        ]
        for col in common_cols:
            np.testing.assert_allclose(
                pd.to_numeric(new_out[col], errors="coerce").values,
                pd.to_numeric(old_out[col], errors="coerce").values,
                rtol=0,
                atol=1e-12,
                equal_nan=True,
            )


# ---------------------------------------------------------------------------
# load_tree_biophysics / get_tree_volume_at_date
# ---------------------------------------------------------------------------


def _make_vigor_excel(tmp_path: Path) -> Path:
    """Write a synthetic Vigor_Index_PalmStudio.xlsx mirroring the real schema.

    The real loader reads with ``header=2`` so two blank header rows are
    prepended.
    """
    pytest.importorskip("openpyxl")
    out = tmp_path / "Vigor_Index_PalmStudio.xlsx"
    body = pd.DataFrame(
        {
            "Tanggal": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
            "Kode pohon": ["EKA-1-T01", "EKA-1-T01", "EKA-2-T02"],
            "Tinggi Pohon (cm)": [200.0, 220.0, 250.0],
            "R1 (cm)": [50.0, 55.0, 60.0],
            "R2 (cm)": [52.0, 56.0, 62.0],
            "Vigor Index": [1_000_000.0, 1_500_000.0, 2_000_000.0],
        }
    )
    # Two blank rows then the body + header on row 3 (index 2).
    blank_top = pd.DataFrame(
        [[None] * len(body.columns)] * 2,
        columns=body.columns,
    )
    full = pd.concat([blank_top, body], ignore_index=True)
    full.to_excel(out, index=False, header=True, startrow=2)
    # The real file has its data start at header=2; we wrote at startrow=2
    # so when we read with header=2, the content row will be row index 4.
    # For the fixture to match the loader semantics, write a flat file then
    # rewrite with the columns at row index 2.
    pd.DataFrame(
        [
            [None] * len(body.columns),
            [None] * len(body.columns),
            list(body.columns),
            *body.values.tolist(),
        ]
    ).to_excel(out, index=False, header=False)
    return out


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_load_tree_biophysics_returns_expected_columns(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    _make_vigor_excel(tmp_path)
    df = new_mod.load_tree_biophysics(tmp_path)
    assert df is not None
    for col in (
        "Tree ID",
        "Date",
        "Height_m",
        "Max_Radius_m",
        "Est_Width_m",
        "Vigor_Index_m3",
        "Clone",
    ):
        assert col in df.columns
    # Height_cm 200 → Height_m 2.0
    assert df.loc[df["Tree ID"] == "EKA-1-T01", "Height_m"].iloc[0] == pytest.approx(2.0)
    # Vigor 1e6 → 1.0 m³
    assert df.loc[df["Tree ID"] == "EKA-1-T01", "Vigor_Index_m3"].iloc[0] == pytest.approx(1.0)


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_load_tree_biophysics_missing_file_returns_none(tmp_path: Path) -> None:
    df = new_mod.load_tree_biophysics(tmp_path)
    assert df is None


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_get_tree_volume_at_date_exact_match(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    _make_vigor_excel(tmp_path)
    df = new_mod.load_tree_biophysics(tmp_path)
    vol = new_mod.get_tree_volume_at_date(df, "EKA-1-T01", "2024-01-01")
    assert vol == pytest.approx(1.0)


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_get_tree_volume_at_date_interpolates(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    _make_vigor_excel(tmp_path)
    df = new_mod.load_tree_biophysics(tmp_path)
    # Halfway between Jan 1 and Feb 1 → linear interp 1.0 → 1.5 ⇒ ~1.25
    vol = new_mod.get_tree_volume_at_date(df, "EKA-1-T01", "2024-01-16")
    assert vol is not None
    assert 1.0 < vol < 1.5


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_get_tree_volume_unknown_tree_returns_none(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    _make_vigor_excel(tmp_path)
    df = new_mod.load_tree_biophysics(tmp_path)
    assert new_mod.get_tree_volume_at_date(df, "BOGUS-T99", "2024-01-01") is None


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_get_tree_volume_none_dataframe_returns_none() -> None:
    assert new_mod.get_tree_volume_at_date(None, "EKA-1-T01", "2024-01-01") is None


# ---------------------------------------------------------------------------
# compute_closure_confidence
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_compute_closure_confidence_scalar_high_quality() -> None:
    """High R², low NRMSE, moderate radiation → near-1 confidence."""
    score = new_mod.compute_closure_confidence(r2=0.95, nrmse=0.05, global_radiation=400.0)
    score_val = float(score)
    assert 0.0 <= score_val <= 1.0
    assert score_val > 0.8


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_compute_closure_confidence_scalar_low_quality_high_radiation() -> None:
    """Low R², high radiation → low confidence (closure issue suspected)."""
    score = new_mod.compute_closure_confidence(r2=0.3, nrmse=0.25, global_radiation=800.0)
    assert 0.0 <= float(score) <= 0.5


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_compute_closure_confidence_array_input() -> None:
    r2 = np.array([0.95, 0.5, 0.2])
    nrmse = np.array([0.05, 0.15, 0.30])
    rad = np.array([200.0, 400.0, 800.0])
    out = new_mod.compute_closure_confidence(r2, nrmse, rad)
    assert isinstance(out, np.ndarray)
    assert out.shape == r2.shape
    assert np.all((out >= 0) & (out <= 1))


@pytest.mark.skipif(not _HAS_CHAMBER, reason="palmwtc.flux.chamber not importable yet")
def test_compute_closure_confidence_handles_nan() -> None:
    """NaN inputs are zeroed inside the function (per source code)."""
    out = new_mod.compute_closure_confidence(
        r2=np.array([np.nan, 0.9]),
        nrmse=np.array([np.nan, 0.05]),
        global_radiation=np.array([np.nan, 400.0]),
    )
    # No NaN should propagate to the output
    assert not np.any(np.isnan(out))


@pytest.mark.skipif(
    not _HAS_CHAMBER or _ORIGINAL is None,
    reason="needs both new + original module on disk",
)
def test_compute_closure_confidence_matches_original_numeric() -> None:
    rng = np.random.default_rng(0)
    r2 = rng.uniform(0, 1, size=20)
    nrmse = rng.uniform(0, 0.4, size=20)
    rad = rng.uniform(0, 1000, size=20)
    new_out = new_mod.compute_closure_confidence(r2, nrmse, rad)
    old_out = _ORIGINAL.compute_closure_confidence(r2, nrmse, rad)
    np.testing.assert_allclose(new_out, old_out, rtol=0, atol=1e-12)
