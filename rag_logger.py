"""RAG debug logger — menyimpan log proses retrieval ke file JSONL."""

from __future__ import annotations

import json
import os
import fcntl
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
RAG_LOG_FILE = RUNTIME_DIR / "rag_debug.jsonl"
MAX_LINES = 10_000

_WIB = timezone(timedelta(hours=7))


def save_rag_log(
    *,
    user_id: Any,
    username: str = "",
    channel: str = "",
    question: str = "",
    chunks: list[str] | None = None,
    answer: str = "",
    response_ms: int = 0,
) -> None:
    """Append satu entry RAG debug log ke file JSONL."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(_WIB).strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "username": username,
        "channel": channel,
        "question": question,
        "chunks_count": len(chunks) if chunks else 0,
        "chunks": chunks or [],
        "answer": answer[:500],
        "response_ms": response_ms,
    }
    try:
        with open(RAG_LOG_FILE, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:
        print(f"[RAG_LOGGER] Failed to write: {exc}")

    # Auto-rotate: keep only last MAX_LINES entries
    try:
        if RAG_LOG_FILE.exists() and RAG_LOG_FILE.stat().st_size > MAX_LINES * 1024:
            lines = RAG_LOG_FILE.read_text(encoding="utf-8").splitlines()
            if len(lines) > MAX_LINES:
                RAG_LOG_FILE.write_text(
                    "\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8"
                )
    except Exception:
        pass


def read_rag_logs(
    *,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Baca log RAG debug, kembalikan (entries, total_count).

    Entries dikembalikan dalam urutan terbaru-di-atas.
    """
    if not RAG_LOG_FILE.exists():
        return [], 0

    all_entries: list[dict] = []
    try:
        with open(RAG_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if search:
                    needle = search.lower()
                    haystack = (
                        (entry.get("question") or "")
                        + " "
                        + (entry.get("username") or "")
                        + " "
                        + (entry.get("answer") or "")
                    ).lower()
                    if needle not in haystack:
                        continue
                all_entries.append(entry)
    except Exception:
        return [], 0

    # Reverse for newest-first
    all_entries.reverse()
    total = len(all_entries)
    page_entries = all_entries[offset : offset + limit]
    return page_entries, total
