{ config, lib, pkgs, ... }:

let
  cfg = config.my.audio;
in
{
  config = lib.mkIf cfg.enable {
    home.packages = with pkgs; [
      # Audio control & routing
      pavucontrol          # PulseAudio/PipeWire volume control GUI
      helvum               # PipeWire patchbay (GTK)
      qpwgraph             # PipeWire graph manager (Qt)

      # CLI utilities
      playerctl            # MPRIS media player control
      pulsemixer           # TUI mixer for PulseAudio/PipeWire
      ffmpeg               # Audio conversion, IR file processing

      # PipeWire tools (pw-cli, pw-dump, pw-top, etc.)
      pipewire
    ];

    # Session variables so EasyEffects can find LV2/LADSPA plugins from Nix
    home.sessionVariables = {
      LV2_PATH = "${config.home.profileDirectory}/lib/lv2";
      LADSPA_PATH = "${config.home.profileDirectory}/lib/ladspa";
    };
  };
}
