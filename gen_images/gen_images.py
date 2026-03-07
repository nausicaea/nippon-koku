#!/usr/bin/python3

import argparse
from collections.abc import Iterable
import csv
import json
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
from passlib.hash import sha512_crypt


def which(name: str) -> Path:
    """
    Perform a path lookup for a particular command or program.
    Raise `ValueError` if the command or program was not found.
    """

    p = shutil.which(name)
    if p is None:
        raise SystemExit(f"Unknown command: {name}")
    return Path(p)


@dataclass(frozen=True)
class ImageSpec:
    """
    Define all parameters for a particular Debian installer image.
    """

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


def to_grub_arch(arch: str) -> str:
    """
    Convert the machine architecture name to a format that Grub understands.
    """
    return {"amd64": "amd", "i386": "386", "arm64": "a64"}.get(arch, arch)


def download_image(
    debian_version: str, arch: str, cache_dir: Path, verbose: bool
) -> Path:
    """
    Download the Debian netinstall ISO file to the local cache.
    """
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


def unpack_image(src: Path, dest: Path) -> Path:
    """
    Unpack the cached ISO image to a directory.
    """
    run([which("bsdtar"), "-xf", src], cwd=dest, check=True)
    return dest


def _render(src: Path, params: dict[str, str]) -> str:
    return Template(src.read_text()).substitute(params)


def template_grub(spec: ImageSpec, prefix: Path) -> Path:
    """
    Substitute parameters in the grub.cfg template for a particular installer image.
    """
    output = prefix / "boot/grub/grub.cfg"
    output.write_text(
        _render(
            Path("/src/grub.cfg.t"),
            {"arch_short": to_grub_arch(spec.arch)},
        )
    )
    return output


def template_post_install(spec: ImageSpec, prefix: Path) -> Path:
    """
    Substitute parameters in the post-install.sh script template for a particular installer image.
    """
    output = prefix / "post-install.sh"
    output.write_text(
        _render(
            Path("/src/post-install.sh.t"),
            {
                "repo": spec.bootstrap_repo,
                "branch": spec.bootstrap_branch,
                "dest": spec.bootstrap_dest,
                "ansible_home": spec.ansible_home,
                "vault_password": spec.ansible_vault_password,
                "email": spec.git_author_email,
                "ssh_pub": spec.git_author_ssh_pub,
            },
        )
    )
    return output


def template_preseed(spec: ImageSpec, prefix: Path) -> Path:
    """
    Substitute parameters in the preseed.cfg template for a particular installer image.
    """
    output = prefix / "preseed.cfg"
    output.write_text(
        _render(
            Path("/src/preseed.cfg.t"),
            {
                "hostname": spec.host_name,
                "domain": spec.domain,
                "mirror": spec.debian_mirror,
                "password": spec.root_password_crypted,
                "timezone": spec.timezone,
                "nonfree_firmware": str(spec.install_nonfree_firmware),
                "boot_device": spec.boot_device,
            },
        )
    )
    return output


def bake_preseed(
    spec: ImageSpec,
    prefix: Path,
    preseed_staging_dir: Path,
    tmp_dir: Path | None = None,
) -> Path:
    """
    Append the preseed.cfg to the initrd.gz archive in the installer image. This is an in-place operation that modifies the initrd.gz archive.
    """
    initrd_path = prefix / f"install.{to_grub_arch(spec.arch)}" / "initrd.gz"
    with NamedTemporaryFile(
        mode="r+b", prefix="initrd", dir=tmp_dir, delete=(tmp_dir is None)
    ) as initrd_decompressed:
        initrd_decompressed_path = Path(initrd_decompressed.name)

        with gzip.open(initrd_path, mode="rb") as initrd:
            shutil.copyfileobj(initrd, initrd_decompressed)

        initrd_decompressed.seek(0)

        run(
            [
                which("cpio"),
                "-H",
                "newc",
                "-o",
                "-A",
                "--reproducible",
                "-F",
                initrd_decompressed_path,
            ],
            cwd=preseed_staging_dir,
            input="preseed.cfg",
            text=True,
            check=True,
        )

        with gzip.open(initrd_path, mode="wb") as initrd:
            shutil.copyfileobj(initrd_decompressed, initrd)

    return initrd_path


def update_md5sum(prefix: Path) -> Path:
    """
    Recalculate all files' MD5 hashes inside the installer image.
    """
    output = prefix / "md5sum.txt"
    with output.open("wb") as f:
        run(
            [which("find"), ".", "-type", "f", "-exec", "md5sum", "{}", ";"],
            cwd=prefix,
            stdout=f,
            check=True,
        )

    return output


def _efi_partition(image: Path) -> tuple[int, int]:
    """
    Retrieve the EFI partition boundary as a tuple of `(start_block, block_count)`.
    In the standard output of `fdisk -l <ISO-image>`, try to find the EFI partition. Return a tuple of `(start_block, block_count)`. Raise `ValueError` if the EFI partition cannot be found.
    """
    fdisk_list = run(
        [which("fdisk"), "-l", image], capture_output=True, text=True, check=True
    )
    for line in fdisk_list.stdout.splitlines():
        if ".iso2" in line and "EFI" in line:
            parts = line.split()
            print(repr(parts))
            return int(parts[1]), int(parts[3])
    raise ValueError("Cannot find the EFI partition in the disk image")


def _dd(
    src: Path, dest: Path, start_block: int, block_size: int, block_count: int
) -> Path:
    """
    Copy the contents of a partition, delimited by start_block and block_count, to the destination.
    """
    run(
        [
            which("dd"),
            f"if={src}",
            f"skip={start_block}",
            f"bs={block_size}",
            f"count={block_count}",
            f"of={dest}",
        ],
        check=True,
    )

    return dest


def _xorriso(dest: Path, volume_id: str, extra_args: list[str], verbose: bool) -> Path:
    """
    Create an ISO image from arguments using xorriso.
    """
    base_args: list[str] = [
        "-r",
        "-checksum_algorithm_iso",
        "sha256,sha512",
        "-volid",
        volume_id,
        "-o",
        str(dest),
        "-J",
        "-joliet-long",
    ]
    if not verbose:
        base_args.insert(0, "-quiet")
    run(
        [which("xorrisofs"), *base_args, *extra_args],
        check=True,
    )
    return dest


def build_xorriso_image(
    spec: ImageSpec,
    orig_image_path: Path,
    prefix: Path,
    dest: Path,
    verbose: bool,
    tmp_dir: Path | None,
) -> None:
    """
    Rebuild the Debian ISO installer image from an image spec and staging directory.
    """
    volume_id = f"Debian_{spec.debian_version}_{spec.arch}_a".replace(".", "_")
    dest_file = dest.joinpath(
        f"{spec.host_name}-debian-{spec.debian_version}-{spec.arch}-auto.iso"
    )
    with NamedTemporaryFile(
        mode="wb", prefix="efi", dir=tmp_dir, delete=(tmp_dir is None)
    ) as efi_or_mbr_tempfile:
        efi_or_mbr = Path(efi_or_mbr_tempfile.name)
        match spec.arch:
            case "arm64":
                start_block, block_count = _efi_partition(orig_image_path)

                # Extract the EFI partition
                _dd(orig_image_path, efi_or_mbr, start_block, 512, block_count)
                _xorriso(
                    dest_file,
                    volume_id,
                    [
                        "-e",
                        "boot/grub/efi.img",
                        "-no-emul-boot",
                        "-append_partition",
                        "2",
                        "0xef",
                        str(efi_or_mbr),
                        "-partition_cyl_align",
                        "all",
                        str(prefix),
                    ],
                    verbose,
                )
            case "amd64" | "i386":
                # Extract MBR template file to disk
                _dd(orig_image_path, efi_or_mbr, 0, 1, 432)
                _xorriso(
                    dest_file,
                    volume_id,
                    [
                        "-isohybrid-mbr",
                        str(efi_or_mbr),
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
                    verbose,
                )
            case _:
                raise ValueError(f"Unsupported architecture {spec.arch}")


def build_image(
    spec: ImageSpec,
    dest: Path,
    cache_dir: Path,
    verbose: bool,
    tmp_dir: Path | None,
) -> None:
    """
    Download, extract, modify, and rebuild a Debian installer image.
    """
    orig_image_file = download_image(spec.debian_version, spec.arch, cache_dir, verbose)
    with TemporaryDirectory(
        prefix="staging", dir=tmp_dir, delete=(tmp_dir is None)
    ) as staging_tmpdir:
        staging_dir = Path(staging_tmpdir)
        unpack_image(orig_image_file, staging_dir)
        template_grub(spec, staging_dir)
        template_post_install(spec, staging_dir)
        with TemporaryDirectory(
            prefix="preseed", dir=tmp_dir, delete=(tmp_dir is None)
        ) as preseed_tmpdir:
            preseed_dir = Path(preseed_tmpdir)
            template_preseed(spec, preseed_dir)
            bake_preseed(spec, staging_dir, preseed_dir, tmp_dir)
        update_md5sum(staging_dir)
        build_xorriso_image(spec, orig_image_file, staging_dir, dest, verbose, tmp_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generates one or more Debian ISO images with a preseed configuration. The preseed images are saved to the ./artifacts/ directory, while the original unmodified images are saved to the ./cache/ directory.",
        epilog="Project home page: https://app.radicle.xyz/nodes/iris.radicle.xyz/rad:zoBPQV6X2FH296n9gQxJr6suvSSi",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debugging"
    )
    return parser.parse_args()


def parse_stdin() -> list[ImageSpec]:
    payload = json.load(sys.stdin)
    root_password_crypted = sha512_crypt.hash(payload["root_password"])
    return [
        ImageSpec(
            hd["host_name"],
            hd["arch"],
            hd["boot_device"],
            root_password_crypted,
            payload["ansible_vault_password"],
            payload["git_author_email"],
            payload["git_author_ssh_pub"],
        )
        for hd in payload["host_data"]
    ]


def main() -> None:
    args = parse_args()

    verbose: bool = args.verbose
    debug: bool = args.debug
    output_dir = Path("/artifacts")
    cache_dir = Path("/cache")
    tmp_dir = Path("/tmp") if debug else None

    for spec in parse_stdin():
        build_image(
            spec,
            output_dir,
            cache_dir,
            verbose,
            tmp_dir,
        )


if __name__ == "__main__":
    main()
