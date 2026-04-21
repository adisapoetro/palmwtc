"""Phase 1 smoke tests — verify the skeleton imports + CLI is wired."""

from __future__ import annotations

import subprocess
import sys


def test_palmwtc_imports() -> None:
    import palmwtc

    assert palmwtc.__version__
    assert palmwtc.__version__ != ""


def test_subpackages_import() -> None:
    """All planned subpackages exist as importable modules."""
    import palmwtc.data
    import palmwtc.flux
    import palmwtc.hardware
    import palmwtc.io
    import palmwtc.qc
    import palmwtc.validation
    import palmwtc.viz
    import palmwtc.windows  # noqa: F401


def test_cli_version() -> None:
    """`palmwtc --version` prints the package version and exits 0."""
    result = subprocess.run(
        [sys.executable, "-m", "palmwtc.cli", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "palmwtc" in result.stdout


def test_cli_info() -> None:
    """`palmwtc info` runs without error in Phase 1 stub state."""
    result = subprocess.run(
        [sys.executable, "-m", "palmwtc.cli", "info"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "palmwtc" in result.stdout


def test_data_paths_dataclass_shape() -> None:
    """DataPaths exists with the expected fields, even though resolve() is stubbed."""
    from palmwtc.config import DataPaths

    fields = {f for f in DataPaths.__dataclass_fields__}
    assert {"raw_dir", "processed_dir", "exports_dir", "config_dir", "site"} <= fields
