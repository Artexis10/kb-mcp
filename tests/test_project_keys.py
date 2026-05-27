"""Tests for project-key registry + auto-register behaviour.

The writer auto-registers unknown slug-shaped project keys so LLMs don't
have to drop out to YAML edits. Invalid slugs still get rejected.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from kb_mcp import note as note_module
from kb_mcp import project_keys as project_keys_module


TODAY = dt.date(2026, 5, 28)


def test_load_registry_falls_back_when_yaml_missing(vault: Path) -> None:
    """Fixture vault has no project-keys.yaml — loader returns fallback set."""
    registry = project_keys_module.load_project_registry(vault)
    assert "substrate" in registry.project_to_folder
    assert registry.folder_for("q") == "Q"


def test_register_new_project_key_writes_yaml(vault: Path) -> None:
    """`register_project_key` bootstraps the YAML if missing + adds the key."""
    key, folder, was_new = project_keys_module.register_project_key(
        vault, "vehicles"
    )
    assert was_new is True
    assert key == "vehicles"
    assert folder == "Vehicles"
    yaml_path = vault / "Knowledge Base" / "_Schema" / "project-keys.yaml"
    assert yaml_path.exists()
    text = yaml_path.read_text(encoding="utf-8")
    assert "vehicles:" in text
    assert "folder: Vehicles" in text
    # Folder was created.
    folder_path = vault / "Knowledge Base" / "Notes" / "Research" / "Vehicles"
    assert folder_path.is_dir()


def test_register_existing_key_is_idempotent(vault: Path) -> None:
    """Registering the same key twice no-ops the second time."""
    project_keys_module.register_project_key(vault, "vehicles")
    _, _, was_new = project_keys_module.register_project_key(vault, "vehicles")
    assert was_new is False


def test_register_rejects_non_slug_keys(vault: Path) -> None:
    with pytest.raises(ValueError, match="not a valid slug"):
        project_keys_module.register_project_key(vault, "Vehicles!")
    with pytest.raises(ValueError):
        project_keys_module.register_project_key(vault, "UPPERCASE")
    with pytest.raises(ValueError):
        project_keys_module.register_project_key(vault, "")


def test_note_auto_registers_unknown_project_key(vault: Path) -> None:
    """`note(project=<new-slug>)` registers + creates folder + writes."""
    result = note_module.note(
        vault,
        content="# Test\n\n## Question\n\nWhat?\n",
        note_type="research-note",
        title="Vehicle test note",
        project="vehicles",
        today=TODAY,
    )
    # Note landed under the new folder.
    assert result.path == "Knowledge Base/Notes/Research/Vehicles/vehicle-test-note.md"
    assert (vault / result.path).exists()
    # Warning surfaced the registration.
    assert any(
        "Auto-registered" in w and "vehicles" in w for w in result.warnings
    ), result.warnings
    # YAML now contains the key.
    yaml_path = vault / "Knowledge Base" / "_Schema" / "project-keys.yaml"
    assert "vehicles:" in yaml_path.read_text(encoding="utf-8")


def test_note_auto_register_is_silent_on_second_use(vault: Path) -> None:
    """Once a key is registered, subsequent uses don't warn again."""
    note_module.note(
        vault,
        content="# First\n\n## Question\n\nWhat?\n",
        note_type="research-note",
        title="First in new scope",
        project="vehicles",
        today=TODAY,
    )
    second = note_module.note(
        vault,
        content="# Second\n\n## Question\n\nWhat?\n",
        note_type="research-note",
        title="Second in new scope",
        project="vehicles",
        today=TODAY,
    )
    assert not any(
        "Auto-registered" in w and "vehicles" in w for w in second.warnings
    ), second.warnings


def test_note_rejects_non_slug_project(vault: Path) -> None:
    """Invalid project slugs (uppercase, special chars) fall through to validation."""
    with pytest.raises(note_module.NoteError) as excinfo:
        note_module.note(
            vault,
            content="# Test\n\n## Question\n\nWhat?\n",
            note_type="research-note",
            title="Bad project",
            project="BAD-SLUG",
            today=TODAY,
        )
    assert excinfo.value.code == "INVALID_NOTE"


def test_note_projects_plural_auto_registers_each(vault: Path) -> None:
    """`projects:` list (plural) auto-registers every unknown key."""
    result = note_module.note(
        vault,
        content="# Pat\n\n## Problem\n\nX.\n",
        note_type="pattern",
        title="Cross-project pattern",
        projects=["vehicles", "automotive-something"],
        today=TODAY,
    )
    # Both keys appear in warnings.
    msgs = " ".join(result.warnings)
    assert "vehicles" in msgs
    assert "automotive-something" in msgs
