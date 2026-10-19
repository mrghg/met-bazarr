# AGENTS.md

Canonical instructions for AI coding agents working in this repository. This is
the **single source of truth** — every agent-specific file (`CLAUDE.md`,
`.github/copilot-instructions.md`, etc.) is a thin pointer back to this file so
that switching between agents changes nothing about how they behave here.

> New to how the agent-agnostic setup works, or adding a new agent? See
> [docs/agents.md](docs/agents.md).

## Start of session

1. **Read [STATUS.md](STATUS.md)** for current state, next actions, and open
   questions. Update it as things change and before you finish.
2. Consult [docs/decisions/](docs/decisions/) only when a past decision is
   relevant — don't read them all. Record significant new decisions there.

This file is stable; volatile working state lives in `STATUS.md`, and scratch
notes go in `notes/` (git-ignored). See [docs/architecture.md](docs/architecture.md)
for why the docs are tiered this way.

## Project overview

<!-- One paragraph: what this project does and who it's for. Replace this. -->
A scientific computing project. Reusable code lives in `src/project/`; analysis
lives in `notebooks/` and `scripts/`; data lives in `data/` (git-ignored).

## Environment & commands

This project uses [uv](https://docs.astral.sh/uv/) for environment and
dependency management. **Do not** call `pip` or edit `pyproject.toml`
dependencies by hand — use `uv`.

| Task | Command |
|------|---------|
| Install / sync the environment | `uv sync` |
| Add a runtime dependency | `uv add <pkg>` |
| Add a dev dependency | `uv add --dev <pkg>` |
| Run a script | `uv run python scripts/<name>.py` |
| Run a one-off command in the env | `uv run <cmd>` |
| Lint (with autofix) | `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Run all pre-commit hooks | `uv run pre-commit run --all-files` |

Full setup details: [docs/setup.md](docs/setup.md).

## Working agreement

- **Read before writing.** Match the conventions in the file you're editing.
- **Run `ruff check --fix` and `ruff format` before finishing** any change.
- **Never commit secrets.** Gitleaks runs on every commit; if it blocks you,
  stop and tell the user rather than working around it. Put credentials in
  `.env` (git-ignored), never in tracked files or notebooks.
- **Follow the [security policy](docs/security.md).** No pipe-to-shell, no
  `sudo`, no reading secret files, no destructive git without sign-off.
  Enforced permissions for Claude Code live in `.claude/settings.json`. For
  isolated runs, work inside the [dev container](docs/containers.md).
- **Keep data out of git.** Anything under `data/`, plus `.nc/.h5/.zarr/.parquet`
  outputs, is git-ignored by design. Don't force-add it.
- **Notebooks:** clear outputs before committing where practical; heavy outputs
  bloat the repo and can leak data.
- **Ask before** installing large dependencies, changing the Python version, or
  restructuring the project layout.
- **Commits:** only commit when the user asks. Write focused, present-tense
  commit messages.

## Conventions

Coding style, naming, and scientific-computing specifics live in
[docs/conventions.md](docs/conventions.md).

## Project structure

Where things live and why: [docs/architecture.md](docs/architecture.md).
