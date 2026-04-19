"""Characterization tests for ``palmwtc.viz.timeseries``.

Behaviour ported verbatim from ``flux_chamber/src/flux_visualization.py``.

These are smoke tests: build minimal synthetic flux DataFrames, call each
timeseries / aggregate plot, and verify it returns a matplotlib ``Figure``
(or ``None`` for the empty-input early-exit branch) without raising.

The matplotlib ``Agg`` backend is set in ``tests/conftest.py``.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from palmwtc.viz import timeseries as ts

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def flux_df() -> pd.DataFrame:
    """Two-chamber synthetic flux DataFrame spanning ~6 weeks at 1-hour step.

    Columns mirror the schema used by the source viz module: ``flux_date``,
    ``Source_Chamber``, ``flux_absolute``, ``flux_slope``, ``qc_flag``.
    """
    rng = np.random.default_rng(42)
    timestamps = pd.date_range("2024-06-01", "2024-07-15", freq="1h")
    rows = []
    for chamber in ("Chamber 1", "Chamber 2"):
        for ts_ in timestamps:
            hour = ts_.hour
            base = -8.0 if 7 <= hour <= 18 else 4.0
            rows.append(
                {
                    "flux_date": ts_,
                    "Source_Chamber": chamber,
                    "flux_absolute": base + rng.normal(0, 1.5),
                    "flux_slope": (base / 100.0) + rng.normal(0, 0.01),
                    "qc_flag": int(rng.integers(0, 3)),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def empty_flux_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "flux_date",
            "Source_Chamber",
            "flux_absolute",
            "flux_slope",
            "qc_flag",
        ]
    )


@pytest.fixture
def gap_filled_df() -> pd.DataFrame:
    """DataFrame indexed by datetime with ``flux_filled`` + ``Source_Chamber``."""
    idx = pd.date_range("2024-06-01", "2024-07-15", freq="1h")
    parts = []
    for chamber in ("Chamber 1", "Chamber 2"):
        df = pd.DataFrame(
            {
                "flux_filled": np.linspace(-2.0, -1.0, len(idx)),
                "Source_Chamber": chamber,
            },
            index=idx,
        )
        parts.append(df)
    return pd.concat(parts)


# ---------------------------------------------------------------------------
# Tests for inventoried public functions
# ---------------------------------------------------------------------------


def test_plot_tropical_seasonal_diurnal_returns_figure(flux_df) -> None:
    fig = ts.plot_tropical_seasonal_diurnal(flux_df)
    assert isinstance(fig, Figure)
    plt.close(fig)


def test_plot_tropical_seasonal_diurnal_empty_returns_none(empty_flux_df) -> None:
    assert ts.plot_tropical_seasonal_diurnal(empty_flux_df) is None


def test_plot_flux_heatmap_returns_figure(flux_df) -> None:
    fig = ts.plot_flux_heatmap(flux_df)
    assert isinstance(fig, Figure)
    # Source spec: 3 stacked subplots (Overall + Chamber 1 + Chamber 2)
    assert len(fig.axes) >= 3
    plt.close(fig)


def test_plot_flux_heatmap_empty_returns_none(empty_flux_df) -> None:
    assert ts.plot_flux_heatmap(empty_flux_df) is None


def test_plot_flux_vs_tree_age_returns_figure(flux_df) -> None:
    fig = ts.plot_flux_vs_tree_age(flux_df)
    assert isinstance(fig, Figure)
    # 2 chambers => 2 stacked axes
    assert len(fig.axes) == 2
    plt.close(fig)


def test_plot_flux_vs_tree_age_empty_returns_none(empty_flux_df) -> None:
    assert ts.plot_flux_vs_tree_age(empty_flux_df) is None


def test_plot_concentration_slope_vs_tree_age_returns_figure(flux_df) -> None:
    fig = ts.plot_concentration_slope_vs_tree_age(flux_df)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2
    plt.close(fig)


def test_plot_concentration_slope_vs_tree_age_empty_returns_none(empty_flux_df) -> None:
    assert ts.plot_concentration_slope_vs_tree_age(empty_flux_df) is None


# ---------------------------------------------------------------------------
# Tests for the additional helpers retained for parity
# ---------------------------------------------------------------------------


def test_plot_flux_timeseries_tiers_returns_figure(flux_df) -> None:
    fig = ts.plot_flux_timeseries_tiers(flux_df)
    assert isinstance(fig, Figure)
    # 3 tiers x 2 chambers = 6 axes
    assert len(fig.axes) == 6
    plt.close(fig)


def test_plot_cumulative_flux_with_gaps_returns_figure(gap_filled_df) -> None:
    fig = ts.plot_cumulative_flux_with_gaps(
        flux_df=None,
        gap_filled_df=gap_filled_df,
        birth_date_str="2024-02-01",
    )
    assert isinstance(fig, Figure)
    plt.close(fig)


def test_plot_cumulative_flux_by_date_returns_figure(gap_filled_df) -> None:
    fig = ts.plot_cumulative_flux_by_date(gap_filled_df)
    assert isinstance(fig, Figure)
    plt.close(fig)


def test_plot_flux_boxplot_vs_tree_age_returns_figure(flux_df) -> None:
    fig = ts.plot_flux_boxplot_vs_tree_age(flux_df)
    assert isinstance(fig, Figure)
    plt.close(fig)


def test_plot_concentration_slope_boxplot_vs_tree_age_returns_figure(flux_df) -> None:
    fig = ts.plot_concentration_slope_boxplot_vs_tree_age(flux_df)
    assert isinstance(fig, Figure)
    plt.close(fig)


def test_plot_flux_monthly_boxplot_returns_figure(flux_df) -> None:
    fig = ts.plot_flux_monthly_boxplot(flux_df)
    assert isinstance(fig, Figure)
    plt.close(fig)
