{ config, pkgs, ... }:

{
  imports = [
    ./modules/audio
  ];

  # Enable the audio stack
  my.audio.enable = true;

  home = {
    username = "kvn";
    homeDirectory = "/home/kvn";
    stateVersion = "24.11";
  };

  programs.home-manager.enable = true;
}
