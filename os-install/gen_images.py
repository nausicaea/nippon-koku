#!/usr/bin/python3

import argparse
from collections.abc import Iterable
import csv
from dataclasses import dataclass
import gzip
import io
import os
from pathlib import Path
import shutil
from string import Template
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
import urllib.request


@dataclass
class ImageSpec:
    host_name: str
    arch: str
    boot_device: str
    root_password_crypted: str
    ansible_vault_password: str
    git_author_email: str
    git_author_ssh_pub: str
    bootstrap_repo: str = "https://iris.radicle.xyz/zoBPQV6X2FH296n9gQxJr6suvSSi.git"
    bootstrap_branch: str = "main"
    bootstrap_dest: str = "/var/lib/ansible/repo"
    debian_mirror: str = "debian.ethz.ch"
    debian_version: str = "13.1.0"
    install_nonfree_firmware: bool = False
    timezone: str = "Europe/Zurich"
    domain: str = ""
    ansible_home: str = "/var/lib/ansible"


@dataclass
class HostData:
    host_name: str
    arch: str
    boot_device: str


def to_grub_arch(arch: str) -> str:
    match arch:
        case "amd64":
            return "amd"
        case "i386":
            return "386"
        case "arm64":
            return "a64"
        case _:
            return arch


# Download the Debian netinstall image
def download_image(debian_version: str, arch: str, verbose: bool) -> Path:
    with Path("/cache/CACHEDIR.TAG").open("wt") as f:
        f.write("Signature: 8a477f597d28d172789f06886806bc55\n")

    image_url = f"https://cdimage.debian.org/debian-cd/{debian_version}/{arch}/iso-cd/debian-{debian_version}-{arch}-netinst.iso"
    orig_image_file = Path(f"/cache/debian-{debian_version}-{arch}-netinst.iso")
    if not orig_image_file.exists():
        if verbose:
            print(f'Downloading "{image_url}"')
        with urllib.request.urlopen(image_url) as response:
            with orig_image_file.open("wb") as f:
                shutil.copyfileobj(response, f)

    return orig_image_file


# Unpack the Debian netinstall image
def unpack_image(src: Path, dest: Path, verbose: bool) -> None:
    subprocess.run(
        ["bsdtar", f'-{"v" if verbose else ""}xf', str(src)], cwd=dest, check=True
    )


def template_grub(spec: ImageSpec, prefix: Path) -> None:
    with Path("/src/grub.cfg.t").open("rt") as f:
        template = Template(f.read())

    substitutions = {
        "arch_short": to_grub_arch(spec.arch),
    }

    result = template.substitute(substitutions)

    with prefix.joinpath("boot/grub/grub.cfg").open("wt") as f:
        f.write(result)


def template_post_install(spec: ImageSpec, prefix: Path) -> None:
    with Path("/src/post-install.sh.t").open("rt") as f:
        template = Template(f.read())

    substitutions = {
        "repo": spec.bootstrap_repo,
        "branch": spec.bootstrap_branch,
        "dest": spec.bootstrap_dest,
        "ansible_home": spec.ansible_home,
        "vault_password": spec.ansible_vault_password,
        "email": spec.git_author_email,
        "ssh_pub": spec.git_author_ssh_pub,
    }

    result = template.substitute(substitutions)

    with prefix.joinpath("post-install.sh").open("wt") as f:
        f.write(result)


def template_preseed(spec: ImageSpec, tmp_prefix: Path) -> None:
    with Path("/src/preseed.cfg.t").open("rt") as f:
        template = Template(f.read())

    substitutions = {
        "hostname": spec.host_name,
        "domain": spec.domain,
        "mirror": spec.debian_mirror,
        "password": spec.root_password_crypted,
        "timezone": spec.timezone,
        "nonfree_firmware": spec.install_nonfree_firmware,
        "boot_device": spec.boot_device,
    }

    result = template.substitute(substitutions)

    with tmp_prefix.joinpath("preseed.cfg").open("wt") as f:
        f.write(result)


def bake_preseed(
    spec: ImageSpec, prefix: Path, tmp_prefix: Path, verbose: bool
) -> None:
    grub_arch = to_grub_arch(spec.arch)
    initrd_dir = prefix.joinpath(f"install.{grub_arch}")
    initrd_path = initrd_dir.joinpath("initrd.gz")
    with NamedTemporaryFile(mode="r+b") as initrd_decompressed:
        with gzip.open(initrd_path, mode="rb") as initrd:
            shutil.copyfileobj(initrd, initrd_decompressed)

        initrd_decompressed_path = Path(initrd_decompressed.name)
        cpio_args = [
            "cpio",
            "-H",
            "newc",
            "-o",
            "-A",
            "-F",
            str(initrd_decompressed_path),
        ]
        if verbose:
            cpio_args.append("-v")
        subprocess.run(
            cpio_args, cwd=tmp_prefix, input="preseed.cfg\n", text=True, check=True
        )

        with gzip.open(initrd_path, mode="wb") as initrd:
            initrd_decompressed.seek(0)
            shutil.copyfileobj(initrd_decompressed, initrd)


def update_md5sum(prefix: Path, verbose: bool) -> None:
    with prefix.joinpath("md5sum.txt").open("wb") as f:
        subprocess.run(
            ["find", ".", "-type", "f", "-exec", "md5sum", "{}", ";"],
            cwd=prefix,
            stdout=f,
            check=True,
        )


def parse_efi_partition_info(fdisk_output: str) -> (int, int):
    lines = fdisk_output.splitlines()
    candidates = (line for line in lines if ".iso2" in line and "EFI" in line)
    efi_row = next(candidates, None)
    if efi_row is None:
        raise ValueError("cannot find the EFI partition in the disk image")
    efi_values = efi_row.split()
    return int(efi_values[1]), int(efi_values[3])


def efi_partition_info(image: Path) -> (int, int):
    fdisk_info_proc = subprocess.run(
        ["fdisk", "-l", str(image)], capture_output=True, text=True, check=True
    )
    start_block, block_count = parse_efi_partition_info(fdisk_info_proc.stdout)
    return start_block, block_count


def build_xorriso_image(
    spec: ImageSpec, orig_image_path: Path, prefix: Path, dest: Path, verbose: bool
) -> None:
    base_args = [
        "-r",
        "-checksum_algorithm_iso",
        "sha256,sha512",
        "-volid",
        f"Debian-{spec.debian_version}-{spec.arch}-a",
        "-o",
        str(
            dest.joinpath(
                f"{spec.host_name}-debian-{spec.debian_version}-{spec.arch}-auto.iso"
            )
        ),
        "-J",
        "-joliet-long",
    ]
    if not verbose:
        base_args.insert(0, "-quiet")

    match spec.arch:
        case "arm64":
            with NamedTemporaryFile(mode="wb") as f:
                start_block, block_count = efi_partition_info(orig_image_path)

                # Extract the EFI partition
                subprocess.run(
                    [
                        "dd",
                        f"if={orig_image_path}",
                        "bs=512",
                        f"count={block_count}",
                        f"of={f.name}",
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        "xorrisofs",
                        *base_args,
                        "-e",
                        "boot/grub/efi.img",
                        "-no-emul-boot",
                        "-append_partition",
                        "2",
                        "0xef",
                        f.name,
                        "-partition_cyl_align",
                        "all",
                        str(prefix),
                    ],
                    check=True,
                )
        case "amd64" | "i386":
            with NamedTemporaryFile(mode="wb") as f:
                # Extract MBR template file to disk
                subprocess.run(
                    [
                        "dd",
                        f"if={orig_image_path}",
                        "bs=1",
                        "count=432",
                        f"of={f.name}",
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        "xorrisofs",
                        *base_args,
                        "-isohybrid-mbr",
                        f.name,
                        "-b",
                        "isolinux/isolinux.bin",
                        "-c",
                        "isolinux/boot.cat",
                        "-boot-load-size",
                        "4",
                        "-boot-info-table",
                        "-no-emul-boot",
                        "-eltorito-alt-boot",
                        "-e",
                        "boot/grub/efi.img",
                        "-no-emul-boot",
                        "-isohybrid-gpt-basdat",
                        "-isohybrid-apm-hfsplus",
                        str(prefix),
                    ],
                    check=True,
                )
        case _:
            raise ValueError(f'Unsupported architecture "{spec.arch}"')


def build_image(spec: ImageSpec, dest: Path, verbose: bool) -> None:
    grub_arch = to_grub_arch(spec.arch)
    orig_image_file = download_image(spec.debian_version, spec.arch, verbose)
    with TemporaryDirectory() as staging_tmpdir:
        staging_dir = Path(staging_tmpdir)
        unpack_image(orig_image_file, staging_dir, verbose)
        template_grub(spec, staging_dir)
        template_post_install(spec, staging_dir)
        with TemporaryDirectory() as preseed_tmpdir:
            preseed_dir = Path(preseed_tmpdir)
            template_preseed(spec, preseed_dir)
            bake_preseed(spec, staging_dir, preseed_dir, verbose)
        update_md5sum(staging_dir, verbose)
        build_xorriso_image(spec, orig_image_file, staging_dir, dest, verbose)


def parse_host_data(src: Iterable[str]) -> list[HostData]:
    host_data = list()
    csv_data = csv.DictReader(
        src, dialect="unix", fieldnames=["host_name", "arch", "boot_device"]
    )
    for row in csv_data:
        host_data.append(
            HostData(
                row["host_name"],
                row["arch"],
                row["boot_device"],
            )
        )

    return host_data


def require_env(name: str) -> str:
    env_value = os.environ.get(name)
    if env_value is None or len(env_value) == 0:
        raise ValueError(f'Missing required environment variable "{name}"')
    return env_value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generates one or more Debian ISO images with a preseed configuration. The preseed images are saved to the ./artifacts/ directory, while the original unmodified images are saved to the ./cache/ directory.",
        epilog="Project home page: https://app.radicle.xyz/nodes/iris.radicle.xyz/rad:zoBPQV6X2FH296n9gQxJr6suvSSi",
    )
    parser.add_argument(
        "-i",
        "--input-file",
        help='Optionally specify a file with host data triplets (each separated by newlines). The special value "-" indicates that you would like to read data from stdin.',
    )
    parser.add_argument(
        "host_data",
        nargs="*",
        help="For every image to generate, specify hostname, architecture, and boot device URL as CSV format.",
    )
    matches = parser.parse_args()

    # Retrieve data from required environment variables
    root_password_crypted = require_env("ROOT_PASSWORD_CRYPTED")
    ansible_vault_password = require_env("ANSIBLE_VAULT_PASSWORD")
    git_author_email = require_env("GIT_AUTHOR_EMAIL")
    git_author_ssh_pub = require_env("GIT_AUTHOR_SSH_PUB")

    output_dir = Path("/artifacts")
    verbose = True

    # Parse the host data
    host_data = list()
    if matches.input_file == "-":
        host_data.extend(parse_host_data(sys.stdin))
    elif matches.input_file is not None:
        input_file = Path(matches.input_file)
        if input_file.is_file():
            with input_file.open("rt") as f:
                host_data.extend(parse_host_data(f))

    host_data.extend(parse_host_data(matches.host_data))

    for hd in host_data:
        build_image(
            ImageSpec(
                hd.host_name,
                hd.arch,
                hd.boot_device,
                root_password_crypted,
                ansible_vault_password,
                git_author_email,
                git_author_ssh_pub,
            ),
            output_dir,
            verbose,
        )


if __name__ == "__main__":
    main()
