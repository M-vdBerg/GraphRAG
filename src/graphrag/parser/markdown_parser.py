"""Markdown-to-chunk parser.

Splitting strategy
──────────────────
The file is split on heading lines (``#`` through ``######``). Content
appearing before the first heading becomes chunk 0 with an empty heading.
Each heading + the text that follows it until the next heading becomes one
chunk. This preserves heading context inside the chunk text.

Links
──────
Only relative ``.md`` links are extracted — absolute URLs and anchors are
ignored. Links are resolved relative to the source file's directory so the
watcher can look up target documents in the graph by their absolute path.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


@dataclass
class Chunk:
    heading: str          # heading text; empty string for pre-heading content
    position: int         # 0-based ordinal within document
    content: str          # full text of section (heading line included)
    token_count: int      # word-count approximation


@dataclass
class ParsedDocument:
    file_path: str
    title: str                              # text of first H1, or basename
    chunks: list[Chunk] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (anchor, abs_path)


class MarkdownParser:
    def parse(self, file_path: str) -> ParsedDocument:
        with open(file_path, encoding="utf-8") as fh:
            text = fh.read()

        chunks = _split_into_chunks(text)
        title = _extract_title(text) or os.path.basename(file_path)
        links = _extract_links(text, file_path)

        return ParsedDocument(
            file_path=file_path,
            title=title,
            chunks=chunks,
            links=links,
        )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _split_into_chunks(text: str) -> list[Chunk]:
    """Split markdown text into sections on heading boundaries."""
    matches = list(_HEADING_RE.finditer(text))

    sections: list[tuple[str, int, int]] = []  # (heading_text, start, end)

    if not matches:
        sections.append(("", 0, len(text)))
    else:
        # Content before first heading
        if matches[0].start() > 0:
            sections.append(("", 0, matches[0].start()))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append((m.group(2).strip(), m.start(), end))

    chunks: list[Chunk] = []
    for pos, (heading, start, end) in enumerate(sections):
        content = text[start:end].strip()
        if not content:
            continue
        chunks.append(
            Chunk(
                heading=heading,
                position=pos,
                content=content,
                token_count=len(content.split()),
            )
        )
    return chunks


def _extract_title(text: str) -> str | None:
    """Return the text of the first H1 heading, or None."""
    for m in _HEADING_RE.finditer(text):
        if len(m.group(1)) == 1:  # single '#' = H1
            return m.group(2).strip()
    return None


def _extract_links(text: str, source_file: str) -> list[tuple[str, str]]:
    """Extract relative .md links and resolve them to absolute paths."""
    source_dir = os.path.dirname(os.path.abspath(source_file))
    links: list[tuple[str, str]] = []
    for m in _LINK_RE.finditer(text):
        anchor, href = m.group(1), m.group(2)
        # Skip absolute URLs, anchors, and non-markdown hrefs
        if href.startswith(("http://", "https://", "#", "mailto:")):
            continue
        # Strip any in-page anchor fragment
        href_path = href.split("#")[0]
        if not href_path.endswith(".md"):
            continue
        abs_path = os.path.normpath(os.path.join(source_dir, href_path))
        links.append((anchor, abs_path))
    return links
