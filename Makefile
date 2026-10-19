# Dev-container convenience commands — usable WITHOUT VS Code.
# Requires: Docker + the devcontainer CLI (npm install -g @devcontainers/cli).
#
#   make box                     build & start the container
#   make shell                   open a shell inside it
#   make agent AGENT=opencode    run a coding agent INSIDE it (contained)
#   make agent AGENT=claude      claude and opencode CLIs are baked into the image
#   make rebuild                 rebuild from scratch (also picks up new CLI versions)
#   make stop                    stop the container
#
# The security benefit only holds when the agent runs INSIDE the box (via
# `make agent` / `make shell`), not on your host against the mounted folder.

AGENT ?= bash

.PHONY: box shell agent rebuild stop

box:
	devcontainer up --workspace-folder .

shell: box
	devcontainer exec --workspace-folder . bash

agent: box
	devcontainer exec --workspace-folder . $(AGENT)

rebuild:
	devcontainer up --workspace-folder . --remove-existing-container

stop:
	-docker stop $$(docker ps -q --filter "label=devcontainer.local_folder=$(CURDIR)")
