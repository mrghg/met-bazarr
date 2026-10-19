# Running in a container

This repo ships a **Dev Container** (`.devcontainer/`) so you can run agents and
code inside an isolated box. The agent sees only this project — not `~/.ssh`,
`~/.aws`, your other repos, or the rest of your disk. If something goes wrong
(a destructive command, a prompt-injection), the blast radius is the container.

## The one rule that makes it secure

> **The agent must run *inside* the container.**

Isolation comes from *where the process runs*, not which folder it edits.
Running an agent on your host against the mounted folder gives **zero**
isolation. Launch it inside (`make agent`, `make shell`, VS Code's terminal
after "Reopen in Container", or `devcontainer exec`).

## After editing the Dockerfile or devcontainer.json, rebuild

`make box` (`devcontainer up`) reuses an already-running container — it does
**not** detect Dockerfile changes on its own. If you edit the Dockerfile (e.g.
add a package or bump a CLI version) and just run `make box`/`make agent`
again, you'll silently get the *old* container. Symptom: a tool you just added
comes back `command not found`. Fix: `make rebuild` (forces a fresh image +
container), then `make agent` as usual.

## Three ways into the same box

The `.devcontainer/` config is an open spec — not VS Code-only. Same box, three doors:

| Door | Command | For |
|------|---------|-----|
| VS Code | Command Palette → "Dev Containers: Reopen in Container" | GUI editing |
| devcontainer CLI | `make box` then `make shell` / `make agent AGENT=opencode` | OpenCode, Claude, any CLI agent |
| Plain Docker | `docker exec -it <container> bash` | low-level fallback |

The CLI doors need it once: `npm install -g @devcontainers/cli`.

### Running a CLI agent (e.g. OpenCode)

```bash
make box                      # build & start
make agent AGENT=opencode     # run OpenCode INSIDE the container
make agent AGENT=claude       # or Claude Code
```

Agent API keys must exist *inside* the box. `.devcontainer/devcontainer.json`
passes specific host env vars through (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) —
add whichever your agent needs there, and export them in your host shell. It
deliberately does **not** pass your whole `.env`.

### How the agent CLIs get into the container

Both `@anthropic-ai/claude-code` and `opencode-ai` are npm packages, so the
[Dockerfile](../.devcontainer/Dockerfile) adds Node.js (via NodeSource) and
`npm install -g`s them **at build time** — baked into the image, not fetched on
every container start. This mirrors Anthropic's own reference devcontainer.

Two things to know:

- **You cannot use your Mac's `claude`/`opencode` binaries.** A host binary
  won't run in the container even on the same chip — different OS/libc. They
  must be installed inside the image.
- **Pin versions for reproducibility.** The Dockerfile defaults to `latest` at
  each build, which is convenient early on but means two builds a week apart
  can silently differ. Once you've settled on a setup, pin exact versions:
  ```dockerfile
  ARG CLAUDE_CODE_VERSION=2.x.x
  ARG OPENCODE_VERSION=x.x.x
  ```
  Bump them and run `make rebuild` when you want to upgrade — don't rely on
  the running container picking up a new version on its own.
- **Adding another agent CLI:** if it's npm-distributed, add it to the same
  `npm install -g` line with its own version ARG. If it ships as a standalone
  binary instead, add its official install step as its own `RUN` line, the
  same way — reviewed once by you, baked at build time.

### VS Code Remote over SSH

Works, and composes: Remote-SSH into the server, then "Reopen in Container" —
the container runs **on the remote host** and isolates you there. Requirement:
Docker installed on the remote host. The mounted folder is the project *on that
host*. CLI agents: SSH in, then `make agent` on the remote.

## Pointing `data/` at files outside the repo

**Do not symlink.** A symlink to a host path (`/Volumes/…`) dangles inside the
container. Use a **bind mount** instead:

1. Export the real location on your host (once, e.g. in `~/.zshrc`):
   ```bash
   export LOCAL_DATA_DIR=/absolute/path/to/your/data
   ```
2. Uncomment the data mount line in `.devcontainer/devcontainer.json`. It maps
   that folder onto `data/` **read-only** — the agent can read it, not corrupt it.

Code always accesses data via `DATA_DIR` (see [`src/project/config.py`](../src/project/config.py)),
which the container sets to `/workspace/data`. So the same code works whether
data is in-repo, bind-mounted, or on a remote host.

## Notes & gotchas

- **The venv is not shared with your host.** The container builds its own Linux
  virtualenv (`uv sync` runs on create) at `/home/dev/.venv`, separate from your
  macOS `./.venv`. This is deliberate — they're built for different platforms.
- **Apple Silicon:** the image is arm64, so scientific wheels are native/fast.
- **Network** is open by default (uv needs it). To lock it down after deps are
  installed, see the `--network=none` note in `devcontainer.json` — but it also
  blocks the agent's own API calls, so it's a deliberate per-run choice.
- **This is strong isolation, not absolute.** Containers share the host kernel;
  a kernel exploit could escape. That's beyond this threat model (accidental
  damage + prompt injection), against which the container is more than enough.
