"""Tests for palmwtc.dashboard.

These don't actually launch Streamlit (that needs a browser + interactive
session). They verify the module surface, the CLI gate behaviour, and
the helper functions that are unit-testable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from palmwtc.dashboard import is_streamlit_available


class TestSubpackage:
    def test_is_streamlit_available_returns_bool(self) -> None:
        assert isinstance(is_streamlit_available(), bool)

    def test_subpackage_imports_without_streamlit(self) -> None:
        """`import palmwtc.dashboard` must work even without streamlit installed."""
        import palmwtc.dashboard  # noqa: F401


@pytest.mark.skipif(not is_streamlit_available(), reason="needs [dashboard] extra")
class TestAppModule:
    def test_app_module_imports(self) -> None:
        import palmwtc.dashboard.app

        assert hasattr(palmwtc.dashboard.app, "main")
        assert hasattr(palmwtc.dashboard.app, "cli_entry")

    def test_resolve_qc_path_finds_synthetic(self) -> None:
        from palmwtc.config import DataPaths
        from palmwtc.dashboard.app import _resolve_qc_path

        paths = DataPaths.resolve()
        qc_path = _resolve_qc_path(paths)
        assert qc_path is not None, "bundled synthetic QC parquet should be found"
        assert qc_path.exists()
        assert qc_path.suffix == ".parquet"

    def test_load_qc_returns_dataframe(self, tmp_path: Path) -> None:
        from palmwtc.dashboard.app import _load_qc

        # Construct a tiny parquet so we don't depend on the bundled one's shape.
        parquet = tmp_path / "tiny.parquet"
        pd.DataFrame(
            {"TIMESTAMP": pd.date_range("2026-04-20", periods=3, freq="30min"), "x": [1, 2, 3]}
        ).to_parquet(parquet)

        df = _load_qc(parquet)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3


class TestCliGate:
    def test_dashboard_subcommand_listed_in_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "palmwtc.cli", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "dashboard" in result.stdout

    @pytest.mark.skipif(is_streamlit_available(), reason="path tested when streamlit absent")
    def test_dashboard_command_errors_clearly_without_extra(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "palmwtc.cli", "dashboard"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "palmwtc[dashboard]" in result.stdout
