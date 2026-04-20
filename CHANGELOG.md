# Changelog

All notable changes to `palmwtc` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (Phase 6 — Streamlit dashboard)
- `palmwtc.dashboard.app` — clean Streamlit monitoring app (~250 lines)
  built on the palmwtc API. Sections: DataPaths summary, QC parquet
  sanity, QC flag totals, inter-chamber agreement, per-cycle flux
  (with on-demand pipeline-run button), cycle-quality distribution.
- `palmwtc dashboard` CLI command actually launches Streamlit (was a
  stub in Phase 3).
- New `[dashboard]` extra now also pulls `anywidget` (for plotly
  `FigureWidget`).
- 6 new tests in `tests/unit/test_dashboard.py` (subpackage import,
  helpers, CLI gate behaviour without/with extra).

### Added (Phase 3 — config + CLI + pipeline + sample)
- `palmwtc.config.DataPaths` — frozen dataclass with layered resolver
  (kwargs → env `PALMWTC_DATA_DIR` → `palmwtc.yaml` → bundled sample).
- `palmwtc.pipeline` — library-mode orchestrator: `qc → flux → windows → validation`
  steps callable directly from Python, no papermill.
- `palmwtc.notebooks_runner` — port of `flux_chamber/scripts/run_notebooks.py`
  for the `palmwtc run --notebooks` papermill mode.
- `palmwtc.cli` real subcommands: `run`, `info`, `sample path`, `sample fetch` (stub),
  `dashboard` (stub).
- `scripts/make_sample_data.py` — deterministic synthetic chamber + climate dataset
  (~3 MB, 7 days × 30 s sampling, 2 chambers, edge cases injected for QC paths).
- Bundled synthetic sample at `src/palmwtc/data/sample/synthetic/` so
  `palmwtc run` works zero-config.
- CI pipeline-smoke job now runs `palmwtc run` end-to-end on the bundled sample.

### Added (Phase 2 — earlier)
- Repository skeleton: `pyproject.toml`, `LICENSE` (MIT), `README.md`,
  `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`.
- Package directory layout (`src/palmwtc/{io,qc,flux,windows,validation,viz,hardware,data}/`)
  with empty modules ready for Phase 2 port from `flux_chamber/src/`.
- `.github/workflows/ci.yml` (lint + typecheck + test + docs + smoke matrix
  on Python 3.11/3.12/3.13 × Ubuntu + macOS).
- `.github/workflows/release.yml` (tag → PyPI trusted publish + GitHub Release).
- `docs/_config.yml` + `_toc.yml` jupyter-book skeleton.
- `tests/{unit,integration,fixtures}/` skeleton with smoke test.
- Tooling: `ruff`, `mypy`, `pytest`, `pre-commit`, `nbstripout`, `uv`.

### Notes
- This is Phase 1 (skeleton only). No flux/QC code yet — see plan at
  `~/.claude/plans/venv-bin-python-scripts-run-notebooks-p-eventual-hellman.md`
  for the full extraction roadmap from `flux_chamber/`.
- Git history of the original `flux_chamber/{src,notebooks,scripts/run_notebooks.py,tests}`
  is **not** carried into this repo. If `git blame` traceability becomes needed,
  a follow-up commit can do a `git-filter-repo` of the flux_chamber repo and
  merge with `--allow-unrelated-histories`. For now, the original repo at
  `https://github.com/adisapoetro/flux_chamber@597ff89` is the historical
  source of truth.

## [0.1.0.dev0] — 2026-04-17

Initial PyPI name reservation.
