"""Execute each shipped tutorial notebook headless via papermill.

This is the per-notebook acceptance gate from Phase 4: every tutorial
notebook in `notebooks/` must execute end-to-end against the bundled
synthetic sample without raising. Output is discarded (we don't assert
on cell content here — that lives in the unit tests for the underlying
library functions).

If you add a new tutorial notebook, just drop it in `notebooks/` and the
parametrize loop picks it up automatically. To exclude one (e.g. a
widget-only notebook), add the filename to the SKIP set below.
"""

from __future__ import annotations

from pathlib import Path

import pytest

NB_DIR = Path(__file__).resolve().parent.parent.parent / "notebooks"
# Notebooks that require real LIBZ data (PALMWTC_LIBZ_DATA_ROOT) and therefore
# cannot run on the bundled-synthetic CI runner. They ship with locally-executed
# outputs already embedded; CI just skips the re-execution.
SKIP: set[str] = {
    "001_End_to_End_LIBZ.ipynb",
}
TIMEOUT_SECONDS = 180


def _discover() -> list[Path]:
    return [p for p in sorted(NB_DIR.glob("*.ipynb")) if p.name not in SKIP]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("nb_path", _discover(), ids=lambda p: p.name)
def test_notebook_executes_headless(nb_path: Path, tmp_path: Path) -> None:
    """`papermill` execution must complete with no exceptions."""
    pm = pytest.importorskip("papermill")

    output = tmp_path / nb_path.name
    pm.execute_notebook(
        str(nb_path),
        str(output),
        cwd=str(nb_path.parent),
        timeout=TIMEOUT_SECONDS,
    )
    assert output.exists()
