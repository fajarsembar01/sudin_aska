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


def qa_only_mode_enabled() -> bool:
    """Master switch: only allow QA chat, disable all special flows."""
    return env_flag("ASKA_QA_ONLY_MODE", False)


def teacher_mode_enabled() -> bool:
    """Toggle teacher mode independently (unless QA-only mode is active)."""
    if qa_only_mode_enabled():
        return False
    return env_flag("ASKA_TEACHER_MODE_ENABLED", True)


def smalltalk_enabled() -> bool:
    """Toggle smalltalk/canned responses.

    QA-only mode intentionally still allows smalltalk so short messages like
    thanks/hello/oke do not waste RAG/model tokens. Teacher and reporting flows
    remain disabled by qa_only_mode_enabled().
    """
    return env_flag("ASKA_SMALLTALK_ENABLED", True)


def reporting_enabled(kind: Optional[str] = None) -> bool:
    """Global/per-kind toggle for ASKA reporting flows."""
    if qa_only_mode_enabled():
        return False

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
