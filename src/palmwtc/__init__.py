"""palmwtc — Automated whole-tree chamber workflow for oil-palm ecophysiology.

Top-level convenience re-exports of the most-used symbols. Subpackages
(``palmwtc.io``, ``palmwtc.qc``, ``palmwtc.flux``, ``palmwtc.windows``,
``palmwtc.validation``, ``palmwtc.viz``, ``palmwtc.hardware``) are
importable directly and own the full per-area public API.

Symbols whose names collide across subpackages (e.g. ``DEFAULT_CONFIG``,
which differs in shape between ``flux``, ``windows``, and ``validation``)
are NOT re-exported here — import them from the subpackage to avoid
ambiguity.
"""

from importlib.metadata import PackageNotFoundError, version

# Flux
from palmwtc.flux import (
    calculate_absolute_flux,
    calculate_flux_cycles,
    calculate_h2o_absolute_flux,
    calculate_h2o_flux_cycles,
    compute_closure_confidence,
    compute_day_scores,
    identify_cycles,
    prepare_chamber_data,
    score_cycle,
    score_day_quality,
)

# I/O
from palmwtc.io import (
    find_latest_qc_file,
    get_cloud_sensor_dirs,
    get_usecols,
    load_from_multiple_dirs,
    load_monthly_data,
    load_radiation_data,
)

# QC
from palmwtc.qc import (
    QCProcessor,
    apply_iqr_flags,
    apply_physical_bounds_flags,
    combine_qc_flags,
    detect_breakpoints_ruptures,
    detect_drift_windstats,
    process_variable_qc,
    render_field_alert_html,
)

# Validation
from palmwtc.validation import derive_is_daytime, run_science_validation

# Visualisation
from palmwtc.viz import (
    interactive_flux_dashboard,
    plot_flux_heatmap,
    plot_tropical_seasonal_diurnal,
    set_style,
)

# Windows
from palmwtc.windows import WindowSelector, merge_sensor_qc_onto_cycles

try:
    __version__ = version("palmwtc")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

__all__ = [
    "QCProcessor",
    "WindowSelector",
    "__version__",
    "apply_iqr_flags",
    "apply_physical_bounds_flags",
    "calculate_absolute_flux",
    "calculate_flux_cycles",
    "calculate_h2o_absolute_flux",
    "calculate_h2o_flux_cycles",
    "combine_qc_flags",
    "compute_closure_confidence",
    "compute_day_scores",
    "derive_is_daytime",
    "detect_breakpoints_ruptures",
    "detect_drift_windstats",
    "find_latest_qc_file",
    "get_cloud_sensor_dirs",
    "get_usecols",
    "identify_cycles",
    "interactive_flux_dashboard",
    "load_from_multiple_dirs",
    "load_monthly_data",
    "load_radiation_data",
    "merge_sensor_qc_onto_cycles",
    "plot_flux_heatmap",
    "plot_tropical_seasonal_diurnal",
    "prepare_chamber_data",
    "process_variable_qc",
    "render_field_alert_html",
    "run_science_validation",
    "score_cycle",
    "score_day_quality",
    "set_style",
]
