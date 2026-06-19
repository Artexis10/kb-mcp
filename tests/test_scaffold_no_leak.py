"""Regression backstop: the shipped generic scaffold must not contain personal data.

`src/kb_mcp/_scaffold/_Schema/` is a derived artifact (built by
scripts/genericize-schema.py from the vault canonical). This test scans the
COMMITTED scaffold for the same machine-path/personal patterns the genericize
script guards against — so the leak class (which once shipped `Evidence/Mother
Cancer/` and the author's machine paths to a friend) can't recur on a hand-edit.
Runs without the vault, so it works in CI.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import kb_mcp

SCAFFOLD = Path(kb_mcp.__file__).resolve().parent / "_scaffold" / "_Schema"
REPO = Path(kb_mcp.__file__).resolve().parent.parent.parent  # src/kb_mcp -> repo root


def _leak_patterns() -> list[str]:
    """Import the pattern list from the (hyphenated) genericize script by path,
    so the test and the generator never drift."""
    spec = importlib.util.spec_from_file_location(
        "genericize_schema", REPO / "scripts" / "genericize-schema.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.LEAK_PATTERNS


def test_scaffold_ships_no_personal_data() -> None:
    patterns = [re.compile(p) for p in _leak_patterns()]
    offenders: list[str] = []
    for f in sorted(SCAFFOLD.rglob("*")):
        if not f.is_file():
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for p in patterns:
                if p.search(line):
                    offenders.append(f"{f.relative_to(SCAFFOLD)}:{i}: /{p.pattern}/ -> {line.strip()[:80]}")
    assert not offenders, (
        "personal-data patterns found in the shipped scaffold (regenerate via "
        "scripts/genericize-schema.py; never hand-edit _scaffold/_Schema):\n" + "\n".join(offenders)
    )
