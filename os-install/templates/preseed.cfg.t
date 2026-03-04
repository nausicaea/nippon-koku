#_preseed_V1
#### Contents of the preconfiguration file (for trixie)
d-i auto-install/enable boolean true
d-i debconf/frontend select Noninteractive

### Localization
d-i debian-installer/language string en
d-i debian-installer/country string CH
d-i debian-installer/locale string en_GB.UTF-8
d-i localechooser/supported-locales multiselect en_US.UTF-8 en_GB.UTF-8, de_CH.UTF-8

# Keyboard selection
d-i keyboard-configuration/xkb-keymap select ch

### Network configuration
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string ${hostname}
d-i netcfg/get_domain string ${domain}
# Disable that annoying WEP key dialog.
d-i netcfg/wireless_wep string

# Try to autoload non-free firmware
d-i hw-detect/load_firmware boolean true

### Mirror settings
d-i mirror/country string manual
d-i mirror/http/hostname string ${mirror}
d-i mirror/http/directory string /debian
d-i mirror/http/proxy string

### Account setup
# Skip creation of a normal user account
d-i passwd/make-user boolean false
# Supply the root password as crypt(3) hash
d-i passwd/root-password-crypted password ${password}

### Clock and time zone setup
d-i clock-setup/utc boolean true
d-i time/zone string ${timezone}
d-i clock-setup/ntp boolean true

### Partitioning
# Thanks to @cavcrosby for the tip with the early command! https://github.com/cavcrosby/homelab-cm/blob/9339b9ed805f71064f81bc868d435503eb01e6f6/preseed.cfg.j2#L103C1-L103C126
d-i partman/early_command string debconf-set partman-auto/disk "$$(readlink -f "${boot_device}")"
d-i partman-auto/method string lvm
d-i partman-auto-lvm/guided_size string max
d-i partman-auto/choose_recipe select server

# Force UEFI booting
#d-i partman-efi/non_efi_system boolean true
#d-i partman-partitioning/choose_label select gpt
#d-i partman-partitioning/default_label string gpt

# Enforce UUID-based partition mounting
d-i partman/mount_style select uuid

# Remove any previous file-systems
d-i partman-md/device_remove_md boolean true
d-i partman-lvm/device_remove_lvm boolean true
d-i partman-lvm/confirm boolean true
d-i partman-lvm/confirm_nooverwrite boolean true
d-i partman-md/confirm boolean true

# Automatically commit the desired partitioning scheme
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

### Apt setup
# Disable additional installation media
d-i apt-setup/cdrom/set-first boolean false
# Disable CDROM entries in Apt sources.list in the installed system
d-i apt-setup/disable-cdrom-entries boolean true
d-i apt-setup/non-free-firmware boolean ${nonfree_firmware}

### Package selection
tasksel tasksel/first multiselect standard, ssh-server
d-i pkgsel/upgrade select safe-upgrade
d-i pkgsel/include string resolvconf git curl ansible-core openssh-server

# Participate in package use analytics
popularity-contest popularity-contest/participate boolean true

### Boot loader installation
d-i grub-installer/only_debian boolean true
d-i grub-installer/with_other_os boolean true
d-i grub-installer/bootdev string ${boot_device}

# Kernel options
d-i debian-installer/add-kernel-opts string audit=1

### Postinstall
#   Shell command or commands to run in the d-i environment as late as possible
# d-i preseed/late_command string <string>
d-i preseed/late_command string \
    in-target sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config; \
    mkdir -p /target/tmp; \
    cp /cdrom/post-install.sh /target/tmp/post-install.sh; \
    chmod 0500 /target/tmp/post-install.sh; \
    in-target /bin/sh /tmp/post-install.sh

# Avoid that last message about the install being complete.
d-i finish-install/reboot_in_progress note

# Power off the system instead of rebooting at the end of the installation
d-i debian-installer/exit/poweroff boolean true
