"""Characterization tests for ``palmwtc.viz.qc_plots``.

Behaviour ported verbatim from ``flux_chamber/src/qc_visualizations.py``.

These are smoke tests: they build minimal synthetic inputs, call each public
function, and verify it returns the documented type (matplotlib ``Figure``,
None, or a tuple) without raising. Where the original function compared
against the upstream source, we assert structural identity (same number of
axes, same flag-counts annotated, etc.).

The matplotlib ``Agg`` backend is set in ``tests/conftest.py``, so plotting
calls are headless.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

# ---------------------------------------------------------------------------
# Optional: load the original qc_visualizations module for cross-checks
# ---------------------------------------------------------------------------

_ORIGINAL_SRC = Path("/Users/adisapoetro/flux_chamber/src/qc_visualizations.py")


def _load_original_module():
    """Import the upstream ``qc_visualizations`` module.

    Returns ``None`` when the upstream tree is not present on this machine.
    """
    if not _ORIGINAL_SRC.exists():
        return None
    src_root = _ORIGINAL_SRC.parent.parent  # .../flux_chamber/
    sys.path.insert(0, str(src_root))
    try:
        if "src" in sys.modules:
            del sys.modules["src"]
        if "src.qc_visualizations" in sys.modules:
            del sys.modules["src.qc_visualizations"]
        module = importlib.import_module("src.qc_visualizations")
        return module
    except Exception:
        return None


_ORIGINAL = _load_original_module()


# ---------------------------------------------------------------------------
# New module under test
# ---------------------------------------------------------------------------

_HAS_QC_PLOTS = importlib.util.find_spec("palmwtc.viz.qc_plots") is not None

if _HAS_QC_PLOTS:
    from palmwtc.viz import qc_plots as new_mod
else:
    new_mod = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    """A 200-row time series for variable ``co2`` with a QC flag column."""
    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    rng = np.random.default_rng(42)
    values = 400.0 + rng.normal(0, 5, n)
    # Inject a couple of obvious bad points
    values[50] = 1000.0
    values[150] = -50.0

    flags = np.zeros(n, dtype=int)
    flags[50] = 2  # bad
    flags[150] = 2
    flags[10:15] = 1  # suspect run

    df = pd.DataFrame({"co2": values, "co2_qc_flag": flags}, index=idx)
    df["TIMESTAMP"] = idx
    return df


@pytest.fixture
def synthetic_qc_results() -> dict:
    """A qc_results-style dict for one variable mirroring ``process_variable_qc``."""
    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")

    bounds = pd.Series(np.zeros(n, dtype=int), index=idx)
    bounds.iloc[50] = 2
    bounds.iloc[150] = 2

    iqr = pd.Series(np.zeros(n, dtype=int), index=idx)
    iqr.iloc[10:15] = 1

    final_flags = pd.Series(np.zeros(n, dtype=int), index=idx)
    final_flags.iloc[50] = 2
    final_flags.iloc[150] = 2
    final_flags.iloc[10:15] = 1

    summary = {
        "flag_0_count": int((final_flags == 0).sum()),
        "flag_1_count": int((final_flags == 1).sum()),
        "flag_2_count": int((final_flags == 2).sum()),
        "flag_0_percent": float((final_flags == 0).mean() * 100),
        "flag_1_percent": float((final_flags == 1).mean() * 100),
        "flag_2_percent": float((final_flags == 2).mean() * 100),
    }

    return {
        "bounds_flags": bounds,
        "iqr_flags": iqr,
        "persistence_flags": None,
        "roc_flags": None,
        "final_flags": final_flags,
        "summary": summary,
    }


@pytest.fixture
def multi_var_qc_results(synthetic_qc_results: dict) -> dict:
    """qc_results dict spanning multiple variables for comparison/heatmap tests."""
    return {
        "co2": synthetic_qc_results,
        "h2o": synthetic_qc_results,
        "temp": synthetic_qc_results,
    }


@pytest.fixture
def var_config() -> dict:
    return {
        "co2": {
            "hard": (200.0, 800.0),
            "soft": (350.0, 500.0),
            "label": "CO2 (ppm)",
            "title": "Chamber CO2",
        },
        "soil_moisture": {
            "hard": (0.0, 0.6),
            "soft": (0.05, 0.5),
            "label": "Soil moisture (m3/m3)",
            "pattern": "SM",
        },
    }


@pytest.fixture
def chamber_two_chamber_df() -> pd.DataFrame:
    n = 100
    idx = pd.date_range("2024-01-01", periods=n, freq="5min")
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "TIMESTAMP": idx,
            "CO2_C1": 400.0 + rng.normal(0, 5, n),
            "CO2_C2": 410.0 + rng.normal(0, 5, n),
        }
    )


@pytest.fixture
def soil_df() -> pd.DataFrame:
    n = 100
    idx = pd.date_range("2024-01-01", periods=n, freq="30min")
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"TIMESTAMP": idx})
    for depth in ["15", "48", "80", "200", "350"]:
        df[f"SM_{depth}_Avg_Soil"] = 0.3 + rng.normal(0, 0.02, n)
    return df


# ---------------------------------------------------------------------------
# Module is importable
# ---------------------------------------------------------------------------


def test_module_importable() -> None:
    assert _HAS_QC_PLOTS, "palmwtc.viz.qc_plots must be importable"


PUBLIC_FUNCS = [
    "visualize_qc_flags",
    "plot_qc_comparison",
    "plot_qc_summary_heatmap",
    "visualize_missing_data",
    "visualize_breakpoints",
    "filter_plot",
    "plot_soil_var",
    "plot_drift_and_hq_timeseries",
    "plot_breakpoints_analysis",
]


@pytest.mark.parametrize("name", PUBLIC_FUNCS)
def test_public_function_exists(name: str) -> None:
    assert hasattr(new_mod, name), f"{name} missing from palmwtc.viz.qc_plots"
    assert callable(getattr(new_mod, name))


# ---------------------------------------------------------------------------
# visualize_qc_flags
# ---------------------------------------------------------------------------


def test_visualize_qc_flags_returns_figure(
    synthetic_df: pd.DataFrame, synthetic_qc_results: dict, var_config: dict
) -> None:
    fig = new_mod.visualize_qc_flags(
        synthetic_df, "co2", synthetic_qc_results, config=var_config["co2"]
    )
    assert isinstance(fig, Figure)
    # Should have multiple axes: main + active method panels + 2 summary axes
    assert len(fig.axes) >= 3
    plt.close(fig)


def test_visualize_qc_flags_missing_var_returns_none(
    synthetic_df: pd.DataFrame, synthetic_qc_results: dict
) -> None:
    fig = new_mod.visualize_qc_flags(synthetic_df, "nonexistent_variable", synthetic_qc_results)
    assert fig is None


# ---------------------------------------------------------------------------
# plot_qc_comparison
# ---------------------------------------------------------------------------


def test_plot_qc_comparison_returns_figure(multi_var_qc_results: dict) -> None:
    fig = new_mod.plot_qc_comparison(
        df=None, var_names=list(multi_var_qc_results.keys()), qc_results=multi_var_qc_results
    )
    assert isinstance(fig, Figure)
    # 2x2 grid expected
    assert len(fig.axes) == 4
    plt.close(fig)


def test_plot_qc_comparison_handles_flat_summary_dict(
    multi_var_qc_results: dict,
) -> None:
    """V2 ``qc_results`` can be a flat summary dict (no nested ``summary`` key)."""
    flat = {var: res["summary"] for var, res in multi_var_qc_results.items()}
    fig = new_mod.plot_qc_comparison(df=None, var_names=list(flat.keys()), qc_results=flat)
    assert isinstance(fig, Figure)
    plt.close(fig)


# ---------------------------------------------------------------------------
# plot_qc_summary_heatmap
# ---------------------------------------------------------------------------


def test_plot_qc_summary_heatmap_returns_figure(multi_var_qc_results: dict) -> None:
    fig = new_mod.plot_qc_summary_heatmap(multi_var_qc_results)
    assert isinstance(fig, Figure)
    # Single heatmap axis + 1 colorbar axis
    assert len(fig.axes) >= 1
    plt.close(fig)


# ---------------------------------------------------------------------------
# visualize_missing_data
# ---------------------------------------------------------------------------


def test_visualize_missing_data_returns_figure(synthetic_df: pd.DataFrame) -> None:
    fig = new_mod.visualize_missing_data(synthetic_df, "co2", frequency_seconds=60.0)
    assert isinstance(fig, Figure)
    # Two stacked axes
    assert len(fig.axes) == 2
    plt.close(fig)


def test_visualize_missing_data_missing_var_returns_none(
    synthetic_df: pd.DataFrame,
) -> None:
    fig = new_mod.visualize_missing_data(
        synthetic_df, "nonexistent_variable", frequency_seconds=60.0
    )
    assert fig is None


def test_visualize_missing_data_resolves_freq_from_config() -> None:
    n = 100
    idx = pd.date_range("2024-01-01", periods=n, freq="2min")
    df = pd.DataFrame({"co2": np.linspace(400.0, 410.0, n)}, index=idx)

    config = {"co2": {"measurement_frequency": 120.0}}
    fig = new_mod.visualize_missing_data(df, "co2", config=config)
    assert isinstance(fig, Figure)
    plt.close(fig)


# ---------------------------------------------------------------------------
# filter_plot
# ---------------------------------------------------------------------------


def test_filter_plot_draws_on_axes(chamber_two_chamber_df: pd.DataFrame, var_config: dict) -> None:
    fig, ax = plt.subplots()
    new_mod.filter_plot(
        ax,
        chamber_two_chamber_df,
        col_c1="CO2_C1",
        col_c2="CO2_C2",
        var_key="co2",
        var_config=var_config,
    )
    # Two chamber lines + 4 threshold lines
    assert len(ax.lines) >= 2
    assert ax.get_ylabel() == "CO2 (ppm)"
    plt.close(fig)


def test_filter_plot_unknown_var_key_skips_gracefully(
    chamber_two_chamber_df: pd.DataFrame, var_config: dict
) -> None:
    fig, ax = plt.subplots()
    new_mod.filter_plot(
        ax,
        chamber_two_chamber_df,
        col_c1="CO2_C1",
        col_c2="CO2_C2",
        var_key="not_in_config",
        var_config=var_config,
    )
    # The function returns early after setting the title
    assert ax.get_title() == "not_in_config"
    plt.close(fig)


# ---------------------------------------------------------------------------
# plot_soil_var
# ---------------------------------------------------------------------------


def test_plot_soil_var_returns_true_when_data_present(
    soil_df: pd.DataFrame, var_config: dict
) -> None:
    fig, ax = plt.subplots()
    has_data = new_mod.plot_soil_var(ax, "soil_moisture", "Soil Moisture", soil_df, var_config)
    assert has_data is True
    # Five depth lines + 4 threshold lines expected
    assert len(ax.lines) >= 5
    plt.close(fig)


def test_plot_soil_var_returns_false_when_var_key_missing(
    soil_df: pd.DataFrame, var_config: dict
) -> None:
    fig, ax = plt.subplots()
    has_data = new_mod.plot_soil_var(ax, "missing_key", "Missing", soil_df, var_config)
    assert has_data is False
    plt.close(fig)


# ---------------------------------------------------------------------------
# plot_drift_and_hq_timeseries
# ---------------------------------------------------------------------------


def test_plot_drift_and_hq_timeseries_runs(synthetic_df: pd.DataFrame) -> None:
    drift_scores = pd.DataFrame({0: np.linspace(0, 1, len(synthetic_df))}, index=synthetic_df.index)
    drift_result = {"scores": drift_scores}
    # Function calls plt.show() and returns None — just verify it runs cleanly.
    result = new_mod.plot_drift_and_hq_timeseries(
        synthetic_df, "co2", drift_result, qc_flag_col="co2_qc_flag"
    )
    assert result is None
    plt.close("all")


def test_plot_drift_and_hq_timeseries_none_input_returns_early(
    synthetic_df: pd.DataFrame,
) -> None:
    result = new_mod.plot_drift_and_hq_timeseries(synthetic_df, "co2", None)
    assert result is None


# ---------------------------------------------------------------------------
# plot_breakpoints_analysis
# ---------------------------------------------------------------------------


def test_plot_breakpoints_analysis_returns_two_figures(
    synthetic_df: pd.DataFrame,
) -> None:
    bp_result = {
        "breakpoints": [synthetic_df.index[60], synthetic_df.index[120]],
        "confidence_scores": [0.85, 0.45],
        "n_breakpoints": 2,
        "segment_info": [
            {
                "start": synthetic_df.index[0],
                "end": synthetic_df.index[60],
                "mean": 400.0,
                "std": 5.0,
            },
            {
                "start": synthetic_df.index[60],
                "end": synthetic_df.index[120],
                "mean": 405.0,
                "std": 6.0,
            },
            {
                "start": synthetic_df.index[120],
                "end": synthetic_df.index[-1],
                "mean": 410.0,
                "std": 4.0,
            },
        ],
    }

    out = new_mod.plot_breakpoints_analysis(
        synthetic_df, "co2", bp_result, qc_flag_col="co2_qc_flag"
    )
    assert isinstance(out, tuple)
    assert len(out) == 2
    fig_analysis, fig_table = out
    assert isinstance(fig_analysis, Figure)
    assert isinstance(fig_table, Figure)
    plt.close(fig_analysis)
    plt.close(fig_table)


def test_plot_breakpoints_analysis_none_input_returns_pair_of_nones(
    synthetic_df: pd.DataFrame,
) -> None:
    out = new_mod.plot_breakpoints_analysis(synthetic_df, "co2", None)
    assert out == (None, None)


# ---------------------------------------------------------------------------
# visualize_breakpoints
# ---------------------------------------------------------------------------


def test_visualize_breakpoints_runs(synthetic_df: pd.DataFrame) -> None:
    bp_result = {
        "breakpoints": [synthetic_df.index[60], synthetic_df.index[120]],
        "confidence_scores": [0.85, 0.45],
        "n_breakpoints": 2,
        "segment_info": [
            {"start": synthetic_df.index[0], "end": synthetic_df.index[60], "mean": 400.0},
            {"start": synthetic_df.index[60], "end": synthetic_df.index[120], "mean": 405.0},
            {"start": synthetic_df.index[120], "end": synthetic_df.index[-1], "mean": 410.0},
        ],
    }
    # Returns None and calls plt.show().
    result = new_mod.visualize_breakpoints(
        synthetic_df,
        "co2",
        bp_result,
        filtered_bps=[synthetic_df.index[60]],
    )
    assert result is None
    plt.close("all")


def test_visualize_breakpoints_zero_bp_returns_early(
    synthetic_df: pd.DataFrame,
) -> None:
    result = new_mod.visualize_breakpoints(
        synthetic_df, "co2", {"n_breakpoints": 0, "breakpoints": []}
    )
    assert result is None


# ---------------------------------------------------------------------------
# Cross-check vs original module (when reachable)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_ORIGINAL is None, reason="original qc_visualizations not on disk")
def test_public_signatures_match_original() -> None:
    """All ported public functions must keep their original signatures."""
    import inspect

    for name in PUBLIC_FUNCS:
        orig = getattr(_ORIGINAL, name, None)
        new = getattr(new_mod, name, None)
        assert orig is not None, f"original missing {name}"
        assert new is not None, f"port missing {name}"
        assert inspect.signature(orig) == inspect.signature(new), f"signature drift in {name}"


@pytest.mark.skipif(_ORIGINAL is None, reason="original qc_visualizations not on disk")
def test_visualize_qc_flags_axes_count_matches_original(
    synthetic_df: pd.DataFrame, synthetic_qc_results: dict, var_config: dict
) -> None:
    fig_orig = _ORIGINAL.visualize_qc_flags(
        synthetic_df, "co2", synthetic_qc_results, config=var_config["co2"]
    )
    fig_new = new_mod.visualize_qc_flags(
        synthetic_df, "co2", synthetic_qc_results, config=var_config["co2"]
    )
    assert len(fig_orig.axes) == len(fig_new.axes)
    plt.close(fig_orig)
    plt.close(fig_new)


@pytest.mark.skipif(_ORIGINAL is None, reason="original qc_visualizations not on disk")
def test_plot_qc_comparison_axes_count_matches_original(
    multi_var_qc_results: dict,
) -> None:
    var_names = list(multi_var_qc_results.keys())
    fig_orig = _ORIGINAL.plot_qc_comparison(None, var_names, multi_var_qc_results)
    fig_new = new_mod.plot_qc_comparison(None, var_names, multi_var_qc_results)
    assert len(fig_orig.axes) == len(fig_new.axes)
    plt.close(fig_orig)
    plt.close(fig_new)


@pytest.mark.skipif(_ORIGINAL is None, reason="original qc_visualizations not on disk")
def test_plot_qc_summary_heatmap_axes_count_matches_original(
    multi_var_qc_results: dict,
) -> None:
    fig_orig = _ORIGINAL.plot_qc_summary_heatmap(multi_var_qc_results)
    fig_new = new_mod.plot_qc_summary_heatmap(multi_var_qc_results)
    assert len(fig_orig.axes) == len(fig_new.axes)
    plt.close(fig_orig)
    plt.close(fig_new)
