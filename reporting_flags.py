from __future__ import annotations

import os
from typing import Optional

_TRUE_VALUES = {"1", "true", "yes", "on"}


def env_flag(name: str, default: bool) -> bool:
    """Parse a boolean env flag with a default."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def reporting_enabled(kind: Optional[str] = None) -> bool:
    """Global/per-kind toggle for ASKA reporting flows."""
    global_enabled = env_flag("ASKA_REPORTING_ENABLED", False)
    if not global_enabled:
        return False
    if not kind:
        return global_enabled

    kind_map = {
        "bullying": "ASKA_REPORTING_BULLYING_ENABLED",
        "corruption": "ASKA_REPORTING_CORRUPTION_ENABLED",
        "psych": "ASKA_REPORTING_PSYCH_ENABLED",
        "psikologis": "ASKA_REPORTING_PSYCH_ENABLED",
    }
    env_name = kind_map.get(kind.strip().lower())
    if not env_name:
        return global_enabled

    return global_enabled and env_flag(env_name, True)
