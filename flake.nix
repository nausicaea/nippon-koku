{
  description = "Ansible development environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/dc205f7b4fdb04c8b7877b43edb7b73be7730081";
    flake-utils = {
      url = "github:numtide/flake-utils";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            openssl
            ansible
            ansible-lint
            kubeseal
          ];
        };
      }
    );
}
