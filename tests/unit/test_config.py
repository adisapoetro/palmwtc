"""Tests for palmwtc.config.DataPaths layered resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from palmwtc.config import (
    ENV_CONFIG_FILE,
    ENV_DATA_DIR,
    DataPaths,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear env vars + redirect cwd-dependent yaml lookups so tests don't see real config."""
    monkeypatch.delenv(ENV_DATA_DIR, raising=False)
    monkeypatch.delenv(ENV_CONFIG_FILE, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("palmwtc.config.DEFAULT_PROJECT_CONFIG", tmp_path / "palmwtc.yaml")
    monkeypatch.setattr("palmwtc.config.DEFAULT_USER_CONFIG", tmp_path / ".palmwtc" / "config.yaml")


class TestResolveLayerOrder:
    """Verify each layer wins precedence over the layer below it."""

    def test_zero_config_falls_back_to_bundled_sample(self) -> None:
        paths = DataPaths.resolve()
        assert paths.source.startswith("sample")
        assert "synthetic" in str(paths.raw_dir)
        assert paths.site == "libz"

    def test_yaml_overrides_sample(self, tmp_path: Path) -> None:
        cfg = tmp_path / "palmwtc.yaml"
        cfg.write_text(f"raw_dir: {tmp_path / 'my-data'}\n")
        paths = DataPaths.resolve()
        assert paths.source.startswith("yaml")
        assert paths.raw_dir == (tmp_path / "my-data").resolve()

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "palmwtc.yaml"
        cfg.write_text(f"raw_dir: {tmp_path / 'yaml-data'}\n")
        env_dir = tmp_path / "env-data"
        env_dir.mkdir()
        monkeypatch.setenv(ENV_DATA_DIR, str(env_dir))

        paths = DataPaths.resolve()
        assert paths.source == "env"
        assert paths.raw_dir == env_dir.resolve()

    def test_kwargs_override_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_dir = tmp_path / "env-data"
        env_dir.mkdir()
        monkeypatch.setenv(ENV_DATA_DIR, str(env_dir))
        kwarg_dir = tmp_path / "kwarg-data"
        kwarg_dir.mkdir()

        paths = DataPaths.resolve(raw_dir=kwarg_dir)
        assert paths.source == "kwargs"
        assert paths.raw_dir == kwarg_dir.resolve()

    def test_explicit_config_file_arg_wins_over_default_yaml_locations(
        self, tmp_path: Path
    ) -> None:
        default_cfg = tmp_path / "palmwtc.yaml"
        default_cfg.write_text(f"raw_dir: {tmp_path / 'default-data'}\n")
        explicit_cfg = tmp_path / "custom.yaml"
        explicit_cfg.write_text(f"raw_dir: {tmp_path / 'explicit-data'}\n")

        paths = DataPaths.resolve(config_file=explicit_cfg)
        assert paths.raw_dir == (tmp_path / "explicit-data").resolve()


class TestPathDerivation:
    """When a yaml or env only provides raw_dir, derived paths must be sane."""

    def test_only_raw_dir_derives_sibling_paths(self, tmp_path: Path) -> None:
        raw = tmp_path / "project" / "Raw"
        raw.mkdir(parents=True)

        paths = DataPaths.resolve(raw_dir=raw)
        # Derived paths sit next to raw_dir under the project root.
        assert (
            paths.processed_dir == (tmp_path / "project" / "Data" / "Integrated_QC_Data").resolve()
        )
        assert paths.exports_dir == (tmp_path / "project" / "exports").resolve()
        assert paths.config_dir == (tmp_path / "project" / "config").resolve()

    def test_yaml_can_override_individual_paths(self, tmp_path: Path) -> None:
        cfg = tmp_path / "palmwtc.yaml"
        cfg.write_text(f"raw_dir: {tmp_path / 'r'}\nexports_dir: {tmp_path / 'somewhere-else'}\n")
        paths = DataPaths.resolve()
        assert paths.exports_dir == (tmp_path / "somewhere-else").resolve()
        # processed_dir + config_dir derived under raw_dir parent
        assert paths.processed_dir == (tmp_path / "Data" / "Integrated_QC_Data").resolve()


class TestExtras:
    def test_yaml_extras_passed_through(self, tmp_path: Path) -> None:
        cfg = tmp_path / "palmwtc.yaml"
        cfg.write_text(f"raw_dir: {tmp_path}\nnotebook_timeout: 1800\nparallel_workers: 4\n")
        paths = DataPaths.resolve()
        assert paths.extras == {"notebook_timeout": 1800, "parallel_workers": 4}


class TestValidation:
    def test_invalid_site_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="site must be"):
            DataPaths.resolve(raw_dir=tmp_path, site="bogus")  # type: ignore[arg-type]

    def test_describe_emits_multi_line_summary(self) -> None:
        paths = DataPaths.resolve()
        out = paths.describe()
        assert "DataPaths" in out
        assert "raw_dir" in out
        assert "site=libz" in out

    def test_with_overrides_returns_new_frozen_instance(self, tmp_path: Path) -> None:
        original = DataPaths.resolve(raw_dir=tmp_path)
        overridden = original.with_overrides(site="cige")
        assert overridden.site == "cige"
        assert original.site == "libz"  # original unchanged
        assert overridden.raw_dir == original.raw_dir
