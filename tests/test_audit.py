"""audit tool tests — findings must carry the affected page path, and
parent-vault wikilinks must resolve (SKILL.md rule 1 allows them)."""

from __future__ import annotations

from pathlib import Path

from kb_mcp import audit as audit_module


def test_audit_findings_have_non_empty_path(vault: Path) -> None:
    """Regression: every finding must carry the path of the file it concerns.

    Previously _parse_page set rel_path="" and relied on find() to fill it.
    audit called _parse_page directly, so every finding's `path` was empty —
    making the report un-triagable.
    """
    # Plant a broken wikilink in an existing fixture file.
    insight = (
        vault / "Knowledge Base" / "Notes" / "Insights"
        / "progressive-disclosure-without-mode-fragmentation.md"
    )
    original = insight.read_text(encoding="utf-8")
    insight.write_text(
        original + "\n\nDangling: [[Knowledge Base/Notes/Insights/does-not-exist]]\n",
        encoding="utf-8",
    )

    report = audit_module.audit(vault, categories=["broken_wikilink"])
    assert report.findings, "expected at least one broken_wikilink finding"
    for f in report.findings:
        assert f.path, f"finding has empty path: {f.as_dict()}"
        assert f.path.startswith("Knowledge Base/"), f.path


def test_audit_does_not_flag_parent_vault_wikilinks(vault: Path, tmp_path: Path) -> None:
    """Wikilinks to curated parent-vault paths (Cognitive Core, Domains,
    Products, etc.) are legitimate per SKILL.md rule 1 and must not be flagged.
    """
    # Create a parent-vault page outside Knowledge Base/.
    (vault / "Domains").mkdir()
    (vault / "Domains" / "Domain - AI Systems & Architecture.md").write_text(
        "# Domain page\n", encoding="utf-8"
    )

    # Link to it from a compiled note.
    insight = (
        vault / "Knowledge Base" / "Notes" / "Insights"
        / "progressive-disclosure-without-mode-fragmentation.md"
    )
    insight.write_text(
        insight.read_text(encoding="utf-8")
        + "\n\nSee [[Domains/Domain - AI Systems & Architecture]] "
        + "and [[Domain - AI Systems & Architecture]] (bare name).\n",
        encoding="utf-8",
    )

    report = audit_module.audit(vault, categories=["broken_wikilink"])
    bad = [f for f in report.findings if "Domain - AI Systems" in f.detail]
    assert not bad, [f.as_dict() for f in bad]
