# palmwtc

**Automated whole-tree chamber workflow for perennial-crop ecophysiology.**

`palmwtc` is a data-processing and analysis pipeline for automated whole-tree
chambers (WTC) that enclose an individual perennial-crop tree. Its reference
deployment is the first such chamber built for oil palm, at the LIBZ field site
(Riau, Indonesia), instrumented with LI-COR LI-850 gas analyzers.

It transforms raw chamber cycles into validated CO₂ and H₂O fluxes,
applies multi-stage quality control (rules + breakpoints + ML outliers),
and produces inputs for the XPalm digital-twin calibration pipeline.

```{tableofcontents}
```

## Quick links

- [Quickstart](quickstart.md) — install, run on the bundled sample, see results
- [Tutorials](tutorials/index.md) — step-by-step walkthroughs of each pipeline stage
- [Science Reference](science/index.md) — methods, validation thresholds, literature
- [API Reference](api/index.md) — auto-generated from docstrings

## Cite

If you use `palmwtc` in scientific work, please cite the Zenodo DOI for the
release you used. See the [Citation File](https://github.com/adisapoetro/palmwtc/blob/main/CITATION.cff).
