let
    nixpkgs = fetchTarball { name = "nixpkgs-25.11"; url = "https://github.com/NixOS/nixpkgs/archive/nixos-25.11.tar.gz"; sha256 = "0rb04nkqgcglpjnm418qr59y0i6mjlvgn7j1hxhgl48dpavbs36b"; };
    pkgs = import nixpkgs { config = {}; overrides = []; };
in
pkgs.mkShell {
    name = "Ansible Development Environment";
    packages = [
        pkgs.openssl
        pkgs.ansible
        pkgs.ansible-lint
        pkgs.kubeseal
        pkgs.python313Packages.passlib
    ];
}
