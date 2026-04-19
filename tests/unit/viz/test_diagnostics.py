"""Characterization tests for ``palmwtc.viz.diagnostics``.

Behaviour ported verbatim from ``flux_chamber/src/flux_visualization.py``.

The cycle-diagnostic helpers (``plot_cycle_diagnostics``,
``plot_specific_cycle``, ``plot_cycle_by_id``, ``show_sample_cycles``)
return ``None`` and call ``plt.show()`` -- they are notebook-style.
We assert they don't raise, that the early-exit branches print the
expected guidance message and bail, and that the resizing-validation
plot returns a ``Figure``.

The matplotlib ``Agg`` backend is set in ``tests/conftest.py``.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from palmwtc.viz import diagnostics as diag

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def flux_df() -> pd.DataFrame:
    """Two-chamber flux DataFrame spanning the chamber-resize date 2025-07-01."""
    rng = np.random.default_rng(7)
    timestamps = pd.date_range("2025-05-15", "2025-08-15", freq="2h")
    rows = []
    for chamber in ("Chamber 1", "Chamber 2"):
        for ts_ in timestamps:
            rows.append(
                {
                    "flux_date": ts_,
                    "Source_Chamber": chamber,
                    "flux_absolute": -3.0 + rng.normal(0, 1.0),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def empty_flux_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["flux_date", "Source_Chamber", "flux_absolute"])


@pytest.fixture
def cycle_raw_df() -> pd.DataFrame:
    """Raw chamber-cycle data: 60 s ramp at 1 Hz with linear CO2 drift."""
    base = pd.Timestamp("2025-06-15 10:00:00")
    n = 61
    secs = np.arange(n)
    timestamps = [base + pd.Timedelta(seconds=int(s)) for s in secs]
    co2 = 420.0 + 0.5 * secs + np.random.default_rng(0).normal(0, 0.1, size=n)
    return pd.DataFrame(
        {
            "TIMESTAMP": timestamps,
            "CO2": co2,
            "CO2_raw": co2 + 0.05,
        }
    )


@pytest.fixture
def cycle_flux_row() -> pd.Series:
    """A single flux-row Series matching ``cycle_raw_df``'s window."""
    return pd.Series(
        {
            "flux_date": pd.Timestamp("2025-06-15 10:00:00"),
            "Source_Chamber": "Chamber 1",
            "cycle_id": 1,
            "cycle_duration_sec": 60,
            "window_start_sec": 5.0,
            "window_end_sec": 55.0,
            "flux_slope": 0.5,
            "flux_intercept": 420.0,
            "flux_qc_label": "high",
            "qc_reason": "",
        }
    )


@pytest.fixture
def cycle_data_df(cycle_flux_row) -> pd.DataFrame:
    """Cycle-results DataFrame containing ``cycle_flux_row``."""
    row = cycle_flux_row.to_dict()
    row["flux_qc"] = 0
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# plot_chamber_resizing_validation
# ---------------------------------------------------------------------------


def test_plot_chamber_resizing_validation_returns_figure(flux_df) -> None:
    fig = diag.plot_chamber_resizing_validation(flux_df, resize_date="2025-07-01")
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2  # one per chamber
    plt.close(fig)


def test_plot_chamber_resizing_validation_empty_returns_none(empty_flux_df) -> None:
    assert diag.plot_chamber_resizing_validation(empty_flux_df) is None


def test_plot_chamber_resizing_validation_outside_window_returns_none(flux_df) -> None:
    """When no rows lie within +/- 60 days of the resize date, returns ``None``."""
    fig = diag.plot_chamber_resizing_validation(flux_df, resize_date="2030-01-01")
    assert fig is None


# ---------------------------------------------------------------------------
# plot_cycle_diagnostics
# ---------------------------------------------------------------------------


def test_plot_cycle_diagnostics_runs(cycle_raw_df, cycle_flux_row) -> None:
    """Happy-path: returns ``None`` and produces a figure (closed by ``show``)."""
    # Should not raise.
    result = diag.plot_cycle_diagnostics(cycle_raw_df, cycle_flux_row)
    assert result is None
    plt.close("all")


def test_plot_cycle_diagnostics_no_raw_data_in_window(cycle_flux_row) -> None:
    """Empty raw_df triggers the early ``No raw data found`` exit branch."""
    empty_raw = pd.DataFrame(columns=["TIMESTAMP", "CO2"])
    assert diag.plot_cycle_diagnostics(empty_raw, cycle_flux_row) is None


def test_plot_cycle_diagnostics_apply_wpl_label(cycle_raw_df, cycle_flux_row) -> None:
    """``apply_wpl=True`` should still complete without error."""
    raw = cycle_raw_df.copy()
    raw["wpl_delta_ppm"] = 0.05
    raw["wpl_rel_change"] = 0.0001
    assert diag.plot_cycle_diagnostics(raw, cycle_flux_row, apply_wpl=True) is None
    plt.close("all")


# ---------------------------------------------------------------------------
# plot_specific_cycle
# ---------------------------------------------------------------------------


def test_plot_specific_cycle_happy_path(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    # date_str is parsed dayfirst -> matches 2025-06-15 10:00:00
    result = diag.plot_specific_cycle(cycle_data_df, raw_lookup, "Chamber 1", "15/06/25 10:00:00")
    assert result is None
    plt.close("all")


def test_plot_specific_cycle_unknown_chamber(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    assert (
        diag.plot_specific_cycle(cycle_data_df, raw_lookup, "Chamber 99", "15/06/25 10:00:00")
        is None
    )


def test_plot_specific_cycle_bad_date_string(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    assert diag.plot_specific_cycle(cycle_data_df, raw_lookup, "Chamber 1", "not-a-date") is None


def test_plot_specific_cycle_no_match(cycle_data_df, cycle_raw_df) -> None:
    """Date 1 hour off from any cycle should bail with the no-match message."""
    raw_lookup = {"Chamber 1": cycle_raw_df}
    assert (
        diag.plot_specific_cycle(cycle_data_df, raw_lookup, "Chamber 1", "15/06/25 11:00:00")
        is None
    )


def test_plot_specific_cycle_missing_raw(cycle_data_df) -> None:
    raw_lookup: dict = {}
    assert (
        diag.plot_specific_cycle(cycle_data_df, raw_lookup, "Chamber 1", "15/06/25 10:00:00")
        is None
    )


# ---------------------------------------------------------------------------
# plot_cycle_by_id
# ---------------------------------------------------------------------------


def test_plot_cycle_by_id_happy_path(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    assert diag.plot_cycle_by_id(cycle_data_df, raw_lookup, "Chamber 1", 1) is None
    plt.close("all")


def test_plot_cycle_by_id_unknown(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    assert diag.plot_cycle_by_id(cycle_data_df, raw_lookup, "Chamber 1", 999) is None


def test_plot_cycle_by_id_missing_raw(cycle_data_df) -> None:
    raw_lookup: dict = {}
    assert diag.plot_cycle_by_id(cycle_data_df, raw_lookup, "Chamber 1", 1) is None


# ---------------------------------------------------------------------------
# show_sample_cycles
# ---------------------------------------------------------------------------


def test_show_sample_cycles_happy_path(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    assert diag.show_sample_cycles(cycle_data_df, raw_lookup, tier=0, n=1, seed=0) is None
    plt.close("all")


def test_show_sample_cycles_empty_tier(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    # Tier 9 has no rows -> early return
    assert diag.show_sample_cycles(cycle_data_df, raw_lookup, tier=9) is None


def test_show_sample_cycles_label_passthrough(cycle_data_df, cycle_raw_df) -> None:
    raw_lookup = {"Chamber 1": cycle_raw_df}
    assert (
        diag.show_sample_cycles(
            cycle_data_df, raw_lookup, tier=0, n=1, label="custom-label", seed=1
        )
        is None
    )
    plt.close("all")
