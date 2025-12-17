{
  description = "Ansible development environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/363465f8f9d3b335f9ddb86a895023974d678a9d";
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
