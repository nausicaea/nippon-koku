#!/bin/sh

set -e

IMAGE_TAG="nausicaea/debian-auto:latest"
SCRIPT_DIR=$(dirname "$0")
CONTEXT_DIR="${SCRIPT_DIR}/os-install"
HOSTNAMES="shizuoka osaka"
ARCH="${ARCH:-amd64}"
BOOT_DEVICE="${BOOT_DEVICE:-/dev/nvme0n1}"
BOOTSTRAP_BRANCH="${BOOTSTRAP_BRANCH:-main}"

docker build -q -t "$IMAGE_TAG" "$CONTEXT_DIR"

echo $HOSTNAMES | tr ' ' '\n' | while read HOSTNAME; do
    docker run --rm -q \
        -v "$SCRIPT_DIR/cache:/cache" -v "$SCRIPT_DIR/artifacts:/artifacts" \
        "$IMAGE_TAG" \
        -b "$BOOT_DEVICE" -H "$HOSTNAME" -a "$ARCH" -B "$BOOTSTRAP_BRANCH" \
        -r $(openssl passwd -6 $(op read --account="$OP_ACCOUNT_SERVER" "$OP_ROOT_PW_ID")) \
        -v $(op read --account="$OP_ACCOUNT_SERVER" "$OP_VAULT_ID") \
        -e "$GIT_AUTHOR_EMAIL" -s "$GIT_AUTHOR_SSH_PUB"
done
