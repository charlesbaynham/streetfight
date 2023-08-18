{
  description = "Simple npm-only environment
  ";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
      pkgs = nixpkgs.legacyPackages.${system};
      reqs = [
        pkgs.nodejs
      ];
      
      in {
        devShell = 
          pkgs.mkShell {
            name="devShell";
            buildInputs=reqs;
          };
        
        # apps = rec {
        #   hello = flake-utils.lib.mkApp { drv = self.packages.${system}.hello; };
        #   default = hello;
        # };
      }
    );
}
