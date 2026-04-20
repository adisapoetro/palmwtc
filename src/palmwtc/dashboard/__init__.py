"""palmwtc.dashboard — Streamlit monitoring app.

Requires the ``[dashboard]`` extra (``pip install palmwtc[dashboard]``).
The streamlit dependency is imported lazily inside ``app`` so the
subpackage can be imported safely from a core install (lets tests
introspect the module path without forcing streamlit on every user).

Launch via the CLI::

    palmwtc dashboard

or directly::

    python -m streamlit run src/palmwtc/dashboard/app.py
"""

from importlib.util import find_spec


def is_streamlit_available() -> bool:
    """Return True when the ``streamlit`` package is importable."""
    return find_spec("streamlit") is not None


__all__ = ["is_streamlit_available"]
