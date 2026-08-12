"""Compatibility shim for projects that import ``zoneinfo`` from the repo root.

This file shadows Python's stdlib ``zoneinfo`` module when commands are run from
the project directory. On Python 3.9+, load the real stdlib package explicitly.
On older Python versions, fall back to ``backports.zoneinfo``.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import sysconfig

if sys.version_info >= (3, 9):
    stdlib_path = sysconfig.get_path("stdlib")
    spec = importlib.machinery.PathFinder.find_spec("zoneinfo", [stdlib_path])
    if spec is None or spec.loader is None or spec.origin == __file__:
        raise ImportError("Could not locate Python's standard library zoneinfo module.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
    globals().update(module.__dict__)
else:
    try:
        from backports.zoneinfo import *  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "backports.zoneinfo is required for zoneinfo support on Python < 3.9. "
            "Please run 'pip install backports.zoneinfo'."
        ) from e
