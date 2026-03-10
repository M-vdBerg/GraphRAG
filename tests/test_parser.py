"""Unit tests for the markdown parser — no database required."""

from __future__ import annotations

import os
import tempfile

import pytest

from graphrag.parser.markdown_parser import MarkdownParser


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


def _write_md(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class TestMarkdownParser:
    def test_single_chunk_no_headings(self, parser: MarkdownParser) -> None:
        path = _write_md("Just some text without any headings.")
        try:
            doc = parser.parse(path)
            assert len(doc.chunks) == 1
            assert doc.chunks[0].heading == ""
            assert "Just some text" in doc.chunks[0].content
        finally:
            os.unlink(path)

    def test_splits_on_headings(self, parser: MarkdownParser) -> None:
        path = _write_md("# Title\n\nIntro text.\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n")
        try:
            doc = parser.parse(path)
            # Expect: pre-H1 (empty, skip if blank), H1, H2-A, H2-B
            headings = [c.heading for c in doc.chunks]
            assert "Title" in headings
            assert "Section A" in headings
            assert "Section B" in headings
        finally:
            os.unlink(path)

    def test_title_from_h1(self, parser: MarkdownParser) -> None:
        path = _write_md("# My Document\n\nSome content.\n")
        try:
            doc = parser.parse(path)
            assert doc.title == "My Document"
        finally:
            os.unlink(path)

    def test_title_falls_back_to_filename(self, parser: MarkdownParser) -> None:
        path = _write_md("No heading here, just text.\n")
        try:
            doc = parser.parse(path)
            assert doc.title == os.path.basename(path)
        finally:
            os.unlink(path)

    def test_extracts_relative_md_links(self, parser: MarkdownParser) -> None:
        path = _write_md("# Doc\n\nSee [other page](other.md) for more.\n")
        try:
            doc = parser.parse(path)
            assert len(doc.links) == 1
            anchor, abs_path = doc.links[0]
            assert anchor == "other page"
            assert abs_path.endswith("other.md")
            assert os.path.isabs(abs_path)
        finally:
            os.unlink(path)

    def test_ignores_absolute_urls(self, parser: MarkdownParser) -> None:
        path = _write_md("# Doc\n\nVisit [site](https://example.com) or [local](local.md).\n")
        try:
            doc = parser.parse(path)
            assert len(doc.links) == 1
            assert doc.links[0][0] == "local"
        finally:
            os.unlink(path)

    def test_token_count_approximation(self, parser: MarkdownParser) -> None:
        text = " ".join(["word"] * 100)
        path = _write_md(f"# Section\n\n{text}\n")
        try:
            doc = parser.parse(path)
            chunk = next(c for c in doc.chunks if c.heading == "Section")
            assert chunk.token_count > 90  # heading adds a few words
        finally:
            os.unlink(path)

    def test_position_is_sequential(self, parser: MarkdownParser) -> None:
        path = _write_md("# A\n\ntext\n\n# B\n\ntext\n\n# C\n\ntext\n")
        try:
            doc = parser.parse(path)
            positions = [c.position for c in doc.chunks]
            assert positions == sorted(positions)
            assert len(set(positions)) == len(positions)
        finally:
            os.unlink(path)
