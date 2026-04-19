"""Characterization tests for ``palmwtc.viz.interactive``.

Behaviour ported verbatim from
``flux_chamber/src/flux_visualization_interactive.py``.

The interactive dashboard depends on ``ipywidgets`` and ``IPython.display``,
both of which are only installed via the ``palmwtc[dashboard]`` extra. When
``ipywidgets`` is not present the module-level import of the public Plotly
helpers must still succeed; only ``interactive_flux_dashboard`` requires the
extra (it imports ipywidgets lazily inside its body).

The test suite is split:

* tests that build Plotly figures (``plot_*_interactive``) run unconditionally —
  Plotly is a core dep.
* tests that exercise ``interactive_flux_dashboard`` are gated with
  ``pytest.importorskip("ipywidgets")`` and assert structural identity (widget
  types, callback wiring), not visual rendering.

Where the original module is reachable on disk we cross-check public function
signatures.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Optional: load the original interactive module for cross-checks
# ---------------------------------------------------------------------------

_ORIGINAL_SRC = Path("/Users/adisapoetro/flux_chamber/src/flux_visualization_interactive.py")


def _load_original_module():
    """Import the upstream ``flux_visualization_interactive`` module.

    Returns ``None`` when the upstream tree is not present on this machine.
    """
    if not _ORIGINAL_SRC.exists():
        return None
    src_root = _ORIGINAL_SRC.parent.parent  # .../flux_chamber/
    sys.path.insert(0, str(src_root))
    try:
        if "src" in sys.modules:
            del sys.modules["src"]
        if "src.flux_visualization_interactive" in sys.modules:
            del sys.modules["src.flux_visualization_interactive"]
        module = importlib.import_module("src.flux_visualization_interactive")
        return module
    except Exception:
        return None


_ORIGINAL = _load_original_module()


# ---------------------------------------------------------------------------
# New module under test
# ---------------------------------------------------------------------------

_HAS_INTERACTIVE = importlib.util.find_spec("palmwtc.viz.interactive") is not None

if _HAS_INTERACTIVE:
    from palmwtc.viz import interactive as new_mod
else:
    new_mod = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_flux_df() -> pd.DataFrame:
    """A small flux-results frame with the columns the interactive plots expect."""
    n = 240
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    rng = np.random.default_rng(42)
    chambers = np.where(np.arange(n) % 2 == 0, "Chamber 1", "Chamber 2")
    flags = rng.integers(0, 3, n)
    return pd.DataFrame(
        {
            "flux_date": dates,
            "flux_absolute": rng.normal(0.0, 5.0, n),
            "flux_slope": rng.normal(0.0, 0.05, n),
            "qc_flag": flags,
            "Source_Chamber": chambers,
            "cycle_id": np.arange(n),
        }
    )


@pytest.fixture
def synthetic_chamber_raw() -> dict:
    """A {chamber_name: raw_df} dict shaped like 030's chamber_raw input."""
    n = 200
    out = {}
    for chamber, base_co2 in (("Chamber 1", 410.0), ("Chamber 2", 405.0)):
        rng = np.random.default_rng(hash(chamber) & 0xFFFF)
        out[chamber] = pd.DataFrame(
            {
                "TIMESTAMP": pd.date_range("2024-01-01", periods=n, freq="5min"),
                "CO2": base_co2 + rng.normal(0.0, 1.0, n),
                "Flag": rng.integers(0, 3, n),
            }
        )
    return out


@pytest.fixture
def gap_filled_df() -> pd.DataFrame:
    n = 100
    dates = pd.date_range("2024-04-01", periods=n, freq="6h")
    chambers = np.where(np.arange(n) % 2 == 0, "Chamber 1", "Chamber 2")
    rng = np.random.default_rng(5)
    return pd.DataFrame(
        {
            "flux_date": dates,
            "flux_filled": rng.normal(0.0, 1.0, n),
            "Source_Chamber": chambers,
        }
    )


# ---------------------------------------------------------------------------
# Module is importable (without ipywidgets)
# ---------------------------------------------------------------------------


def test_module_importable() -> None:
    """The module must import even when ipywidgets is absent."""
    assert _HAS_INTERACTIVE, "palmwtc.viz.interactive must be importable"


PLOTLY_PUBLIC_FUNCS = [
    "plot_flux_timeseries_tiers_interactive",
    "plot_tropical_seasonal_diurnal_interactive",
    "plot_flux_heatmap_interactive",
    "plot_flux_vs_tree_age_interactive",
    "plot_chamber_resizing_validation_interactive",
    "plot_cumulative_flux_with_gaps_interactive",
    "plot_concentration_slope_vs_tree_age_interactive",
    "plot_flux_boxplot_vs_tree_age_interactive",
    "plot_concentration_slope_boxplot_vs_tree_age_interactive",
    "plot_flux_monthly_boxplot_interactive",
]

DASHBOARD_PUBLIC_FUNCS = [
    "interactive_flux_dashboard",
]


@pytest.mark.parametrize("name", PLOTLY_PUBLIC_FUNCS + DASHBOARD_PUBLIC_FUNCS)
def test_public_function_exists(name: str) -> None:
    assert hasattr(new_mod, name), f"{name} missing from palmwtc.viz.interactive"
    assert callable(getattr(new_mod, name))


# ---------------------------------------------------------------------------
# Plotly-only helpers (no ipywidgets needed)
# ---------------------------------------------------------------------------


def test_plot_flux_timeseries_tiers_returns_figure(synthetic_flux_df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_flux_timeseries_tiers_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_flux_timeseries_tiers_empty_returns_none() -> None:
    fig = new_mod.plot_flux_timeseries_tiers_interactive(pd.DataFrame())
    assert fig is None


def test_plot_tropical_seasonal_diurnal_returns_figure(synthetic_flux_df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_tropical_seasonal_diurnal_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_tropical_seasonal_diurnal_empty_returns_none() -> None:
    assert new_mod.plot_tropical_seasonal_diurnal_interactive(pd.DataFrame()) is None


def test_plot_flux_heatmap_returns_figure(synthetic_flux_df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_flux_heatmap_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_flux_heatmap_empty_returns_none() -> None:
    assert new_mod.plot_flux_heatmap_interactive(pd.DataFrame()) is None


def test_plot_flux_vs_tree_age_returns_figure(synthetic_flux_df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_flux_vs_tree_age_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_flux_vs_tree_age_empty_returns_none() -> None:
    assert new_mod.plot_flux_vs_tree_age_interactive(pd.DataFrame()) is None


def test_plot_chamber_resizing_validation_returns_figure(synthetic_flux_df: pd.DataFrame) -> None:
    """Use a resize date inside the synthetic window so we get data back."""
    import plotly.graph_objects as go

    fig = new_mod.plot_chamber_resizing_validation_interactive(
        synthetic_flux_df, resize_date="2024-01-05"
    )
    assert isinstance(fig, go.Figure)


def test_plot_chamber_resizing_validation_empty_returns_none() -> None:
    assert (
        new_mod.plot_chamber_resizing_validation_interactive(
            pd.DataFrame(), resize_date="2024-01-01"
        )
        is None
    )


def test_plot_chamber_resizing_validation_outside_window_returns_none(
    synthetic_flux_df: pd.DataFrame,
) -> None:
    """If the resize-date window does not overlap the data, return None."""
    assert (
        new_mod.plot_chamber_resizing_validation_interactive(
            synthetic_flux_df, resize_date="2030-01-01"
        )
        is None
    )


def test_plot_cumulative_flux_returns_figure(gap_filled_df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_cumulative_flux_with_gaps_interactive(
        flux_df=pd.DataFrame(), gap_filled_df=gap_filled_df
    )
    assert isinstance(fig, go.Figure)


def test_plot_cumulative_flux_no_gap_filled_returns_none() -> None:
    assert (
        new_mod.plot_cumulative_flux_with_gaps_interactive(
            flux_df=pd.DataFrame(), gap_filled_df=None
        )
        is None
    )


def test_plot_concentration_slope_vs_tree_age_returns_figure(
    synthetic_flux_df: pd.DataFrame,
) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_concentration_slope_vs_tree_age_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_concentration_slope_vs_tree_age_empty_returns_none() -> None:
    assert new_mod.plot_concentration_slope_vs_tree_age_interactive(pd.DataFrame()) is None


def test_plot_flux_boxplot_vs_tree_age_returns_figure(synthetic_flux_df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_flux_boxplot_vs_tree_age_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_flux_boxplot_vs_tree_age_empty_returns_none() -> None:
    assert new_mod.plot_flux_boxplot_vs_tree_age_interactive(pd.DataFrame()) is None


def test_plot_concentration_slope_boxplot_vs_tree_age_returns_figure(
    synthetic_flux_df: pd.DataFrame,
) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_concentration_slope_boxplot_vs_tree_age_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_concentration_slope_boxplot_vs_tree_age_empty_returns_none() -> None:
    assert new_mod.plot_concentration_slope_boxplot_vs_tree_age_interactive(pd.DataFrame()) is None


def test_plot_flux_monthly_boxplot_returns_figure(synthetic_flux_df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = new_mod.plot_flux_monthly_boxplot_interactive(synthetic_flux_df)
    assert isinstance(fig, go.Figure)


def test_plot_flux_monthly_boxplot_empty_returns_none() -> None:
    assert new_mod.plot_flux_monthly_boxplot_interactive(pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def test_natural_key_sorts_chamber_names() -> None:
    raw = ["Chamber 10", "Chamber 2", "Chamber 1"]
    assert sorted(raw, key=new_mod._natural_key) == ["Chamber 1", "Chamber 2", "Chamber 10"]


def test_downsample_uniform_keeps_at_most_max_points(synthetic_flux_df: pd.DataFrame) -> None:
    out = new_mod._downsample_uniform(synthetic_flux_df, max_points=50)
    assert len(out) <= 50
    # Empty / None passes through unchanged
    assert new_mod._downsample_uniform(None, 10) is None
    empty = pd.DataFrame()
    assert new_mod._downsample_uniform(empty, 10).empty


def test_extract_relayout_payload_handles_garbage() -> None:
    assert new_mod._extract_relayout_payload(None) == {}
    assert new_mod._extract_relayout_payload({}) == {}
    assert new_mod._extract_relayout_payload({"new": "not-a-dict"}) == {}


def test_extract_relayout_payload_returns_relayout_data() -> None:
    change = {"new": {"_js2py_relayout": {"relayout_data": {"xaxis.range[0]": "2024-01-01"}}}}
    assert new_mod._extract_relayout_payload(change) == {"xaxis.range[0]": "2024-01-01"}


def test_extract_xrange_from_relayout_autorange() -> None:
    out = new_mod._extract_xrange_from_relayout({"xaxis.autorange": True})
    assert out == (None, None, True)


def test_extract_xrange_from_relayout_explicit_range() -> None:
    rd = {"xaxis.range[0]": "2024-01-01", "xaxis.range[1]": "2024-01-31"}
    x0, x1, autorange = new_mod._extract_xrange_from_relayout(rd)
    assert autorange is False
    assert x0 == pd.Timestamp("2024-01-01")
    assert x1 == pd.Timestamp("2024-01-31")


def test_extract_xrange_from_relayout_no_range() -> None:
    assert new_mod._extract_xrange_from_relayout({}) == (None, None, False)


# ---------------------------------------------------------------------------
# interactive_flux_dashboard (requires ipywidgets)
# ---------------------------------------------------------------------------


def test_interactive_flux_dashboard_handles_empty_data_gracefully() -> None:
    """With no chambers, the dashboard should print + return without raising.

    Requires ipywidgets because the original module imports it at the very
    top of the function body (before any data checks).
    """
    pytest.importorskip("ipywidgets")
    pytest.importorskip("IPython")

    # Empty chamber_raw + empty flux frame => no chambers found, function returns
    out = new_mod.interactive_flux_dashboard(pd.DataFrame(), {}, debug=False)
    assert out is None


def test_interactive_flux_dashboard_builds_widgets() -> None:
    """End-to-end: build the dashboard widget tree without rendering."""
    pytest.importorskip("ipywidgets")
    pytest.importorskip("IPython")

    import ipywidgets as widgets

    flux = pd.DataFrame(
        {
            "flux_date": pd.date_range("2024-01-01", periods=20, freq="1h"),
            "flux_absolute": np.linspace(-1, 1, 20),
            "qc_flag": np.zeros(20, dtype=int),
            "Source_Chamber": ["Chamber 1"] * 20,
            "cycle_id": np.arange(20),
        }
    )
    chamber_raw = {
        "Chamber 1": pd.DataFrame(
            {
                "TIMESTAMP": pd.date_range("2024-01-01", periods=50, freq="10min"),
                "CO2": np.linspace(400.0, 410.0, 50),
                "Flag": np.zeros(50, dtype=int),
            }
        )
    }

    # The function calls IPython.display.display, which is a no-op when no
    # frontend is connected; widget construction itself should not raise.
    new_mod.interactive_flux_dashboard(
        flux,
        chamber_raw,
        renderer=None,  # don't override pio renderer
        replace_previous=False,
        debug=False,
        enable_detail=True,
    )

    cached = getattr(new_mod.interactive_flux_dashboard, "_widgets", None)
    assert cached is not None
    ui, output_overview, output_detail = cached
    assert isinstance(ui, widgets.Widget)
    assert isinstance(output_overview, widgets.Output)
    assert isinstance(output_detail, widgets.Output)


# ---------------------------------------------------------------------------
# Cross-check vs original module (when reachable)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_ORIGINAL is None, reason="original flux_visualization_interactive not on disk")
def test_public_signatures_match_original() -> None:
    """All ported public functions must keep their original signatures."""
    import inspect

    for name in PLOTLY_PUBLIC_FUNCS + DASHBOARD_PUBLIC_FUNCS:
        orig = getattr(_ORIGINAL, name, None)
        new = getattr(new_mod, name, None)
        assert orig is not None, f"original missing {name}"
        assert new is not None, f"port missing {name}"
        assert inspect.signature(orig) == inspect.signature(new), f"signature drift in {name}"
