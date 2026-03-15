#!/usr/bin/env python3

"""
gen-images.py: Build modified Debian installer ISOs.
"""

import argparse
import csv
import importlib
import os
from pathlib import Path
import json
import shutil
from subprocess import run, DEVNULL
import sys


def dbg(v):
    print(f"dbg: {type(v)} {repr(v)}")
    return v


def op_read(ref: str, account: str) -> str:
    """Read a single secret from 1Password via the `op` CLI."""
    op_path = shutil.which("op")
    if op_path is None:
        raise SystemExit(
            "Cannot find the command `op`. Did you install the 1Password CLI?"
        )
    result = run(
        [Path(op_path), "read", ref, f"--account={account}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).parent
    parser = argparse.ArgumentParser(
        description="Generates Debian ISO images; secrets are sourced from 1Password.",
        epilog="Project home page: https://app.radicle.xyz/nodes/iris.radicle.xyz/rad:zoBPQV6X2FH296n9gQxJr6suvSSi",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--prefix",
        type=Path,
        default=script_dir / "build",
        help="Prefix path for build artifacts",
    )
    parser.add_argument(
        "-c",
        "--context",
        type=Path,
        default=script_dir / "gen_images",
        help="Docker build-context directory",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        default=None,
        help="Docker file path",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Disable image generation, just build the docker image",
    )
    parser.add_argument(
        "-t",
        "--tag",
        default="nausicaea/debian-auto:latest",
        help="Tag for the locally built Docker image",
    )
    parser.add_argument(
        "--bootstrap-branch",
        default="main",
        help="Branch name to retrieve the Ansible playbook from for host provisioning",
    )
    parser.add_argument(
        "--debian-mirror",
        default="deb.debian.org",
        help="FQDN of the Debian download mirror",
    )
    parser.add_argument(
        "--debian-version",
        default="13.4.0",
        help="Debian version used to create the installer image",
    )
    parser.add_argument(
        "-I",
        "--install-nonfree-firmware",
        action="store_true",
        help="Also install nonfree firmware",
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Zurich",
        help="The primary timezone for the installer image",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value.strip()


def find_docker_cli() -> Path:
    for candidate in ("docker", "podman"):
        path = shutil.which(candidate)
        if path is not None:
            return Path(path)
    raise SystemExit(
        "No Docker-compatible CLI found (looked for 'docker' and 'podman')"
    )


def parse_host_data(src: str) -> list[dict[str, str]]:
    """
    Parse data from the input as rows of CSV of `HostData`.
    """
    host_data = list()
    csv_data = csv.DictReader(
        filter(lambda row: not row.startswith("#"), src.splitlines()),
        dialect="unix",
        fieldnames=["host_name", "arch", "boot_device"],
    )
    for row in csv_data:
        host_data.append(row)
    return host_data


def main() -> None:
    args = parse_args()

    verbose: bool = args.verbose
    debug: bool = args.debug
    build_only: bool = args.build_only
    prefix: Path = args.prefix.resolve()
    docker_context_dir: Path = args.context.resolve()
    docker_file_path: Path | None = args.file.resolve() if args.file is not None else None
    docker_image_tag: str = args.tag
    bootstrap_branch: str = args.bootstrap_branch
    debian_mirror: str = args.debian_mirror
    debian_version: str = args.debian_version
    install_nonfree_firmware: bool = args.install_nonfree_firmware
    timezone: str = args.timezone

    cache_dir = prefix / "cache"
    artifacts_dir = prefix / "artifacts"
    temp_dir = prefix / "temp"

    # Retrieve data from required environment variables
    git_author_email = require_env("GIT_AUTHOR_EMAIL")
    git_author_ssh_pub = require_env("GIT_AUTHOR_SSH_PUB")
    op_account_server = require_env("OP_ACCOUNT_SERVER")
    root_pw = op_read(require_env("OP_ROOT_PW_ID"), op_account_server)
    ansible_vault_pw = op_read(require_env("OP_VAULT_ID"), op_account_server)
    host_data = parse_host_data(
        op_read(require_env("OP_HOST_DATA_ID"), op_account_server)
    )

    for d in (cache_dir, artifacts_dir):
        d.mkdir(parents=True, exist_ok=True)
    if debug:
        temp_dir.mkdir(parents=True, exist_ok=True)

    docker_cli = find_docker_cli()
    if docker_cli.name == "docker":
        os.environ["DOCKER_CLI_HINTS"] = "false"
    docker_build_args = [docker_cli, "build", "-q", f"-t={docker_image_tag}", docker_context_dir]
    if docker_file_path is not None:
        docker_build_args.insert(len(docker_build_args) - 1, f"-f={docker_file_path}")
    run(
        docker_build_args,
        stdout=DEVNULL,
        check=True,
    )

    if build_only:
        sys.exit(0)

    payload = json.dumps(
        {
            "root_password": root_pw,
            "ansible_vault_password": ansible_vault_pw,
            "git_author_email": git_author_email,
            "git_author_ssh_pub": git_author_ssh_pub,
            "host_data": host_data,
            "options": {
                "bootstrap_branch": bootstrap_branch,
                "debian_mirror": debian_mirror,
                "debian_version": debian_version,
                "install_nonfree_firmware": install_nonfree_firmware,
                "timezone": timezone,
            },
        }
    )

    docker_run_args: list[str | Path] = [
        docker_cli,
        "run",
        "--rm",
        "-i",
        f"-v={cache_dir}:/cache",
        f"-v={artifacts_dir}:/artifacts",
    ]
    if debug:
        docker_run_args.append(f"-v={temp_dir}:/tmp")

    docker_run_args.append(docker_image_tag)
    if verbose:
        docker_run_args.append("-v")
    if debug:
        docker_run_args.append("-d")

    run(docker_run_args, input=payload, text=True, check=True)


if __name__ == "__main__":
    main()
