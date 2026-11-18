"""Revision-aware plain text merging for shared report notes."""
from difflib import SequenceMatcher


class NotesConflict(ValueError):
    pass


def text_changes(before, after):
    return [
        {"start": i, "end": j, "before": before[i:j], "after": after[k:l],
         "line": before.count("\n", 0, i) + 1}
        for tag, i, j, k, l in SequenceMatcher(None, before, after).get_opcodes()
        if tag != "equal"
    ]


def merge_notes(base, current, incoming):
    """Merge independent edits; reject ambiguous overlapping edits without loss."""
    if incoming == current or incoming == base:
        return current
    if current == base:
        return incoming
    remote = text_changes(base, current)
    local = text_changes(base, incoming)
    combined = list(remote)
    for edit in local:
        if edit in remote:
            continue
        for other in remote:
            # Insertions at edit boundaries are ambiguous, so require resolution.
            if max(edit["start"], other["start"]) <= min(edit["end"], other["end"]):
                raise NotesConflict("Bagian yang sama sedang diubah anggota lain.")
        combined.append(edit)
    result = base
    for edit in sorted(combined, key=lambda item: item["start"], reverse=True):
        result = result[:edit["start"]] + edit["after"] + result[edit["end"]:]
    return result
