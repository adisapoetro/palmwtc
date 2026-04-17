"""palmwtc — Automated whole-tree chamber workflow for oil-palm ecophysiology.

This is the Phase 1 skeleton. Public API re-exports will be wired up in Phase 2
once the modules are ported from `flux_chamber/src/`. See plan at
``~/.claude/plans/venv-bin-python-scripts-run-notebooks-p-eventual-hellman.md``.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("palmwtc")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
