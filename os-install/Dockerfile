FROM debian:12.9-slim@sha256:40b107342c492725bc7aacbe93a49945445191ae364184a6d24fedb28172f6f7

LABEL org.opencontainers.image.title="Debian Automated Install Builder"
LABEL org.opencontainers.image.description="Builds Debian ISO installers with a preseed configuration"
LABEL org.opencontainers.image.authors="developer@nausicaea.net"
LABEL org.opencontainers.image.source="https://github.com/nausicaea/debian-auto"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.licenses="GPLv3"

VOLUME ["/cache", "/artifacts"]

ENV ARCH="amd64"
ENV BOOT_DEVICE="/dev/nvme0n1"
ENV BOOTSTRAP_REPO="https://github.com/nausicaea/nippon-koku"
ENV DEBIAN_MIRROR="debian.ethz.ch"
ENV DEBIAN_VERSION="12.9.0"
ENV DOMAIN=""
ENV HOSTNAME="debian"
ENV INSTALL_NONFREE_FIRMWARE="false"
ENV TIMEZONE="Europe/Zurich"

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

ENTRYPOINT ["/usr/local/bin/docker-entrypoint"]
