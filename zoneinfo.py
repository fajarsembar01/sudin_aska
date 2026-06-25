# zoneinfo.py - Compatibility shim for Python 3.8
import sys

# Try to import from backports.zoneinfo
try:
    from backports.zoneinfo import *
except ImportError as e:
    raise ImportError(
        "backports.zoneinfo is required for zoneinfo support on Python < 3.9. "
        "Please run 'pip install backports.zoneinfo'."
    ) from e
