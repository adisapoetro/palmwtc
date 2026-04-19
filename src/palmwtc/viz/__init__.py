"""palmwtc.viz — static + interactive visualisation helpers.

Phase 2 splits ``flux_chamber/src/flux_visualization.py`` into
``style.py``, ``diagnostics.py``, ``timeseries.py``;
``flux_visualization_interactive.py`` lands as ``interactive.py`` (gated
behind ``palmwtc[dashboard]`` extra at call time);
``qc_visualizations.py`` lands as ``qc_plots.py``.

This umbrella re-exports the public plotting API used by notebooks
010, 020, 030, 031, 032, 033, 035, 070, 080. Helpers that are only
used inside the interactive Plotly dashboard remain reachable via
``palmwtc.viz.interactive.*`` and are NOT re-exported here to keep the
top-level namespace focused.
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
