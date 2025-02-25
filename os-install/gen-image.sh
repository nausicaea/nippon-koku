#!/bin/sh

set -e

ARCH="${ARCH:-amd64}"
BOOT_DEVICE="${BOOT_DEVICE:-/dev/sda}"
HOSTNAME="${HOSTNAME:-debian}"
IMAGE_TAG="nausicaea/debian-auto:latest"
INSTALL_NONFREE_FIRMWARE="${INSTALL_NONFREE_FIRMWARE:-false}"
ROOT_PASSWORD_CRYPTED="$ROOT_PASSWORD_CRYPTED"

while getopts ':a:b:hH:nr:' 'opt'; do
    case ${opt} in
        a)
            ARCH="${OPTARG}"
            ;;
        b)
            BOOT_DEVICE="${OPTARG}"
            ;;
        h)
            printf \
'nippon-koku 0.1.0 (gen-image.sh)
Eleanor Young <developer@nausicaea.net>

Generates a Debian ISO image with a preseed configuration. The preseed images
are saved to the ./artifacts/ directory, while the original unmodified images
are saved to the ./cache/ directory. Requires Docker to work.

Project home page: https://github.com/nausicaea/nippon-koku

USAGE:
  gen-image.sh [OPTIONS]

OPTIONS:
  -a ARCH                       Specify the architecture of the Debian image
                                (available options are "amd64", "i386", and 
                                "arm64").
  -b BOOT_DEVICE                Specify the boot device (e.g. "/dev/sda").
  -h                            Print this usage message and exit.
  -H                            Specify the target hostname.
  -n                            Install non-free firmware.
  -r ROOT_PASSWORD_CRYPTED      Specify the crypt(3) root password (e.g. 
                                "$6$SALT$HASH"). You can use "openssl passwd" 
                                to create such hashes.
'
            ;;
        H)
            HOSTNAME="${OPTARG}"
            ;;
        n)
            INSTALL_NONFREE_FIRMWARE=true
            ;;
        r)
            ROOT_PASSWORD_CRYPTED="${OPTARG}"
            ;;
        :)
            echo "Option -${OPTARG} requires an argument."
            exit 1
            ;;
        ?)
            echo "Unknown option: -${OPTARG}."
            exit 1
            ;;
    esac
done

if [ -z "$ROOT_PASSWORD_CRYPTED" ]; then
    echo "Empty root passwords are not allowed. You must provide the hashed root password either as command line parameter or as environment variable 'ROOT_PASSWORD_CRYPTED'"
    exit 1
fi

docker build -t "$IMAGE_TAG" .
exec docker run --rm \
    -v ./cache:/cache -v ./artifacts:/artifacts \
    -e ARCH="$ARCH" -e INSTALL_NONFREE_FIRMWARE="$INSTALL_NONFREE_FIRMWARE" \
    -e BOOT_DEVICE="$BOOT_DEVICE" -e HOSTNAME="$HOSTNAME" \
    "$IMAGE_TAG" "$ROOT_PASSWORD_CRYPTED"
