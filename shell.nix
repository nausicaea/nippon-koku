let
    nixpkgs = fetchTarball { name = "nixpkgs-25.11"; url = "https://github.com/NixOS/nixpkgs/archive/nixos-25.11.tar.gz"; sha256 = "0rb04nkqgcglpjnm418qr59y0i6mjlvgn7j1hxhgl48dpavbs36b"; };
    pkgs = import nixpkgs { config = {}; overrides = []; };
    types-passlib = pkgs.python313Packages.callPackage ./nix/types-passlib.nix {};
in
pkgs.mkShell {
    name = "Ansible and Rust Development Environment";
    packages = [
        pkgs.openssl
        pkgs.ansible
        pkgs.ansible-lint
        pkgs.kubeseal
        pkgs.pre-commit
        pkgs.cargo
        pkgs.rustc
        pkgs.rust-analyzer
        pkgs.rustfmt
        pkgs.clippy
        pkgs.cargo-nextest
    ];
    RUST_SRC_PATH = "${pkgs.rust.packages.stable.rustPlatform.rustLibSrc}";
}
