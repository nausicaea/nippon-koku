#!/bin/sh

set -e

IMAGE_TAG="nausicaea/debian-auto:latest"
SCRIPT_DIR=$(dirname "$0")

docker build -t "$IMAGE_TAG" "$SCRIPT_DIR"
exec docker run --rm \
    -v "$SCRIPT_DIR/cache:/cache" -v "$SCRIPT_DIR/artifacts:/artifacts" \
    "$IMAGE_TAG" "$@"
