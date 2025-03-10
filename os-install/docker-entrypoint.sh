#!/bin/sh

# The following code was adapted from information on 
#
# * [Debian preseeding](https://wiki.debian.org/DebianInstaller/Preseed),
# * [Debian ISO repacking](https://wiki.debian.org/RepackBootableISO),
# * [Phil Pagel's "Debian Headless" repository](https://github.com/philpagel/debian-headless),
# * and [Ricardo Branco's FAI builder for Docker](https://github.com/ricardobranco777/docker-fai).

set -e

# Required arguments (provided via getotps)
# ANSIBLE_VAULT_PASSWORD=""
# GIT_AUTHOR_EMAIL=""
# GIT_AUTHOR_SSH_PUB=""
# ROOT_PASSWORD_CRYPTED=""
# KUBE_APISERVER_URL=""

# Arguments with defaults
ARCH="${ARCH:-amd64}"
BOOT_DEVICE="${BOOT_DEVICE:-/dev/nvme0n1}"
BOOTSTRAP_REPO="${BOOTSTRAP_REPO:-https://github.com/nausicaea/nippon-koku}"
BOOTSTRAP_BRANCH="${BOOTSTRAP_BRANCH:-main}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-debian.ethz.ch}"
DEBIAN_VERSION="${DEBIAN_VERSION:-12.9.0}"
HOSTNAME="${HOSTNAME:-debian}"
DOMAIN="${DOMAIN}"
INSTALL_NONFREE_FIRMWARE="${INSTALL_NONFREE_FIRMWARE:-false}"
TIMEZONE="${TIMEZONE:-Europe/Zurich}"

# Hardcoded variables
ANSIBLE_HOME="/var/lib/ansible"
BOOTSTRAP_DEST="/var/lib/ansible/repo"

while getopts ':a:b:B:e:hH:k:nr:s:v:' 'opt'; do
    case $opt in
        a)
            ARCH="${OPTARG}"
            ;;
        b)
            BOOT_DEVICE="${OPTARG}"
            ;;
        B)
            BOOTSTRAP_BRANCH="${OPTARG}"
            ;;
        e)
            GIT_AUTHOR_EMAIL="${OPTARG}"
            ;;
        h)
            printf \
'nippon-koku 0.1.0 (docker-entrypoint.sh)
Eleanor Young <developer@nausicaea.net>

Generates a Debian ISO image with a preseed configuration. The preseed images
are saved to the ./artifacts/ directory, while the original unmodified images
are saved to the ./cache/ directory.

Project home page: https://github.com/nausicaea/nippon-koku

USAGE:
  docker-entrypoint.sh [OPTIONS]

OPTIONS:
  -a ARCH                       Specify the architecture of the Debian image
                                (available options are "amd64", "i386", and 
                                "arm64").
  -b BOOT_DEVICE                Specify the boot device (e.g. "/dev/sda").
  -B BOOTSTRAP_BRANCH           Specify the branch to check out during
                                postinstall.
  -e GIT_AUTHOR_EMAIL           Specify the email address of the author who 
                                signs commits.
  -h                            Print this usage message and exit.
  -H                            Specify the target hostname.
  -k                            Specify the Kube API server URL
  -n                            Install non-free firmware.
  -r ROOT_PASSWORD_CRYPTED      Specify the crypt(3) root password (e.g. 
                                "$6$SALT$HASH"). You can use "openssl passwd" 
                                to create such hashes.
  -s GIT_AUTHOR_SSH_PUB         Specify the public SSH key of the author
                                who signs commits.
  -v ANSIBLE_VAULT_PASSWORD     Specify the Ansible vault password in 
                                plaintext.
'
            exit 0
            ;;
        H)
            HOSTNAME="${OPTARG}"
            ;;
        k)
            KUBE_APISERVER_URL="${OPTARG}"
            ;;
        n)
            INSTALL_NONFREE_FIRMWARE=true
            ;;
        r)
            ROOT_PASSWORD_CRYPTED="${OPTARG}"
            ;;
        s)
            GIT_AUTHOR_SSH_PUB="${OPTARG}"
            ;;
        v)
            ANSIBLE_VAULT_PASSWORD="${OPTARG}"
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

if [ -z "$ANSIBLE_VAULT_PASSWORD" ]; then
    echo "Empty Ansible vault passwords are not allowed. You must provide the plaintext password either as command line parameter or as environment variable 'ANSIBLE_VAULT_PASSWORD'"
    exit 1
fi

if [ -z "$GIT_AUTHOR_EMAIL" -o -z "$GIT_AUTHOR_SSH_PUB" ]; then
    echo "You must provide git commit signing parameters either on the command line or as environment variables 'GIT_AUTHOR_EMAIL' and 'GIT_AUTHOR_SSH_PUB'"
    exit 1
fi

if [ -z "$KUBE_APISERVER_URL" ]; then
    echo "You must provide a URL for the Kube API server either on the command line or as environment variable 'KUBE_APISERVER_URL'"
    exit 1
fi

echo "Building Debian ($DEBIAN_VERSION/$ARCH) preseed image for $HOSTNAME"
echo "Configuring Ansible to check out branch $BOOTSTRAP_BRANCH"
echo "Configuring K3s to use the Kube API server $KUBE_APISERVER_URL"

SLASH_ESCAPE='s/\//\\\//g'
ANSIBLE_HOME=$(echo "$ANSIBLE_HOME" | sed "$SLASH_ESCAPE")
ANSIBLE_VAULT_PASSWORD=$(echo "$ANSIBLE_VAULT_PASSWORD" | sed "$SLASH_ESCAPE")
BOOT_DEVICE=$(echo "$BOOT_DEVICE" | sed "$SLASH_ESCAPE")
BOOTSTRAP_REPO=$(echo "$BOOTSTRAP_REPO" | sed "$SLASH_ESCAPE")
BOOTSTRAP_BRANCH=$(echo "$BOOTSTRAP_BRANCH" | sed "$SLASH_ESCAPE")
BOOTSTRAP_DEST=$(echo "$BOOTSTRAP_DEST" | sed "$SLASH_ESCAPE")
DOMAIN=$(echo "$DOMAIN" | sed "$SLASH_ESCAPE")
DEBIAN_MIRROR=$(echo "$DEBIAN_MIRROR" | sed "$SLASH_ESCAPE")
GIT_AUTHOR_EMAIL=$(echo "$GIT_AUTHOR_EMAIL" | sed "$SLASH_ESCAPE")
GIT_AUTHOR_SSH_PUB=$(echo "$GIT_AUTHOR_SSH_PUB" | sed "$SLASH_ESCAPE")
HOSTNAME=$(echo "$HOSTNAME" | sed "$SLASH_ESCAPE")
INSTALL_NONFREE_FIRMWARE=$(echo "$INSTALL_NONFREE_FIRMWARE" | sed "$SLASH_ESCAPE")
KUBE_APISERVER_URL=$(echo "$KUBE_APISERVER_URL" | sed "$SLASH_ESCAPE")
ROOT_PASSWORD_CRYPTED=$(echo "$ROOT_PASSWORD_CRYPTED" | sed "$SLASH_ESCAPE")
TIMEZONE=$(echo "$TIMEZONE" | sed "$SLASH_ESCAPE")

ARCH_SHORT=$(echo $ARCH | awk '{ if ($0 == "amd64") print "amd"; else if ($0 == "i386") print "386"; else if ($0 == "arm64") print "a64"; else print $0; }')
IMAGE_LABEL="Debian-$DEBIAN_VERSION-$ARCH-a"
IMAGE_FILE="$HOSTNAME-debian-$DEBIAN_VERSION-$ARCH-auto.iso"
ORIG_IMAGE_FILE="debian-$DEBIAN_VERSION-$ARCH-netinst.iso"

mkdir -p /cache /build /artifacts

# Download the Debian netinstall image
cd /cache
echo "Signature: 8a477f597d28d172789f06886806bc55" > /cache/CACHEDIR.TAG
if [ ! -f "$ORIG_IMAGE_FILE" ]; then
    curl -LO "https://cdimage.debian.org/debian-cd/$DEBIAN_VERSION/$ARCH/iso-cd/$ORIG_IMAGE_FILE"
fi

# Unpack the Debian netinstall image
cd /build
bsdtar -xf /cache/$ORIG_IMAGE_FILE

# Configure the Grub boot menu
sed -e "s/{{ arch_short }}/$ARCH_SHORT/g" \
    /src/grub.cfg.j2 > ./boot/grub/grub.cfg

# Configure the post-install script
sed -e "s/{{ repo }}/$BOOTSTRAP_REPO/g" \
    -e "s/{{ branch }}/$BOOTSTRAP_BRANCH/g" \
    -e "s/{{ dest }}/$BOOTSTRAP_DEST/g" \
    -e "s/{{ ansible_home }}/$ANSIBLE_HOME/g" \
    -e "s/{{ vault_password }}/$ANSIBLE_VAULT_PASSWORD/g" \
    -e "s/{{ email }}/$GIT_AUTHOR_EMAIL/g" \
    -e "s/{{ ssh_pub }}/$GIT_AUTHOR_SSH_PUB/g" \
    -e "s/{{ kube_apiserver_url }}/$KUBE_APISERVER_URL/g" \
    /src/post-install.sh.j2 > ./post-install.sh

# Fix the permissions on the image
chown -R root:root .
chmod -R u=rwX,go= .

# Configure the preseed file
PRESEED_FILE=/tmp/preseed.cfg
sed -e "s/{{ hostname }}/$HOSTNAME/g" \
    -e "s/{{ domain }}/$DOMAIN/g" \
    -e "s/{{ mirror }}/$DEBIAN_MIRROR/g" \
    -e "s/{{ password }}/$ROOT_PASSWORD_CRYPTED/g" \
    -e "s/{{ timezone }}/$TIMEZONE/g" \
    -e "s/{{ nonfree_firmware }}/$INSTALL_NONFREE_FIRMWARE/g" \
    -e "s/{{ boot_device }}/$BOOT_DEVICE/g" \
    /src/preseed.cfg.j2 > "$PRESEED_FILE"
chown root:root "$PRESEED_FILE"
chmod 0644 "$PRESEED_FILE"

# Add the preseed.cfg file to the kernel
INITRD_TMP=$(mktemp)
gunzip -c ./install.$ARCH_SHORT/initrd.gz > "$INITRD_TMP"
cd /tmp && echo "preseed.cfg" | cpio -H newc -o -A -F "$INITRD_TMP" 2> /dev/null && cd /build
gzip -c "$INITRD_TMP" > ./install.$ARCH_SHORT/initrd.gz

# Rebuild the checksums of the Debian netinstall image
find . -type f -exec md5sum {} \; > ./md5sum.txt

XORRISO_BASE_ARGS="-quiet -r -checksum_algorithm_iso sha256,sha512 -volid $IMAGE_LABEL -o /artifacts/$IMAGE_FILE -J -joliet-long"
if [ "$ARCH" = "arm64" ]; then
    # Extract the EFI partition
    EFI_IMAGE=$(mktemp)
    START_BLOCK=$(fdisk -l /cache/debian-12.9.0-arm64-netinst.iso | grep 'iso2' | awk '{ print $2 }')
    BLOCK_COUNT=$(fdisk -l /cache/debian-12.9.0-arm64-netinst.iso | grep 'iso2' | awk '{ print $4 }')
    dd if="/cache/$ORIG_IMAGE_FILE" bs=512 skip="$START_BLOCK" count="$BLOCK_COUNT" of="$EFI_IMAGE" 2> /dev/null
    # The file /build/boot/grub/efi.img might be a good alternative

    exec xorrisofs $XORRISO_BASE_ARGS \
        -e boot/grub/efi.img -no-emul-boot \
        -append_partition 2 0xef "$EFI_IMAGE" \
        -partition_cyl_align all \
        /build
elif [ "$ARCH" = "amd64" -o "$ARCH" = "i386" ]; then
    # Extract MBR template file to disk
    MBR_TEMPLATE=$(mktemp)
    dd if="/cache/$ORIG_IMAGE_FILE" bs=1 count=432 of="$MBR_TEMPLATE" 2> /dev/null
    # The file /usr/lib/ISOLINUX/isohdpfx.bin might be a good alternative
    
    exec xorrisofs $XORRISO_BASE_ARGS \
        -isohybrid-mbr "$MBR_TEMPLATE" -b isolinux/isolinux.bin -c isolinux/boot.cat \
        -boot-load-size 4 -boot-info-table -no-emul-boot -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
        -isohybrid-gpt-basdat -isohybrid-apm-hfsplus \
        /build
else
    echo "Unsupported architecture $ARCH"
    exit 1
fi
