"""palmwtc.qc — quality control: rules, breakpoints, drift, ML, processor, reporting.

Phase 2 port from ``flux_chamber/src/qc_functions.py`` (1452 lines), split
across five sub-modules (plus the previously ported reporting module):

- ``rules.py``       — physical bounds, IQR, RoC, persistence, battery,
                        sensor exclusion, the procedural ``process_variable_qc``
                        orchestrator, and ``add_cycle_id``
- ``breakpoints.py`` — ``detect_breakpoints_ruptures`` plus baseline-drift /
                        cross-variable consistency checks
- ``drift.py``       — ``detect_drift_windstats`` + ``apply_drift_correction``
- ``ml.py``          — placeholder; re-exports ``get_isolation_forest`` from
                        ``palmwtc.hardware.gpu`` for the ML-anchored import path
- ``processor.py``   — the user-preferred OOP wrapper ``QCProcessor``
- ``reporting.py``   — Parquet/CSV export + Jinja2 field-alert HTML report
                        (ported earlier from ``flux_chamber/src/qc_reporting.py``)

The public functions are re-exported here so callers can write
``from palmwtc.qc import apply_physical_bounds_flags`` without knowing the
sub-module layout — this is the backward-compat contract that lets the
ported notebooks (020, 022, 025, 026) stay intact.
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
