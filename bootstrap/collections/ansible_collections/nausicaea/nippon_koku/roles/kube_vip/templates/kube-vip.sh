#!/bin/sh

KVVERSION='v1.0.0'
KVIMAGE="ghcr.io/kube-vip/kube-vip:$KVVERSION"

PODMAN_VERSION=$(podman --version 2> /dev/null || true )
CTR_VERSION=$(ctr --version 2> /dev/null || true )

if [ -n "$PODMAN_VERSION" ]; then
    exec podman run --rm --network=host "$KVIMAGE" "$@"
elif [ -n "$CTR_VERSION" ]; then
    ctr image pull "$KVIMAGE"
    exec ctr run --rm --net-host "$KVIMAGE" vip /kube-vip "$@"
fi

