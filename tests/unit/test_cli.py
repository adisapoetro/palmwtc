"""Tests for palmwtc.cli (typer subcommands)."""

from __future__ import annotations

import subprocess
import sys

import pytest


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "palmwtc.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )


class TestVersion:
    def test_dash_dash_version(self) -> None:
        result = _run_cli("--version")
        assert result.returncode == 0
        assert "palmwtc" in result.stdout

    def test_dash_v_short_flag(self) -> None:
        result = _run_cli("-V")
        assert result.returncode == 0
        assert "palmwtc" in result.stdout


class TestInfo:
    def test_info_prints_data_paths(self) -> None:
        result = _run_cli("info")
        assert result.returncode == 0
        assert "DataPaths" in result.stdout
        assert "raw_dir" in result.stdout

    def test_info_with_explicit_raw_dir(self, tmp_path) -> None:
        result = _run_cli("info", "--raw-dir", str(tmp_path))
        assert result.returncode == 0
        assert str(tmp_path.resolve()) in result.stdout


class TestSample:
    def test_sample_path_prints_synthetic_dir(self) -> None:
        result = _run_cli("sample", "path")
        assert result.returncode == 0
        assert "synthetic" in result.stdout

    def test_sample_fetch_is_a_stub(self) -> None:
        result = _run_cli("sample", "fetch")
        assert result.returncode == 2
        assert "not yet implemented" in result.stdout.lower()


class TestRun:
    @pytest.mark.slow
    @pytest.mark.integration
    def test_run_against_synthetic_succeeds(self) -> None:
        """End-to-end: `palmwtc run` against bundled sample exits 0."""
        result = _run_cli("run")
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        assert "OK" in result.stdout
        assert "Total:" in result.stdout

    def test_run_only_qc_succeeds_quickly(self) -> None:
        """Run only the qc step — fast subset of the full pipeline."""
        result = _run_cli("run", "--only", "qc")
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        assert "qc" in result.stdout

    def test_run_with_unknown_step_exits_nonzero(self) -> None:
        result = _run_cli("run", "--only", "bogus")
        assert result.returncode != 0


class TestDashboard:
    """The `dashboard` subcommand was removed in v0.2.0 (out of scope)."""

    def test_dashboard_subcommand_removed(self) -> None:
        result = _run_cli("--help")
        assert result.returncode == 0
        assert "dashboard" not in result.stdout

    def test_dashboard_invocation_errors(self) -> None:
        result = _run_cli("dashboard")
        # typer exits non-zero with a "no such command" message.
        assert result.returncode != 0
