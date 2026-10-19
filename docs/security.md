# Security policy for agents

This policy has two layers. The **advisory** layer is portable — every agent
reads it. The **enforcement** layer is per-agent, because tools don't share a
permission model.

## What an allow-list can and can't do

- It **reduces prompting friction** for common safe commands and **guards
  against accidents** (an errant `rm -rf`, a stray force-push).
- It is **not containment.** Once `python` / `uv run` are allowed — which
  scientific work requires — an agent can do anything through the interpreter,
  and Bash pattern-matching (`rm -rf`) is bypassable (`rm -r -f`, subshells).
- The **real boundary is OS-level isolation**, which Claude Code's sandboxing
  provides. The rules below are defense-in-depth on top of it, not a
  substitute.

The one enforced control that *is* a real boundary: **Read/Edit deny rules on
secret files** (`.env`, `~/.ssh`, `~/.aws`). Those stop an agent pulling
credentials into context at all.

## Advisory rules (all agents)

- **Never exfiltrate secrets.** Don't read `.env`, `~/.ssh`, `~/.aws`, tokens,
  or credentials, and never paste them into commits, notebooks, or web requests.
- **No pipe-to-shell.** Never `curl … | sh` / `wget … | bash`.
- **No privilege escalation.** No `sudo`, no changing system config.
- **Destructive git needs sign-off.** No force-push, `reset --hard`, or history
  rewriting on shared branches without the user asking.
- **Prefer reversible actions.** Ask before deleting files or data.
- **Network egress is sensitive.** Flag before fetching from or posting to the
  network beyond declared dependencies.

## Enforcement layer (per-agent)

| Agent | Where enforcement lives | Status here |
|-------|-------------------------|-------------|
| Claude Code | `.claude/settings.json` (`permissions.allow/ask/deny`) | **Configured** — permissive deny-list |
| Codex | sandbox mode + approval policy (`~/.codex/config.toml`, `sandbox_mode = "workspace-write"`) | Not set up — configure when adopted |
| Cursor | terminal allow/deny lists in Cursor settings | Not set up — configure when adopted |

### Claude Code (configured)

`.claude/settings.json` uses a **permissive deny-list** (precedence:
deny > ask > allow):

- **allow** — common safe dev commands (`uv`, `ruff`, `python`, `pytest`, git
  read/stage/commit, `ls`/`cat`/`grep`, …) run without prompting.
- **ask** — reversible-but-risky commands prompt each time (`rm`, `mv`,
  `git push`, `git checkout`, `gh`, `curl`, `wget`, `WebFetch`).
- **deny** — catastrophic or exfiltration-risk actions are blocked outright
  (`sudo`, `rm -rf`, force-push, `reset --hard`, and Read/Edit of secret files).

Personal overrides go in `.claude/settings.local.json` (git-ignored); the
committed `settings.json` is the shared team baseline.

### Adding another agent

Mirror the *intent* above in that agent's own config, then update the table.
For sandbox-based agents (Codex), the equivalent of the deny-list is choosing a
restrictive `sandbox_mode` and letting approvals cover the rest.
