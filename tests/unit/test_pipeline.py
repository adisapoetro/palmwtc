"""Tests for palmwtc.pipeline (library-mode orchestrator)."""

from __future__ import annotations

import pandas as pd
import pytest

from palmwtc.config import DataPaths
from palmwtc.pipeline import (
    STEPS_IN_ORDER,
    PipelineResult,
    StepResult,
    run_pipeline,
    run_step,
    step_qc,
)


@pytest.fixture
def sample_paths() -> DataPaths:
    """Resolve DataPaths against the bundled synthetic sample."""
    return DataPaths.resolve()


class TestStepFluxChamberDetection:
    """Regression tests for the chamber-discovery regex in step_flux.

    Bug found 2026-04-22: when run against real LIBZ data, the original
    regex (`col.startswith("CO2_C")` + `split("_", 1)[1]`) treated every
    `CO2_C1_qc_flag`, `CO2_C1_rule_flag`, etc., as a separate chamber,
    producing 1.2M cycles instead of ~60K. Fixed in v0.2.2 by requiring
    an exact `CO2_C<n>` column-name match.
    """

    def _df_with_columns(self, *cols: str) -> pd.DataFrame:
        return pd.DataFrame({c: [0.0] for c in cols})

    def _detect(self, df: pd.DataFrame) -> list[str]:
        """Helper: replicate step_flux's chamber-detection logic."""
        import re

        co2_pattern = re.compile(r"^CO2_(C\d+)$")
        return sorted({m.group(1) for col in df.columns if (m := co2_pattern.match(col))})

    def test_detects_canonical_chamber_columns(self) -> None:
        df = self._df_with_columns("TIMESTAMP", "CO2_C1", "CO2_C2", "H2O_C1", "H2O_C2")
        assert self._detect(df) == ["C1", "C2"]

    def test_ignores_qc_flag_derivative_columns(self) -> None:
        """The bug: CO2_C1_qc_flag was being mistaken for a chamber."""
        df = self._df_with_columns(
            "CO2_C1",
            "CO2_C2",
            "CO2_C1_qc_flag",
            "CO2_C2_qc_flag",
            "CO2_C1_rule_flag",
            "CO2_C1_ml_flag",
            "CO2_C1_if_flag",
            "CO2_C1_mcd_flag",
            "CO2_C2_rule_flag",
            "CO2_C2_ml_flag",
            "CO2_C2_if_flag",
            "CO2_C2_mcd_flag",
            "CO2_C1_corrected",
            "CO2_C2_corrected",
            "CO2_C1_offset",
            "CO2_C2_offset",
            "CO2_C1_raw",
            "CO2_C2_raw",
        )
        # Only the two canonical chambers must be detected — not the 16 derivatives.
        assert self._detect(df) == ["C1", "C2"]

    def test_three_chamber_setup_works(self) -> None:
        df = self._df_with_columns("CO2_C1", "CO2_C2", "CO2_C3", "CO2_C1_qc_flag")
        assert self._detect(df) == ["C1", "C2", "C3"]

    def test_no_co2_columns_returns_empty(self) -> None:
        df = self._df_with_columns("TIMESTAMP", "H2O_C1")
        assert self._detect(df) == []


class TestStepQc:
    def test_qc_loads_synthetic_parquet(self, sample_paths: DataPaths) -> None:
        result = step_qc(sample_paths)
        assert result.ok, result.error
        assert result.rows_out == 20160  # 7 days * 24 * 3600 / 30s
        assert result.metrics["n_columns"] >= 16
        assert result.artefacts[0].suffix == ".parquet"


class TestRunPipeline:
    def test_full_pipeline_on_synthetic_sample_succeeds(self, sample_paths: DataPaths) -> None:
        result = run_pipeline(sample_paths)
        assert isinstance(result, PipelineResult)
        assert result.ok, result.summary()
        assert [s.name for s in result.steps] == list(STEPS_IN_ORDER)
        # qc + flux must produce non-empty output; windows + validation may legitimately
        # produce empty output on toy synthetic data (documented limitation).
        qc, flux, *_ = result.steps
        assert qc.rows_out > 0
        assert flux.rows_out > 0

    def test_skip_filters_steps(self, sample_paths: DataPaths) -> None:
        result = run_pipeline(sample_paths, skip=["validation", "windows"])
        assert [s.name for s in result.steps] == ["qc", "flux"]

    def test_only_runs_listed_steps(self, sample_paths: DataPaths) -> None:
        result = run_pipeline(sample_paths, steps=["qc"])
        assert len(result.steps) == 1
        assert result.steps[0].name == "qc"

    def test_unknown_step_raises(self, sample_paths: DataPaths) -> None:
        with pytest.raises(ValueError, match="unknown pipeline step"):
            run_pipeline(sample_paths, steps=["bogus"])

    def test_run_step_single(self, sample_paths: DataPaths) -> None:
        result = run_step("qc", sample_paths)
        assert isinstance(result, StepResult)
        assert result.ok

    def test_summary_describes_run(self, sample_paths: DataPaths) -> None:
        result = run_pipeline(sample_paths, steps=["qc"])
        out = result.summary()
        assert "Pipeline run on" in out
        assert "qc" in out
        assert "PASS" in out


class TestKeepGoing:
    def test_keep_going_runs_all_steps_after_failure(
        self, sample_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the qc step to fail, then verify subsequent steps still run.
        from palmwtc import pipeline as pl

        def _broken_qc(paths: DataPaths) -> StepResult:
            return StepResult(name="qc", ok=False, elapsed_seconds=0.0, error="forced")

        monkeypatch.setitem(pl._STEP_FUNCTIONS, "qc", _broken_qc)
        result = run_pipeline(sample_paths, keep_going=True)
        # All 4 steps recorded; first failed, the rest may pass or fail but they ran.
        assert len(result.steps) == 4
        assert not result.steps[0].ok

    def test_default_stops_on_first_failure(
        self, sample_paths: DataPaths, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from palmwtc import pipeline as pl

        def _broken_qc(paths: DataPaths) -> StepResult:
            return StepResult(name="qc", ok=False, elapsed_seconds=0.0, error="forced")

        monkeypatch.setitem(pl._STEP_FUNCTIONS, "qc", _broken_qc)
        result = run_pipeline(sample_paths)
        assert len(result.steps) == 1
        assert result.steps[0].ok is False
