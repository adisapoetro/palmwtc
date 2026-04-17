# Quickstart

## Install

```bash
pip install palmwtc            # core only
pip install 'palmwtc[ml]'      # + scikit-learn IsolationForest QC
pip install 'palmwtc[all]'     # everything
```

Requires Python 3.11–3.13.

## Run on the bundled synthetic sample

```bash
palmwtc info       # prints version + resolved data paths
palmwtc run        # runs full pipeline on bundled sample (Phase 3+)
```

(Phase 1 status: `palmwtc info` works; `palmwtc run` is a stub until Phase 3.)

## Run on your own data

Set `PALMWTC_DATA_DIR` to a directory containing the chamber raw output, or
write a `palmwtc.yaml` config in your working directory.

```bash
export PALMWTC_DATA_DIR=/path/to/chamber/data
palmwtc run --skip 022 025
```

## Library use

```python
from palmwtc.config import DataPaths
from palmwtc.qc import QCProcessor          # available from Phase 2
from palmwtc.flux import calculate_flux_cycles

paths = DataPaths.resolve()
qc = QCProcessor(paths).run("CO2_C1")
flux = calculate_flux_cycles(qc.data)
```

## Next

- [Tutorials](tutorials/index.md) walk through each stage of the pipeline.
- [Science Reference](science/index.md) explains the methods and validation thresholds.
