#!/usr/bin/env python3

"""
Generate a certificate hierarchy for K3s and the cluster join token, then
encrypt them with Ansible.
"""

import argparse
import hashlib
import pathlib
import secrets
import subprocess
import tarfile
import tempfile
import urllib.request

import OpenSSL.crypto


SCRIPT_COMMIT_HASH: str = "0a47df6f60c8fa62ebedf7f44ca46cd27ef2ec85"
SCRIPT_SHA256_HASH: str = "0dcbcb95891ee05fdbd81dc3487753bbcf7f3cd290a01667185a809994954887"
SCRIPT_URL: str = f"https://raw.githubusercontent.com/k3s-io/k3s/{SCRIPT_COMMIT_HASH}/contrib/util/generate-custom-ca-certs.sh"


def download_cert_generation_script(script_dest: pathlib.Path):
    """
    Downloads and verifies the K3S helper script to a temporary directory.
    """

    # Download the cert generation script
    urllib.request.urlretrieve(SCRIPT_URL, filename=script_dest)

    # Verify the integrity of the script
    with script_dest.open("rb") as script_data:
        sha256_hash = hashlib.sha256(script_data.read()).hexdigest()
        if sha256_hash != SCRIPT_SHA256_HASH:
            raise Exception(f"SHA256 hash mismatch: expected {SCRIPT_SHA256_HASH}, got {sha256_hash}")


def create_k3s_cert_hierarchy(generate_custom_ca_certs: pathlib.Path, data_dir: pathlib.Path, temp_dir: pathlib.Path, cert_temp_dir: pathlib.Path, cert_archive_dest: pathlib.Path, ansible_args: list[str]):
    """
    Generate a custom certificate chain by calling the K3S helper script,
    archive all certificates, keys, and additional files into a TAR-GZIP
    archive, and encrypt the archive using ansible-vault.
    """

    # Execute the script within the temporary directory
    data_dir.mkdir()
    subprocess.run(
        ["/bin/sh", str(generate_custom_ca_certs)], 
        cwd=temp_dir, 
        env={"DATA_DIR": str(data_dir)},
        capture_output=True,
    )

    # Create and encrypt the certificate archive
    cert_archive_dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(cert_archive_dest, mode="w:gz") as cert_archive_file:
        cert_archive_file.add(cert_temp_dir, arcname=".", recursive=True)

    subprocess.run(
        ["ansible-vault", "encrypt", *ansible_args, str(cert_archive_dest)], 
        capture_output=True,
    )


def create_k3s_secure_token(root_ca_pem: pathlib.Path, k3s_token_dest: pathlib.Path, ansible_args: list[str]):
    """
    Calculate the SHA256 hash of the root CA certificate in DER format,
    generate 16 bits of secure random data, construct a K3S secure token, write
    this token to a file, and encrypt the file with ansible-vault.
    """

    with root_ca_pem.open("rb") as root_ca_pem_file:
        root_ca_pem_data = root_ca_pem_file.read()

    cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, root_ca_pem_data)
    root_ca_der_data = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_ASN1, cert)

    root_ca_der_sha256_hash = hashlib.sha256(root_ca_der_data).hexdigest()
    k3s_token_short = secrets.token_hex(16)

    k3s_token_dest.parent.mkdir(parents=True, exist_ok=True)
    with k3s_token_dest.open("wt") as ktf:
        ktf.write(f"K10{root_ca_der_sha256_hash}::server:{k3s_token_short}")

    subprocess.run(
        ["ansible-vault", "encrypt", *ansible_args, str(k3s_token_dest)], 
        capture_output=True,
    )


def main():
    script_dir = pathlib.Path(__file__).parent
    default_output_prefix = script_dir.joinpath("bootstrap", "roles", "nausicaea.k3s", "files")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-a", "--ansible-arg", action="append", type=str, default=None, help="""Specify an additional argument for ansible-vault. Can be specified more than once. You must use the equal sign between the option '-a' and its value, i.e. '--ansible-arg="--vault-id vault-id"'""")
    parser.add_argument("-p", "--output-prefix", type=pathlib.Path, default=default_output_prefix, help="Specify the output directory prefix")
    matches = parser.parse_args()

    ansible_args: list[str] = matches.ansible_arg
    output_prefix: pathlib.Path = matches.output_prefix.resolve(strict=False)
    k3s_token_file = output_prefix.joinpath("k3s-token")
    cert_archive = output_prefix.joinpath("k3s-server-tls.tgz")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = pathlib.Path(temp_dir)
        script_dest = temp_dir.joinpath("generate-custom-ca-certs.sh")
        data_dir = temp_dir.joinpath("k3s")
        cert_dir = temp_dir.joinpath("k3s", "server", "tls")
        root_ca_pem = cert_dir.joinpath("root-ca.pem")

        download_cert_generation_script(script_dest)

        # Generate the certificate hierarchy
        create_k3s_cert_hierarchy(
            script_dest,
            data_dir,
            temp_dir,
            cert_dir,
            cert_archive,
            ansible_args,
        )

        # Generate the K3S secure token
        create_k3s_secure_token(
            root_ca_pem,
            k3s_token_file,
            ansible_args,
        )


if __name__ == "__main__":
    main()
