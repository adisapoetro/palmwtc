# Changelog

All notable changes to `palmwtc` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

(no changes yet)

## [0.2.0] — 2026-04-21

Scope correction: drop the Streamlit dashboard from palmwtc. Operational
monitoring is out of scope for the public chamber-flux package. The
companion `flux_chamber` working repo retains the LIBZ-specific
operational dashboard (~6600 lines with auth, ngrok, email reports —
none of which belongs in a published library).

### Removed (BREAKING)

- `palmwtc.dashboard` subpackage — deleted entirely.
- `palmwtc dashboard` CLI subcommand — removed.
- `[dashboard]` extra — removed (was: `streamlit + ipywidgets + anywidget`).

### Added

- `[interactive]` extra — `ipywidgets + anywidget` for the Jupyter
  `interactive_flux_dashboard` helper in `palmwtc.viz.interactive`. Same
  contents as the old `[dashboard]` extra minus Streamlit.

### Migration from 0.1.x

Users who installed `palmwtc[dashboard]` and want the Jupyter widgets:
```bash
pip uninstall streamlit  # optional, no longer pulled
pip install 'palmwtc[interactive]'
```

Users who relied on the Streamlit `palmwtc dashboard` CLI: that
operational dashboard now lives in the upstream `flux_chamber` working
repo (private). The public `palmwtc` package focuses on the chamber-flux
algorithms + tutorials + bundled sample only.

## [0.1.0] — 2026-04-20

First public release. The full library + CLI + bundled synthetic sample
+ tutorial notebooks + Streamlit dashboard + auto-deployed docs site.

A user can now:

```bash
pip install palmwtc
palmwtc run                  # ~20 s end-to-end on bundled synthetic sample
palmwtc dashboard            # streamlit monitoring app (requires [dashboard])
palmwtc run --notebooks      # papermill mode (requires --raw-dir or palmwtc.yaml)
```

### Added — Library

- `palmwtc.config.DataPaths` — frozen dataclass with layered resolver
  (kwargs → env `PALMWTC_DATA_DIR` → `palmwtc.yaml` → bundled sample).
- `palmwtc.pipeline` — library-mode orchestrator with steps `qc → flux → windows → validation`.
  Each step callable via `run_step(name, paths)`; whole pipeline via `run_pipeline(paths)`.
- `palmwtc.notebooks_runner` — papermill-mode equivalent for `palmwtc run --notebooks`.
- `palmwtc.cli` — typer app with `info`, `run`, `sample {path,fetch}`, `dashboard` subcommands.
- 7 subpackages, 33 top-level public symbols, full backward-compat re-exports.

### Added — Subpackages (ported from `flux_chamber/src/`, behaviour-preserving at 1e-12)

- `palmwtc.io` — loaders, paths, cloud-mount adapters (from `data_utils.py`).
- `palmwtc.qc` — rules, breakpoints, drift, ML, processor, reporting (from `qc_functions.py` + `qc_reporting.py`).
- `palmwtc.flux` — absolute, scaling, cycles, chamber-aware (from `flux_analysis.py` + `flux_qc_fast.py` + `chamber_flux.py`).
- `palmwtc.windows` — `WindowSelector` (from `window_selection.py`).
- `palmwtc.validation` — science validation against literature ecophysiology bounds (from `science_validation.py`).
- `palmwtc.viz` — matplotlib + plotly viz helpers (from `flux_visualization*.py` + `qc_visualizations.py`).
- `palmwtc.hardware` — GPU/MPS-aware optional accelerators (from `gpu_utils.py`).
- `palmwtc.dashboard` — clean Streamlit monitoring app (NEW; not a port of `flux_chamber/dashboard/`).

### Added — Tutorials & docs

- 13 thin tutorial notebooks in `notebooks/` (010, 011, 020, 022, 023, 025, 026, 030, 031, 032, 033, 034, 035), each ≤30 cells, all execute headless on bundled sample.
- Jupyter-book docs site auto-deployed to <https://adisapoetro.github.io/palmwtc/> on every push to main.
- `scripts/build_tutorial_notebooks.py` + `scripts/build_phase5_notebooks.py` — declarative cell-list specs (re-runnable, deterministic).

### Added — Bundled synthetic sample

- `scripts/make_sample_data.py` — deterministic generator (`seed=42`).
- 1 week × 30 s sampling × 2 chambers = ~3 MB parquet + weather + biophysics.
- Edge cases injected: NaN bursts, linear drift, OOB spikes, saturated H2O.

### Added — Infrastructure

- `pyproject.toml` (uv-managed, hatchling backend, compatible-bounds pinning, Python 3.11–3.13).
- Extras: `[ml]`, `[ml-merlion]`, `[gpu]`, `[dashboard]`, `[docs]`, `[dev]`, `[all]`.
- CI matrix: lint (ruff) + typecheck (mypy, non-blocking) + test (Py 3.11/3.12/3.13 × ubuntu/macos) + docs (jupyter-book) + pipeline-smoke (full `palmwtc run` + 13 notebook execution).
- Release workflow (tag `v*.*.*` → PyPI Trusted Publishing + GitHub Release + Zenodo DOI).
- 447 tests passing (13 expected skips for optional extras).
- `.devcontainer/` for one-click VS Code dev environment.
- `CLAUDE.md` (AI-assistant conventions) + `docs/PROJECT_PULSE.md` (living status).

### Known limitations

- The bundled synthetic sample only exercises `qc + flux` end-to-end. `windows` produces 0 windows on toy data; `validation` reports skip-with-message because synthetic lacks `h2o_slope` + `Global_Radiation` columns. Real LIBZ data exercises all four steps.
- `palmwtc run --notebooks` requires a `notebooks_dir` in `palmwtc.yaml` or env (bundled notebooks are tutorial-style; the spine-runner path expects user-managed working notebooks).
- Notebook 036 (manual cycle QC labelling, ipywidgets-interactive) is intentionally not shipped — doesn't render headless.
- Mypy reports 2 pre-existing implicit-Optional warnings inherited from the source port; non-blocking in CI.

### Notes

- Git history of the original `flux_chamber/{src,notebooks,scripts/run_notebooks.py,tests}` is **not** carried into this repo. The original repo at <https://github.com/adisapoetro/flux_chamber> is the historical source of truth for blame archaeology.
- This release is the artefact of an 8-phase extraction plan executed across 2026-04-17 → 2026-04-20.

## [0.1.0.dev0] — 2026-04-17

Initial PyPI name reservation. Empty placeholder.
