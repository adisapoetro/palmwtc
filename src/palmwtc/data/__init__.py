"""palmwtc.data — bundled sample datasets.

``sample/synthetic/`` holds deterministic synthetic chamber cycles (~5 MB) used
by CI and the zero-config first-run experience. ``sample/real/`` is fetched
on demand from Zenodo via ``palmwtc sample fetch`` (~10-50 MB, anonymized
LIBZ data).
"""

from importlib.resources import files
from pathlib import Path


def sample_dir(kind: str = "synthetic") -> Path:
    """Return the on-disk path to a bundled sample dataset.

    Parameters
    ----------
    kind : {"synthetic", "real"}
        ``"synthetic"`` is bundled with the package wheel and always present.
        ``"real"`` is fetched on-demand via ``palmwtc sample fetch`` and may
        not exist until then.
    """
    if kind not in {"synthetic", "real"}:
        raise ValueError(f"unknown sample kind: {kind!r}")
    return Path(str(files("palmwtc").joinpath("data", "sample", kind)))
