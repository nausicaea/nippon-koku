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
from subprocess import run
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any
import urllib.request


def which_optional(name: str) -> Path | None:
    p = shutil.which(name)
    return Path(p) if p is not None else None


def which(name: str) -> Path:
    p = shutil.which(name)
    if p is None:
        raise ValueError(f"Unknown command: {name}")
    return Path(p)


@dataclass(frozen=True)
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
    debian_version: str = "13.3.0"
    install_nonfree_firmware: bool = False
    timezone: str = "Europe/Zurich"
    domain: str = ""
    ansible_home: str = "/var/lib/ansible"


@dataclass(frozen=True)
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
def download_image(debian_version: str, arch: str, cache_dir: Path, verbose: bool) -> Path:
    with cache_dir.joinpath("CACHEDIR.TAG").open("wt") as f:
        f.write("Signature: 8a477f597d28d172789f06886806bc55\n")

    image_url = f"https://cdimage.debian.org/debian-cd/{debian_version}/{arch}/iso-cd/debian-{debian_version}-{arch}-netinst.iso"
    orig_image_file = cache_dir.joinpath(f"debian-{debian_version}-{arch}-netinst.iso")
    if not orig_image_file.exists():
        if verbose:
            print(f'Downloading "{image_url}"', file=sys.stderr)
        with urllib.request.urlopen(image_url) as response:
            with orig_image_file.open("wb") as f:
                shutil.copyfileobj(response, f)

    return orig_image_file


# Unpack the Debian netinstall image
def unpack_image(src: Path, dest: Path, verbose: bool) -> None:
    bsdtar_path = which("bsdtar")
    run([bsdtar_path, "-xf", src], cwd=dest, check=True)


def template_grub(spec: ImageSpec, prefix: Path) -> None:
    with Path("/src/grub.cfg.t").open("rt") as f:
        template = Template(f.read())

    substitutions = {"arch_short": to_grub_arch(spec.arch)}

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


def template_preseed(spec: ImageSpec, preseed_staging_dir: Path) -> None:
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

    with preseed_staging_dir.joinpath("preseed.cfg").open("wt") as f:
        f.write(result)


def bake_preseed(
    spec: ImageSpec, prefix: Path, preseed_staging_dir: Path, verbose: bool, tmp_dir: Path | None = None
) -> None:
    cpio_path = which("cpio")
    grub_arch = to_grub_arch(spec.arch)
    initrd_dir = prefix.joinpath(f"install.{grub_arch}")
    initrd_path = initrd_dir.joinpath("initrd.gz")
    with NamedTemporaryFile(mode="r+b", prefix="initrd", dir=tmp_dir, delete=(tmp_dir is None)) as initrd_decompressed:
        with gzip.open(initrd_path, mode="rb") as initrd:
            shutil.copyfileobj(initrd, initrd_decompressed)
            initrd_decompressed.seek(0)

        initrd_decompressed_path = Path(initrd_decompressed.name)
        cpio_args = [cpio_path, "-v", "-H", "newc", "-o", "-A", "--reproducible", "-F", initrd_decompressed_path]
        run(cpio_args, cwd=preseed_staging_dir, input="preseed.cfg", text=True, check=True)

        with gzip.open(initrd_path, mode="wb") as initrd:
            shutil.copyfileobj(initrd_decompressed, initrd)


def update_md5sum(prefix: Path, verbose: bool) -> None:
    find_path = which("find")
    with prefix.joinpath("md5sum.txt").open("wb") as f:
        run(
            [find_path, ".", "-type", "f", "-exec", "md5sum", "{}", ";"],
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
    fdisk_path = which("fdisk")
    fdisk_info_proc = run(
        [fdisk_path, "-l", image], capture_output=True, text=True, check=True
    )
    start_block, block_count = parse_efi_partition_info(fdisk_info_proc.stdout)
    return start_block, block_count


def dd(
    src: Path, dest: Path, start_block: int, block_size: int, block_count: int
) -> None:
    dd_path = which("dd")
    run(
        [
            dd_path,
            f"if={src}",
            f"skip={start_block}",
            f"bs={block_size}",
            f"count={block_count}",
            f"of={dest}",
        ],
        check=True,
    )


def xorriso(dest: Path, volume_id: str, extra_args: list[Any], verbose: bool) -> None:
    xorrisofs_path = which("xorrisofs")
    base_args = [
        "-r",
        "-checksum_algorithm_iso",
        "sha256,sha512",
        "-volid",
        volume_id,
        "-o",
        dest,
        "-J",
        "-joliet-long",
    ]
    if not verbose:
        base_args.insert(0, "-quiet")
    run(
        [xorrisofs_path, *base_args, *extra_args],
        check=True,
    )


def build_xorriso_image(
    spec: ImageSpec, orig_image_path: Path, prefix: Path, dest: Path, verbose: bool, tmp_dir: Path | None = None
) -> None:
    volume_id = f"Debian_{spec.debian_version}_{spec.arch}_a".replace(".", "_")
    dest_file = dest.joinpath(
        f"{spec.host_name}-debian-{spec.debian_version}-{spec.arch}-auto.iso"
    )
    with NamedTemporaryFile(mode="wb", prefix="efi", dir=tmp_dir, delete=(tmp_dir is None)) as efi_or_mbr_tempfile:
        efi_or_mbr = Path(efi_or_mbr_tempfile.name)
        match spec.arch:
            case "arm64":
                start_block, block_count = efi_partition_info(orig_image_path)

                # Extract the EFI partition
                dd(orig_image_path, efi_or_mbr, start_block, 512, block_count)
                xorriso(
                    dest_file,
                    volume_id,
                    [
                        "-e",
                        "boot/grub/efi.img",
                        "-no-emul-boot",
                        "-append_partition",
                        "2",
                        "0xef",
                        efi_or_mbr,
                        "-partition_cyl_align",
                        "all",
                        prefix,
                    ],
                    verbose,
                )
            case "amd64" | "i386":
                # Extract MBR template file to disk
                dd(orig_image_path, efi_or_mbr, 0, 1, 432)
                xorriso(
                    dest_file,
                    volume_id,
                    [
                        "-isohybrid-mbr",
                        efi_or_mbr,
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
                        prefix,
                    ],
                    verbose,
                )
            case _:
                raise ValueError(f'Unsupported architecture "{spec.arch}"')


def build_image(spec: ImageSpec, dest: Path, cache_dir: Path, verbose: bool, tmp_dir: Path | None = None) -> None:
    grub_arch = to_grub_arch(spec.arch)
    orig_image_file = download_image(spec.debian_version, spec.arch, cache_dir, verbose)
    with TemporaryDirectory(prefix="staging", dir=tmp_dir, delete=(tmp_dir is None)) as staging_tmpdir:
        staging_dir = Path(staging_tmpdir)
        unpack_image(orig_image_file, staging_dir, verbose)
        template_grub(spec, staging_dir)
        template_post_install(spec, staging_dir)
        with TemporaryDirectory(prefix="preseed", dir=tmp_dir, delete=(tmp_dir is None)) as preseed_tmpdir:
            preseed_dir = Path(preseed_tmpdir)
            template_preseed(spec, preseed_dir)
            bake_preseed(spec, staging_dir, preseed_dir, verbose, tmp_dir)
        update_md5sum(staging_dir, verbose)
        build_xorriso_image(spec, orig_image_file, staging_dir, dest, verbose, tmp_dir)


def parse_host_data(src: Iterable[str]) -> list[HostData]:
    host_data = list()
    csv_data = csv.DictReader(
        src, dialect="unix", fieldnames=["host_name", "arch", "boot_device"]
    )
    for row in csv_data:
        host_data.append(HostData(row["host_name"], row["arch"], row["boot_device"]))
    return host_data


def require_env(name: str) -> str:
    env_value = os.environ.get(name)
    if env_value is None or len(env_value) == 0:
        raise ValueError(f'Missing required environment variable "{name}"')
    return env_value


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Generates one or more Debian ISO images with a preseed configuration. The preseed images are saved to the ./artifacts/ directory, while the original unmodified images are saved to the ./cache/ directory.",
        epilog="Project home page: https://app.radicle.xyz/nodes/iris.radicle.xyz/rad:zoBPQV6X2FH296n9gQxJr6suvSSi",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
    root_password_crypted = require_env("ROOT_PASSWORD_CRYPTED")
    ansible_vault_password = require_env("ANSIBLE_VAULT_PASSWORD")
    git_author_email = require_env("GIT_AUTHOR_EMAIL")
    git_author_ssh_pub = require_env("GIT_AUTHOR_SSH_PUB")

    output_dir = Path("/artifacts")
    cache_dir = Path("/cache")
    verbose: bool = matches.verbose
    debug: bool = matches.debug

    tmp_dir: Path | None = None
    if debug:
        tmp_dir = Path("/tmp")

    # Parse the host data
    for hd in parse_host_data(sys.stdin):
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
            cache_dir,
            verbose,
            tmp_dir,
        )


if __name__ == "__main__":
    _main()
