"""One-page Plotly report for a FICO Xpress problem.

Not affiliated with, endorsed by, or supported by FICO. "FICO" and "Xpress"
are trademarks of Fair Isaac Corporation.
"""

from __future__ import annotations

from .report import ALL_SECTIONS, MATRIX_SECTIONS, report

try:
    from ._version import __version__
except ImportError:  # pragma: no cover - source checkout without a build
    __version__ = "0+unknown"

__all__ = ["ALL_SECTIONS", "MATRIX_SECTIONS", "__version__", "report"]
