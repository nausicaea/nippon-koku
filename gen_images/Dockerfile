FROM docker.io/library/rust:1.91.1-alpine3.21@sha256:32817dd3ce1cd4ed459dcc289df1b906dc53719975156636e605063821668b1e AS builder

RUN apk add --no-cache openssl-libs-static openssl-dev musl-dev
WORKDIR /src
COPY --link Cargo.toml .
COPY --link Cargo.lock .
COPY --link src ./src
RUN --mount=type=cache,target=/root/.cargo cargo fetch
RUN --mount=type=cache,target=/root/.cargo --mount=type=cache,target=/src/target cargo build --locked --release
WORKDIR /artifacts
RUN --mount=type=cache,target=/src/target cp /src/target/release/gen-images /artifacts/gen-images


FROM docker.io/library/alpine:3.21@sha256:c3f8e73fdb79deaebaa2037150150191b9dcbfba68b4a46d70103204c53f4709

LABEL org.opencontainers.image.title="Debian Automated Install Builder"
LABEL org.opencontainers.image.description="Builds Debian ISO installers with a preseed configuration"
LABEL org.opencontainers.image.authors="developer@nausicaea.net"
LABEL org.opencontainers.image.source="https://iris.radicle.xyz/zoBPQV6X2FH296n9gQxJr6suvSSi.git"
LABEL org.opencontainers.image.version="0.4.0"
LABEL org.opencontainers.image.licenses="GPLv3"

VOLUME ["/cache", "/artifacts"]

RUN set -e; apk add --no-cache libarchive-tools cpio xorriso

WORKDIR /src
COPY --link --chown=root:root --chmod=0400 ./templates/* ./

WORKDIR /usr/local/bin
COPY --from=builder --link --chown=root:root --chmod=0755 /artifacts/gen-images /usr/local/bin/gen-images

WORKDIR /cache
ENTRYPOINT ["/usr/local/bin/gen-images"]
