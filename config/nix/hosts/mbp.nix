{ config, pkgs, ... }:

{
  # Keep system-integrated packages native on CachyOS. These are portable
  # user-space tools useful specifically on the laptop.
  home.packages = with pkgs; [
    powertop
  ];

  # The existing audio module references desktop-only hardware and is not
  # enabled on the MacBook Pro.
  my.audio.enable = false;

  xdg.configFile."hypr/config/device-binds.lua" = {
    source = config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/workspace/.files/config/hyprland/hosts/mbp/binds.lua";
    force = true;
  };
}
