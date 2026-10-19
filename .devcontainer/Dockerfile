# Dev container image: Python + uv, Debian-based, running as a non-root user.
# Base image ships uv preinstalled. https://github.com/astral-sh/uv
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# System packages: git for version control, curl/ca-certificates/gnupg for
# fetching Node.js below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gnupg \
        make \
    && rm -rf /var/lib/apt/lists/*

# Node.js — needed only to install the agent CLIs below (both are npm-
# distributed). NodeSource's official setup script, run once at build time
# under your control — not the kind of runtime pipe-to-shell docs/security.md
# warns agents off.
ARG NODE_MAJOR=20
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Agent CLIs, baked into the image (reproducible, fast container start).
# Pin versions here rather than "latest" once you've settled on one; bump by
# editing the ARG and running `make rebuild`.
ARG CLAUDE_CODE_VERSION=latest
ARG OPENCODE_VERSION=latest
RUN npm install -g \
        @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
        opencode-ai@${OPENCODE_VERSION} \
    && npm cache clean --force

# Non-root user — the agent should not run as root inside the box.
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

# uv configuration:
#  - Put the virtualenv OUTSIDE the mounted workspace, so the Linux venv in the
#    container never collides with the macOS venv on your host's ./.venv.
#  - copy link mode avoids hardlink warnings across the bind-mount filesystem.
ENV UV_PROJECT_ENVIRONMENT=/home/$USERNAME/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/home/$USERNAME/.venv/bin:$PATH

USER $USERNAME
