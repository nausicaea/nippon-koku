#!/bin/sh

set -e

# Required arguments (provided via getotps)
# HOST_DATA=""

# Required environment variables (we assume that these environment variables are present)
# GIT_AUTHOR_EMAIL=""
# GIT_AUTHOR_SSH_PUB=""
# KUBE_APISERVER_URL=""

# Arguments with defaults
BOOTSTRAP_BRANCH="${BOOTSTRAP_BRANCH:-main}"

# Hardcoded variables
SCRIPT_DIR=$(dirname "$0")
CONTEXT_DIR="${SCRIPT_DIR}/os-install"
IMAGE_TAG="nausicaea/debian-auto:latest"

while getopts ':h' 'opt'; do
    case $opt in
        h)
            printf \
'nippon-koku 0.1.0 (gen-images.sh)
Eleanor Young <developer@nausicaea.net>

Convenience script to generate Debian images for many hosts

Project home page: https://github.com/nausicaea/nippon-koku

USAGE:
  gen-images.sh [OPTIONS] HOST_DATA [HOST_DATA ...]

OPTIONS:
  -h                            Print this usage message and exit.

ARGUMENTS:
  HOST_DATA                     For every image to generate, specify 
                                a hostname, architecture, and boot 
                                device triplet, e.g. "debian:arm64:/dev/sda"
'
            exit 0
            ;;
        :)
            echo "Option -${OPTARG} requires an argument."
            exit 1
            ;;
        ?)
            echo "Unknown option: -${OPTARG}."
            exit 1
            ;;
    esac
done

docker build -q -t "$IMAGE_TAG" "$CONTEXT_DIR"

for host_data in "$@"; do
    IFS=":" read -r host_name host_arch host_boot_device <<< "$host_data"
    docker run --rm -q \
        -v "$SCRIPT_DIR/cache:/cache" -v "$SCRIPT_DIR/artifacts:/artifacts" \
        "$IMAGE_TAG" \
        -b "$host_boot_device" -H "$host_name" -a "$host_arch" -B "$BOOTSTRAP_BRANCH" \
        -r $(openssl passwd -6 $(op read --account="$OP_ACCOUNT_SERVER" "$OP_ROOT_PW_ID")) \
        -v $(op read --account="$OP_ACCOUNT_SERVER" "$OP_VAULT_ID") \
        -e "$GIT_AUTHOR_EMAIL" -s "$GIT_AUTHOR_SSH_PUB" -k "$KUBE_APISERVER_URL"
done
