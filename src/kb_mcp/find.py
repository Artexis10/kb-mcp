"""Read-only search across the Knowledge Base.

Scans every `.md` under `Knowledge Base/`, parses YAML frontmatter, filters by
structured fields, then does case-insensitive substring matching on
title + body. Hugo's vault is hundreds of pages — full-scan is fast enough.

Cached in-process between calls: keyed by file path, invalidated by mtime.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


log = logging.getLogger(__name__)

EXCLUDED_DIR_NAMES = frozenset({"_Schema", "_attachments", "_archive", "_trash"})
FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)
H1_PATTERN = re.compile(r"^# (.+)$", re.MULTILINE)

EXCERPT_RADIUS = 100  # chars on each side of the match
EXCERPT_MAX_LEN = 220


@dataclass
class ParsedPage:
    path: Path  # absolute
    rel_path: str  # vault-relative, e.g. "Knowledge Base/Notes/Insights/foo.md"
    frontmatter: dict[str, Any]
    body: str
    title: str
    mtime: float

    @property
    def page_type(self) -> str | None:
        t = self.frontmatter.get("type")
        return str(t) if t else None

    @property
    def scope(self) -> str | None:
        """Per-type "scope" field as defined in the plan.

        - research-note → project
        - pattern / insight / failure → project (singular) or projects (joined)
        - experiment → domain
        - production-log → medium
        - entity → entity_type
        - source → source_type
        Fallback: project / projects / domain / medium / entity_type in that order.
        """
        fm = self.frontmatter
        t = self.page_type

        def _project_or_projects() -> str | None:
            if (proj := fm.get("project")):
                return str(proj)
            if (projects := fm.get("projects")):
                if isinstance(projects, list) and projects:
                    return ",".join(str(p) for p in projects)
                return str(projects)
            return None

        if t == "production-log":
            return str(fm["medium"]) if fm.get("medium") else None
        if t == "experiment":
            return str(fm["domain"]) if fm.get("domain") else None
        if t == "entity":
            return str(fm["entity_type"]) if fm.get("entity_type") else None
        if t == "source":
            return str(fm["source_type"]) if fm.get("source_type") else None
        if t in ("research-note", "pattern", "insight", "failure"):
            return _project_or_projects()

        # Unknown type: fall back across all candidates
        return (
            _project_or_projects()
            or (str(fm["domain"]) if fm.get("domain") else None)
            or (str(fm["medium"]) if fm.get("medium") else None)
            or (str(fm["entity_type"]) if fm.get("entity_type") else None)
        )

    @property
    def updated(self) -> str:
        u = self.frontmatter.get("updated") or self.frontmatter.get("captured") or ""
        return str(u)

    @property
    def tags(self) -> list[str]:
        t = self.frontmatter.get("tags") or []
        return [str(x).lower() for x in t] if isinstance(t, list) else []


@dataclass
class Hit:
    path: str
    type: str | None
    scope: str | None
    title: str
    updated: str
    excerpt: str

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "type": self.type,
            "scope": self.scope,
            "title": self.title,
            "updated": self.updated,
            "excerpt": self.excerpt,
        }


@dataclass
class FrontmatterCache:
    """Per-process cache of parsed pages, invalidated by mtime."""

    entries: dict[Path, ParsedPage] = field(default_factory=dict)

    def get(self, path: Path, vault_root: Path) -> ParsedPage | None:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            self.entries.pop(path, None)
            return None
        cached = self.entries.get(path)
        if cached and cached.mtime == mtime:
            return cached
        parsed = _parse_page(path, mtime, vault_root)
        if parsed is not None:
            self.entries[path] = parsed
        return parsed


_CACHE = FrontmatterCache()


def find(
    vault_root: Path,
    *,
    query: str,
    types: list[str] | None = None,
    projects: list[str] | None = None,
    tags: list[str] | None = None,
    limit: int = 15,
    scope: str = "kb",
    mode: str = "hybrid",
) -> list[Hit]:
    """Search the vault. Returns up to `limit` hits.

    `scope` controls the walk root:
    - "kb" (default): only `Knowledge Base/`. Compiled material + sources.
    - "vault": full vault, including curated trees (`Cognitive Core/`,
      `Domains/`, `Prompt Bank/`, `Products/`, `Personal Context/`,
      `Systems Thinking/`). Use when you need to discover content
      outside the KB. Existing filters still apply — curated-tree pages
      typically lack structured frontmatter so `types`/`projects`/`tags`
      filters won't match many of them; free-text queries work fine.

    `mode` controls the ranker:
    - "hybrid" (default): BM25 + local vector embeddings fused via RRF.
      Best recall on natural-language queries. Empty query falls back to
      keyword behavior (filtered most-recent). Embedding sidecar is
      KB-scoped; with `scope="vault"`, vector results cover KB only
      while BM25 covers the full vault.
    - "keyword": case-insensitive substring matching across title + body,
      sorted most-recently-updated first. The original behavior, preserved
      for backward compatibility.
    - "vector": vector embeddings only, no BM25. Testing aid for
      isolating semantic recall.
    """
    if scope not in ("kb", "vault"):
        raise ValueError(
            f"find: scope must be 'kb' or 'vault', got {scope!r}"
        )
    if mode not in ("hybrid", "keyword", "vector"):
        raise ValueError(
            f"find: mode must be 'hybrid', 'keyword', or 'vector', got {mode!r}"
        )
    if limit < 1:
        limit = 1
    limit = min(limit, 100)
    query_norm = (query or "").lower().strip()

    # Empty queries always degrade to keyword behavior — there's no signal
    # to embed or score with, just "give me recent stuff that matches the
    # structured filters."
    if mode == "keyword" or not query_norm:
        return _find_keyword(
            vault_root,
            query_norm=query_norm,
            types=types, projects=projects, tags=tags,
            limit=limit, scope=scope,
        )
    return _find_semantic(
        vault_root,
        query=query, query_norm=query_norm,
        types=types, projects=projects, tags=tags,
        limit=limit, scope=scope, mode=mode,
    )


def _find_keyword(
    vault_root: Path,
    *,
    query_norm: str,
    types: list[str] | None,
    projects: list[str] | None,
    tags: list[str] | None,
    limit: int,
    scope: str,
) -> list[Hit]:
    """Original keyword-mode find. Preserved for backward compat."""
    if scope == "kb":
        kb = vault_root / "Knowledge Base"
        if not kb.is_dir():
            log.error("KB directory missing: %s", kb)
            return []
        walk = _walk_md(kb)
    else:
        from .vault import walk_vault_md
        walk = walk_vault_md(vault_root)

    hits: list[tuple[str, Hit]] = []
    for path in walk:
        page = _CACHE.get(path, vault_root)
        if page is None:
            continue
        if not _passes_filters(page, types=types, projects=projects, tags=tags):
            continue
        excerpt = _make_excerpt(page, query_norm)
        if query_norm and excerpt is None:
            continue
        hits.append(
            (
                page.updated or "0000-00-00",
                Hit(
                    path=page.rel_path,
                    type=page.page_type,
                    scope=page.scope,
                    title=page.title,
                    updated=page.updated,
                    excerpt=excerpt or "",
                ),
            )
        )

    hits.sort(key=lambda t: (t[0], t[1].path), reverse=True)
    return [h for _, h in hits[:limit]]


def _find_semantic(
    vault_root: Path,
    *,
    query: str,
    query_norm: str,
    types: list[str] | None,
    projects: list[str] | None,
    tags: list[str] | None,
    limit: int,
    scope: str,
    mode: str,
) -> list[Hit]:
    """Hybrid (BM25+vector) or vector-only mode."""
    # Lazy imports — keep keyword-mode users out of the torch import path.
    from . import bm25, embeddings, fusion

    # Pull more than we need so post-filter losses don't starve the result.
    candidate_k = max(limit * 5, 50)

    # ---- Vector contribution ----
    vector_ranking: list[str] = []
    chunk_text_by_path: dict[str, str] = {}
    try:
        idx = embeddings.EmbeddingIndex(vault_root)
        query_vec = embeddings.embed_texts([query], is_query=True)[0]
        chunk_hits = idx.search(query_vec, k=candidate_k * 3)  # over-fetch chunks
        # Collapse chunks → file-level: keep the best-scoring chunk per file.
        best_per_file: dict[str, tuple[float, str]] = {}
        for fp, _idx, ctext, score in chunk_hits:
            existing = best_per_file.get(fp)
            if existing is None or score > existing[0]:
                best_per_file[fp] = (score, ctext)
        vector_ranking = sorted(
            best_per_file.keys(), key=lambda p: -best_per_file[p][0]
        )[:candidate_k]
        chunk_text_by_path = {p: best_per_file[p][1] for p in vector_ranking}
    except ImportError as e:
        log.warning(
            "vector search unavailable (%s); falling back to BM25-only ranking",
            e,
        )
    except Exception as e:
        log.warning("vector search failed: %s; falling back to BM25-only", e)

    if mode == "vector":
        rankings = [vector_ranking] if vector_ranking else []
    else:
        # ---- BM25 contribution ----
        bm25_ranking: list[str] = []
        try:
            bm25_hits = bm25.search(vault_root, query, k=candidate_k, scope=scope)
            bm25_ranking = [p for p, _ in bm25_hits]
        except ImportError as e:
            log.warning("BM25 unavailable (%s); using vector-only", e)
        except Exception as e:
            log.warning("BM25 search failed: %s; using vector-only", e)
        rankings = [r for r in (vector_ranking, bm25_ranking) if r]

    if not rankings:
        # Both rankers failed or produced nothing. Degrade to keyword.
        log.info("semantic search produced no candidates; falling back to keyword")
        return _find_keyword(
            vault_root,
            query_norm=query_norm,
            types=types, projects=projects, tags=tags,
            limit=limit, scope=scope,
        )

    fused = fusion.reciprocal_rank_fusion(rankings, k=60)
    vector_paths: set[str] = set(vector_ranking)

    # Resolve fused paths back to ParsedPage, filter, build hits in fused order.
    # BM25-only candidates must still satisfy the keyword all-tokens-present
    # gate — without it, BM25's word-level tokenizer surfaces files that share
    # any single token with the query (false positives). Vector-ranked
    # candidates skip that gate by design: surfacing semantically-similar
    # files that don't contain the literal tokens is the whole point.
    hits: list[Hit] = []
    seen: set[str] = set()
    for rel_path, _score in fused:
        if rel_path in seen:
            continue
        seen.add(rel_path)
        abs_path = vault_root / rel_path
        page = _CACHE.get(abs_path, vault_root)
        if page is None:
            continue
        if not _passes_filters(page, types=types, projects=projects, tags=tags):
            continue
        keyword_excerpt = _make_excerpt(page, query_norm)
        if rel_path not in vector_paths and keyword_excerpt is None:
            # BM25-only, no literal match. Drop.
            continue
        chunk = chunk_text_by_path.get(rel_path)
        excerpt = _semantic_excerpt(page, query_norm, chunk, keyword_excerpt)
        hits.append(Hit(
            path=page.rel_path,
            type=page.page_type,
            scope=page.scope,
            title=page.title,
            updated=page.updated,
            excerpt=excerpt or "",
        ))
        if len(hits) >= limit:
            break
    return hits


def _semantic_excerpt(
    page: ParsedPage,
    query_norm: str,
    best_chunk: str | None,
    keyword_excerpt: str | None,
) -> str:
    """Prefer the matching chunk text (trimmed); fall back to the keyword excerpt."""
    if best_chunk:
        # Strip the title prefix the chunker prepends — it's redundant with
        # the Hit.title field.
        body = best_chunk
        title_prefix = (page.title or "").strip()
        if title_prefix and body.startswith(title_prefix + "\n\n"):
            body = body[len(title_prefix) + 2:]
        snippet = body.strip()[:EXCERPT_MAX_LEN].strip()
        if len(body) > EXCERPT_MAX_LEN:
            snippet = snippet.rstrip() + "…"
        return _collapse(snippet)
    return keyword_excerpt or ""


def _walk_md(root: Path):
    """Yield every .md path under root, skipping excluded subtrees."""
    for child in root.iterdir():
        if child.is_dir():
            if child.name in EXCLUDED_DIR_NAMES:
                continue
            yield from _walk_md(child)
        elif child.is_file() and child.suffix.lower() == ".md":
            yield child


def _parse_page(path: Path, mtime: float, vault_root: Path) -> ParsedPage | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        log.warning("could not read %s: %s", path, e)
        return None

    fm_match = FRONTMATTER_PATTERN.match(text)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
            if not isinstance(frontmatter, dict):
                frontmatter = {}
        except yaml.YAMLError as e:
            log.warning("YAML parse error in %s: %s", path, e)
            frontmatter = {}
        body = fm_match.group(2)
        # The FRONTMATTER_PATTERN consumes the closing `\n---\n` but not the
        # blank line that conventionally follows. Strip a single leading `\n`
        # so callers (notably `get`) can feed `body` back into `edit` without
        # accumulating blanks across round-trips.
        if body.startswith("\n"):
            body = body[1:]
    else:
        frontmatter = {}
        body = text

    h1_match = H1_PATTERN.search(body)
    title = h1_match.group(1).strip() if h1_match else path.stem

    try:
        rel_path = path.resolve().relative_to(vault_root.resolve()).as_posix()
    except ValueError:
        rel_path = path.as_posix()

    return ParsedPage(
        path=path,
        rel_path=rel_path,
        frontmatter=frontmatter,
        body=body,
        title=title,
        mtime=mtime,
    )


def _passes_filters(
    page: ParsedPage,
    *,
    types: list[str] | None,
    projects: list[str] | None,
    tags: list[str] | None,
) -> bool:
    if types and page.page_type not in types:
        return False
    if projects:
        page_projects = _all_projects(page.frontmatter)
        if not any(p in page_projects for p in projects):
            return False
    if tags:
        page_tags = set(page.tags)
        if not any(t.lower() in page_tags for t in tags):
            return False
    return True


def _all_projects(fm: dict) -> set[str]:
    out: set[str] = set()
    if (p := fm.get("project")):
        out.add(str(p))
    if (ps := fm.get("projects")):
        if isinstance(ps, list):
            out.update(str(x) for x in ps)
        else:
            out.add(str(ps))
    return out


def _make_excerpt(page: ParsedPage, query_norm: str) -> str | None:
    """Return ~200-char snippet anchored to the query; None if no match.

    Tokenizes the query on whitespace and requires every token to appear in
    title or body (case-insensitive, any order). So `contract employment`
    matches a page mentioning "employment contract" — natural-language
    queries don't have to guess exact phrasing.

    If query is empty, returns the first ~200 chars of body (no match required).
    """
    body = page.body.strip()
    if not query_norm:
        snippet = body[:EXCERPT_MAX_LEN]
        return _collapse(snippet)
    title_norm = page.title.lower()
    body_norm = body.lower()
    tokens = query_norm.split()
    if not tokens:
        snippet = body[:EXCERPT_MAX_LEN]
        return _collapse(snippet)
    # Every token must appear somewhere in title or body.
    for tok in tokens:
        if tok not in title_norm and tok not in body_norm:
            return None
    # Pick the anchor: first token's first body occurrence; if every token is
    # title-only, return a leading body snippet for context.
    anchor_idx = -1
    anchor_len = 0
    for tok in tokens:
        idx = body_norm.find(tok)
        if idx != -1:
            anchor_idx = idx
            anchor_len = len(tok)
            break
    if anchor_idx == -1:
        snippet = body[:EXCERPT_MAX_LEN]
        return _collapse(snippet)
    start = max(0, anchor_idx - EXCERPT_RADIUS)
    end = min(len(body), anchor_idx + anchor_len + EXCERPT_RADIUS)
    snippet = body[start:end]
    if start > 0:
        snippet = "…" + snippet.lstrip()
    if end < len(body):
        snippet = snippet.rstrip() + "…"
    return _collapse(snippet)


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clear_cache() -> None:
    """Test hook: flush the in-process cache between tests."""
    _CACHE.entries.clear()
