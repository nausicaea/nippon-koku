#!/bin/sh

set -e

SCRIPT_DIR=$(realpath $(dirname "$0"))
TEMP_DIR=$(mktemp -d)
COMMIT_HASH="0a47df6f60c8fa62ebedf7f44ca46cd27ef2ec85"
SHA256_FILE_HASH="0dcbcb95891ee05fdbd81dc3487753bbcf7f3cd290a01667185a809994954887"
SCRIPT_DEST="$TEMP_DIR/generate-custom-ca-certs.sh"
SCRIPT_CHECKSUM="$TEMP_DIR/generate-custom-ca-certs.sha256"
CERT_DIR="$TEMP_DIR/k3s/server/tls"
CERT_ARCHIVE="$SCRIPT_DIR/bootstrap/roles/nausicaea.k3s_server/files/k3s-server-tls.tgz"
K3S_TOKEN_FILE="$SCRIPT_DIR/bootstrap/roles/nausicaea.k3s_server/files/k3s-token"

# Download the cert generation script
curl -Lo "$SCRIPT_DEST" "https://raw.githubusercontent.com/k3s-io/k3s/$COMMIT_HASH/contrib/util/generate-custom-ca-certs.sh"
chmod 0500 "$SCRIPT_DEST"
echo "$SHA256_FILE_HASH  $SCRIPT_DEST" > "$SCRIPT_CHECKSUM"
shasum -a 256 -c "$SCRIPT_CHECKSUM"

# Generate the new certificates
export DATA_DIR="$TEMP_DIR/k3s"
mkdir -p "$DATA_DIR"
cd "$TEMP_DIR"
"$SCRIPT_DEST"
cd "$SCRIPT_DIR"

# Calculate the SHA256 hash of the CA certificate
#ROOT_CA_CRT_HASH=$(shasum -a 256 "$CERT_DIR/root-ca.crt")
#SERVER_CA_PEM_HASH=$(shasum -a 256 "$CERT_DIR/server-ca.pem")
SERVER_CA_CRT_HASH=$(shasum -a 256 "$CERT_DIR/server-ca.crt" | cut -d ' ' -f 1)

echo "K10${SERVER_CA_CRT_HASH}::server:$(openssl rand -hex 16)" > "$K3S_TOKEN_FILE"
ansible-vault encrypt --vault-id=@op-client.sh "$K3S_TOKEN_FILE"

# Create and encrypt the certificate archive
if [ -e "$CERT_ARCHIVE" ]; then
    rm "$CERT_ARCHIVE"
fi
tar -czf "$CERT_ARCHIVE" --exclude "._*" -C "$CERT_DIR" "."
ansible-vault encrypt --vault-id=@op-client.sh "$CERT_ARCHIVE"
