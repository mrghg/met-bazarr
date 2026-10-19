# Agent-agnostic setup

This repo is designed so that **any** AI coding agent behaves identically,
because they all read from one canonical file: [`AGENTS.md`](../AGENTS.md).

## How it works

`AGENTS.md` is an emerging cross-tool convention (Codex, Cursor, Gemini CLI,
opencode, Zed, and others read it natively). For agents that look for their own
filename instead, we drop a **one-line pointer** file that redirects them to
`AGENTS.md`. That way there is exactly one place to edit instructions, and
switching agents requires no changes.

## Current pointers

| Agent | File it reads | How it's wired here |
|-------|---------------|---------------------|
| Claude Code | `CLAUDE.md` | Pointer → `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` | Pointer → `AGENTS.md` |
| Codex / Cursor / Gemini CLI / opencode / Zed | `AGENTS.md` | Read natively — no pointer needed |

## Adding a new agent

1. Find out which instruction file the agent reads (check its docs).
2. If it reads `AGENTS.md` natively, you're done.
3. Otherwise create that file with a single line pointing to `AGENTS.md`, e.g.:

   ```markdown
   See [AGENTS.md](AGENTS.md) for all instructions in this repository.
   ```
4. Add a row to the table above.

## Why keep instructions modular

`AGENTS.md` stays short and links out to focused docs
([setup](setup.md), [conventions](conventions.md),
[architecture](architecture.md)). This keeps the always-loaded context small
(cheaper, sharper) while letting agents pull in detail only when relevant.
