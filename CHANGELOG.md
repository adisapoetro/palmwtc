# Changelog

All notable changes to `palmwtc` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- New tutorial notebook `001_End_to_End_Real_Chamber_Data.ipynb` — sibling
  of `000_Integrated_End_to_End.ipynb`. Demonstrates the canonical
  pipeline (chamber prep → flux cycles → calibration windows → science
  validation → threshold-sensitivity sweep → visualisation) end-to-end
  using **default arguments throughout**, against either real LIBZ-style
  QC parquet (when `processed_dir/020_rule_qc_output.parquet` exists) or
  the bundled synthetic sample (auto-fallback). Generated deterministically
  by `scripts/build_001_end_to_end_notebook.py`.

### Queued for next release

- Rewrite the README intro paragraph to make clear that QC operates across the
  full sensor set — gas concentrations (CO₂, H₂O), air temperature, humidity,
  vapor pressure, atmospheric pressure, and battery proxy — not just CO₂/H₂O
  fluxes. The current wording undersells the QC scope.
- `palmwtc.flux.run_flux_pipeline()` — single function that ties together the
  orchestration currently inline in `research/notebooks/030` (per-row
  tree-volume recompute, score_cycle, day_score, ML anomaly, the new advanced
  outlier ensemble landed in 0.4.0, is_nighttime re-derivation, and the
  ~27k-cycle filter that drops 88,602 raw cycles down to the canonical 61,161
  baseline). Closes the residual sandbox-vs-baseline parity gap (currently
  88.5% bit-exact) by letting downstream consumers run the full pipeline with
  one call.
- LOF (Local Outlier Factor) and Temporal IsolationForest detectors that feed
  into `compute_ensemble_score`. Currently the ensemble scores only the three
  detectors landed in 0.4.0 (`stl`, `rz`) plus whichever of `ml_if`/`ml_mcd`
  the caller already populated via `compute_ml_anomaly_flags`; LOF and TIF
  weights are kept in `DEFAULT_ADVANCED_OUTLIER_CONFIG["ensemble_weights"]`
  so the ensemble auto-uses them once they ship.

## [0.4.1] — 2026-04-28

Bug-fix release. Fixes a silent-data-corruption bug in
`palmwtc.io.load_radiation_data` that surfaced when the AWS Excel
export contained the LIBZ logger's `"--"` and `"-"` sensor-error
markers. Without the fix, those markers were imported as Python
strings on object-dtype columns (e.g. `"Temp - °C"`, `"Hum - %"`)
which then broke any downstream `to_parquet` write that included them
with `ArrowInvalid: Could not convert '--' with type str`.

The bug had been masked for at least a month by the
`research/notebooks/030` checkpoint reload (`_checkpoint_033_*.parquet`)
short-circuiting the pipeline before it touched the radiation columns.
It surfaced when a fresh re-run of 030 (with the checkpoints deleted)
went through the real code path.

### Fixed

- **`palmwtc.io.load_radiation_data` now passes `na_values=["--", "-"]`
  to `pd.read_excel`.** AWS sensor-error markers are now parsed as NaN
  at load time, so all numeric AWS columns retain their numeric dtype
  and downstream parquet writes succeed.

### Added

- **Regression test** `test_load_radiation_data_parses_dash_dash_as_nan`
  in `tests/unit/io/test_loaders.py`. Builds a synthetic AWS Excel file
  containing `"--"` and `"-"` markers in three columns
  (`Global_Radiation`, `"Temp - °C"`, `"Hum - %"`), loads it via
  `load_radiation_data`, asserts every column ends up numeric-dtype,
  and round-trips the result through `to_parquet` (which is the
  contract that broke before the fix).

### Changed

- `CITATION.cff` version bumped to `0.4.1`.

## [0.4.0] — 2026-04-28

Adds three advanced outlier-detection algorithms that previously lived inline
in `research/notebooks/030` to the public `palmwtc.flux` API. No breaking
changes; existing call sites are unaffected.

This is the first half of the architectural debt identified in
`research/docs/Audit/2026-04-27_palmwtc_0.3.0_defaults_audit.md` — a portion
of the orchestration that produces `Data/digital_twin/01_chamber_cycles.csv`
now lives in the package. The remaining orchestration (`run_flux_pipeline()`
that ties everything together) is queued for 0.5.0.

### Added

- **`palmwtc.flux.advanced_outlier`** — new module exposing three
  cycle-level outlier-detection helpers and a configuration constant:

  - `compute_stl_residual_scores(df, cfg)` — per-chamber Seasonal-Trend-LOWESS
    decomposition of the cycle-level CO₂ slope.  Adds `stl_residual`,
    `stl_residual_zscore` (IQR-based robust z-score), `stl_soft_flag`, and
    `stl_hard_flag` columns.  Runs the per-chamber STL fits in parallel via
    `joblib`.  Tropical diurnal amplitude tuned via the default
    `stl_soft_iqr_mult=2.0` and `stl_hard_iqr_mult=3.5`.
  - `compute_rolling_zscore(df, cfg)` — per-chamber centred rolling-window
    z-score on the cycle-level slope.  Adds `rolling_zscore` and
    `rolling_zscore_flag` columns.  Default window is 12 cycles
    (≈ 3 h at 1 cycle / 15 min); configurable via `cfg["rz_window_cycles"]`.
    Catches single-cycle hardware glitches that the STL hourly-median step
    would otherwise absorb.
  - `compute_ensemble_score(df, cfg)` — rank-normalises every detector
    column present in the input (`ml_if_score`, `ml_mcd_dist`, `lof_score`,
    `tif_score`, `stl_residual_zscore`, `rolling_zscore`) into ``[0, 1]``
    and combines them with `cfg["ensemble_weights"]` into
    `anomaly_ensemble_score`, then sets
    `anomaly_ensemble_flag = score > cfg["ensemble_flag_threshold"]`.
    Detectors whose source column is missing are silently skipped, so the
    function works with any subset of the six detectors.
  - `DEFAULT_ADVANCED_OUTLIER_CONFIG` — the tuning dict for STL,
    rolling-zscore, and the ensemble.  All values match the LIBZ
    deployment defaults from `research/notebooks/030 ADVANCED_OUTLIER_CONFIG`
    line-for-line.

  All three functions return a copy; they do not mutate the input frame.

- 13 unit tests in `tests/unit/flux/test_advanced_outlier.py` covering
  expected output columns, no-input-mutation, STL handling of short
  chambers (insufficient data), rolling-zscore detection of an injected
  spike, ensemble behaviour with missing detectors, ensemble behaviour
  on an empty frame, and ensemble ranking sanity (a single anomalous row
  must score higher than non-anomalous rows).

### Changed

- `statsmodels>=0.14,<1.0` added as a core dependency.  Required by
  `compute_stl_residual_scores`; imported lazily inside `_stl_one_chamber`
  so the rest of `palmwtc` remains importable on systems where statsmodels
  is missing.

- `palmwtc.flux.__init__` re-exports the four new symbols
  (`DEFAULT_ADVANCED_OUTLIER_CONFIG`, `compute_stl_residual_scores`,
  `compute_rolling_zscore`, `compute_ensemble_score`).

### Test suite

- 525 passed, 50 skipped, 0 failed (was 512 / 50 / 0 in 0.3.0).
  The 13 added tests are all the new coverage; no existing test was
  modified.

## [0.3.0] — 2026-04-28

**Breaking change release.** Promotes 5 LIBZ-tested overrides to package
defaults so calling palmwtc with no kwargs produces the same result as the
research notebooks. Motivation: the 2026-04-27 sandbox parity audit traced
the 11.5% bit-exact gap between sandbox and baseline to 5 kwargs that the
research notebooks override at every call site. Promoting them to defaults
eliminates the divergence by construction. Audit:
[`research/docs/Audit/2026-04-27_palmwtc_0.3.0_defaults_audit.md`](https://github.com/adisapoetro/flux_chamber/blob/main/docs/Audit/2026-04-27_palmwtc_0.3.0_defaults_audit.md).

The full test suite (512 tests) passes at the new defaults — no behaviour
relying on the old defaults was tested.

### Changed (BREAKING)

- **`palmwtc.flux.prepare_chamber_data`** — four default flips:

  | Kwarg | Old default | New default |
  |---|---|---|
  | `accepted_co2_qc_flags` | `None` | `(0,)` |
  | `accepted_h2o_qc_flags` | `None` | `(0, 1)` |
  | `apply_wpl` | `True` | `False` |
  | `require_h2o_for_wpl` | `True` | `False` |

  Why: LI-COR LI-850 firmware applies WPL internally, so software-side WPL
  is double-correction (originally fixed in 0.2.3 as a flag flip; now hard
  default). And `accepted_*_qc_flags=None` was silently permissive — keeping
  every QC flag value, including `flag=2` (= bad data). The notebooks
  always overrode these to `[0]` (CO₂) and `[0, 1]` (H₂O) to filter
  scientifically. New defaults match.

  **Migration to restore old behaviour:**

  ```python
  # If you relied on the old "no QC filter + apply WPL in software" defaults:
  prepare_chamber_data(
      df, suffix,
      accepted_co2_qc_flags=None,    # disable filter
      accepted_h2o_qc_flags=None,    # disable filter
      apply_wpl=True,                # software WPL
      require_h2o_for_wpl=True,
  )
  ```

  Passing `None` explicitly still works as a backward-compatible "use
  DEFAULT_CONFIG fallback" path (see `prepare_chamber_data` body lines
  611-614 — preserved for legacy callers).

- **`palmwtc.validation.run_science_validation`** — `derive_daytime` default
  flipped from `True` to `False`. The notebooks always pass `False` because
  the LIBZ pipeline computes `is_daytime` from `Global_Radiation` upstream
  (more reliable than the function's hour-of-day fallback). Passing
  `derive_daytime=True` explicitly restores old behaviour.

- **`palmwtc.qc.process_variable_qc`** — `use_sensor_exclusions` default
  flipped from `False` to `True`. If a `config/sensor_exclusions.yaml` file
  exists in the configured directory, the exclusion windows are now applied
  by default (was previously silently skipped unless explicitly enabled).
  Passing `use_sensor_exclusions=False` explicitly restores old behaviour.

### Unchanged (already at LIBZ defaults — audit confirmed)

- `palmwtc.flux.compute_ml_anomaly_flags` — all 13 kwargs already at the
  LIBZ-tested values; no change needed.
- `palmwtc.validation.derive_is_daytime.radiation_threshold` — already
  defaults to `10.0` W/m²; no change needed.

### Migration recipe

For research/notebooks/030 and similar consumers, the explicit kwargs that
match the new defaults can simply be **removed** from call sites. For
example:

```python
# BEFORE:
prepare_chamber_data(
    df, "C1",
    accepted_co2_qc_flags=[0],
    accepted_h2o_qc_flags=[0, 1],
    apply_wpl=False,
    require_h2o_for_wpl=False,
    prefer_corrected_h2o=True,
)

# AFTER (palmwtc 0.3.0):
prepare_chamber_data(df, "C1")    # all defaults already correct
```

## [0.2.8] — 2026-04-27

Bug-fix release. `palmwtc.qc.render_field_alert_html` was silently broken
between 0.2.0 and 0.2.7: its default `template_dir` pointed at the
`palmwtc.dashboard` subpackage, which was deleted in 0.2.0. Calling it
without an explicit `template_dir=` raised
`jinja2.TemplateNotFound`. The 7:30 AM daily field-alert cron of
downstream consumers (e.g. `flux_chamber/research`) may have been silently
failing since the 0.2.0 cutover.

### Fixed

- **`palmwtc.qc.render_field_alert_html` default template path.** Moved
  `field_alert.html` from the deleted `palmwtc/dashboard/email_report/templates/`
  tree into the surviving `palmwtc/qc/templates/` directory. The default
  `template_dir` now resolves to `Path(__file__).parent / "templates"`,
  which is bundled with the wheel via the standard hatchling
  `packages = ["src/palmwtc"]` config (HTML files are included
  automatically alongside Python files).

### Added

- **Regression test** `test_render_field_alert_html_default_template_dir_resolves`
  in `tests/unit/qc/test_reporting.py`. Calls
  `render_field_alert_html({...minimal context...}, template_dir=None)` and
  asserts the output starts with `<!DOCTYPE html`. Replaces the previous
  test that **explicitly asserted the bug** (it expected
  `pytest.raises(TemplateNotFound)`), which is why nobody noticed the
  regression.

### Changed

- `CITATION.cff` version bumped to `0.2.8`.

## [0.2.7] — 2026-04-27

Documentation-only release. No behaviour changes; the existing test suite
remains green and consumer-parity tests against downstream sandbox + research
projects pass against this release.

### Added

- README "Background" section now includes an example illustration of an
  automated whole-tree chamber (the LIBZ deployment in Riau, Indonesia,
  from which `palmwtc` was originally developed). The illustration is
  framed as **one possible implementation, not a specification** —
  surrounding prose enumerates the dimensions along which other
  deployments will vary (chamber volume, tree species, sensor pole layout,
  soil instrumentation depth/brand, datalogger choice). The image renders
  on the PyPI project page and the GitHub repo landing page.
  ([`docs/_static/example_chamber_libz.png`](docs/_static/example_chamber_libz.png))

### Changed

- `CITATION.cff` version field bumped to `0.2.7` and `date-released` to
  `2026-04-27`. The previous 0.2.6 release missed bumping `CITATION.cff`
  from 0.2.5 — corrected in this release.

## [0.2.6] — 2026-04-25

Documentation sprint. No behaviour changes; the 463-test pretest suite
remains green and consumer-parity tests in downstream sandbox + research
projects pass against this release.

### Changed

- Comprehensive NumPy-style docstrings on every public function, class,
  and method across all subpackages (`io`, `qc`, `flux`, `windows`,
  `validation`, `viz`, `hardware`) plus `palmwtc.config.DataPaths`.
  Each docstring documents required input columns (for DataFrame-taking
  functions), units (SI throughout), sign conventions, and includes a
  runnable Examples block where practical.
- Type hints on every public signature. Backward-compatible — no caller
  code breaks.
- `pyproject.toml` enables `pytest --doctest-modules` so the runnable
  examples in docstrings are validated as tests.
- Rewritten `docs/quickstart.md` as a 3-minute scientist-facing
  walkthrough from `pip install` → first flux plot. Every snippet runs
  copy-paste against the bundled synthetic sample.
- New `docs/tutorials/000_Integrated_End_to_End.ipynb` — executable
  end-to-end tutorial covering qc → flux → windows → validation against
  the bundled synthetic sample. Markdown cells explain the scientific
  meaning of each step. Sorts before the existing 13 per-stage tutorials.
- Rewritten `docs/science/index.md` with proper bibliographic citations
  (Medlyn 2011/2016, Lamade & Bouillet 2005, Liu 2008, Truong 2020,
  McCree 1972).
- Removed all internal project-management references ("Phase N",
  `flux_chamber/src/*` paths, "behaviour preservation rule") from
  published source and docs. Verification:
  `grep -rn "Phase [0-9]\|flux_chamber/src" src/palmwtc/ docs/` returns
  zero hits.

### Removed

- `docs/PROJECT_PULSE.md` — internal phase-progress tracker, not
  appropriate for published documentation.
- `docs/api/index.md` — orphaned static placeholder; sphinx-autoapi
  auto-generates the API reference page from the source docstrings.
- `palmwtc sample fetch` CLI subcommand — was a stub printing "not yet
  implemented — Zenodo wiring lands in Phase 7" with exit code 2. Will
  be re-added when there is a real Zenodo DOI to fetch from.

### Known issues (deferred to v0.3.0)

- **Column-name inconsistency.** `calculate_flux_cycles` emits
  `flux_date` (date), but downstream `WindowSelector` and
  `run_science_validation` expect `flux_datetime` (timestamp). The
  quickstart and integrated tutorial both apply a `rename()` between
  the stages. Cleanup pending.
- **`run_science_validation` requires extra columns** beyond what the
  minimal QC → flux path produces (`Global_Radiation`, `h2o_slope`,
  `co2_slope`, `vpd_kPa`). The quickstart fills these with NaN
  placeholders for the demo; real validation requires the full
  pipeline.

## [0.2.5] — 2026-04-22

Fourth hotfix in the post-cutover-verification series. v0.2.4 ported
notebook 030 cell 18's tree-volume correction and turned it on whenever
`biophys_data_dir` was set. Real-data verification revealed the
post-cutover flux_chamber baseline CSV (`Data/digital_twin/01_chamber_cycles.csv`)
was itself produced WITHOUT tree-volume correction — so v0.2.4's
"always-on if biophys is available" default broke parity (88.5%
bit-exact match dropped to 1.2%). v0.2.5 re-gates the correction
behind an explicit opt-in flag and stops swallowing biophys-load errors.

### Changed (BEHAVIOUR)

- Tree-volume correction in `step_flux` is now **opt-in**. To enable,
  add to `palmwtc.yaml`:

  ```yaml
  correct_tree_volume: true
  biophys_data_dir: /path/to/BiophysicalParam
  ```

  Without `correct_tree_volume: true`, `step_flux` produces the same
  cycles output as v0.2.3 — preserving parity with the post-cutover
  flux_chamber baseline. This mirrors the original notebook 030's
  `CORRECT_TREE_VOLUME` flag semantics.

### Fixed

- `_apply_tree_volume_correction` no longer silently swallows biophys
  load errors. When opt-in is on but biophysics fail to load (missing
  `openpyxl`, missing dir, malformed xlsx, etc.) the function now emits
  a `UserWarning` so users can see *why* `tree_volume` is missing from
  their cycles output.

### Added

- `openpyxl>=3.1,<4.0` is now a core dependency. Tree-volume correction
  reads `Vigor Index.xlsx`-style files via `pandas.read_excel`, which
  needs `openpyxl`. Adding it as a core dep ensures opt-in actually
  works without forcing users to discover the silent ImportError.
- Three updated regression tests pinning the v0.2.5 opt-in contract:
  - `test_no_op_when_correct_tree_volume_flag_unset` — default off.
  - `test_warns_when_flag_on_but_biophys_dir_missing` — loud warn.
  - `test_warns_when_flag_on_but_biophys_dir_does_not_exist` — loud warn.

### Notes

- v0.2.4 will remain on PyPI but should be considered a transient
  release; pin to 0.2.5+ to get the opt-in semantics.
- Verified on real LIBZ data (974 MB QC parquet, 53,671 aligned
  cycles): default-off produces 88.5% bit-exact match against the
  flux_chamber baseline; opt-in produces tree-volume-corrected fluxes
  as a scientifically-correct alternative when the user accepts the
  baseline divergence.

## [0.2.4] — 2026-04-22

Third hotfix in the post-cutover-verification series. After v0.2.3
fixed WPL double-correction, mean `flux_absolute` divergence dropped
from 5% to 0.4% — but a residual outlier tail (p99 ≈ 1.3 µmol/m²/s,
max ≈ 22) persisted on real LIBZ data. Cause: missing tree-volume
correction in `step_flux`.

### Added

- `palmwtc.pipeline._apply_tree_volume_correction` — replays the
  tree-volume re-calculation from `flux_chamber/notebooks/030` cell 18.
  Per cycle: look up tree biophysics at `flux_date`, compute
  `tree_volume_m³`, re-run `calculate_absolute_flux` so the chamber
  air-volume divisor accounts for tree displacement.
- Two new optional `palmwtc.yaml` extras:
  - `biophys_data_dir`: absolute path to the biophysics folder
    (containing `Vigor Index.xlsx`, etc.). Required to enable correction.
  - `chamber_tree_map`: dict `{"C1": "tree-id-string", ...}`. Defaults
    to the LIBZ deployment map (`{"C1": "2.2/EKA-1/2107", "C2": "2.4/EKA-2/2858"}`)
    when not specified.
- New `tree_volume_corrected: <int>` field in `step_flux` result metrics
  reporting how many cycles got the per-tree correction applied.

### Behaviour change

- When `biophys_data_dir` is configured and the directory exists,
  `step_flux` now returns `cycles_df` with `tree_id`, `tree_volume`,
  and a recomputed `flux_absolute` column. Previously these columns
  were absent.
- When `biophys_data_dir` is **not** configured (or doesn't exist on
  disk), behaviour is identical to v0.2.3 — silently no-op, no new
  columns added.

### Tests

- `TestStepFluxTreeVolume` adds 3 cases: no-op when biophys missing,
  no-op when configured path doesn't exist, no-op on empty cycles.

### Migration

To enable tree-volume correction in your `flux_chamber2/palmwtc.yaml`:

```yaml
processed_dir:    /path/to/Data/Integrated_QC_Data
exports_dir:     /path/to/your/exports
biophys_data_dir: /path/to/Raw/local/BiophysicalParam   # ← NEW
# chamber_tree_map: defaults to LIBZ — override only for other deployments
#   C1: "2.2/EKA-1/2107"
#   C2: "2.4/EKA-2/2858"
```

### Discovery context

Found during the v0.2.3 verification re-run (same harness):

- v0.2.3: mean `flux_absolute` = -3.07 (vs baseline -3.09, diff 0.014)
- p99 |diff| = 1.33; max = 22.4 still
- Reading `flux_chamber/notebooks/030` cell 18 line-by-line revealed
  the post-`calculate_flux_cycles` tree-volume merge + re-apply that
  palmwtc was missing.

Recommend re-running `~/Projects/flux_chamber2/run.sh` after pulling
0.2.4 + adding `biophys_data_dir:` to `palmwtc.yaml`.

## [0.2.3] — 2026-04-22

Second hotfix found by the same `flux_chamber2` real-data verification
harness. After v0.2.2 fixed the chamber-detection over-count, the
remaining cycle-count was right (~60K) but per-cycle `flux_absolute`
diverged from baseline by a median of 0.075 µmol/m²/s and up to
22 µmol/m²/s on outliers. Root cause: WPL double-correction.

### Fixed

- `palmwtc.pipeline.step_flux` now calls
  `prepare_chamber_data(..., apply_wpl=False, require_h2o_for_wpl=False)`
  matching the real-instrument behaviour and the original
  `flux_chamber/notebooks/030` call.

  **Why this was wrong:** the LI-COR LI-850 (and the broader LI-7x00 /
  LI-8x0 chamber-analyser class palmwtc targets) applies the
  Webb–Pearman–Leuning dilution correction *inside the analyser
  firmware* before reporting CO2 ppm. Re-applying WPL in software is a
  double-correction. It also shrank the cycle-fit window because rows
  lacking a valid H2O reading got filtered out by
  `require_h2o_for_wpl=True`, dropping cycle durations by ~80 sec and
  shifting per-cycle slopes.

  Symptom on real LIBZ data:
  - Median `|flux_absolute| diff` vs baseline = 0.075 µmol/m²/s
  - p99 = 2.16 µmol/m²/s
  - max = 22.3 µmol/m²/s (cycles where window-shrinkage was severe)

  After fix (expected): per-cycle diff < 1e-6 against the original
  notebook output.

### Tests

- Added `tests/unit/test_pipeline.py::TestStepFluxWplDefaults::test_step_flux_passes_wpl_false_to_prepare`
  that monkey-patches `prepare_chamber_data` and asserts step_flux
  passes both `apply_wpl=False` and `require_h2o_for_wpl=False`.

### Discovery context

Found during the same real-data verification as v0.2.2's chamber bug.
Verification harness (`~/Projects/flux_chamber2/`):
1. Wipe outputs, install palmwtc 0.2.2, re-run pipeline
2. Notebook reported PARITY FAILED — per-cycle diff > tolerance
3. Per-cycle inspection of worst-diff cycle (Chamber 1, 2026-01-17 15:15)
   showed `cycle_duration_sec = 144 (new) vs 224 (old)` — exactly an
   80-second shorter window
4. Reading the original `flux_chamber/notebooks/030` cell 18 showed
   the explicit `apply_wpl=False, require_h2o_for_wpl=False` kwargs
   that step_flux was missing

Recommend re-running `~/Projects/flux_chamber2/run.sh` (or
`verify_palmwtc.ipynb`) after pulling 0.2.3 to confirm parity.

## [0.2.2] — 2026-04-22

Critical bug fix found during real-data verification of the
`flux_chamber` cutover. Anyone running `palmwtc run` against real LIBZ
data on 0.2.0 or 0.2.1 was getting wildly wrong cycle counts (~20× the
correct number); zero impact on the bundled-synthetic-sample CI smoke,
which is why automated tests didn't catch it.

### Fixed

- `palmwtc.pipeline.step_flux` chamber-detection regex.
  Old logic: `col.startswith("CO2_C")` + `col.split("_", 1)[1]` —
  treated every `CO2_C1_qc_flag`, `CO2_C1_rule_flag`, `CO2_C1_ml_flag`,
  `CO2_C1_corrected`, `CO2_C1_offset`, `CO2_C1_raw`, `CO2_C1_dp_upper`,
  etc. as a separate "chamber". On real LIBZ data with 286 columns,
  this produced **26 phantom chambers** instead of 2.
  New logic: exact regex match `^CO2_(C\d+)$`. Only canonical CO2_C1
  and CO2_C2 columns count as chambers.

### Tests

- Added `tests/unit/test_pipeline.py::TestStepFluxChamberDetection`
  with 4 regression tests:
  - `test_detects_canonical_chamber_columns` — basic case
  - `test_ignores_qc_flag_derivative_columns` — the actual bug
    (16 derivative columns + 2 chambers → only chambers)
  - `test_three_chamber_setup_works` — generalises to N chambers
  - `test_no_co2_columns_returns_empty` — graceful handling

### Discovery context

Found during user-driven `flux_chamber2` verification harness run
against the 974 MB real LIBZ QC parquet on 2026-04-22:

- Expected: ~61K cycles (matching pre-cutover baseline)
- Actual on 0.2.1: 1,243,377 cycles (≈20× too many)
- Root cause: chamber-detection over-counts by 13×

Cutover of `flux_chamber` PR #1 was correctly held until this fix
ships. After 0.2.2 lands, re-run `flux_chamber2/run.sh` to reverify.

## [0.2.1] — 2026-04-21

Hygiene patch — addresses deferred code-review nits from Phase 2 + 4
mypy warnings. No API changes; library and CLI surface identical to 0.2.0.

### Fixed

- `palmwtc/viz/timeseries.py` docstring: the original was claiming
  `plot_concentration_slope_vs_date_interactive` "lives in
  palmwtc.viz.interactive" — that function was actually retired during
  the port (zero notebook usage). Docstring now describes the retirement
  accurately.
- `palmwtc/flux/cycles.py` + `palmwtc/flux/chamber.py`: removed dead
  `try/except ImportError` around sibling `palmwtc.flux.absolute`
  imports. The try/except was faithful to the pre-port staging when the
  sibling file might not yet exist; once consolidated in v0.1.0 the
  sibling is always present, so the fallbacks were unreachable.
- `palmwtc/pipeline.py`: `find_latest_qc_file` was called with a
  non-existent `processed_dir=` keyword; fixed to positional arg. Did
  not manifest at runtime because the canonical path check short-circuits
  first on synthetic + real data, but would have bitten edge cases where
  neither canonical nor bundled-synthetic paths exist.

### Changed (type safety)

- `palmwtc/io/cloud.py`: added explicit type annotation for `result`
  dict.
- `palmwtc/io/loaders.py`: `load_monthly_data(months=...)` now typed
  as `list | None` (was implicit Optional).
- Added `types-PyYAML` to the `[dev]` extra.

### Docs

- `README.md`: Zenodo DOI badge + real DOI in citation section
  (concept DOI 10.5281/zenodo.19680893; v0.2.0 version DOI
  10.5281/zenodo.19675971).
- `CITATION.cff`: `identifiers:` block listing both DOIs.

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
