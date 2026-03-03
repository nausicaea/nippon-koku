default=Install
timeout=4
menuentry 'Install' {
    set background_color=black
    linux    /install.${arch_short}/vmlinuz auto=true priority=critical DEBIAN_FRONTEND=noninteractive BOOT_DEBUG=1 console=ttyAMA0 ---
    initrd   /install.${arch_short}/initrd.gz
}
