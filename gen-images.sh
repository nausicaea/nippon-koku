#!/bin/bash

set -e

function build_image() {
    OLD_IFS="$IFS"
    IFS=","
    read -r 'host_name' 'host_arch' 'host_boot_device' 'kube_apiserver_url' <<< "$9"
    IFS="$OLD_IFS"

    if [ "x$host_name" = "x" -o "x$host_arch" = "x" -o "x$host_boot_device" = "x" -o "x$kube_apiserver_url" = "x" ]; then
        echo "Wrong host data format: Expected CSV data with four columns, got: '$9'"
        return 1
    fi

    docker run --rm -q \
        -v "$1/cache:/cache" -v "$1/artifacts:/artifacts" \
        "$2" \
        -b "$host_boot_device" -H "$host_name" -a "$host_arch" -B "$3" \
        -r $(openssl passwd -6 $(op read --account="$4" "$5")) \
        -v $(op read --account="$4" "$6") \
        -e "$7" -s "$8" -k "$kube_apiserver_url"
}

# Positional arguments (provided via getotps)
# HOST_DATA=""

# Required environment variables (we assume that these environment variables are present)
# GIT_AUTHOR_EMAIL=""
# GIT_AUTHOR_SSH_PUB=""
# KUBE_APISERVER_URL=""

# Arguments with defaults
BOOTSTRAP_BRANCH="${BOOTSTRAP_BRANCH:-main}"
INPUT_FILE=""

# Hardcoded variables
SCRIPT_DIR=$(dirname "$0")
CONTEXT_DIR="${SCRIPT_DIR}/os-install"
IMAGE_TAG="nausicaea/debian-auto:latest"

while getopts ':hi:' 'opt'; do
    case $opt in
        h)
            printf \
'nippon-koku 0.1.0 (gen-images.sh)
Eleanor Young <developer@nausicaea.net>

Convenience script to generate Debian images for many hosts

Project home page: https://app.radicle.xyz/nodes/iris.radicle.xyz/rad:zoBPQV6X2FH296n9gQxJr6suvSSi

USAGE:
  gen-images.sh [OPTIONS] HOST_DATA [HOST_DATA ...]

OPTIONS:
  -h                            Print this usage message and exit.
  -i INPUT_FILE                 Optionally specify a file with host
                                data triplets (each separated by 
                                newlines). The special value "-" 
                                indicates that you would like 
                                to read data from stdin.

ARGUMENTS:
  HOST_DATA                     For every image to generate, 
                                specify hostname, architecture, 
                                boot device, and Kube API server 
                                URL as CSV format.
'
            exit 0
            ;;
        i)
            INPUT_FILE="${OPTARG}"
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
shift $((OPTIND-1))

export DOCKER_CLI_HINTS=false
docker build -q -t "$IMAGE_TAG" "$CONTEXT_DIR" >/dev/null

if [ -f "$INPUT_FILE" ]; then
    while read 'host_data'; do
        if ! [ -z "$host_data" ]; then
            build_image "$SCRIPT_DIR" "$IMAGE_TAG" "$BOOTSTRAP_BRANCH" "$OP_ACCOUNT_SERVER" \
                "$OP_ROOT_PW_ID" "$OP_VAULT_ID" "$GIT_AUTHOR_EMAIL" "$GIT_AUTHOR_SSH_PUB" \
                "$host_data"
        fi
    done < "$INPUT_FILE"
elif [ "$INPUT_FILE" = "-" ]; then
    while IFS= read -r 'host_data'; do
        if ! [ -z "$host_data" ]; then
            build_image "$SCRIPT_DIR" "$IMAGE_TAG" "$BOOTSTRAP_BRANCH" "$OP_ACCOUNT_SERVER" \
                "$OP_ROOT_PW_ID" "$OP_VAULT_ID" "$GIT_AUTHOR_EMAIL" "$GIT_AUTHOR_SSH_PUB" \
                "$host_data"
        fi
    done
fi

for host_data in "$@"; do
    if ! [ -z "$host_data" ]; then
        build_image "$SCRIPT_DIR" "$IMAGE_TAG" "$BOOTSTRAP_BRANCH" "$OP_ACCOUNT_SERVER" \
            "$OP_ROOT_PW_ID" "$OP_VAULT_ID" "$GIT_AUTHOR_EMAIL" "$GIT_AUTHOR_SSH_PUB" \
            "$host_data"
    fi
done
