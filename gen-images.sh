#!/bin/bash

set -e

# Positional arguments (provided via getotps)
# HOST_DATA=""

# Required environment variables (we assume that these environment variables are present)
# GIT_AUTHOR_EMAIL=""
# GIT_AUTHOR_SSH_PUB=""

# Hardcoded variables
SCRIPT_DIR=$(dirname "$0")
CONTEXT_DIR="$SCRIPT_DIR/os-install"
IMAGE_TAG="nausicaea/debian-auto:latest"

DOCKER=$(which docker || true)
PODMAN=$(which podman || true)
DOCKER_CLI=""
if [ -n "$DOCKER" ]; then
    export DOCKER_CLI_HINTS=false
    DOCKER_CLI="$DOCKER"
elif [ -n "$PODMAN" ]; then
    DOCKER_CLI="$PODMAN"
else
    printf 'Could not find a Docker-compatible CLI application (looked for "docker" and "podman")\n' 1>&2
    exit 1
fi

# Create helper directories
CACHE_DIR="$SCRIPT_DIR/cache"
if [ ! -d "$CACHE_DIR" ]; then
    mkdir "$CACHE_DIR"
fi
ARTIFACT_DIR="$SCRIPT_DIR/artifacts"
if [ ! -d "$ARTIFACT_DIR" ]; then
    mkdir "$ARTIFACT_DIR"
fi

# Build the docker image
"$DOCKER_CLI" build -q -t "$IMAGE_TAG" "$CONTEXT_DIR" >/dev/null

# Execute the Debian image builder
export ROOT_PASSWORD_CRYPTED=$(openssl passwd -6 $(op read --account="$OP_ACCOUNT_SERVER" "$OP_ROOT_PW_ID"))
export ANSIBLE_VAULT_PASSWORD=$(op read --account="$OP_ACCOUNT_SERVER" "$OP_VAULT_ID")

op read "$OP_HOST_DATA_ID" | "$DOCKER_CLI" run --rm -i \
    -e "ROOT_PASSWORD_CRYPTED=$ROOT_PASSWORD_CRYPTED" \
    -e "ANSIBLE_VAULT_PASSWORD=$ANSIBLE_VAULT_PASSWORD" \
    -e "GIT_AUTHOR_EMAIL=$GIT_AUTHOR_EMAIL" \
    -e "GIT_AUTHOR_SSH_PUB=$GIT_AUTHOR_SSH_PUB" \
    -v "$CACHE_DIR:/cache" \
    -v "$ARTIFACT_DIR:/artifacts" \
    "$IMAGE_TAG" -i -
