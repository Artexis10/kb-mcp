# kb-mcp — instructions for Claude

## Concurrent sessions share ONE checkout — work in a worktree

This repo is often worked on by more than one Claude Code session at the same
time, all sharing a single working tree. `git checkout <branch>` or `git stash`
in that shared checkout yanks files out from under the other session (it has
already caused a mid-edit collision).

**Rule: never switch branches or `git stash` in the primary checkout.** For ANY
new change — feature, fix, or docs — work in a dedicated git worktree and
commit/push from there, leaving the primary checkout on whatever branch the other
session is using.

What's forbidden is anything that *yanks files out from under another session*:
`git checkout <branch>`, `git switch`, `git stash`, `git reset --hard`, a
rebase/merge that rewrites the working tree. What's **fine** (do it yourself, no
worktree needed): a fast-forward `git pull` / `git pull --ff-only` on the branch
the checkout is *already* on (e.g. pulling `main` while on `main` after a merge) —
it only advances, it doesn't switch or stash. Read-only git (`status`, `log`,
`diff`, `fetch`) is always fine. So: don't make the user paste a `git pull` you
could run — only the worktree/branch-switch operations are off-limits here.

- Native (Claude Code): `EnterWorktree` — branches off `origin/main`; edit,
  commit, `git push origin HEAD:main` (or open a PR), then `ExitWorktree`.
- Manual: `git worktree add ../kb-mcp-<topic> -b <branch>`; work, commit, push;
  then `git worktree remove ../kb-mcp-<topic>`.

## Editing the skill scaffold (hand-authored — keep it generic)

The skill shipped to new users lives at `src/kb_mcp/_scaffold/_Schema/`
(SKILL.md + `references/*.md` + `project-keys.yaml`). It is a **hand-authored,
deliberately-generic starter** — edit it directly. It is NOT generated from a
private vault; `scripts/genericize-schema.py` is retired as a generator (running
it would clobber the hand-authored scaffold).

The hard rule: **keep it generic.** `tests/test_scaffold_no_leak.py` fails if any
personal name, product, or vault-structure label appears in the scaffold — or
anywhere under `src/kb_mcp/`. If a test flags a token, genericize it; don't add it
to an allowlist.

(Maintainer-only: a private claude.ai `.skill` zip is still derived from a private
canonical via `scripts/rebuild-schema-zip.py`; that's separate from the public
scaffold and needs no version bump here.)

## Connector triage ("MCP not working" / forced reconnect)

claude.ai connector problems are almost always **connection-side, not the service**.
A healthy service returns a fast `401` at the funnel. The most common cause is the
**Tailscale Funnel relay throttling the connector's request burst** — the connector
looks disconnected but the kb-mcp service is RUNNING and fine. **Diagnose from the
access log before touching the server** (look for the claude.ai gateway IPs); don't
restart the service reflexively.
