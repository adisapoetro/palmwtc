"""palmwtc.notebooks_runner — Papermill-mode pipeline orchestrator.

Ported from ``flux_chamber/scripts/run_notebooks.py`` with these changes:

- Notebook directory is now resolved via ``DataPaths.extras['notebooks_dir']``
  rather than walking up from the script location.
- Output directory mirrors that resolution.
- Spine/parallel split preserved exactly.
- Thread-saturation env vars set as before.
- ``BATCH_MODE=1`` set by default so widget cells gracefully skip.

The library-mode equivalent (no papermill, faster, headless) lives in
``palmwtc.pipeline``. Use this module when you want the full executed
HTML reports as documentation of a run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# Saturate BLAS/OpenMP/numexpr threads on Apple Silicon before any numpy import
# downstream pins thread counts. Safe to set here since papermill spawns fresh
# kernels that inherit this environment.
_DEFAULT_THREADS = str(os.cpu_count() or 8)
for _var in (
    "VECLIB_MAXIMUM_THREADS",  # Apple Accelerate (macOS NumPy)
    "OMP_NUM_THREADS",  # scikit-learn, XGBoost, C extensions
    "NUMEXPR_NUM_THREADS",  # pandas eval/query
    "OPENBLAS_NUM_THREADS",  # no-op on Accelerate builds, harmless
    "MKL_NUM_THREADS",  # no-op on Accelerate builds, harmless
):
    os.environ.setdefault(_var, _DEFAULT_THREADS)
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

# Strict sequential pipeline spine (per CLAUDE.md §2): 010 → 020 → 030 → 040.
SPINE_PREFIXES = {10, 20, 30, 40}


@dataclass(frozen=True)
class NotebookResult:
    """Outcome of executing one notebook."""

    name: str
    ok: bool
    elapsed_seconds: float
    error: str = ""


def discover_notebooks(notebooks_dir: Path) -> list[dict]:
    """Find .ipynb files in ``notebooks_dir`` root (no subdirs), return sorted metadata."""
    notebooks: list[dict] = []
    for nb_path in sorted(notebooks_dir.glob("*.ipynb")):
        match = re.match(r"(\d+)", nb_path.name)
        sort_key = int(match.group(1)) if match else 9999

        with open(nb_path) as f:
            meta = json.load(f).get("metadata", {})
        language = meta.get("kernelspec", {}).get("language", "python").lower()

        notebooks.append(
            {
                "path": nb_path,
                "name": nb_path.name,
                "sort_key": sort_key,
                "language": language,
            }
        )

    notebooks.sort(key=lambda x: x["sort_key"])
    return notebooks


def _convert_to_html(nb_path: Path, html_path: Path) -> None:
    """Convert an executed .ipynb to a clean HTML report (no code cells)."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "jupyter",
            "nbconvert",
            "--to",
            "html",
            "--no-input",
            "--output",
            str(html_path),
            str(nb_path),
        ],
        check=True,
        capture_output=True,
    )


def _run_with_papermill(nb_path: Path, output_path: Path, timeout: int) -> tuple[bool, float, str]:
    """Execute a notebook via papermill. Returns (success, elapsed, error_msg)."""
    import papermill as pm

    os.environ["BATCH_MODE"] = "1"
    kernel_name = None  # let papermill use the notebook's own kernel
    export_html = output_path.suffix == ".html"

    t0 = time.time()
    try:
        if export_html:
            with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as tmp:
                tmp_ipynb = Path(tmp.name)
            try:
                pm.execute_notebook(
                    str(nb_path),
                    str(tmp_ipynb),
                    kernel_name=kernel_name,
                    cwd=str(nb_path.parent),
                    timeout=timeout,
                )
                _convert_to_html(tmp_ipynb, output_path)
            finally:
                tmp_ipynb.unlink(missing_ok=True)
        else:
            pm.execute_notebook(
                str(nb_path),
                str(output_path),
                kernel_name=kernel_name,
                cwd=str(nb_path.parent),
                timeout=timeout,
            )

        return True, time.time() - t0, ""

    except pm.PapermillExecutionError as e:
        return False, time.time() - t0, f"Cell {e.exec_count}: {e.ename}: {e.evalue}"

    except Exception as e:
        return False, time.time() - t0, str(e)[:500]


def run_notebooks(
    notebooks_dir: Path,
    output_dir: Path | None = None,
    *,
    start: int | None = None,
    only: list[int] | None = None,
    skip: list[int] | None = None,
    timeout: int = 1800,
    inplace: bool = False,
    keep_going: bool = False,
    parallel: int = 1,
) -> list[NotebookResult]:
    """Run all notebooks in ``notebooks_dir``, sorted by numeric prefix.

    See ``flux_chamber/scripts/run_notebooks.py`` for the original CLI shape.
    The behaviour here is byte-equivalent: spine notebooks (010/020/030/040)
    run sequentially first, then non-spine notebooks run with ``parallel``
    workers (default 1 = sequential).
    """
    notebooks = discover_notebooks(notebooks_dir)
    if not notebooks:
        print(f"[notebooks_runner] no notebooks in {notebooks_dir}")
        return []

    if start is not None:
        notebooks = [nb for nb in notebooks if nb["sort_key"] >= start]
    if only is not None:
        notebooks = [nb for nb in notebooks if nb["sort_key"] in set(only)]
    if skip is not None:
        notebooks = [nb for nb in notebooks if nb["sort_key"] not in set(skip)]

    if not inplace:
        output_dir = output_dir or (notebooks_dir / "executed")
        output_dir.mkdir(exist_ok=True)
    else:
        output_dir = notebooks_dir  # ignored when inplace, kept for type-cleanliness

    def _output_for(nb: dict) -> Path:
        return nb["path"] if inplace else output_dir / nb["path"].with_suffix(".html").name

    print(f"{'=' * 65}")
    print(f"  Notebook Runner (papermill) — {len(notebooks)} notebooks")
    print(f"  Timeout: {timeout}s | Output: {'inplace' if inplace else str(output_dir)}")
    print(f"  BATCH_MODE=1 | threads={_DEFAULT_THREADS} | parallel workers={parallel}")
    print(f"{'=' * 65}")
    for i, nb in enumerate(notebooks, 1):
        lang_tag = f"[{nb['language'].upper()}]"
        print(f"  {i:2d}. {lang_tag:8s} {nb['name']}")
    print(f"{'=' * 65}")

    spine = [nb for nb in notebooks if nb["sort_key"] in SPINE_PREFIXES]
    rest = [nb for nb in notebooks if nb["sort_key"] not in SPINE_PREFIXES]

    results: list[NotebookResult] = []
    aborted = False

    # Spine notebooks: always sequential (each depends on the previous).
    for i, nb in enumerate(spine, 1):
        print(f"\n[spine {i}/{len(spine)}] {nb['name']} ({nb['language']}) ...")
        ok, elapsed, err = _run_with_papermill(nb["path"], _output_for(nb), timeout)
        print(f"    {'OK' if ok else 'FAILED'} ({elapsed:.0f}s)")
        if err:
            print(f"    Error: {err}")
        results.append(NotebookResult(nb["name"], ok, elapsed, err))
        if not ok and not keep_going:
            print(f"\n    Stopping. Re-run with: --start {nb['sort_key']}")
            aborted = True
            break

    # Non-spine notebooks: independent, may run sequentially or in parallel.
    if rest and not aborted:
        workers = max(1, parallel)
        if workers == 1:
            for i, nb in enumerate(rest, 1):
                print(f"\n[rest {i}/{len(rest)}] {nb['name']} ({nb['language']}) ...")
                ok, elapsed, err = _run_with_papermill(nb["path"], _output_for(nb), timeout)
                print(f"    {'OK' if ok else 'FAILED'} ({elapsed:.0f}s)")
                if err:
                    print(f"    Error: {err}")
                results.append(NotebookResult(nb["name"], ok, elapsed, err))
                if not ok and not keep_going:
                    print(f"\n    Stopping. Re-run with: --start {nb['sort_key']}")
                    break
        else:
            print(f"\n--- Launching {len(rest)} non-spine notebooks across {workers} workers ---")
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_run_with_papermill, nb["path"], _output_for(nb), timeout): nb
                    for nb in rest
                }
                for fut in as_completed(futures):
                    nb = futures[fut]
                    ok, elapsed, err = fut.result()
                    print(f"  [{'OK' if ok else 'FAIL'}] {nb['name']:55s} {elapsed:6.0f}s")
                    if err:
                        print(f"         {err}")
                    results.append(NotebookResult(nb["name"], ok, elapsed, err))

    n_ok = sum(1 for r in results if r.ok)
    n_fail = sum(1 for r in results if not r.ok)
    total = sum(r.elapsed_seconds for r in results)
    print(f"\n{'=' * 65}")
    print(f"  SUMMARY: {n_ok} passed, {n_fail} failed, {total:.0f}s total")
    print(f"{'-' * 65}")
    for r in results:
        tag = "PASS" if r.ok else "FAIL"
        print(f"  [{tag}] {r.name:55s} {r.elapsed_seconds:6.0f}s")
    print(f"{'=' * 65}")

    return results
