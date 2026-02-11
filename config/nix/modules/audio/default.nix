{ config, lib, pkgs, ... }:

let
  cfg = config.my.audio;
in
{
  imports = [
    ./pipewire.nix
    ./easyeffects.nix
    ./packages.nix
  ];

  options.my.audio = {
    enable = lib.mkEnableOption "audiophile audio stack (PipeWire + EasyEffects + AutoEQ)";

    dotfilesPath = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/workspace/.files";
      description = "Absolute path to the dotfiles repo for mkOutOfStoreSymlink.";
    };
  };
}
