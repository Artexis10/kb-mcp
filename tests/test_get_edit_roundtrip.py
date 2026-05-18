"""get/edit round-trip tests — body field must not accumulate blank lines."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from kb_mcp import edit as edit_module
from kb_mcp import get_page as get_module


TODAY = dt.date(2026, 5, 18)


def test_get_body_has_no_leading_newline(vault: Path) -> None:
    """Regression: previously `get` returned body with a leading \\n, the
    frontmatter-separator artifact. Round-tripping through edit accumulated
    blank lines. After the fix, body starts at the first content character.
    """
    result = get_module.get_page(
        vault,
        path="Knowledge Base/Notes/Insights/progressive-disclosure-without-mode-fragmentation.md",
    )
    assert not result.body.startswith("\n"), repr(result.body[:20])
    assert result.body.startswith("# "), repr(result.body[:40])


def test_edit_roundtrip_does_not_accumulate_blanks(vault: Path) -> None:
    path = "Knowledge Base/Notes/Insights/progressive-disclosure-without-mode-fragmentation.md"
    first = get_module.get_page(vault, path=path)
    edit_module.edit(
        vault, path=path, why="round-trip test", new_body=first.body, today=TODAY
    )
    second = get_module.get_page(vault, path=path)
    edit_module.edit(
        vault, path=path, why="round-trip test 2", new_body=second.body, today=TODAY
    )
    third = get_module.get_page(vault, path=path)
    # The body should be byte-identical across edits.
    assert first.body == second.body == third.body
