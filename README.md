# project

<!-- Replace this with a one-line description of your project. -->
A scientific computing project, scaffolded from a template.

## Quick start

```bash
uv sync                       # create the env + install everything
uv run pre-commit install     # install git hooks (once per clone)
```

Then rename the `src/project/` package (see
[docs/architecture.md](docs/architecture.md)) and start working.

To run an agent in an isolated container instead (recommended for agentic work):

```bash
make box                      # build & start the dev container
make agent AGENT=opencode     # run your agent INSIDE the box
```

See [docs/containers.md](docs/containers.md) for VS Code, SSH, and data mounting.

## What's in the box

- **[uv](https://docs.astral.sh/uv/)** — environment & dependency management.
- **[ruff](https://docs.astral.sh/ruff/)** — linting + formatting.
- **[gitleaks](https://github.com/gitleaks/gitleaks)** — secret scanning on
  every commit.
- **[pre-commit](https://pre-commit.com/)** — runs ruff + gitleaks + hygiene
  checks automatically.
- **[AGENTS.md](AGENTS.md)** — one canonical instruction file for any AI coding
  agent, with thin pointers (`CLAUDE.md`, Copilot) so switching agents is
  seamless. See [docs/agents.md](docs/agents.md).
- **Dev Container** (`.devcontainer/`) — run agents/code in an isolated box so
  they can't touch your host filesystem or secrets. See
  [docs/containers.md](docs/containers.md).
- **Agent permissions** (`.claude/settings.json`) + a portable security policy.
  See [docs/security.md](docs/security.md).

## Layout

`src/project/` (reusable code) · `scripts/` (analysis entry points) ·
`notebooks/` (exploration) · `data/` (git-ignored) · `docs/` (project + agent
docs). Full map: [docs/architecture.md](docs/architecture.md).

## Using this as a template

1. Copy the folder (or use it as a GitHub template repo).
2. Rename `src/project/` and update `pyproject.toml`.
3. Edit `AGENTS.md` and `README.md` to describe the actual project.
4. Update `CITATION.cff` (title, authors, ORCID) and confirm the `LICENSE`
   suits the project — check any institution/funder policy.
5. `uv sync && uv run pre-commit install`.

Optional extras not wired in by default (add when needed): pytest, GitHub
Actions CI, static type checking, and containerisation/sandboxing — see notes in
[docs/architecture.md](docs/architecture.md) and [docs/setup.md](docs/setup.md).

## Contributing, citing, licensing

- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md) (the human front door;
  agents use [AGENTS.md](AGENTS.md)).
- **Citing:** citation metadata is in [CITATION.cff](CITATION.cff) — GitHub shows
  a "Cite this repository" button from it.
- **License:** [Apache-2.0](LICENSE).
