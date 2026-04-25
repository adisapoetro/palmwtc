# Science Reference

This section documents the scientific methods, QC thresholds, and validation
bounds used by `palmwtc`.

## Pipeline overview

```
raw cycles ──► QC ──► flux ──► windows ──► validation
              │
              └── 30-min weather + soil + tree biophysics
```

Each stage is described in detail in the corresponding tutorial notebook
under [tutorials/](../tutorials/index.md). The integrated end-to-end run is
covered in [tutorials/000](../tutorials/000_Integrated_End_to_End.ipynb).

## Method references

- **Whole-tree-chamber method**: Medlyn, B. E. *et al.* (2016).
  Pinpointing drivers of widespread declines in Australian streamflow.
  *Global Change Biology*, 22(8), 2834–2851.
- **CO₂ flux closure (Amax bounds)**: literature canopy-basis Amax
  15–35 µmol m⁻² ground s⁻¹ (Lamade & Bouillet 2005).
- **Q10 respiration**: 1.4–2.5 (literature range, tropical canopy).
- **Stomatal conductance (Medlyn g₁)**: Medlyn, B. E. *et al.* (2011).
  Reconciling the optimal and empirical approaches to modelling stomatal
  conductance. *Global Change Biology*, 17(6), 2134–2144.
  https://doi.org/10.1111/j.1365-2486.2010.02375.x
- **Isolation Forest (ML-assisted QC)**: Liu, F. T., Ting, K. M., &
  Zhou, Z.-H. (2008). Isolation forest. *2008 Eighth IEEE International
  Conference on Data Mining*, 413–422.
  https://doi.org/10.1109/ICDM.2008.17
- **Breakpoint detection (PELT)**: Truong, C., Oudre, L., & Vayatis, N.
  (2020). Selective review of offline change point detection methods.
  *Signal Processing*, 167, 107299.
  https://doi.org/10.1016/j.sigpro.2019.107299
- **PAR conversion (shortwave → photosynthetic photon flux density)**:
  McCree, K. J. (1972). Test of current definitions of photosynthetically
  active radiation against leaf photosynthesis data. *Agricultural
  Meteorology*, 10, 443–453.

For the full per-function citation, see the docstrings on the
implementing functions in `palmwtc.qc.breakpoints`, `palmwtc.qc.ml`,
`palmwtc.flux.scaling`, and `palmwtc.validation.science`.
