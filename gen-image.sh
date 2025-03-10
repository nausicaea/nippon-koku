#!/bin/sh

set -e

IMAGE_TAG="nausicaea/debian-auto:latest"
SCRIPT_DIR=$(dirname "$0")
CONTEXT_DIR="${SCRIPT_DIR}/os-install"

docker build -t "$IMAGE_TAG" "$CONTEXT_DIR"
exec docker run --rm \
    -v "$SCRIPT_DIR/cache:/cache" -v "$SCRIPT_DIR/artifacts:/artifacts" \
    "$IMAGE_TAG" "$@"
