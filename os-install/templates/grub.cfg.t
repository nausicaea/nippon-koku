default=Install
timeout=4
menuentry "Install" {
    echo "System installing..."
    linux /install.${arch_short}/vmlinuz
    initrd /install.${arch_short}/initrd.gz
}
menuentry "System restart" {
    echo "System rebooting..."
    reboot
}
if [ $${grub_platform} == "efi" ]; then
    menuentry "UEFI Firmware Settings" --id "uefi-firmware" {
        fwsetup
    }
fi
