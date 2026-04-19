"""Tests for palmwtc.pipeline (library-mode orchestrator)."""

from __future__ import annotations

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
