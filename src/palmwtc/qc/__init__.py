"""Quality control for whole-tree chamber sensor streams.

Rule-based flagging (physical bounds, IQR, rate of change, persistence,
battery proxy, sensor exclusions) lives in :mod:`~palmwtc.qc.rules`.
Breakpoint and drift detection are in :mod:`~palmwtc.qc.breakpoints`
and :mod:`~palmwtc.qc.drift` respectively. ML-assisted outlier
detection (Isolation Forest, optional GPU acceleration) lives in
:mod:`~palmwtc.qc.ml`. A stateful orchestrator,
:class:`~palmwtc.qc.QCProcessor`, is in :mod:`~palmwtc.qc.processor`.
HTML field-alert reporting is in :mod:`~palmwtc.qc.reporting`.

Tuned for:

- CO2 and H2O concentration from a LI-COR LI-850 gas analyser inside a
  whole-tree chamber enclosing an individual oil palm.
- Soil water content and temperature at 5, 15, 30, 60, and 80 cm depths.
- Ambient climate (air temperature, humidity, rainfall, shortwave
  radiation) from a co-located weather station.

All public symbols from the sub-modules are re-exported here so callers
can write ``from palmwtc.qc import apply_physical_bounds_flags`` without
knowing the sub-module layout. See :attr:`__all__` for the full list.
"""

from palmwtc.qc.breakpoints import (
    check_baseline_drift,
    check_cross_variable_consistency,
    detect_breakpoints_ruptures,
    filter_major_breakpoints,
)
from palmwtc.qc.drift import apply_drift_correction, detect_drift_windstats
from palmwtc.qc.ml import DEVICE, get_isolation_forest
from palmwtc.qc.processor import QCProcessor
from palmwtc.qc.reporting import (
    build_field_alert_context,
    export_qc_data,
    generate_qc_summary_from_results,
    render_field_alert_html,
)
from palmwtc.qc.rules import (
    add_cycle_id,
    apply_battery_proxy_flags,
    apply_iqr_flags,
    apply_persistence_flags,
    apply_physical_bounds_flags,
    apply_rate_of_change_flags,
    apply_sensor_exclusion_flags,
    combine_qc_flags,
    generate_exclusion_recommendations,
    generate_qc_summary,
    get_variable_config,
    process_variable_qc,
)

__all__ = [
    "DEVICE",
    "QCProcessor",
    "add_cycle_id",
    "apply_battery_proxy_flags",
    "apply_drift_correction",
    "apply_iqr_flags",
    "apply_persistence_flags",
    "apply_physical_bounds_flags",
    "apply_rate_of_change_flags",
    "apply_sensor_exclusion_flags",
    "build_field_alert_context",
    "check_baseline_drift",
    "check_cross_variable_consistency",
    "combine_qc_flags",
    "detect_breakpoints_ruptures",
    "detect_drift_windstats",
    "export_qc_data",
    "filter_major_breakpoints",
    "generate_exclusion_recommendations",
    "generate_qc_summary",
    "generate_qc_summary_from_results",
    "get_isolation_forest",
    "get_variable_config",
    "process_variable_qc",
    "render_field_alert_html",
]
