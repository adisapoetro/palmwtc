# palmwtc — AI assistant instructions

This file is loaded into every AI-assistant session that touches the
`palmwtc` repo. It encodes the conventions that shouldn't be re-derived
each time. **Read it before making non-trivial changes.**

`palmwtc` is the **public package** — clean, MIT-licensed, PyPI-published.
The companion **working / data repo** is `flux_chamber/` (private), which
holds raw chamber data, exports, presentations, and the Streamlit
dashboard. They are siblings; they share an author but not a release
cadence.

If you are confused about palmwtc vs flux_chamber, the rule is:
- **palmwtc** = the algorithms + library + CLI + tutorials. Public.
- **flux_chamber** = the LIBZ field data + day-to-day analysis workspace. Private.

---

## 1. Hard rules

### Scientific integrity
- Every numerical claim in docs, tutorials, or notebooks must trace to
  either (a) a `file.py:line` reference, (b) an executed notebook
  output, or (c) a cited publication. **No invented numbers.**
- If a test result is uncertain or data insufficient, return `"N/A"`
  or document the limitation. Don't manufacture a pass.

### Behaviour preservation (for ports / refactors)
- Function signatures + bodies stay identical. Only `import` statements
  change. Numeric outputs match the original to **1e-12**.
- **Don't fix bugs while porting.** Even if you see something broken,
  leave it. Bug fixes are separate commits with their own tests.
- Parity tests (`test_*_parity.py`) load the *original* via
  `importlib.util.spec_from_file_location` and assert numeric/series
  equality with `pytest.approx(abs=1e-12, rel=1e-12)` or
  `pd.testing.assert_*_equal`. **Never delete a parity test** — it's
  the only proof the port preserved behaviour.

### System description (don't confuse)
This package processes data from **automated whole-tree chambers (WTC)
sized to enclose individual oil palm trees** instrumented with LI-COR
LI-850. It is **NOT** a flux tower / eddy covariance deployment.
Anywhere — docs, tutorials, plot titles, commit messages — do not use
"flux tower" or "eddy covariance" language for this system.

### Notebook authoring convention (thin notebooks)
- Notebooks are the *narrative* wrapped around the library API.
- All algorithmic logic lives in `palmwtc.*`. Notebook cells are either:
  (a) markdown narrative, (b) one library call, (c) a plot.
- ≤30 cells per notebook (notebook 030 may go up to ~60), ≤30 lines of
  non-import code per cell.
- **Generate notebooks with `nbformat`**, not by hand. Cell specs live in
  `scripts/build_*_notebooks.py`. Re-runnable, deterministic.
- Every new notebook must execute headless via papermill against the
  bundled synthetic sample (or be marked as a documented stub).

### Public API surface
- `palmwtc.__init__` re-exports the most-used 33 symbols. Don't grow
  this set casually.
- Symbols whose names collide across subpackages (e.g. `DEFAULT_CONFIG`
  in `flux` vs `windows` vs `validation`) are **deliberately not
  re-exported** at top level. Import from the subpackage.
- Backward-compat re-exports in subpackage `__init__.py` are part of the
  contract — moving a function between sub-files requires keeping the
  re-export surface intact.

### Conventions
- **Python**: `unset VIRTUAL_ENV && uv run <command>` from repo root.
- **Notebooks**: edit by re-running `scripts/build_*_notebooks.py`, not
  via direct cell edits. JSON edits are brittle.
- **Git**: `main` is sole branch. Conventional Commits
  (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`).
  Always PR + squash-merge — no direct pushes to main.
- **Public-by-default**: this is a public repo. No LIBZ raw data, no
  internal presentations, no private credentials. Always check before
  committing.
- **`# ruff: noqa: <list>`** at file top is acceptable for behaviour-
  preserving ports (matches sibling files). For new code, use per-line
  `# noqa: <RULE>` with a comment explaining the rationale.

---

## 2. Pipeline architecture

**Stack**: Python 3.11–3.13, `uv` for env, `hatchling` build backend.

### Library-mode pipeline (`palmwtc.pipeline`)
```
qc → flux → windows → validation
```
Each step is callable via `run_step(name, paths)` or the whole pipeline
via `run_pipeline(paths)`. No papermill required.

### Notebook-mode pipeline (`palmwtc.notebooks_runner`)
Spine: `010 → 020 → 030 → 040` (Julia 040 out of scope for palmwtc 0.1).
Non-spine notebooks run in parallel after spine completes. Mirrors the
original `flux_chamber/scripts/run_notebooks.py` behaviour.

### Subpackages

| Subpackage | What it does |
|---|---|
| `palmwtc.io` | Data loaders, path resolution, cloud-mount adapters |
| `palmwtc.qc` | Quality control: rules, breakpoints, drift, ML, processor, reporting |
| `palmwtc.flux` | Flux calculation: absolute, cycles, chamber-aware, scaling |
| `palmwtc.windows` | Calibration window selection (`WindowSelector`) |
| `palmwtc.validation` | Science validation against literature ecophysiology bounds |
| `palmwtc.viz` | Static (matplotlib) + interactive (plotly) viz |
| `palmwtc.hardware` | GPU/MPS-aware optional accelerators (cuML/sklearn) |
| `palmwtc.dashboard` | Streamlit monitoring app (Phase 6, opt-in extra) |

---

## 3. Data flow

### `DataPaths` resolution (highest precedence first)
1. Explicit kwargs to `DataPaths.resolve()`
2. CLI flags (`palmwtc run --raw-dir ...`)
3. Env var `PALMWTC_DATA_DIR`
4. YAML config (`./palmwtc.yaml` then `~/.palmwtc/config.yaml`)
5. Bundled synthetic sample (`palmwtc.data.sample_dir("synthetic")`)

The last layer always succeeds — `palmwtc run` works with zero config.

### Bundled synthetic sample
- Location: `src/palmwtc/data/sample/synthetic/`
- Generator: `scripts/make_sample_data.py` (deterministic, `seed=42`)
- Contents: 1 week × 30 s, 2 chambers, ~3 MB parquet + weather + biophysics
- **Outputs from `palmwtc run` on the sample are gitignored** — they
  regenerate on every CI run.

---

## 4. Verification

Run from `/Users/adisapoetro/Projects/palmwtc/`:

```bash
unset VIRTUAL_ENV && uv sync --all-extras
unset VIRTUAL_ENV && uv run pytest                          # full suite (~3 min, 445+ tests)
unset VIRTUAL_ENV && uv run ruff check src/ tests/ scripts/
unset VIRTUAL_ENV && uv run ruff format --check src/ tests/ scripts/
unset VIRTUAL_ENV && uv run mypy src/palmwtc                # non-blocking, warn-only in CI
unset VIRTUAL_ENV && uv run palmwtc run                     # ~20s end-to-end smoke on synthetic
```

`pytest` markers:
- `slow` — tests taking > 5 s (deselect with `-m "not slow"` for fast feedback)
- `integration` — end-to-end pipeline + notebook tests
- `requires_real_data` — needs real LIBZ data, skipped in CI
- `requires_gpu` — needs `[gpu]` extra and a GPU/MPS device

### Pre-commit
```bash
unset VIRTUAL_ENV && uv run pre-commit install   # one-time
unset VIRTUAL_ENV && uv run pre-commit run --all-files
```

---

## 5. Documentation

- **Living status**: [`docs/PROJECT_PULSE.md`](docs/PROJECT_PULSE.md) —
  phase progress, CI status, deferred items, known issues. **Update in
  the same commit** as any phase-completing change.
- **User-facing**: `docs/index.md`, `docs/quickstart.md`,
  `docs/tutorials/`, `docs/science/`, `docs/api/` — all rendered by
  jupyter-book.
- **Contributor guide**: [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Citation**: [`CITATION.cff`](CITATION.cff) — keep in sync with
  `pyproject.toml [project] authors`.
- **Changelog**: [`CHANGELOG.md`](CHANGELOG.md), Keep-a-Changelog format,
  manually maintained.

When touching any file under `src/palmwtc/`, **also update**:
- `docs/api/` if you changed public function signatures (auto-generated
  via `sphinx-autoapi`, but verify the build)
- `CHANGELOG.md` under `## [Unreleased]` if user-visible
- `docs/PROJECT_PULSE.md` if it shifts phase status or unblocks something

---

## 6. The 8-phase extraction plan (for AI sessions resuming work)

The full plan lives in the *flux_chamber* repo at
`~/.claude/plans/venv-bin-python-scripts-run-notebooks-p-eventual-hellman.md`.
Status as of palmwtc 0.1.0.dev0:

- ✓ Phase 1 — Repo skeleton (`b33a5ab`)
- ✓ Phase 2 — Port flux_chamber/src/ to palmwtc package, 12 modules (`16ea472`)
- ✓ Phase 3 — Config + CLI + library pipeline + bundled synthetic sample (`cb1ec03`)
- ✓ Phase 4 — Thin tutorial notebooks 010/020/030/033 (`64e0771`)
- ✓ Phase 5 — Thin tutorial notebooks 011/022/023/025/026/031/032/034/035 (`76d5c4b`)
- ✓ Phase 6 — `palmwtc.dashboard` Streamlit app + `palmwtc dashboard` CLI
- ☐ Phase 7 — Full docs site (jupyter-book) deployed to `gh-pages`.
- ☐ Phase 8 — Old-repo cutover + first release (PyPI + Zenodo DOI).

See [`docs/PROJECT_PULSE.md`](docs/PROJECT_PULSE.md) for the per-phase
detail + open blockers.
