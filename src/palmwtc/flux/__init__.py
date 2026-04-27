"""CO₂ and H₂O flux calculation from whole-tree chamber cycles.

- :mod:`~palmwtc.flux.absolute` — single-cycle ppm s⁻¹ → µmol m⁻² s⁻¹
  conversion (CO₂) and mmol mol⁻¹ s⁻¹ → mmol m⁻² s⁻¹ (H₂O) via
  ideal gas law.
- :mod:`~palmwtc.flux.chamber` — chamber geometry, tree-biomass lookup,
  and batch per-cycle flux computation. Also holds the default QC
  threshold dicts used by cycle scoring.
- :mod:`~palmwtc.flux.cycles` — cycle identification, quality scoring,
  bimodal-fault detection, and daily-score aggregation.
- :mod:`~palmwtc.flux.scaling` — LAI estimation and ground → leaf-area
  flux conversion; PAR estimation from shortwave radiation.
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
from palmwtc.flux.advanced_outlier import (
    DEFAULT_ADVANCED_OUTLIER_CONFIG,
    compute_ensemble_score,
    compute_rolling_zscore,
    compute_stl_residual_scores,
)

__all__ = [
    "DEFAULT_ADVANCED_OUTLIER_CONFIG",
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
    "compute_ensemble_score",
    "compute_ml_anomaly_flags",
    "compute_rolling_zscore",
    "compute_stl_residual_scores",
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
