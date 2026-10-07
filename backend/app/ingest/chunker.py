"""
Split a decision into retrieval chunks with stable character offsets.

Offsets are into that section's stored text (opinion_text, dissent_text,
or concur_text). Round-trip: section_text[char_start:char_end] == chunk.text
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

MAX_CHARS = 3200
OVERLAP_CHARS = 400
MIN_CHARS = 40

SECTION_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("opinion", "opinion_text"),
    ("dissent", "dissent_text"),
    ("concur", "concur_text"),
)


def chunk_text(text: str, section: str) -> List[Dict[str, Any]]:
    if not text:
        return []

    n = len(text)
    if n <= MAX_CHARS:
        return [_chunk(section, 0, text, 0, n)]

    chunks: List[Dict[str, Any]] = []
    start = 0
    index = 0
    while start < n:
        end = min(n, start + MAX_CHARS)
        if end < n:
            end = _snap_end(text, start, end)
        piece = text[start:end]
        if piece.strip():
            chunks.append(_chunk(section, index, piece, start, end))
            index += 1
        if end >= n:
            break
        start = max(start + 1, end - OVERLAP_CHARS)
    return chunks


def chunk_decision(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for section, field in SECTION_FIELDS:
        chunks.extend(chunk_text(row.get(field) or "", section))
    for idx, chunk in enumerate(chunks):
        chunk["chunk_index"] = idx
    return chunks


def verify_offsets(row: Dict[str, Any], chunks: Iterable[Dict[str, Any]]) -> List[str]:
    errors = []
    fields = dict(SECTION_FIELDS)
    for chunk in chunks:
        source = row.get(fields[chunk["section"]]) or ""
        sliced = source[chunk["char_start"]:chunk["char_end"]]
        if sliced != chunk["text"]:
            errors.append(
                f"{chunk['section']}[{chunk['char_start']}:{chunk['char_end']}] mismatch"
            )
    return errors


def _chunk(section: str, index: int, text: str, start: int, end: int) -> Dict[str, Any]:
    return {
        "section": section,
        "chunk_index": index,
        "text": text,
        "char_start": start,
        "char_end": end,
        "token_count": max(1, (end - start) // 4),
    }


def _snap_end(text: str, start: int, end: int) -> int:
    window = text[start:end]
    for sep in ("\n\n", ". ", "? ", "! ", "; ", "\n", ", "):
        pos = window.rfind(sep)
        if pos >= int(len(window) * 0.45):
            return start + pos + len(sep)
    return end
