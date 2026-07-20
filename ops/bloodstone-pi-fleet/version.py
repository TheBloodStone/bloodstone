"""Pi fleet package version — re-exports chain_mesh single source of truth."""

from __future__ import annotations

from pathlib import Path

try:
    from chain_mesh import __version__
except ImportError:  # pragma: no cover — package tree incomplete
    _vf = Path(__file__).with_name("VERSION")
    try:
        __version__ = _vf.read_text(encoding="utf-8").strip().splitlines()[0]
    except OSError:
        __version__ = "0.36.1-beta"

__all__ = ["__version__"]
