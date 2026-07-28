{ config, ... }:

let
  dotfiles = "${config.home.homeDirectory}/workspace/.files";
  link = path: config.lib.file.mkOutOfStoreSymlink "${dotfiles}/${path}";
in
{
  # Out-of-store links keep the Git checkout as the editable source of truth.
  xdg.configFile."noctalia/config.toml" = {
    source = link "config/noctalia/config.toml";
    force = true;
  };

  xdg.configFile."hypr/config/binds.lua" = {
    source = link "config/hyprland/config/binds.lua";
    force = true;
  };

  xdg.configFile."nix/nix.conf" = {
    source = link "config/nix/nix.conf";
    force = true;
  };
}
