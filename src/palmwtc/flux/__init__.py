"""palmwtc.flux — flux calculation: absolute, cycles, chamber-aware, scaling.

Phase 2 ports from ``flux_chamber/src/{chamber_flux,flux_analysis,flux_qc_fast}.py``,
split by responsibility:

- ``absolute.py`` — ``calculate_absolute_flux``, ``calculate_h2o_absolute_flux`` primitives
- ``scaling.py`` — LAI / leaf-basis helpers (``estimate_leaf_area``, ``scale_to_leaf_basis``, ...)
- ``cycles.py`` — cycle identification + scoring (``identify_cycles``, ``score_cycle``, ...)
- ``chamber.py`` — chamber-aware flux orchestration (``prepare_chamber_data``, ``calculate_flux_cycles``, ...)
"""

from palmwtc.flux.absolute import (
    calculate_absolute_flux,
    calculate_flux_for_chamber,
    calculate_h2o_absolute_flux,
)
from palmwtc.flux.chamber import (
    DEFAULT_CO2_QC_THRESHOLDS,
    DEFAULT_CONFIG,
    DEFAULT_H2O_QC_THRESHOLDS,
    DEFAULT_WPL_QC_THRESHOLDS,
    NIGHTTIME_CO2_QC_THRESHOLDS,
    NIGHTTIME_H2O_QC_THRESHOLDS,
    apply_wpl_correction,
    apply_wpl_qc_overrides,
    build_cycle_wpl_metrics,
    calculate_flux_cycles,
    calculate_h2o_flux_cycles,
    calculate_h2o_flux_for_cycle,
    compute_closure_confidence,
    get_tree_volume_at_date,
    load_tree_biophysics,
    prepare_chamber_data,
    score_h2o_flux_qc,
    summarize_wpl_correction,
)
from palmwtc.flux.cycles import (
    NIGHTTIME_QC_THRESHOLDS,
    _evaluate_cycle_wrapper,
    compute_day_scores,
    compute_ml_anomaly_flags,
    compute_temporal_coherence,
    detect_bimodal_cycle,
    identify_cycles,
    score_cycle,
    score_day_quality,
)
from palmwtc.flux.scaling import (
    add_par_estimates,
    calculate_lai_effective,
    estimate_leaf_area,
    estimate_par_from_radiation,
    load_biophysical_data,
    scale_to_leaf_basis,
)

__all__ = [
    "DEFAULT_CO2_QC_THRESHOLDS",
    "DEFAULT_CONFIG",
    "DEFAULT_H2O_QC_THRESHOLDS",
    "DEFAULT_WPL_QC_THRESHOLDS",
    "NIGHTTIME_CO2_QC_THRESHOLDS",
    "NIGHTTIME_H2O_QC_THRESHOLDS",
    "NIGHTTIME_QC_THRESHOLDS",
    "_evaluate_cycle_wrapper",
    "add_par_estimates",
    "apply_wpl_correction",
    "apply_wpl_qc_overrides",
    "build_cycle_wpl_metrics",
    "calculate_absolute_flux",
    "calculate_flux_cycles",
    "calculate_flux_for_chamber",
    "calculate_h2o_absolute_flux",
    "calculate_h2o_flux_cycles",
    "calculate_h2o_flux_for_cycle",
    "calculate_lai_effective",
    "compute_closure_confidence",
    "compute_day_scores",
    "compute_ml_anomaly_flags",
    "compute_temporal_coherence",
    "detect_bimodal_cycle",
    "estimate_leaf_area",
    "estimate_par_from_radiation",
    "get_tree_volume_at_date",
    "identify_cycles",
    "load_biophysical_data",
    "load_tree_biophysics",
    "prepare_chamber_data",
    "scale_to_leaf_basis",
    "score_cycle",
    "score_day_quality",
    "score_h2o_flux_qc",
    "summarize_wpl_correction",
]
