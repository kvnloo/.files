{
  description = "kvn's portable CachyOS Home Manager configuration";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, home-manager, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      mkHome = hostModule: home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        modules = [
          ./home.nix
          hostModule
          {
            # Home Manager is running on CachyOS rather than NixOS.
            targets.genericLinux.enable = true;
          }
        ];
      };
    in
    {
      homeConfigurations = {
        "kvn@mbp" = mkHome ./hosts/mbp.nix;
        "kvn@0" = mkHome ./hosts/0.nix;
        "kvn@desktop" = mkHome ./hosts/desktop.nix;

        # Convenient default for the current machine.
        "kvn" = mkHome ./hosts/mbp.nix;
      };
    };
}
