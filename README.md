# palmwtc

**Automated whole-tree chamber workflow for oil-palm ecophysiology.**

[![PyPI](https://img.shields.io/pypi/v/palmwtc.svg)](https://pypi.org/project/palmwtc/)
[![Python](https://img.shields.io/pypi/pyversions/palmwtc.svg)](https://pypi.org/project/palmwtc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/adisapoetro/palmwtc/actions/workflows/ci.yml/badge.svg)](https://github.com/adisapoetro/palmwtc/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/1213667337.svg)](https://doi.org/10.5281/zenodo.19680893)

`palmwtc` is the data-processing and analysis pipeline for the first
automated whole-tree chamber (WTC) sized to enclose individual oil palm trees,
deployed at the LIBZ field site (Riau, Indonesia) and instrumented with
LI-COR LI-850 gas analyzers. It transforms raw sensor cycles into validated
CO₂ and H₂O fluxes, applies multi-stage quality control, and produces inputs
for the XPalm digital-twin calibration pipeline.

## What it does

```
raw chamber cycles  ──►  QC (rules + ML + breakpoints)  ──►  flux calculation  ──►  science validation
        │                                                                                  │
        └── 30-min weather + soil + tree biophysics ──┬───────────────────────────────────►┘
                                                       └── high-confidence calibration windows
```

End-to-end run on the bundled synthetic sample:

```bash
pip install palmwtc
palmwtc run            # uses bundled sample if no PALMWTC_DATA_DIR set
```

For your own data:

```bash
export PALMWTC_DATA_DIR=/path/to/your/chamber/data
palmwtc run --skip 022 025          # mirrors the original notebook-runner CLI
palmwtc run --notebooks             # papermill mode, produces HTML reports
```

## Install

```bash
pip install palmwtc                 # core only
pip install 'palmwtc[ml]'           # + scikit-learn IsolationForest QC
pip install 'palmwtc[interactive]'  # + ipywidgets / anywidget for Jupyter dashboards
pip install 'palmwtc[gpu]'          # + torch (Apple-Silicon MPS / CUDA)
pip install 'palmwtc[all]'          # everything
```

Requires Python 3.11–3.13.

## Library use

```python
from palmwtc.config import DataPaths
from palmwtc.qc import QCProcessor
from palmwtc.flux import calculate_flux_cycles

paths = DataPaths.resolve()                     # layered: CLI → env → yaml → sample
qc_result = QCProcessor(paths).run("CO2_C1")
flux = calculate_flux_cycles(qc_result.data)
```

Full API reference: [adisapoetro.github.io/palmwtc/api/](https://adisapoetro.github.io/palmwtc/api/)

## Citation

If you use `palmwtc` in scientific work, please cite the Zenodo DOI. The
**concept DOI** [10.5281/zenodo.19680893](https://doi.org/10.5281/zenodo.19680893)
always resolves to the latest version; to cite a specific release, use
its own version DOI (visible on the [Zenodo record](https://zenodo.org/records/19680893)
→ *Versions* panel).

```bibtex
@software{adisaputro_palmwtc_2026,
  author  = {Adisaputro, Didi},
  title   = {palmwtc: Automated whole-tree chamber workflow for oil-palm ecophysiology},
  year    = {2026},
  version = {0.2.0},
  doi     = {10.5281/zenodo.19680893},
  url     = {https://github.com/adisapoetro/palmwtc},
}
```

See [`CITATION.cff`](CITATION.cff) for machine-readable metadata.

## Background

Most ecosystem-scale flux measurements over oil-palm plantations use eddy
covariance, which integrates over hectares of canopy and cannot resolve
single-tree behaviour. `palmwtc` is built around a different instrument: an
*automated whole-tree chamber*, sized and ventilated to enclose an individual
mature oil palm, with an LI-COR LI-850 gas analyzer cycling open and closed on
a programmed schedule. This is, to our knowledge, the first WTC deployment for
oil palm — the WTC method was previously applied to temperate broadleaf
species (Medlyn et al. 2016).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Bug reports and feature requests:
[github.com/adisapoetro/palmwtc/issues](https://github.com/adisapoetro/palmwtc/issues).

## License

MIT — see [`LICENSE`](LICENSE).
