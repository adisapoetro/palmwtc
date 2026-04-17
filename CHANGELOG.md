# Changelog

All notable changes to `palmwtc` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
