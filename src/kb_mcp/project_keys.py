"""Project-key registry — single source of truth lives in the vault.

`Knowledge Base/_Schema/project-keys.yaml` declares every valid `project:`
value for research-notes and every valid entry for the `projects:` list on
insights/failures/patterns/production-logs.

Adding a key is a YAML edit, not a code change. Validation in `note.py`
calls into this module to get the current accepted set + folder mapping.

If the YAML is missing or unparseable we fall back to a built-in safe
default so the writer never refuses every project key. The fallback
mirrors what was hardcoded before the config existed; a warning lands in
the service log when it fires.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from .vault import kb_root


log = logging.getLogger(__name__)


# Fallback used when project-keys.yaml is missing or malformed. Matches the
# pre-config hardcoded set so the writer keeps accepting all historical keys
# even if the config disappears.
_FALLBACK_PROJECTS: dict[str, str] = {
    "substrate": "Substrate",
    "q": "Q",
    "endstate": "Endstate",
    "sift": "Sift",
    "tu": "Together Unprocessed",
    "book-club": "Book Club",
    "health": "Health",
    "finance": "Finance",
    "creative": "Creative",
    "science": "Science",
    "travel": "Travel",
    "personal": "Personal",
}


@dataclass(frozen=True)
class ProjectRegistry:
    """Snapshot of the project keys + folder mapping at load time.

    Frozen because keys are referenced from multiple write paths; mutation
    would create inconsistent views across calls.
    """

    project_to_folder: dict[str, str]
    project_to_category: dict[str, str]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self.project_to_folder.keys())

    def folder_for(self, key: str) -> str | None:
        return self.project_to_folder.get(key)

    def category_for(self, key: str) -> str:
        return self.project_to_category.get(key, "uncategorized")


def load_project_registry(vault_root: Path) -> ProjectRegistry:
    """Read `_Schema/project-keys.yaml` and return a typed registry.

    Returns a fallback registry on any read/parse failure, with a warning
    logged so service-log readers can see the misconfiguration.
    """
    path = kb_root(vault_root) / "_Schema" / "project-keys.yaml"
    if not path.exists():
        log.warning(
            "project-keys.yaml missing at %s; using built-in fallback set", path
        )
        return _fallback_registry()
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
    except (OSError, yaml.YAMLError) as e:
        log.warning(
            "project-keys.yaml unreadable (%s); using built-in fallback set", e
        )
        return _fallback_registry()

    projects = data.get("projects")
    if not isinstance(projects, dict) or not projects:
        log.warning(
            "project-keys.yaml has no `projects:` mapping; using fallback"
        )
        return _fallback_registry()

    project_to_folder: dict[str, str] = {}
    project_to_category: dict[str, str] = {}
    for key, entry in projects.items():
        if not isinstance(key, str):
            continue
        if isinstance(entry, dict):
            folder = entry.get("folder") or _title_case_slug(key)
            category = entry.get("category") or "uncategorized"
        elif isinstance(entry, str):
            # Tolerate short form `key: FolderName`.
            folder = entry
            category = "uncategorized"
        else:
            continue
        project_to_folder[key] = str(folder)
        project_to_category[key] = str(category)
    if not project_to_folder:
        return _fallback_registry()
    return ProjectRegistry(
        project_to_folder=project_to_folder,
        project_to_category=project_to_category,
    )


def _fallback_registry() -> ProjectRegistry:
    return ProjectRegistry(
        project_to_folder=dict(_FALLBACK_PROJECTS),
        project_to_category={k: "uncategorized" for k in _FALLBACK_PROJECTS},
    )


def _title_case_slug(key: str) -> str:
    """Auto-derive a folder name from a slug key (`book-club` → `Book Club`)."""
    return " ".join(part.capitalize() for part in key.split("-"))


_SLUG_RE = __import__("re").compile(r"^[a-z][a-z0-9-]{0,40}$")


def register_project_key(
    vault_root: Path,
    key: str,
    *,
    folder: str | None = None,
    category: str = "uncategorized",
) -> tuple[str, str, bool]:
    """Add a new project key to `_Schema/project-keys.yaml`. Idempotent.

    Returns `(key, folder, was_new)`. `was_new` is True when the key
    didn't exist before (so callers can surface a warning to the user).

    Design rationale: the writer auto-registers unknown project keys on
    use rather than refusing — Hugo runs through LLMs almost exclusively
    and shouldn't have to edit YAML by hand. Typo risk is mitigated by
    surfacing the registration as a warning every time it fires; Hugo
    can revert via `move_file` + manual YAML edit if needed.

    Refuses non-slug keys (must match `^[a-z][a-z0-9-]{0,40}$`) so a stray
    `Vehicles` or `vehicles!` doesn't pollute the registry. The folder
    name is free-form (Title Case allowed, matches Hugo's convention).
    """
    if not _SLUG_RE.match(key):
        raise ValueError(
            f"project key {key!r} is not a valid slug "
            f"(must match {_SLUG_RE.pattern}; lowercase + dashes)"
        )

    path = kb_root(vault_root) / "_Schema" / "project-keys.yaml"
    if not path.exists():
        # Fresh install: bootstrap a file with the fallback set + the new key.
        path.parent.mkdir(parents=True, exist_ok=True)
        bootstrap_lines = [
            "# Project keys for research-notes and cross-cutting projects: list.",
            "# kb-mcp loads this at startup and auto-appends new keys on use.",
            "",
            "projects:",
        ]
        for k, f in _FALLBACK_PROJECTS.items():
            bootstrap_lines.append(f"  {k}:")
            bootstrap_lines.append(f"    folder: {f}")
            bootstrap_lines.append(f"    category: uncategorized")
        path.write_text("\n".join(bootstrap_lines) + "\n", encoding="utf-8")

    text = path.read_text(encoding="utf-8")

    folder_name = folder or _title_case_slug(key)

    # Idempotency check: if the key already appears as a top-level entry
    # under `projects:`, no-op.
    import re
    existing = re.search(
        rf"^\s{{2}}{re.escape(key)}:\s*$", text, re.MULTILINE
    )
    if existing:
        return key, folder_name, False

    # Append the entry at end of the file. Keep formatting simple — a YAML
    # round-trip would lose comments + ordering.
    new_block = (
        f"\n  # auto-registered by kb-mcp\n"
        f"  {key}:\n"
        f"    folder: {folder_name}\n"
        f"    category: {category}\n"
    )
    # If file ends without newline, prepend one.
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + new_block, encoding="utf-8")

    # Create the matching folder so the next note write lands cleanly.
    folder_path = kb_root(vault_root) / "Notes" / "Research" / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    return key, folder_name, True
