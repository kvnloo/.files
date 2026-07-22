{ config, ... }:

{
  # Enable after the desktop-only EasyEffects switcher and WirePlumber rule
  # have been migrated into this repository.
  my.audio.enable = false;

  xdg.configFile."hypr/config/device-binds.lua" = {
    source = config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/workspace/.files/config/hyprland/hosts/0/binds.lua";
    force = true;
  };
}
