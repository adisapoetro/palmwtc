---
title: palmwtc — Project Pulse
type: living-status-tracker
version: 0.9.0
last_updated: 2026-04-21
owner: Didi Adisaputro
---

# palmwtc — Project Pulse

The single living entry point for palmwtc status. **Updated in the same
commit** as any change that shifts traffic-light status, unblocks a
deferred item, or completes a phase.

For per-section depth see the linked detail docs. For per-phase
implementation history see git log + the merged PRs (each phase is one
squash commit).

---

## Traffic-light status

| Area | Status | Notes |
|---|---|---|
| Library port (Phase 2) | 🟢 Done | 12 modules, behaviour-preserving, 1e-12 parity |
| Config + CLI + pipeline (Phase 3) | 🟢 Done | `palmwtc run` works zero-config |
| Tutorial notebooks (Phases 4-5) | 🟢 Done | 13 thin notebooks, all execute headless |
| Streamlit dashboard (Phase 6) | ⚪ Reverted in v0.2.0 | Out-of-scope decision; LIBZ ops dashboard stays in flux_chamber working repo |
| Docs site publication (Phase 7) | 🟢 Done | Live at <https://adisapoetro.github.io/palmwtc/>; CI auto-deploys on push to main |
| First public release (Phase 8) | 🟢 v0.1.0 tagged | PyPI + GitHub Release + Zenodo DOI auto-minted via release workflow |
| CI matrix | 🟢 Green | Py 3.11/3.12/3.13 × ubuntu/macos all pass |
| Mypy | 🟡 Non-blocking | 2 pre-existing implicit-Optional warnings inherited from port |
| Test count | 🟢 447 passed | + 13 expected skips (`openpyxl`, `[ml]`, `[dashboard]`-absent paths) |

---

## Phase progress

| # | Phase | Status | Merged | Commit |
|---|---|---|---|---|
| 1 | Repo skeleton | ✓ Done | 2026-04-17 | `b33a5ab` |
| 2 | Port flux_chamber/src/ → palmwtc (12 modules) | ✓ Done | 2026-04-19 | `16ea472` |
| 3 | DataPaths + CLI + library pipeline + bundled sample | ✓ Done | 2026-04-19 | `cb1ec03` |
| 4 | Thin tutorial notebooks 010/020/030/033 | ✓ Done | 2026-04-19 | `64e0771` |
| 5 | Thin tutorial notebooks 011/022/023/025/026/031/032/034/035 | ✓ Done | 2026-04-19 | `76d5c4b` |
| 6 | Streamlit dashboard integration (`palmwtc.dashboard`) | ✓ Done | 2026-04-20 | `f2dd517` |
| 7 | Docs site publication (`palmwtc.github.io/palmwtc/`) | ✓ Done | 2026-04-20 | `e40726e` |
| 8 | Old-repo cutover + first PyPI release + Zenodo DOI | 🟡 Tag-only | 2026-04-20 | (this PR) |

---

## Open blockers

| ID | Blocker | Owner | Severity | Opened | Notes |
|---|---|---|---|---|---|
| ~~OB-001~~ | ~~PyPI name not yet reserved~~ | maintainer | ✅ closed 2026-04-20 | `palmwtc==0.1.0.dev0` placeholder uploaded. |
| ~~OB-002~~ | ~~PyPI Trusted Publishing not configured~~ | maintainer | ✅ closed 2026-04-20 | Configured for `release.yml` workflow + `pypi` environment. |
| ~~OB-003~~ | ~~Zenodo-GitHub integration not enabled~~ | maintainer | ✅ closed 2026-04-20 | Toggle ON for `adisapoetro/palmwtc`. |
| OB-004 | `flux/cycles.py` has dead-code try/except for sibling import | AI | 🟢 low | 2026-04-19 | Code-review nit, deferred follow-up. |
| OB-005 | `viz/timeseries.py:23` docstring promises a function that was dropped | AI | 🟢 low | 2026-04-19 | Same — code-review nit, deferred. |
| OB-006 | Mypy: 2 pre-existing implicit-Optional warnings in `io/loaders.py`, `io/cloud.py` | AI | 🟢 low | 2026-04-17 | Inherited from upstream port. Non-blocking in CI. |

---

## Latest findings & changes (newest first)

| Date | Phase | What | Outcome |
|---|---|---|---|
| 2026-04-21 | scope | Drop palmwtc.dashboard subpackage + CLI; replace [dashboard] with [interactive] extra | Tighter package scope; tag v0.2.0 |
| 2026-04-20 | 8 | v0.1.0 tagged → release workflow → PyPI + GitHub Release + Zenodo DOI | First public release |
| 2026-04-20 | 7 | gh-pages deploy from CI (peaceiris) + Pages enabled | Live docs at adisapoetro.github.io/palmwtc/ |
| 2026-04-20 | 6 | Streamlit dashboard wired (later reverted in v0.2.0) | Decision documented in CHANGELOG [0.2.0] |
| 2026-04-19 | 5 | 9 thin tutorials + auto-discovery papermill CI | All 13 notebooks execute < 60s in CI |
| 2026-04-19 | 4 | 4 first-class tutorials (010/020/030/033) | Jupyter-book ToC wired |
| 2026-04-19 | 3 | DataPaths layered resolver + CLI + pipeline | Zero-config first-run works |
| 2026-04-19 | 3 | Bundled synthetic sample (~3 MB) | Pipeline-smoke CI: 58s |
| 2026-04-19 | 2 | 12-module port complete | 191 unit tests pass at 1e-12 parity |
| 2026-04-17 | 1 | Empty repo skeleton, CI green on first push | 10/10 CI jobs |

---

## Decisions log

| Date | Decision | Rationale | Reference |
|---|---|---|---|
| 2026-04-17 | Package name = `palmwtc` | "Whole-Tree Chamber" plants flag in established literature (Medlyn et al. 2016) | brainstorming, plan §17 |
| 2026-04-17 | License = MIT | Lingua franca of scientific Python | brainstorming |
| 2026-04-17 | Build tool = uv + hatchling + compatible-bounds pinning | Modern, fast, semver-respecting | plan §17 |
| 2026-04-17 | Notebook strategy = thin (option β) | Library-testable + scientific narrative preserved | plan §17 |
| 2026-04-17 | Repo strategy = extract to new repo | Public-ready; data leakage risk avoided | plan §17 |
| 2026-04-17 | Big-bang cutover (vs phased) | Simplest; daily workflow keeps working | plan §17 |
| 2026-04-19 | Synthetic sample = post-QC parquet (not raw) | TOA5 raw ingest too site-specific to fake | Phase 3 PR #2 |
| 2026-04-19 | Notebook 036 not ported | Interactive widget doesn't render headless | Phase 5 PR #4 |

---

## Results log (publishable / shipped artefacts)

| Date | Artefact | What |
|---|---|---|
| 2026-04-20 | `palmwtc==0.1.0` on PyPI | First public release. `pip install palmwtc` works for anyone. |
| 2026-04-20 | Zenodo DOI for v0.1.0 | Citable per release. (Update README placeholder once minted.) |
| 2026-04-19 | [palmwtc-0.1.0.dev0 wheel] | PyPI placeholder for name reservation. |
| 2026-04-19 | [13 tutorial notebooks](tutorials/index.md) | All execute headless on bundled sample |
| 2026-04-19 | Bundled synthetic sample | 3 MB parquet, deterministic seed=42, 5 edge cases injected |
| 2026-04-19 | Library API: 33 top-level + 7 subpackages | Full backward-compat re-exports for ported notebooks |

---

## Upcoming deadlines

| Date | What | Owner |
|---|---|---|
| TBD | Phase 8 release (v0.1.0 → PyPI + Zenodo DOI) | maintainer |
| TBD | First external collaborator onboarding | maintainer |

(No hard external deadlines; cadence is project-driven.)

---

## Active plan

The full implementation plan lives in the *flux_chamber* working repo at
`~/.claude/plans/venv-bin-python-scripts-run-notebooks-p-eventual-hellman.md`.

Active phase: **Phase 8 wrap-up — flux_chamber cutover** (only remaining item).
Rewrite ~14 flux_chamber notebook imports `from src.* import …` → `from palmwtc.* import …`,
delete `flux_chamber/src/` + `flux_chamber/scripts/run_notebooks.py` + `flux_chamber/dashboard/`,
replace `requirements.txt` with `palmwtc[ml,dashboard]`. Done as a separate PR
in the flux_chamber repo (not this one).

---

## Cross-references

- [`CLAUDE.md`](../CLAUDE.md) — AI-assistant project conventions
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — human-contributor guide
- [`CHANGELOG.md`](../CHANGELOG.md) — versioned release notes
- [`README.md`](../README.md) — user-facing landing
- [`CITATION.cff`](../CITATION.cff) — citation metadata

---

## Revision history

| Version | Date | Change |
|---|---|---|
| 0.9.0 | 2026-04-21 | v0.2.0 prep: drop palmwtc.dashboard subpackage + CLI command; replace [dashboard] with [interactive] extra. Tighter scope (chamber-flux algorithms only). |
| 0.8.0 | 2026-04-20 | v0.1.0 tagged. PyPI + GitHub Release + Zenodo DOI live. Cutover only remaining Phase 8 item. |
| 0.7.0 | 2026-04-20 | Phase 7 (docs site publication) merged. Active phase advanced to 8. |
| 0.6.0 | 2026-04-20 | Phase 6 (Streamlit dashboard) merged. Active phase advanced to 7. |
| 0.5.0 | 2026-04-20 | Initial PROJECT_PULSE created. Phases 1-5 logged as completed. |
