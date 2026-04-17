"""palmwtc.config — DataPaths resolver. Phase 1 stub; full impl lands in Phase 3.

Layered resolution order (highest precedence first):
    1. CLI flag (``palmwtc run --raw-dir … --processed-dir …``)
    2. Env var ``PALMWTC_DATA_DIR``
    3. ``palmwtc.yaml`` in cwd or ``~/.palmwtc/config.yaml``
    4. Bundled synthetic sample (``palmwtc.data.sample_dir("synthetic")``)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Site = Literal["libz", "cige"]


@dataclass(frozen=True)
class DataPaths:
    """Resolved I/O paths for a palmwtc run.

    Phase 1 holds only the dataclass shape; the layered ``resolve()``
    classmethod is implemented in Phase 3.
    """

    raw_dir: Path
    processed_dir: Path
    exports_dir: Path
    config_dir: Path
    site: Site = "libz"

    @classmethod
    def resolve(cls) -> DataPaths:
        """Layered resolver. Phase 3 implementation."""
        raise NotImplementedError("DataPaths.resolve() lands in Phase 3 of the extraction plan.")
