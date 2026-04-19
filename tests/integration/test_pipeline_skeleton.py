"""End-to-end pipeline integration test.

Phase 3 wires real pipeline execution against the bundled synthetic sample.
This is the canonical "does the package actually work" smoke test.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.integration
@pytest.mark.slow
def test_cli_run_against_synthetic_sample_succeeds() -> None:
    """`palmwtc run` exits 0 against the bundled synthetic sample (zero config)."""
    result = subprocess.run(
        [sys.executable, "-m", "palmwtc.cli", "run"],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,  # generous: synthetic flux step takes ~20s
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    # All four steps reported in summary output.
    for step in ("qc", "flux", "windows", "validation"):
        assert step in result.stdout
    assert "OK" in result.stdout
