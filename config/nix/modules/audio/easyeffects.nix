{ config, lib, pkgs, ... }:

let
  cfg = config.my.audio;
  dotfiles = cfg.dotfilesPath;

  # AutoEQ impulse response WAV files to symlink into ~/.config/easyeffects/irs/
  irFiles = [
    "Sennheiser HD800 minimum phase 44100 Hz.wav"
    "Sennheiser HD800 minimum phase 48000 Hz.wav"
    "Sennheiser HD800 minimum phase 96000 Hz.wav"
    "Sennheiser HD800 minimum phase 192000 Hz.wav"
    "Sennheiser HD800 minimum phase 384000 Hz.wav"
    "ThieAudio Monarch MKII minimum phase 44100Hz.wav"
    "ThieAudio Monarch MKII minimum phase 48000Hz.wav"
  ];

  # Build attrset of home.file entries for IR WAVs
  irFileEntries = builtins.listToAttrs (map (name: {
    name = ".config/easyeffects/irs/${name}";
    value = {
      source = config.lib.file.mkOutOfStoreSymlink "${dotfiles}/config/autoeq/${name}";
    };
  }) irFiles);
in
{
  config = lib.mkIf cfg.enable {
    # EasyEffects systemd user service (provided by Home Manager)
    services.easyeffects.enable = true;

    # Symlink AutoEQ impulse response files + IR switcher script
    home.file = irFileEntries // {
      "bin/easyeffects-ir-switcher" = {
        source = config.lib.file.mkOutOfStoreSymlink "${dotfiles}/config/easyeffects/easyeffects-ir-switcher.sh";
        executable = true;
      };
    };

    # IR switcher systemd user service
    systemd.user.services.easyeffects-ir-switcher = {
      Unit = {
        Description = "EasyEffects IR Auto-Switcher (PipeWire)";
        Documentation = "https://github.com/jaakkopasanen/AutoEq";
        After = [ "pipewire.service" "wireplumber.service" "easyeffects.service" ];
        Wants = [ "pipewire.service" ];
        Requires = [ "easyeffects.service" ];
      };

      Service = {
        Type = "simple";
        ExecStart = "${config.home.homeDirectory}/bin/easyeffects-ir-switcher monitor";
        Restart = "on-failure";
        RestartSec = 5;
      };

      Install = {
        WantedBy = [ "default.target" ];
      };
    };
  };
}
