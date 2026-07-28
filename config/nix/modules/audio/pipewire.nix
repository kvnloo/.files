{ config, lib, pkgs, ... }:

let
  cfg = config.my.audio;
  dotfiles = cfg.dotfilesPath;
in
{
  config = lib.mkIf cfg.enable {
    # PipeWire daemon config (192kHz default, multi-rate switching)
    home.file.".config/pipewire/pipewire.conf".source =
      config.lib.file.mkOutOfStoreSymlink "${dotfiles}/config/pipewire/pipewire.conf";

    # PipeWire native filter-chain DSP (convolver + loudness comp + limiter)
    home.file.".config/pipewire/pipewire.conf.d/10-headphone-dsp.conf".source =
      config.lib.file.mkOutOfStoreSymlink "${dotfiles}/config/pipewire/pipewire.conf.d/10-headphone-dsp.conf";

    # Route browser audio to clean DSP (no BRIR) via pipewire-pulse rules
    home.file.".config/pipewire/pipewire-pulse.conf.d/20-browser-bypass-brir.conf".source =
      config.lib.file.mkOutOfStoreSymlink "${dotfiles}/config/pipewire/pipewire-pulse.conf.d/20-browser-bypass-brir.conf";

    # WirePlumber rules for Topping DX5 bit-perfect mode
    home.file.".config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua".source =
      config.lib.file.mkOutOfStoreSymlink "${dotfiles}/config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua";
  };
}
