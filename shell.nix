let
    nixpkgs = fetchTarball { name = "nixpkgs-25.11"; url = "https://github.com/NixOS/nixpkgs/archive/nixos-25.11.tar.gz"; sha256 = "0rb04nkqgcglpjnm418qr59y0i6mjlvgn7j1hxhgl48dpavbs36b"; };
    pkgs = import nixpkgs { config = {}; overrides = []; };
    types-passlib = pkgs.python3Packages.buildPythonPackage rec {
        pname = "types-passlib";
        version = "1.7.7.20260211";
        format = "setuptools";

        src = pkgs.fetchPypi {
            pname = "types_passlib";
            inherit version;
            hash = "sha256-r3Ov/+HOlMlcf2ByvSYVcsKYRd50/f+jomX8djS8oFY=";
        };

        propagatedBuildInputs = [];

        # Module doesn't have tests
        doCheck = false;

        pythonImportsCheck = [ "passlib-stubs" ];

        meta = {
            description = "Typing stubs for passlib";
            homepage = "https://github.com/python/typeshed";
            license = pkgs.lib.licenses.asl20;
        };
    };
in
pkgs.mkShell {
    name = "Ansible Development Environment";
    packages = [
        pkgs.openssl
        pkgs.ansible
        pkgs.ansible-lint
        pkgs.kubeseal
        pkgs.python313Packages.passlib
        pkgs.python313Packages.jedi-language-server
        pkgs.python313Packages.types-pyopenssl
        pkgs.mypy
        types-passlib
    ];
}
