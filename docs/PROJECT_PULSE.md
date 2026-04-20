---
title: palmwtc — Project Pulse
type: living-status-tracker
version: 0.5.0
last_updated: 2026-04-20
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
| Streamlit dashboard (Phase 6) | 🟡 Pending | Code in `flux_chamber/dashboard/`, not yet ported |
| Docs site publication (Phase 7) | 🟡 Partial | Jupyter-book builds in CI but no `gh-pages` deploy yet |
| First public release (Phase 8) | 🔴 Not started | PyPI name + trusted publishing + Zenodo not configured |
| CI matrix | 🟢 Green | Py 3.11/3.12/3.13 × ubuntu/macos all pass |
| Mypy | 🟡 Non-blocking | 2 pre-existing implicit-Optional warnings inherited from port |
| Test count | 🟢 445 passed | + 8 expected skips (`openpyxl` + `ipywidgets` extras) |

---

## Phase progress

| # | Phase | Status | Merged | Commit |
|---|---|---|---|---|
| 1 | Repo skeleton | ✓ Done | 2026-04-17 | `b33a5ab` |
| 2 | Port flux_chamber/src/ → palmwtc (12 modules) | ✓ Done | 2026-04-19 | `16ea472` |
| 3 | DataPaths + CLI + library pipeline + bundled sample | ✓ Done | 2026-04-19 | `cb1ec03` |
| 4 | Thin tutorial notebooks 010/020/030/033 | ✓ Done | 2026-04-19 | `64e0771` |
| 5 | Thin tutorial notebooks 011/022/023/025/026/031/032/034/035 | ✓ Done | 2026-04-19 | `76d5c4b` |
| 6 | Streamlit dashboard integration (`palmwtc.dashboard`) | ☐ Pending | — | — |
| 7 | Docs site publication (`palmwtc.github.io/palmwtc/`) | ☐ Partial | — | — |
| 8 | Old-repo cutover + first PyPI release + Zenodo DOI | ☐ Pending | — | — |

---

## Open blockers

| ID | Blocker | Owner | Severity | Opened | Notes |
|---|---|---|---|---|---|
| OB-001 | PyPI name not yet reserved | maintainer | 🟡 medium | 2026-04-17 | Manual `twine upload` of `0.0.1.dev0` placeholder. Blocks Phase 8. |
| OB-002 | PyPI Trusted Publishing not configured | maintainer | 🟡 medium | 2026-04-17 | One-time setup at pypi.org/manage/account/publishing/. Blocks Phase 8. |
| OB-003 | Zenodo-GitHub integration not enabled | maintainer | 🟡 medium | 2026-04-17 | Enable in zenodo.org *before* first tag, else first release gets no DOI. Blocks Phase 8. |
| OB-004 | `flux/cycles.py` has dead-code try/except for sibling import | AI | 🟢 low | 2026-04-19 | Code-review nit, deferred follow-up. |
| OB-005 | `viz/timeseries.py:23` docstring promises a function that was dropped | AI | 🟢 low | 2026-04-19 | Same — code-review nit, deferred. |
| OB-006 | Mypy: 2 pre-existing implicit-Optional warnings in `io/loaders.py`, `io/cloud.py` | AI | 🟢 low | 2026-04-17 | Inherited from upstream port. Non-blocking in CI. |

---

## Latest findings & changes (newest first)

| Date | Phase | What | Outcome |
|---|---|---|---|
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
| 2026-04-19 | [palmwtc-0.1.0.dev0 wheel] | Builds locally; not yet on PyPI. Awaiting Phase 8. |
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

Active phase: **Phase 6 — Streamlit dashboard integration.** Move
`flux_chamber/dashboard/` into `src/palmwtc/dashboard/`, gate behind
`palmwtc[dashboard]` extra, wire `palmwtc dashboard` CLI. Remaining
phases: Phase 7 (docs site publication), Phase 8 (cutover + first release).

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
| 0.5.0 | 2026-04-20 | Initial PROJECT_PULSE created. Phases 1-5 logged as completed. |
