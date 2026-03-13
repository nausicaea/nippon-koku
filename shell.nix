let
    nixpkgs = fetchTarball { name = "nixpkgs-25.11"; url = "https://github.com/NixOS/nixpkgs/archive/nixos-25.11.tar.gz"; sha256 = "0ax8m8l20zd6hrbylrvlgs1inzd4nld8x4kh7r8k11inz7nfdjmw"; };
    pkgs = import nixpkgs { config = {}; overrides = []; };
in
pkgs.mkShell {
    name = "Ansible and Rust Development Environment";
    packages = [
        pkgs.openssl
        pkgs.ansible
        pkgs.ansible-lint
        pkgs.python313Packages.jedi-language-server
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
