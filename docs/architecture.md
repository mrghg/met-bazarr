# Project structure

```
.
├── AGENTS.md                 # Canonical instructions for AI agents (stable)
├── STATUS.md                 # Current working state + next actions (volatile)
├── CLAUDE.md                 # Pointer → AGENTS.md
├── .github/
│   └── copilot-instructions.md  # Pointer → AGENTS.md
├── .claude/
│   └── settings.json         # Claude Code permission allow/ask/deny lists
├── docs/                     # Modular docs referenced from AGENTS.md
│   ├── agents.md
│   ├── setup.md
│   ├── conventions.md
│   ├── architecture.md
│   ├── security.md
│   ├── roadmap.md            # Task list: who needs what, and in what order
│   └── decisions/            # Dated, immutable decision records (ADRs)
│       ├── README.md         #   one-line index
│       └── 0000-template.md
├── notes/                    # Ephemeral per-session scratch (git-ignored)
│   └── README.md
├── src/
│   └── metbazarr/            # Importable package
│       └── __init__.py
├── scripts/                  # Runnable analysis entry points
├── notebooks/                # Exploratory Jupyter notebooks
├── data/                     # Raw/large data (git-ignored)
│   └── README.md
├── pyproject.toml            # Project metadata, deps, ruff config
├── uv.lock                   # Locked dependency versions (commit this)
├── .python-version           # Pinned Python version
├── .pre-commit-config.yaml   # ruff + gitleaks + hygiene hooks
├── .gitleaks.toml            # Secret-scanning config
├── .env.example              # Template for local secrets (copy to .env)
└── .gitignore
```

## How the agent docs are tiered

Instructions are split by how often they change, so the always-loaded context
stays small and the prompt cache stays warm:

- **Tier 1 — `AGENTS.md`** (stable): auto-loaded every session. Editing it
  invalidates the cache, so keep volatile state out of it.
- **Tier 2 — `STATUS.md`** (volatile): a tiny handoff note read at the start of
  a session via the pointer in `AGENTS.md`. Isolated so its churn doesn't touch
  Tier 1.
- **Tier 3 — `docs/decisions/`, `notes/`, deep docs** (on demand): read only
  when relevant. Decision records are immutable once written; session notes are
  git-ignored scratch, distilled into Tier 2/3 when something durable emerges.

## The `src/` layout

Code you want to import and reuse goes in `src/metbazarr/`. The `src/` layout
means the package is only importable after it's installed into the environment
(`uv sync` does this in editable mode), which prevents "works because I'm in the
right directory" bugs.

## Data

`data/` is git-ignored (except its `README.md` and `.gitkeep`). Document where
the real data comes from in `data/README.md` — a path on shared storage, a DOI,
a download script — so the repo stays reproducible without shipping the bytes.
