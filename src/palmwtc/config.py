"""Configuration types for palmwtc — paths, defaults, CLI overrides.

This module defines :class:`DataPaths`, the single source of truth for
where palmwtc reads data from and writes data to.  Paths resolve in this
precedence order (highest first):

1. Explicit keyword arguments to :py:meth:`DataPaths.resolve`.
2. CLI flags (``palmwtc run --raw-dir ...``).
3. Environment variable ``PALMWTC_DATA_DIR``.
4. YAML config (``./palmwtc.yaml`` then ``~/.palmwtc/config.yaml``).
5. Bundled synthetic sample (``palmwtc.data.sample_dir("synthetic")``).

The last layer always succeeds so ``palmwtc run`` works with zero config.

Exported names
--------------
DataPaths
    Frozen dataclass that carries the four resolved directory paths plus
    the ``site`` discriminator and any extra YAML keys.
Site
    Literal type alias (``"libz"`` or ``"cige"``) used by ``DataPaths.site``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml

Site = Literal["libz", "cige"]
"""Calibration-track discriminator.

``"libz"``
    Chamber data from the LIBZ site (Riau — the primary calibration track).
``"cige"``
    Field observations from the SMSE/CIGE site (South Sumatra — out of scope
    for palmwtc 0.1; reserved for future use).
"""

ENV_DATA_DIR = "PALMWTC_DATA_DIR"
ENV_CONFIG_FILE = "PALMWTC_CONFIG"
DEFAULT_USER_CONFIG = Path.home() / ".palmwtc" / "config.yaml"
DEFAULT_PROJECT_CONFIG = Path.cwd() / "palmwtc.yaml"


@dataclass(frozen=True)
class DataPaths:
    """Resolved filesystem paths for palmwtc input and output data.

    ``DataPaths`` is a frozen dataclass that carries four absolute directory
    paths together with a calibration-track discriminator (``site``) and any
    extra keys that were present in the YAML config.

    You rarely construct this class directly.  Use the class method
    :py:meth:`resolve` instead — it builds a ``DataPaths`` from the layered
    resolution chain (kwargs → env var → YAML → bundled synthetic sample) and
    records which layer contributed the primary ``raw_dir`` in the ``source``
    field.

    Resolution order (highest precedence first)
    -------------------------------------------
    1. Explicit keyword arguments passed to :py:meth:`resolve`.
    2. Environment variable ``PALMWTC_DATA_DIR`` (sets ``raw_dir`` only).
    3. YAML config — first of: ``config_file`` arg, ``$PALMWTC_CONFIG`` env,
       ``./palmwtc.yaml``, ``~/.palmwtc/config.yaml``.
    4. Bundled synthetic sample (``palmwtc.data.sample_dir("synthetic")``).

    Parameters
    ----------
    raw_dir : Path
        Directory that contains the raw chamber measurement files (LI-850
        CSV/parquet).  Always absolute.
    processed_dir : Path
        Directory for quality-controlled, integrated output files written by
        ``palmwtc qc``.  Defaults to ``<raw_dir.parent>/Data/Integrated_QC_Data``.
    exports_dir : Path
        Directory for final pipeline exports (figures, summaries, reports).
        Defaults to ``<raw_dir.parent>/exports``.
    config_dir : Path
        Directory that contains site-specific configuration files (calibration
        coefficients, breakpoint tables, etc.).  Defaults to
        ``<raw_dir.parent>/config``.
    site : {"libz", "cige"}, default ``"libz"``
        Calibration-track discriminator.  ``"libz"`` for the LIBZ chamber
        site; ``"cige"`` for SMSE/CIGE field observations (reserved, currently
        out of scope).
    source : str, default ``"default"``
        Read-only provenance tag set by :py:meth:`resolve` to indicate which
        resolution layer contributed ``raw_dir``.  Possible values:
        ``"kwargs"``, ``"env"``, ``"yaml (<path>)"``,
        ``"sample (bundled synthetic)"``.
    extras : dict[str, Any], default ``{}``
        Any YAML keys that are not one of the four path keys or ``site`` are
        collected here (e.g. ``parallel_workers``, ``notebook_timeout``).

    Attributes
    ----------
    raw_dir : Path
        Absolute path to raw input data.
    processed_dir : Path
        Absolute path to QC output data.
    exports_dir : Path
        Absolute path to pipeline exports.
    config_dir : Path
        Absolute path to site configuration files.
    site : str
        Calibration-track identifier, ``"libz"`` or ``"cige"``.
    source : str
        Provenance label produced by :py:meth:`resolve`.
    extras : dict[str, Any]
        Extra YAML keys not in the standard path set.

    Methods
    -------
    resolve(**kwargs) -> DataPaths
        Class method — build a ``DataPaths`` from the layered resolution chain.
    with_overrides(**kwargs) -> DataPaths
        Return a new ``DataPaths`` with selected fields replaced.
    describe() -> str
        Return a human-readable multi-line summary of all resolved paths.

    Examples
    --------
    Using the bundled synthetic sample (works with no config file):

    >>> from palmwtc.config import DataPaths
    >>> paths = DataPaths.resolve()
    >>> "synthetic" in str(paths.raw_dir)  # doctest: +ELLIPSIS
    True
    >>> paths.source
    'sample (bundled synthetic)'
    """

    raw_dir: Path
    processed_dir: Path
    exports_dir: Path
    config_dir: Path
    site: Site = "libz"
    source: str = "default"
    """Provenance tag: which resolution layer set ``raw_dir``."""

    extras: dict[str, Any] = field(default_factory=dict)
    """Extra YAML keys not in the standard path set (e.g. ``parallel_workers``)."""

    def __post_init__(self) -> None:
        # Validate site discriminator (frozen dataclass — use object.__setattr__ via internal API).
        if self.site not in ("libz", "cige"):
            raise ValueError(f"site must be 'libz' or 'cige', got {self.site!r}")

    def with_overrides(self, **kwargs: Any) -> DataPaths:
        """Return a new ``DataPaths`` with selected fields replaced.

        Because ``DataPaths`` is frozen, you cannot change fields in-place.
        This method creates a copy with only the specified fields changed; all
        other fields keep their existing values.

        Accepted keyword arguments match the dataclass fields:
        ``raw_dir``, ``processed_dir``, ``exports_dir``, ``config_dir``,
        ``site``, ``source``, ``extras``.

        Parameters
        ----------
        **kwargs : Any
            Field names and their new values.  Any combination of the public
            ``DataPaths`` fields is valid.

        Returns
        -------
        DataPaths
            A new frozen ``DataPaths`` instance with the overridden values.

        Raises
        ------
        TypeError
            If an unknown field name is passed.
        ValueError
            If ``site`` is overridden with a value other than ``"libz"`` or
            ``"cige"``.

        Examples
        --------
        Override ``exports_dir`` while keeping everything else:

        >>> from pathlib import Path
        >>> from palmwtc.config import DataPaths
        >>> original = DataPaths.resolve()
        >>> modified = original.with_overrides(exports_dir=Path("/tmp/my_exports"))
        >>> modified.exports_dir
        PosixPath('/tmp/my_exports')
        >>> modified.raw_dir == original.raw_dir  # other fields unchanged
        True
        """
        return replace(self, **kwargs)

    def describe(self) -> str:
        """Return a human-readable multi-line summary of all resolved paths.

        The output is suitable for ``palmwtc info`` and for quick visual
        inspection in a notebook.  It shows the provenance (``source``) and
        ``site`` on the first line, followed by one line per path.

        Returns
        -------
        str
            A multi-line string with the header and one row per field.

        Examples
        --------
        >>> from palmwtc.config import DataPaths
        >>> text = DataPaths.resolve().describe()
        >>> text.startswith("DataPaths (source=")  # doctest: +ELLIPSIS
        True
        >>> "raw_dir" in text
        True
        """
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
        """Build a ``DataPaths`` from the layered resolution chain.

        This is the main factory method.  It merges path information from up
        to four sources and returns a frozen ``DataPaths`` whose ``source``
        field records which layer contributed the primary ``raw_dir``.

        Resolution order (highest precedence first):

        1. **Keyword arguments** — any non-``None`` kwarg passed here wins
           unconditionally over all lower layers.
        2. **Environment variable** ``PALMWTC_DATA_DIR`` — sets ``raw_dir``
           only; other paths still fall through to YAML or defaults.
        3. **YAML config** — searched in this order:

           a. ``config_file`` argument (if given),
           b. ``$PALMWTC_CONFIG`` environment variable (if set),
           c. ``./palmwtc.yaml`` (project-local),
           d. ``~/.palmwtc/config.yaml`` (user-global).

           The first file that exists is used; the rest are ignored.
        4. **Bundled synthetic sample** — ``palmwtc.data.sample_dir("synthetic")``.
           This layer always succeeds, so ``DataPaths.resolve()`` never raises
           due to missing configuration.

        When ``raw_dir`` is resolved, the three other path defaults are
        derived relative to ``raw_dir.parent``:

        - ``processed_dir`` → ``<parent>/Data/Integrated_QC_Data``
        - ``exports_dir``   → ``<parent>/exports``
        - ``config_dir``    → ``<parent>/config``

        Any path supplied explicitly (kwarg or YAML) overrides its default.

        Parameters
        ----------
        raw_dir : Path or str or None, optional
            Explicit path to the raw input data directory.  Overrides the
            environment variable, YAML, and the synthetic fallback.
        processed_dir : Path or str or None, optional
            Explicit path to the QC output directory.  If ``None``, derived
            from ``raw_dir.parent`` (see above).
        exports_dir : Path or str or None, optional
            Explicit path to the pipeline exports directory.  If ``None``,
            derived from ``raw_dir.parent``.
        config_dir : Path or str or None, optional
            Explicit path to the site config directory.  If ``None``, derived
            from ``raw_dir.parent``.
        site : {"libz", "cige"} or None, optional
            Calibration-track discriminator.  If ``None``, falls back to the
            YAML value or the default ``"libz"``.
        config_file : Path or str or None, optional
            Explicit path to a YAML config file.  Checked before the standard
            search locations (``$PALMWTC_CONFIG``, ``./palmwtc.yaml``,
            ``~/.palmwtc/config.yaml``).

        Returns
        -------
        DataPaths
            A frozen ``DataPaths`` with all four paths resolved to absolute
            ``Path`` objects and ``source`` set to one of:

            - ``"kwargs"`` — ``raw_dir`` came from an explicit keyword
              argument.
            - ``"env"`` — ``raw_dir`` came from ``PALMWTC_DATA_DIR``.
            - ``"yaml (<path>)"`` — ``raw_dir`` came from the YAML file at
              ``<path>``.
            - ``"sample (bundled synthetic)"`` — no external config was
              found; the bundled synthetic data directory is used.

        Raises
        ------
        yaml.YAMLError
            If a YAML config file exists but contains invalid YAML syntax.

        Examples
        --------
        Zero-config call — always works, uses bundled synthetic data:

        >>> from palmwtc.config import DataPaths
        >>> paths = DataPaths.resolve()
        >>> paths.source
        'sample (bundled synthetic)'
        >>> paths.site
        'libz'

        Override just ``raw_dir`` while letting other paths derive from it:

        >>> import tempfile, pathlib
        >>> tmp = pathlib.Path(tempfile.mkdtemp())
        >>> paths = DataPaths.resolve(raw_dir=tmp)
        >>> paths.raw_dir == tmp.resolve()
        True
        >>> paths.source
        'kwargs'
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
