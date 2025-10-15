FROM docker.io/library/debian:13.1-slim@sha256:1caf1c703c8f7e15dcf2e7769b35000c764e6f50e4d7401c355fb0248f3ddfdb

LABEL org.opencontainers.image.title="Debian Automated Install Builder"
LABEL org.opencontainers.image.description="Builds Debian ISO installers with a preseed configuration"
LABEL org.opencontainers.image.authors="developer@nausicaea.net"
LABEL org.opencontainers.image.source="https://iris.radicle.xyz/zoBPQV6X2FH296n9gQxJr6suvSSi.git"
LABEL org.opencontainers.image.version="0.2.0"
LABEL org.opencontainers.image.licenses="GPLv3"

VOLUME ["/cache", "/artifacts"]

RUN <<-EOM
    set -e
    apt-get update
    apt-get install -y \
        make curl libarchive-tools cpio genisoimage \
        coreutils util-linux xorriso syslinux-common \
        syslinux-efi isolinux fdisk
    apt-get clean
EOM

WORKDIR /src
COPY --link --chown=root:root --chmod=0400 ./templates/* ./

WORKDIR /usr/local/bin
COPY --link --chown=root:root --chmod=0755 ./docker-entrypoint.sh ./docker-entrypoint

WORKDIR /cache
ENTRYPOINT ["/usr/local/bin/docker-entrypoint"]
