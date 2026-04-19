"""palmwtc.config — DataPaths layered resolver.

Layered resolution order (highest precedence first):

1. **Explicit kwargs** — `DataPaths.resolve(raw_dir=..., processed_dir=...)`.
2. **CLI flags** — passed through by ``palmwtc run --data-dir ...``.
3. **Environment variable** ``PALMWTC_DATA_DIR``.
4. **YAML config** — ``./palmwtc.yaml`` then ``~/.palmwtc/config.yaml``.
5. **Bundled synthetic sample** — ``palmwtc.data.sample_dir("synthetic")``.

The last layer always succeeds, so ``DataPaths.resolve()`` never raises.
A user with no config and no env var still gets a working `palmwtc run`
against the bundled synthetic dataset — the zero-config first-run promise.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml

Site = Literal["libz", "cige"]

ENV_DATA_DIR = "PALMWTC_DATA_DIR"
ENV_CONFIG_FILE = "PALMWTC_CONFIG"
DEFAULT_USER_CONFIG = Path.home() / ".palmwtc" / "config.yaml"
DEFAULT_PROJECT_CONFIG = Path.cwd() / "palmwtc.yaml"


@dataclass(frozen=True)
class DataPaths:
    """Resolved I/O paths for a palmwtc run.

    All four paths are absolute. ``site`` indicates which calibration track
    the data belongs to (``"libz"`` for the chamber site, ``"cige"`` for
    SMSE field observations — currently CIGE is out-of-scope for palmwtc 0.1).
    """

    raw_dir: Path
    processed_dir: Path
    exports_dir: Path
    config_dir: Path
    site: Site = "libz"
    source: str = "default"
    """Where the resolved values came from: 'kwargs', 'env', 'yaml', or 'sample'."""

    extras: dict[str, Any] = field(default_factory=dict)
    """Arbitrary extra config from yaml (notebook-runner timeout, parallel workers, etc.)."""

    def __post_init__(self) -> None:
        # Validate site discriminator (frozen dataclass — use object.__setattr__ via internal API).
        if self.site not in ("libz", "cige"):
            raise ValueError(f"site must be 'libz' or 'cige', got {self.site!r}")

    def with_overrides(self, **kwargs: Any) -> DataPaths:
        """Return a new DataPaths with selected fields overridden. Frozen-friendly."""
        return replace(self, **kwargs)

    def describe(self) -> str:
        """Human-readable multi-line summary, used by `palmwtc info`."""
        return (
            f"DataPaths (source={self.source}, site={self.site}):\n"
            f"  raw_dir       = {self.raw_dir}\n"
            f"  processed_dir = {self.processed_dir}\n"
            f"  exports_dir   = {self.exports_dir}\n"
            f"  config_dir    = {self.config_dir}\n"
            f"  extras        = {self.extras or '<none>'}"
        )

    @classmethod
    def resolve(
        cls,
        *,
        raw_dir: Path | str | None = None,
        processed_dir: Path | str | None = None,
        exports_dir: Path | str | None = None,
        config_dir: Path | str | None = None,
        site: Site | None = None,
        config_file: Path | str | None = None,
    ) -> DataPaths:
        """Resolve DataPaths from layered sources.

        Resolution order (highest precedence first):
        1. Any kwarg explicitly passed here (typically by the CLI).
        2. ``PALMWTC_DATA_DIR`` env var (sets ``raw_dir`` to that path).
        3. YAML config (``config_file`` arg, then ``$PALMWTC_CONFIG`` env var,
           then ``./palmwtc.yaml``, then ``~/.palmwtc/config.yaml``).
        4. Bundled synthetic sample (always succeeds).

        Returns a frozen DataPaths whose ``source`` field records which layer
        contributed the primary ``raw_dir``.
        """
        from palmwtc.data import sample_dir

        explicit_kwargs = {
            "raw_dir": raw_dir,
            "processed_dir": processed_dir,
            "exports_dir": exports_dir,
            "config_dir": config_dir,
            "site": site,
        }
        explicit_kwargs = {k: v for k, v in explicit_kwargs.items() if v is not None}

        yaml_kwargs, yaml_extras, yaml_path = _load_yaml(config_file)
        env_raw_dir = os.environ.get(ENV_DATA_DIR)

        merged: dict[str, Any] = {**yaml_kwargs}
        if env_raw_dir:
            merged["raw_dir"] = env_raw_dir
        merged.update(explicit_kwargs)

        if "raw_dir" in merged:
            base_raw = Path(merged["raw_dir"]).expanduser().resolve()
            source = (
                "kwargs"
                if "raw_dir" in explicit_kwargs
                else "env"
                if env_raw_dir
                else f"yaml ({yaml_path})"
            )
        else:
            base_raw = sample_dir("synthetic")
            source = "sample (bundled synthetic)"

        return cls(
            raw_dir=Path(merged.get("raw_dir", base_raw)).expanduser().resolve(),
            processed_dir=_path_or_default(
                merged.get("processed_dir"), base_raw.parent / "Data" / "Integrated_QC_Data"
            ),
            exports_dir=_path_or_default(merged.get("exports_dir"), base_raw.parent / "exports"),
            config_dir=_path_or_default(merged.get("config_dir"), base_raw.parent / "config"),
            site=merged.get("site", "libz"),
            source=source,
            extras=yaml_extras,
        )


def _path_or_default(value: Any, default: Path) -> Path:
    if value is None:
        return Path(default).expanduser().resolve()
    return Path(value).expanduser().resolve()


def _load_yaml(
    explicit_path: Path | str | None,
) -> tuple[dict[str, Any], dict[str, Any], Path | None]:
    """Find and load a YAML config from layered locations. Returns ({paths}, {extras}, path)."""
    candidates: list[Path] = []
    if explicit_path is not None:
        candidates.append(Path(explicit_path).expanduser())
    if env_path := os.environ.get(ENV_CONFIG_FILE):
        candidates.append(Path(env_path).expanduser())
    candidates.extend([DEFAULT_PROJECT_CONFIG, DEFAULT_USER_CONFIG])

    for path in candidates:
        if path.is_file():
            with path.open() as f:
                data = yaml.safe_load(f) or {}
            paths = {
                k: data[k]
                for k in ("raw_dir", "processed_dir", "exports_dir", "config_dir", "site")
                if k in data
            }
            extras = {k: v for k, v in data.items() if k not in paths}
            return paths, extras, path

    return {}, {}, None
