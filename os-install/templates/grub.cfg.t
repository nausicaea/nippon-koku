default=Install
timeout=4
menuentry 'Install' {
    set background_color=black
    linux    /install.${arch_short}/vmlinuz --- DEBIAN_FRONTEND=noninteractive BOOT_DEBUG=1 auto-install/enable=true
    initrd   /install.${arch_short}/initrd.gz
}
