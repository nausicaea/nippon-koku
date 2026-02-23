#!/usr/bin/env python3

import argparse
import importlib
import os
from pathlib import Path
import shutil
from subprocess import run, DEVNULL
import hashlib
import secrets
import base64


op_client = importlib.import_module("op-client")
gen_images = importlib.import_module(".gen_images", package="os-install")
docker_path = gen_images.which_optional("docker")
podman_path = gen_images.which_optional("podman")


def sha512_crypt(password: str, salt: str = None, rounds: int = 5000) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    salt = salt[:16]
    hash = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt.encode('utf-8'), rounds)
    hash_b64 = base64.b64encode(hash).decode('utf-8').replace('+', '.')
    return f"${rounds}${salt}${hash_b64}"


def _main() -> None:
    script_path = Path(__file__)
    script_dir = script_path.parent

    parser = argparse.ArgumentParser(
        description="Generates Debian ISO images from environment variables",
        epilog="Project home page: https://app.radicle.xyz/nodes/iris.radicle.xyz/rad:zoBPQV6X2FH296n9gQxJr6suvSSi",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-p",
        "--prefix",
        type=Path,
        default=script_dir.joinpath("build"),
        help="Specify a prefix path for the artifacts",
    )
    parser.add_argument(
        "-c",
        "--context",
        type=Path,
        default=script_dir.joinpath("os-install"),
        help="Specify the directory for the Docker context",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Optionally enable verbose output"
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Optionally enable debugging"
    )
    matches = parser.parse_args()

    # Retrieve data from required environment variables
    op_account_server = gen_images.require_env("OP_ACCOUNT_SERVER")
    op_root_pw_id = gen_images.require_env("OP_ROOT_PW_ID")
    op_vault_id = gen_images.require_env("OP_VAULT_ID")
    op_host_data_id = gen_images.require_env("OP_HOST_DATA_ID")
    git_author_email = gen_images.require_env("GIT_AUTHOR_EMAIL")
    git_author_ssh_pub = gen_images.require_env("GIT_AUTHOR_SSH_PUB")

    if docker_path is not None:
        os.environ["DOCKER_CLI_HINTS"] = "false"
        docker_cli = docker_path
    elif podman_path is not None:
        docker_cli = podman_path
    else:
        raise ValueError("Could not find a Docker-compatible CLI application (looked for 'docker' and 'podman')")

    prefix: Path = matches.prefix.resolve()
    docker_context_dir: Path = matches.context.resolve()
    docker_image_tag = "nausicaea/debian-auto:latest"
    cache_dir = prefix.joinpath("cache")
    artifacts_dir = prefix.joinpath("artifacts")
    temp_dir = prefix.joinpath("temp")

    if not cache_dir.exists():
        cache_dir.mkdir(parents=True)

    if not artifacts_dir.exists():
        artifacts_dir.mkdir(parents=True)

    if not temp_dir.exists():
        temp_dir.mkdir(parents=True)

    verbose: bool = matches.verbose
    debug: bool = matches.debug

    docker_build_args = [docker_cli, "build", "-q", f"-t={docker_image_tag}", docker_context_dir]
    run(docker_build_args, stdout=DEVNULL, check=True)

    root_password_crypted = sha512_crypt(op_client.op_read(op_root_pw_id, account=op_account_server))
    ansible_vault_password = op_client.op_read(op_vault_id, account=op_account_server)
    host_data = op_client.op_read(op_host_data_id, account=op_account_server)

    docker_run_args = [
        docker_cli, 
        "run", 
        "--rm", 
        "-i",
        f"-e=ROOT_PASSWORD_CRYPTED={root_password_crypted}",
        f"-e=ANSIBLE_VAULT_PASSWORD={ansible_vault_password}",
        f"-e=GIT_AUTHOR_EMAIL={git_author_email}",
        f"-e=GIT_AUTHOR_SSH_PUB={git_author_ssh_pub}",
        f"-v={cache_dir}:/cache",
        f"-v={artifacts_dir}:/artifacts",
        f"-v={temp_dir}:/tmp",
        docker_image_tag,
    ]
    if verbose:
        docker_run_args.append("-v")
    if debug:
        docker_run_args.append("-d")
    run(
        docker_run_args,
        input=host_data,
        text=True,
        check=True
    )


if __name__ == "__main__":
    _main()
