"""Visualization helpers — static (matplotlib) and interactive (plotly).

Five families:

- :mod:`~palmwtc.viz.style` — rcParams defaults for consistent look.
- :mod:`~palmwtc.viz.timeseries` — seasonal / diurnal / tree-age patterns, flux heatmaps.
- :mod:`~palmwtc.viz.diagnostics` — per-cycle inspection plots.
- :mod:`~palmwtc.viz.qc_plots` — QC flag visualisations.
- :mod:`~palmwtc.viz.interactive` — Plotly-based interactive dashboards (use inside Jupyter only).

All static helpers (``style``, ``diagnostics``, ``timeseries``, ``qc_plots``) work
on a core install.  Interactive helpers require ``palmwtc[interactive]`` for
ipywidgets / anywidget; bare imports succeed without the extra, but calling
the dashboard raises an informative error at runtime.
"""

from palmwtc.viz.diagnostics import (
    plot_chamber_resizing_validation,
    plot_cycle_by_id,
    plot_cycle_diagnostics,
    plot_specific_cycle,
    show_sample_cycles,
)
from palmwtc.viz.interactive import interactive_flux_dashboard
from palmwtc.viz.qc_plots import (
    filter_plot,
    plot_breakpoints_analysis,
    plot_drift_and_hq_timeseries,
    plot_qc_comparison,
    plot_qc_summary_heatmap,
    plot_soil_var,
    visualize_breakpoints,
    visualize_missing_data,
    visualize_qc_flags,
)
from palmwtc.viz.style import set_style
from palmwtc.viz.timeseries import (
    plot_concentration_slope_vs_tree_age,
    plot_flux_heatmap,
    plot_flux_vs_tree_age,
    plot_tropical_seasonal_diurnal,
)

__all__ = [
    "filter_plot",
    "interactive_flux_dashboard",
    "plot_breakpoints_analysis",
    "plot_chamber_resizing_validation",
    "plot_concentration_slope_vs_tree_age",
    "plot_cycle_by_id",
    "plot_cycle_diagnostics",
    "plot_drift_and_hq_timeseries",
    "plot_flux_heatmap",
    "plot_flux_vs_tree_age",
    "plot_qc_comparison",
    "plot_qc_summary_heatmap",
    "plot_soil_var",
    "plot_specific_cycle",
    "plot_tropical_seasonal_diurnal",
    "set_style",
    "show_sample_cycles",
    "visualize_breakpoints",
    "visualize_missing_data",
    "visualize_qc_flags",
]
