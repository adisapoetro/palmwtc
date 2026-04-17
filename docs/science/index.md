# Science Reference

This section documents the scientific methods, QC thresholds, and validation
bounds used by `palmwtc`. Phase 7 of the extraction plan ports the relevant
content from `flux_chamber/docs/ReadMe QC/` and `docs/ReadMe digital_twin/`.

## Pipeline overview

```
raw cycles ──► QC ──► flux ──► windows ──► validation
              │
              └── 30-min weather + soil + tree biophysics
```

## Method references (placeholder)

- **Whole-tree-chamber method**: Medlyn et al. 2016, *Global Change Biology* 22(8): 2834–2851.
- **CO₂ flux closure**: literature canopy-basis Amax 15–35 µmol/m² ground/s (Lamade & Bouillet 2005).
- **Q10 respiration**: 1.4–2.5 (literature range, tropical canopy).
- **Stomatal conductance**: Medlyn g₁ formulation.

(Full literature compilation lives in `flux_chamber/docs/abstract/FSPM2026_comprehensive_review.md`
and will be ported to this package's docs in Phase 7.)
