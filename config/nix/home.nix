{ config, pkgs, ... }:

{
  imports = [
    ./modules/dotfiles.nix
    ./modules/audio
    ./modules/k3s-client.nix
  ];

  home = {
    username = "kvn";
    homeDirectory = "/home/kvn";
    stateVersion = "24.11";
  };

  # Hardware, the kernel, Hyprland, portals, and drivers remain managed by
  # CachyOS/pacman. Home Manager owns portable user packages and dotfiles.
  home.packages = with pkgs; [
    bat
    eza
    fd
    fzf
    jq
    ripgrep
  ];

  programs.home-manager.enable = true;
}
