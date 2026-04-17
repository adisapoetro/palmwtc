"""End-to-end pipeline skeleton tests.

Phase 1 just verifies the CLI is invokable. Phase 3 wires real pipeline runs
against the bundled synthetic sample.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.integration
def test_cli_run_stub_exits_cleanly() -> None:
    """The Phase 1 `run` command is a stub; it should exit 2 (NotImplemented marker)."""
    result = subprocess.run(
        [sys.executable, "-m", "palmwtc.cli", "run", "--sample"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, result.stderr
    assert "not yet implemented" in result.stdout.lower()
