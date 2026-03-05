FROM docker.io/library/debian:13.3-slim@sha256:1d3c811171a08a5adaa4a163fbafd96b61b87aa871bbc7aa15431ac275d3d430

LABEL org.opencontainers.image.title="Debian Automated Install Builder"
LABEL org.opencontainers.image.description="Builds Debian ISO installers with a preseed configuration"
LABEL org.opencontainers.image.authors="developer@nausicaea.net"
LABEL org.opencontainers.image.source="https://iris.radicle.xyz/zoBPQV6X2FH296n9gQxJr6suvSSi.git"
LABEL org.opencontainers.image.version="0.3.0"
LABEL org.opencontainers.image.licenses="GPLv3"

VOLUME ["/cache", "/artifacts"]

RUN <<-EOM
    set -e
    apt-get update
    apt-get install -y \
        make curl libarchive-tools cpio genisoimage \
        coreutils util-linux xorriso syslinux-common \
        syslinux-efi isolinux fdisk python3 \
        python3-passlib
    apt-get clean
EOM

WORKDIR /src
COPY --link --chown=root:root --chmod=0400 ./templates/* ./

WORKDIR /usr/local/lib/debian_auto
COPY --link --chown=root:root --chmod=0755 ./gen_images.py ./

WORKDIR /usr/local/bin
RUN ln -s /usr/local/lib/debian_auto/gen_images.py /usr/local/bin/gen-images

WORKDIR /cache
ENTRYPOINT ["/usr/local/bin/gen-images"]
