# Nix Home Manager Best Practices Research (2025-2026)

**Research Date**: 2026-02-10
**Focus**: Production-ready patterns for modularized Home Manager with audio stack (PipeWire/WirePlumber/EasyEffects)

---

## Executive Summary

Home Manager has evolved toward **flakes as the standard approach** in 2025-2026, with modularization best practices centered around **hierarchical folder structures**, **custom modules with mkOption/mkIf**, and **declarative systemd service management**. The standalone installation method works on any Linux distro, making it viable for non-NixOS systems.

**Key Findings**:
- ✅ **Flakes are now the recommended standard** (despite experimental status)
- ✅ **Modular folder structures** with `imports = []` enable scalable configs
- ✅ **Standalone Home Manager** supports Ubuntu/Fedora/Arch via `targets.genericLinux.enable`
- ✅ **Audio stack modules** for PipeWire/EasyEffects exist in Home Manager
- ⚠️ **WirePlumber** requires system-level config (NixOS services.pipewire.wireplumber)
- 📝 **Custom modules** follow options → config → mkIf pattern

---

## 1. Modularized Folder Structure

### Recommended Organization Pattern

Based on [NixOS & Flakes Book - Modularize the Configuration](https://nixos-and-flakes.thiscute.world/nixos-with-flakes/modularize-the-configuration), the community-recommended structure:

```
~/.config/home-manager/
├── flake.nix              # Entry point with inputs/outputs
├── flake.lock             # Locked dependency versions
├── home.nix               # Main user configuration
├── modules/               # Custom reusable modules
│   ├── audio/
│   │   ├── default.nix    # Audio module aggregator
│   │   ├── pipewire.nix   # PipeWire configuration
│   │   └── easyeffects.nix # EasyEffects presets
│   ├── shell/
│   │   ├── default.nix
│   │   ├── zsh.nix
│   │   └── starship.nix
│   └── programs/
│       ├── default.nix
│       ├── git.nix
│       └── neovim.nix
└── hosts/                 # Machine-specific configs (optional)
    └── laptop/
        └── default.nix
```

### Import System Mechanics

**Key Rule** ([Module System Deep Dive](https://nixos-and-flakes.thiscute.world/other-usage-of-flakes/module-system)):
- `import ./folder` → Returns `./folder/default.nix` execution result
- `imports = [ ... ]` → Merges all listed modules intelligently (not simple overwrites)

**Example `modules/audio/default.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  imports = [
    ./pipewire.nix
    ./easyeffects.nix
  ];

  # Shared audio configuration
  home.packages = with pkgs; [
    pavucontrol
    helvum  # PipeWire patchbay GUI
  ];
}
```

**Example `home.nix` with modular imports**:
```nix
{ config, pkgs, ... }:

{
  imports = [
    ./modules/audio
    ./modules/shell
    ./modules/programs
  ];

  home.username = "kvn";
  home.homeDirectory = "/home/kvn";
  home.stateVersion = "25.05";

  # Enable Home Manager self-management
  programs.home-manager.enable = true;
}
```

---

## 2. Standalone Home Manager on Non-NixOS Linux

### Installation Prerequisites

**System Requirements** ([Home Manager Manual](https://nix-community.github.io/home-manager/)):
- Nix 2.4+ with flakes enabled
- Experimental features: `nix-command` and `flakes`

**Enable flakes** in `~/.config/nix/nix.conf`:
```
experimental-features = nix-command flakes
```

### Standalone Installation (Flake-based)

**Initialize Home Manager** ([Getting Started with Home Manager](https://nixos-and-flakes.thiscute.world/nixos-with-flakes/start-using-home-manager)):
```bash
# Create initial flake configuration
nix run home-manager/release-25.05 -- init --switch

# Or for development/latest features
nix run home-manager/master -- init --switch
```

This generates:
- `~/.config/home-manager/flake.nix`
- `~/.config/home-manager/home.nix`

### Non-NixOS Linux Compatibility

**Critical Setting** ([Home Manager - NixOS Wiki](https://nixos.wiki/wiki/Home_Manager)):
```nix
# In home.nix for Ubuntu/Fedora/Arch/etc.
targets.genericLinux.enable = true;
```

**What this does**:
- Fixes XDG_DATA_DIRS for Nix-installed software
- Sets locale variables correctly
- Patches desktop files for non-NixOS environments
- Ensures GUI apps appear in system launchers

### Activation Workflow

```bash
# Apply configuration changes
home-manager switch --flake ~/.config/home-manager

# Or using shorthand (if in the directory)
home-manager switch --flake .

# Build without activating (for testing)
home-manager build --flake .
```

---

## 3. Flakes vs Channels (2025 Recommendation)

### Current Consensus

**Flakes are now standard** ([Next step in Nix: Embracing Flakes and Home Manager](https://callistaenterprise.se/blogg/teknik/2025/04/10/nix-flakes/)):

> "The current lay of the land is very much Flake flavoured, and finding a starter Flake might be the fastest route to Nixify a setup today. While 'it depends' still reigns supreme, Flakes are a very compelling option, even for newcomers taking their first plunge."

### Why Flakes?

**Advantages** ([Getting Started with Home Manager](https://nixos-and-flakes.thiscute.world/nixos-with-flakes/start-using-home-manager)):

1. **Reproducibility**: `flake.lock` pins exact commit hashes
   - Every input's version is cryptographically locked
   - Rebuilds are guaranteed identical across machines

2. **Explicit Dependencies**: All external sources declared in `inputs`
   - No hidden system state
   - Clear dependency graph

3. **Better Composition**: Flakes can reference other flakes
   - Import other users' configs as modules
   - Share configurations across machines/users

### Minimal flake.nix Template

```nix
{
  description = "Home Manager configuration for kvn";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";  # Use same nixpkgs version
    };
  };

  outputs = { nixpkgs, home-manager, ... }: {
    homeConfigurations."kvn" = home-manager.lib.homeManagerConfiguration {
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      modules = [ ./home.nix ];
    };
  };
}
```

**Note**: The `inputs.nixpkgs.follows` prevents duplicate nixpkgs evaluations

---

## 4. Custom Module Structure (Options, Config, Imports)

### Module Architecture Pattern

Based on [Module System and Custom Options](https://nixos-and-flakes.thiscute.world/other-usage-of-flakes/module-system) and [Home Manager EasyEffects module](https://github.com/nix-community/home-manager/blob/master/modules/services/easyeffects.nix):

**Standard Module Template**:
```nix
{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.programs.myprogram;  # or services.myservice
in
{
  # 1. OPTIONS: Define what users can configure
  options.programs.myprogram = {
    enable = mkEnableOption "My Program";

    package = mkOption {
      type = types.package;
      default = pkgs.myprogram;
      description = "The myprogram package to use.";
    };

    settings = mkOption {
      type = types.attrs;
      default = {};
      description = "Configuration settings as Nix attrset.";
      example = literalExpression ''
        {
          theme = "dark";
          fontSize = 12;
        }
      '';
    };

    extraConfig = mkOption {
      type = types.lines;
      default = "";
      description = "Extra configuration lines.";
    };
  };

  # 2. CONFIG: What happens when enabled
  config = mkIf cfg.enable {
    home.packages = [ cfg.package ];

    # Generate config file from settings
    xdg.configFile."myprogram/config.json".text =
      builtins.toJSON cfg.settings;

    # Conditionally add extra config
    xdg.configFile."myprogram/extra.conf" = mkIf (cfg.extraConfig != "") {
      text = cfg.extraConfig;
    };
  };
}
```

### Key Functions Explained

| Function | Purpose | Example |
|----------|---------|---------|
| `mkEnableOption` | Creates boolean enable flag | `enable = mkEnableOption "foo";` |
| `mkOption` | Defines configurable option | `package = mkOption { type = types.package; ... }` |
| `mkIf` | Conditional config application | `config = mkIf cfg.enable { ... }` |
| `mkDefault` | Overrideable default value | `value = mkDefault 42;` |
| `mkForce` | Override other values | `value = mkForce 99;` |
| `literalExpression` | Example code in documentation | `example = literalExpression "{ foo = 1; }"` |

### Type System

**Common Types** ([Module System Deep Dive](https://nix.dev/tutorials/module-system/deep-dive.html)):
```nix
types.bool              # true/false
types.int               # Integer
types.str               # String
types.lines             # Multi-line string
types.path              # Nix path
types.package           # Derivation/package
types.listOf types.str  # List of strings
types.attrsOf types.int # Attribute set of integers
types.enum ["a" "b"]    # Limited choices
types.nullOr types.str  # String or null
```

---

## 5. Audio Stack Module Implementation

### PipeWire Configuration (User-level)

**Limitation**: Full PipeWire configuration requires system-level access ([PipeWire - NixOS Wiki](https://nixos.wiki/wiki/PipeWire)). For non-NixOS, you'll need to configure PipeWire through standard Linux methods.

**Home Manager can manage** ([Home Manager audio services](https://discourse.nixos.org/t/configure-non-nixos-system-from-home-manager/52058)):
- User-specific WirePlumber configs in `~/.config/wireplumber/`
- PipeWire client settings in `~/.config/pipewire/`
- Audio applications (EasyEffects, Helvum, etc.)

**Example `modules/audio/pipewire.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  # Install PipeWire utilities
  home.packages = with pkgs; [
    pavucontrol      # Volume control GUI
    helvum           # PipeWire patchbay
    pwvucontrol      # PipeWire volume control
    qpwgraph         # Qt patchbay alternative
  ];

  # User WirePlumber config (limited scope on non-NixOS)
  xdg.configFile."wireplumber/main.lua.d/51-custom.lua".text = ''
    -- Custom WirePlumber rules
    rule = {
      matches = {
        {
          { "node.name", "matches", "alsa_output.*" },
        },
      },
      apply_properties = {
        ["audio.format"] = "S32LE",
        ["audio.rate"] = 96000,
      },
    }
    table.insert(alsa_monitor.rules, rule)
  '';

  # PipeWire client config
  xdg.configFile."pipewire/pipewire.conf.d/92-low-latency.conf".text = ''
    context.properties = {
      default.clock.rate = 96000
      default.clock.quantum = 512
      default.clock.min-quantum = 512
      default.clock.max-quantum = 2048
    }
  '';
}
```

### EasyEffects Module (Declarative Presets)

Based on [Home Manager EasyEffects module source](https://github.com/nix-community/home-manager/blob/master/modules/services/easyeffects.nix):

**Example `modules/audio/easyeffects.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  services.easyeffects = {
    enable = true;
    preset = "Audiophile";  # Load this preset at startup

    extraPresets = {
      "Audiophile" = {
        output = {
          blocklist = [];
          plugins = {
            # Parametric EQ
            equalizer = {
              enable = true;
              band0 = {
                frequency = 32.0;
                gain = 2.0;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };
              band1 = {
                frequency = 64.0;
                gain = 1.5;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };
              # Add more bands as needed
            };

            # Compressor for dynamics control
            compressor = {
              enable = true;
              attack = 20.0;
              release = 100.0;
              threshold = -18.0;
              ratio = 4.0;
              knee = 3.0;
              makeup = 0.0;
            };

            # Bass enhancer
            bass_enhancer = {
              enable = true;
              amount = 0.5;
              harmonics = 8.5;
              scope = 100.0;
              floor = 20.0;
            };

            # Limiter to prevent clipping
            limiter = {
              enable = true;
              input-gain = 0.0;
              limit = -1.0;
              release = 5.0;
            };
          };
        };
      };

      # Alternative preset for different use case
      "VoiceChat" = {
        input = {
          plugins = {
            gate = {
              enable = true;
              attack = 20.0;
              release = 250.0;
              threshold = -24.0;
            };

            compressor = {
              enable = true;
              attack = 20.0;
              release = 100.0;
              threshold = -20.0;
              ratio = 3.0;
            };
          };
        };
      };
    };
  };

  # Additional audio packages
  home.packages = with pkgs; [
    easyeffects  # Already included by service, but explicit
  ];
}
```

**Important Notes**:
- EasyEffects version 8.0.0+ uses different startup flags
- Home Manager automatically handles version differences
- Presets are JSON files written to `$XDG_DATA_HOME/easyeffects/`
- Service runs as systemd user unit

### Complete Audio Module

**Example `modules/audio/default.nix`** (aggregator):
```nix
{ config, lib, pkgs, ... }:

{
  imports = [
    ./pipewire.nix
    ./easyeffects.nix
  ];

  # Shared audio utilities
  home.packages = with pkgs; [
    # Analysis tools
    audacity
    sonic-visualiser

    # Format support
    ffmpeg-full

    # Additional utilities
    playerctl  # MPRIS media control
  ];
}
```

---

## 6. File Management (home.file, xdg.configFile)

### Symlinking Strategies

**Two Approaches** ([Home Manager dotfiles management](https://gvolpe.com/blog/home-manager-dotfiles-management/)):

1. **Nix Store Symlinks** (immutable, declarative)
2. **Out-of-Store Symlinks** (mutable, for active development)

### Nix Store Symlinks (Read-Only)

**Use when**: Configuration is fully managed by Home Manager

```nix
# Config files in ~/.config/
xdg.configFile."alacritty/alacritty.yml".source = ./alacritty.yml;

# Files in home directory
home.file.".gdbinit".text = ''
  set auto-load safe-path /nix/store
'';

# With templating
home.file.".zshrc".text = ''
  export PATH="${pkgs.nodejs}/bin:$PATH"
  source ${pkgs.zsh-autosuggestions}/share/zsh-autosuggestions/zsh-autosuggestions.zsh
'';
```

**Result**: Symlink points to `/nix/store/...-filename` (read-only)

### Out-of-Store Symlinks (Mutable)

**Use when**: You want to edit files directly ([Managing dotfiles with Nix](https://seroperson.me/2024/01/16/managing-dotfiles-with-nix/))

```nix
home.file.".zshenv".source =
  config.lib.file.mkOutOfStoreSymlink
    "${config.home.homeDirectory}/.dotfiles/.config/zsh/.zshenv";

# For entire directories
xdg.configFile."nvim" = {
  source = config.lib.file.mkOutOfStoreSymlink
    "${config.home.homeDirectory}/.dotfiles/.config/nvim";
  recursive = true;
};
```

**Result**: Symlink points to actual file in your dotfiles repo (writable)

### Advanced File Options

**Available attributes** ([home-manager files.nix](https://github.com/nix-community/home-manager/blob/master/modules/files.nix)):
```nix
home.file."example" = {
  source = ./path;           # Source file/directory
  text = "content";          # Inline text content
  target = ".example";       # Target path (default: attribute name)
  recursive = true;          # For directories
  executable = true;         # Make file executable
  onChange = "systemctl --user restart service";  # Run on change
};
```

### Practical Example

**Hybrid approach** for dotfiles:
```nix
{ config, pkgs, ... }:

let
  dotfilesDir = "${config.home.homeDirectory}/.dotfiles";
in
{
  # Mutable configs (actively edited)
  xdg.configFile = {
    "nvim".source = config.lib.file.mkOutOfStoreSymlink "${dotfilesDir}/.config/nvim";
    "zsh".source = config.lib.file.mkOutOfStoreSymlink "${dotfilesDir}/.config/zsh";
  };

  # Immutable configs (managed by Nix)
  xdg.configFile."git/config".text = ''
    [user]
      name = kvn
      email = kvn@example.com
    [core]
      editor = ${pkgs.neovim}/bin/nvim
  '';

  # Scripts with Nix dependencies
  home.file."bin/update-system" = {
    executable = true;
    text = ''
      #!${pkgs.bash}/bin/bash
      ${pkgs.home-manager}/bin/home-manager switch --flake ~/.config/home-manager
    '';
  };
}
```

---

## 7. Systemd User Services

### Service Declaration Pattern

Based on [How to Create Systemd Services in Nix Home Manager](https://haseebmajid.dev/posts/2023-10-08-how-to-create-systemd-services-in-nix-home-manager/):

**Basic Structure**:
```nix
systemd.user.services.my-service = {
  Unit = {
    Description = "My custom service";
    After = [ "graphical-session.target" ];
  };

  Service = {
    Type = "exec";  # or "simple", "forking", "oneshot"
    ExecStart = "${pkgs.mypackage}/bin/myprogram --daemon";
    Restart = "on-failure";
    RestartSec = 5;
  };

  Install = {
    WantedBy = [ "default.target" ];
  };
};
```

### Practical Examples

**1. Background Daemon Service**:
```nix
systemd.user.services.syncthing = {
  Unit = {
    Description = "Syncthing - Open Source Continuous File Synchronization";
    Documentation = "man:syncthing(1)";
    After = [ "network.target" ];
  };

  Service = {
    ExecStart = "${pkgs.syncthing}/bin/syncthing serve --no-browser --no-restart";
    Restart = "on-failure";
    SuccessExitStatus = [ 3 4 ];
    RestartForceExitStatus = [ 3 4 ];

    # Sandboxing
    PrivateTmp = true;
    ProtectSystem = "strict";
    ProtectHome = "read-only";
    ReadWritePaths = [ "%h/Sync" ];
  };

  Install.WantedBy = [ "default.target" ];
};
```

**2. Periodic Task (Timer)**:
```nix
# Service definition
systemd.user.services.backup-notes = {
  Unit.Description = "Backup notes to cloud";

  Service = {
    Type = "oneshot";
    ExecStart = pkgs.writeShellScript "backup-notes" ''
      #!${pkgs.bash}/bin/bash
      ${pkgs.rsync}/bin/rsync -av ~/notes/ ~/cloud/notes-backup/
    '';
  };
};

# Timer definition
systemd.user.timers.backup-notes = {
  Unit.Description = "Backup notes daily";

  Timer = {
    OnCalendar = "daily";
    Persistent = true;  # Run if system was off
  };

  Install.WantedBy = [ "timers.target" ];
};
```

**3. Graphical Application Service**:
```nix
systemd.user.services.easyeffects = {
  Unit = {
    Description = "EasyEffects daemon";
    After = [ "pipewire.service" ];
    PartOf = [ "graphical-session.target" ];
  };

  Service = {
    ExecStart = "${pkgs.easyeffects}/bin/easyeffects --gapplication-service";
    KillMode = "mixed";
    Restart = "on-failure";
    RestartSec = 5;

    # D-Bus integration (for older versions)
    BusName = "com.github.wwmm.easyeffects";
  };

  Install.WantedBy = [ "graphical-session.target" ];
};
```

### Key Systemd Targets

| Target | Use Case |
|--------|----------|
| `default.target` | Generic user session services |
| `graphical-session.target` | GUI applications requiring X/Wayland |
| `timers.target` | Timer units |
| `sockets.target` | Socket-activated services |

### Service Management

**Control from Home Manager config**:
```nix
# Enable service
systemd.user.services.my-service.Install.WantedBy = [ "default.target" ];

# Run command on service change
systemd.user.services.my-service.Service.ExecReload =
  "${pkgs.coreutils}/bin/echo 'Reloaded'";
```

**Manual control** (CLI):
```bash
# Start/stop/restart
systemctl --user start my-service
systemctl --user stop my-service
systemctl --user restart my-service

# Enable/disable autostart
systemctl --user enable my-service
systemctl --user disable my-service

# Check status
systemctl --user status my-service

# View logs
journalctl --user -u my-service -f
```

---

## 8. Dotfiles Repository Integration

### Modern Flake-Based Setup

Based on [Setting up your dotfiles with home-manager as a flake](https://www.chrisportela.com/posts/home-manager-flake/) and community examples:

**Recommended Structure**:
```
~/dotfiles/                    # Git repository
├── .git/
├── flake.nix                  # Entry point
├── flake.lock
├── home.nix                   # Main config
├── modules/                   # Modular configs
│   ├── audio/
│   ├── shell/
│   └── programs/
├── configs/                   # Raw config files
│   ├── nvim/
│   ├── zsh/
│   └── tmux/
└── hosts/                     # Per-machine configs
    ├── laptop/
    └── desktop/
```

### Integration Pattern 1: Pure Nix Management

**All configs managed by Home Manager**:
```nix
# flake.nix
{
  description = "kvn's dotfiles";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, home-manager, ... }: {
    homeConfigurations = {
      "kvn@laptop" = home-manager.lib.homeManagerConfiguration {
        pkgs = nixpkgs.legacyPackages.x86_64-linux;
        modules = [
          ./home.nix
          ./hosts/laptop/default.nix
        ];
      };

      "kvn@desktop" = home-manager.lib.homeManagerConfiguration {
        pkgs = nixpkgs.legacyPackages.x86_64-linux;
        modules = [
          ./home.nix
          ./hosts/desktop/default.nix
        ];
      };
    };
  };
}
```

**Activation**:
```bash
cd ~/dotfiles
home-manager switch --flake .#kvn@laptop
```

### Integration Pattern 2: Hybrid (Mutable Configs)

**Symlink to existing dotfiles** ([Managing dotfiles with Nix](https://seroperson.me/2024/01/16/managing-dotfiles-with-nix/)):
```nix
# home.nix
{ config, pkgs, ... }:

let
  dotfilesDir = "${config.home.homeDirectory}/dotfiles/configs";
in
{
  # Mutable configs via out-of-store symlinks
  xdg.configFile = {
    "nvim".source = config.lib.file.mkOutOfStoreSymlink "${dotfilesDir}/nvim";
    "zsh".source = config.lib.file.mkOutOfStoreSymlink "${dotfilesDir}/zsh";
    "tmux".source = config.lib.file.mkOutOfStoreSymlink "${dotfilesDir}/tmux";
  };

  # Package declarations in Nix
  home.packages = with pkgs; [
    neovim
    zsh
    tmux
    # ... more packages
  ];
}
```

### Git Workflow

**Ignore Nix build artifacts** (`.gitignore`):
```gitignore
result
result-*
.direnv/
```

**Track only source files**:
```bash
git add flake.nix flake.lock home.nix modules/ configs/
```

### Multi-User Setup

**Share configs across users** ([Home Manager modules](https://nixos.wiki/wiki/Home_Manager)):
```nix
# modules/shared.nix - Reusable module
{ config, pkgs, ... }:

{
  programs.git = {
    enable = true;
    lfs.enable = true;
    extraConfig = {
      init.defaultBranch = "main";
      pull.rebase = true;
    };
  };

  programs.zsh = {
    enable = true;
    # ... shared zsh config
  };
}

# User-specific home.nix
{ config, pkgs, ... }:

{
  imports = [ ../modules/shared.nix ];

  # User-specific overrides
  programs.git.userEmail = "user@example.com";
}
```

### Example Real-World Repos

**Community Examples** ([GitHub home-manager topic](https://github.com/topics/home-manager?o=desc)):

1. **[fufexan/dotfiles](https://github.com/fufexan/dotfiles)** - NixOS + Home Manager with flakes
2. **[aywrite/nix-config](https://github.com/aywrite/nix-config)** - Modular structure example
3. **[tiredofit/home](https://github.com/tiredofit/home)** - Standalone Home Manager flake
4. **[AlexNabokikh/nix-config](https://github.com/AlexNabokikh/nix-config)** - Multi-platform (NixOS/Darwin)

---

## 9. Complete Audiophile Stack Example

### Full Implementation

**Directory Structure**:
```
~/.config/home-manager/
├── flake.nix
├── home.nix
└── modules/
    └── audio/
        ├── default.nix        # Aggregator
        ├── pipewire.nix       # PipeWire user config
        ├── wireplumber.nix    # WirePlumber tweaks
        ├── easyeffects.nix    # EasyEffects presets
        └── packages.nix       # Audio utilities
```

**`modules/audio/default.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  imports = [
    ./pipewire.nix
    ./wireplumber.nix
    ./easyeffects.nix
    ./packages.nix
  ];

  # Enable audio system flag (optional, for conditional logic)
  options.my.audio.enable = lib.mkEnableOption "audiophile audio stack";

  config = lib.mkIf config.my.audio.enable {
    # This wraps all audio modules behind a single flag
  };
}
```

**`modules/audio/pipewire.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  # User-level PipeWire configuration
  xdg.configFile."pipewire/pipewire.conf.d/92-low-latency.conf".text = ''
    context.properties = {
      default.clock.rate = 96000
      default.clock.quantum = 512
      default.clock.min-quantum = 512
      default.clock.max-quantum = 2048
      default.clock.allowed-rates = [ 44100 48000 88200 96000 ]
    }
  '';

  # ALSA client configuration
  xdg.configFile."pipewire/client.conf.d/90-audiophile.conf".text = ''
    stream.properties = {
      resample.quality = 10
      channelmix.normalize = false
      channelmix.mix-lfe = false
    }
  '';
}
```

**`modules/audio/wireplumber.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  # WirePlumber user config (limited on non-NixOS)
  xdg.configFile."wireplumber/main.lua.d/51-audiophile.lua".text = ''
    -- High-quality audio settings
    rule = {
      matches = {
        {
          { "node.name", "matches", "alsa_output.*" },
        },
      },
      apply_properties = {
        ["audio.format"] = "S32LE",
        ["audio.rate"] = 96000,
        ["api.alsa.period-size"] = 512,
        ["api.alsa.headroom"] = 2048,
      },
    }
    table.insert(alsa_monitor.rules, rule)

    -- Input device settings
    input_rule = {
      matches = {
        {
          { "node.name", "matches", "alsa_input.*" },
        },
      },
      apply_properties = {
        ["audio.format"] = "S32LE",
        ["audio.rate"] = 96000,
      },
    }
    table.insert(alsa_monitor.rules, input_rule)
  '';

  # Bluetooth audio quality (if using BT)
  xdg.configFile."wireplumber/bluetooth.lua.d/51-bluez-config.lua".text = ''
    bluez_monitor.properties = {
      ["bluez5.enable-sbc-xq"] = true,
      ["bluez5.enable-msbc"] = true,
      ["bluez5.enable-hw-volume"] = true,
      ["bluez5.codecs"] = "[sbc sbc_xq aac ldac aptx aptx_hd aptx_ll aptx_ll_duplex]",
    }
  '';
}
```

**`modules/audio/easyeffects.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  services.easyeffects = {
    enable = true;
    preset = "Audiophile-Balanced";

    extraPresets = {
      # Primary preset for music listening
      "Audiophile-Balanced" = {
        output = {
          blocklist = [];
          plugins = {
            # Parametric EQ - Harman target curve approximation
            equalizer = {
              enable = true;
              mode = "IIR";
              num-bands = 10;

              # Sub-bass
              band0 = {
                frequency = 32.0;
                gain = 2.0;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };
              band1 = {
                frequency = 64.0;
                gain = 1.5;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };

              # Bass
              band2 = {
                frequency = 125.0;
                gain = 1.0;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };

              # Lower mids
              band3 = {
                frequency = 250.0;
                gain = 0.5;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };

              # Mids (slight dip for clarity)
              band4 = {
                frequency = 500.0;
                gain = -0.3;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.5;
              };
              band5 = {
                frequency = 1000.0;
                gain = -0.5;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.5;
              };

              # Upper mids (presence)
              band6 = {
                frequency = 2000.0;
                gain = 0.3;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.2;
              };
              band7 = {
                frequency = 4000.0;
                gain = 0.5;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.2;
              };

              # Treble
              band8 = {
                frequency = 8000.0;
                gain = 0.8;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };
              band9 = {
                frequency = 16000.0;
                gain = 0.5;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };
            };

            # Multiband compressor for gentle dynamics control
            multiband_compressor = {
              enable = true;

              # Sub-bass band
              subband0 = {
                attack = 150.0;
                release = 300.0;
                threshold = -24.0;
                ratio = 2.0;
                knee = 3.0;
                makeup = 0.0;
                solo = false;
                mute = false;
                lowcut-filter = 20.0;
                highcut-filter = 120.0;
              };

              # Bass band
              subband1 = {
                attack = 100.0;
                release = 200.0;
                threshold = -22.0;
                ratio = 2.5;
                knee = 3.0;
                makeup = 0.0;
                solo = false;
                mute = false;
                lowcut-filter = 120.0;
                highcut-filter = 1000.0;
              };

              # Mids band
              subband2 = {
                attack = 50.0;
                release = 150.0;
                threshold = -20.0;
                ratio = 3.0;
                knee = 3.0;
                makeup = 0.0;
                solo = false;
                mute = false;
                lowcut-filter = 1000.0;
                highcut-filter = 6000.0;
              };

              # Treble band
              subband3 = {
                attack = 30.0;
                release = 100.0;
                threshold = -18.0;
                ratio = 2.0;
                knee = 3.0;
                makeup = 0.0;
                solo = false;
                mute = false;
                lowcut-filter = 6000.0;
                highcut-filter = 20000.0;
              };
            };

            # Stereo enhancer for spatial width
            stereo_tools = {
              enable = true;
              input-gain = 0.0;
              output-gain = 0.0;
              balance-in = 0.0;
              balance-out = 0.0;
              slev = 50.0;  # Side level (stereo width)
              sbal = 0.0;
              mlev = 100.0; # Middle level
              mpan = 0.0;
              stereo-base = 0.0;
              delay = 0.0;
              sc-level = 1.0;
              stereo-phase = false;
            };

            # Final limiter for safety
            limiter = {
              enable = true;
              input-gain = 0.0;
              limit = -1.0;
              lookahead = 5.0;
              release = 8.0;
              oversampling = "None";
              asc = true;
              asc-level = 0.5;
            };

            # Bass enhancer (optional, for small speakers)
            bass_enhancer = {
              enable = false;  # Disable by default
              amount = 0.3;
              harmonics = 8.0;
              scope = 80.0;
              floor = 20.0;
              blend = 0.0;
            };
          };
        };
      };

      # Preset for gaming/movies (more dynamic)
      "Gaming-Cinema" = {
        output = {
          plugins = {
            # Simpler EQ
            equalizer = {
              enable = true;
              mode = "IIR";
              num-bands = 5;

              band0 = {
                frequency = 60.0;
                gain = 3.0;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.5;
              };
              band1 = {
                frequency = 250.0;
                gain = -1.0;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.5;
              };
              band2 = {
                frequency = 1000.0;
                gain = 0.0;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.0;
              };
              band3 = {
                frequency = 4000.0;
                gain = 1.5;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.5;
              };
              band4 = {
                frequency = 12000.0;
                gain = 2.0;
                mode = "RLC (BT)";
                type = "Bell";
                width = 1.5;
              };
            };

            # Bass boost
            bass_enhancer = {
              enable = true;
              amount = 0.6;
              harmonics = 10.0;
              scope = 100.0;
              floor = 20.0;
            };

            # Compressor for louder dialogue
            compressor = {
              enable = true;
              attack = 20.0;
              release = 100.0;
              threshold = -24.0;
              ratio = 4.0;
              knee = 3.0;
              makeup = 3.0;
            };

            # Limiter
            limiter = {
              enable = true;
              input-gain = 0.0;
              limit = -0.5;
              lookahead = 5.0;
              release = 8.0;
            };
          };
        };
      };

      # Microphone input preset
      "Mic-VoiceChat" = {
        input = {
          plugins = {
            # Noise gate
            gate = {
              enable = true;
              attack = 20.0;
              release = 250.0;
              threshold = -30.0;
              ratio = 10.0;
              knee = 3.0;
              makeup = 0.0;
            };

            # De-esser for sibilance
            deesser = {
              enable = true;
              detection = "RMS";
              mode = "Wide";
              threshold = -18.0;
              ratio = 3.0;
              laxity = 15.0;
              makeup = 0.0;
              f1-freq = 6000.0;
              f2-freq = 9000.0;
              f1-level = 0.0;
              f2-level = 12.0;
              f2-q = 1.0;
            };

            # Compressor for consistent volume
            compressor = {
              enable = true;
              attack = 20.0;
              release = 100.0;
              threshold = -20.0;
              ratio = 3.0;
              knee = 3.0;
              makeup = 3.0;
            };

            # Final limiter
            limiter = {
              enable = true;
              input-gain = 0.0;
              limit = -3.0;
              release = 5.0;
            };
          };
        };
      };
    };
  };
}
```

**`modules/audio/packages.nix`**:
```nix
{ config, lib, pkgs, ... }:

{
  home.packages = with pkgs; [
    # PipeWire control
    pavucontrol       # PulseAudio volume control (works with PW)
    pwvucontrol       # Native PipeWire volume control
    helvum            # PipeWire graph patchbay
    qpwgraph          # Qt-based patchbay

    # Analysis tools
    audacity          # Audio editor with spectrum analyzer
    sonic-visualiser  # Advanced audio analysis
    carla             # Audio plugin host

    # Format/codec support
    ffmpeg-full       # Complete codec support

    # JACK compatibility (for pro audio apps)
    qjackctl          # JACK control (works with pw-jack)

    # Utilities
    playerctl         # MPRIS media player control
    pulsemixer        # TUI mixer

    # Audio plugins (if needed)
    lsp-plugins       # LSP plugin suite
    zam-plugins       # ZamAudio plugins
    calf              # Calf Studio Gear plugins
  ];

  # Ensure EasyEffects can find plugins
  home.sessionVariables = {
    LV2_PATH = "${config.home.homeDirectory}/.lv2:${pkgs.lsp-plugins}/lib/lv2";
    LADSPA_PATH = "${config.home.homeDirectory}/.ladspa:${pkgs.lsp-plugins}/lib/ladspa";
  };
}
```

**Main `home.nix` integration**:
```nix
{ config, pkgs, ... }:

{
  imports = [
    ./modules/audio
  ];

  # Enable the audio stack
  my.audio.enable = true;

  # ... rest of config
}
```

---

## 10. Troubleshooting & Best Practices

### Common Issues

**1. EasyEffects Preset Not Loading** ([Issue #5185](https://github.com/nix-community/home-manager/issues/5185))

**Problem**: Preset specified in config doesn't load on startup

**Solution**:
- Ensure EasyEffects has been run at least once manually
- Check preset files exist: `ls ~/.local/share/easyeffects/output/`
- Verify systemd service status: `systemctl --user status easyeffects`
- Check logs: `journalctl --user -u easyeffects -f`

**2. PipeWire Not Detected in Home Manager** ([Issue #6044](https://github.com/nix-community/home-manager/issues/6044))

**Problem**: Applications can't find PipeWire

**Solution**:
```nix
# Ensure PipeWire socket is available
systemd.user.services.pipewire.Install.WantedBy = [ "default.target" ];
systemd.user.sockets.pipewire.Install.WantedBy = [ "sockets.target" ];
```

**3. Config Changes Not Applied**

**Problem**: `home-manager switch` doesn't update configs

**Solution**:
```bash
# Force rebuild
home-manager switch --flake . --impure

# Clear generations
home-manager expire-generations "-7 days"

# Nuclear option: remove and rebuild
rm -rf ~/.local/state/home-manager
home-manager switch --flake .
```

### Best Practices Summary

**Module Design**:
- ✅ Keep modules focused (one concern per file)
- ✅ Use `mkIf` for all conditional logic
- ✅ Provide sensible defaults with `mkDefault`
- ✅ Document options with descriptions and examples

**File Management**:
- ✅ Use Nix store symlinks for declarative configs
- ✅ Use out-of-store symlinks for actively edited dotfiles
- ✅ Never mix both approaches for the same file

**Performance**:
- ✅ Use `imports` liberally (no performance cost)
- ✅ Pin flake inputs for reproducibility
- ✅ Keep `flake.lock` in version control

**Debugging**:
```bash
# Build and show trace
home-manager build --flake . --show-trace

# Dry-run activation
home-manager switch --flake . --dry-run

# Check what changed
nix store diff-closures ~/.local/state/home-manager/gcroots/current-home result
```

---

## 11. Migration Path from Existing Dotfiles

### Incremental Adoption Strategy

**Phase 1: Package Management**
```nix
# Start simple - just packages
home.packages = with pkgs; [
  neovim
  zsh
  tmux
  git
];

# Keep existing dotfiles as-is
xdg.configFile."nvim".source =
  config.lib.file.mkOutOfStoreSymlink
    "${config.home.homeDirectory}/.dotfiles/.config/nvim";
```

**Phase 2: Selective Nixification**
```nix
# Move simple configs to Nix
programs.git = {
  enable = true;
  userName = "kvn";
  userEmail = "kvn@example.com";
  # ... git config in Nix
};

# Keep complex configs mutable
xdg.configFile."nvim".source =
  config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.config/nvim";
```

**Phase 3: Full Declarative**
```nix
# Everything in Nix
programs.neovim = {
  enable = true;
  # ... full neovim config
};
```

### Hybrid Workflow Example

```nix
{ config, pkgs, ... }:

let
  isDevelopment = builtins.pathExists ./dev-mode;
  dotfilesDir = "${config.home.homeDirectory}/.dotfiles";
in
{
  # Development: mutable configs
  xdg.configFile = lib.mkIf isDevelopment {
    "nvim".source = config.lib.file.mkOutOfStoreSymlink "${dotfilesDir}/.config/nvim";
  };

  # Production: declarative configs
  programs.neovim = lib.mkIf (!isDevelopment) {
    enable = true;
    # ... declarative config
  };
}
```

---

## Sources

### Primary Documentation
- [Home Manager Manual](https://nix-community.github.io/home-manager/)
- [Home Manager GitHub Repository](https://github.com/nix-community/home-manager)
- [NixOS & Flakes Book](https://nixos-and-flakes.thiscute.world/nixos-with-flakes/start-using-home-manager)
- [Module System Deep Dive](https://nix.dev/tutorials/module-system/deep-dive.html)

### Best Practices & Tutorials
- [Next step in Nix: Embracing Flakes and Home Manager](https://callistaenterprise.se/blogg/teknik/2025/04/10/nix-flakes/)
- [Setting up dotfiles with home-manager as a flake](https://www.chrisportela.com/posts/home-manager-flake/)
- [Home Manager dotfiles management](https://gvolpe.com/blog/home-manager-dotfiles-management/)
- [Managing dotfiles with Nix](https://seroperson.me/2024/01/16/managing-dotfiles-with-nix/)

### Audio Configuration
- [PipeWire - NixOS Wiki](https://nixos.wiki/wiki/PipeWire)
- [Home Manager EasyEffects Module](https://github.com/nix-community/home-manager/blob/master/modules/services/easyeffects.nix)
- [services.easyeffects - MyNixOS](https://mynixos.com/home-manager/options/services.easyeffects)

### Systemd Services
- [How to Create Systemd Services in Nix Home Manager](https://haseebmajid.dev/posts/2023-10-08-how-to-create-systemd-services-in-nix-home-manager/)

### Community Examples
- [fufexan/dotfiles](https://github.com/fufexan/dotfiles)
- [aywrite/nix-config](https://github.com/aywrite/nix-config)
- [tiredofit/home](https://github.com/tiredofit/home)
- [AlexNabokikh/nix-config](https://github.com/AlexNabokikh/nix-config)

---

## Conclusion

**Key Takeaways for Implementation**:

1. **Start with flakes** - They're the modern standard despite "experimental" label
2. **Modularize from the start** - Use `imports = []` extensively
3. **Hybrid approach works** - Mix declarative Nix with mutable dotfiles via `mkOutOfStoreSymlink`
4. **Audio stack is doable** - EasyEffects has full Home Manager support, PipeWire needs system-level config
5. **Systemd integration is powerful** - Declarative service management is a killer feature
6. **Incremental adoption** - Don't need to Nixify everything at once

**Next Steps**:
1. Initialize Home Manager flake: `nix run home-manager/release-25.05 -- init --switch`
2. Create basic module structure: `mkdir -p ~/.config/home-manager/modules/audio`
3. Implement EasyEffects module with presets
4. Add PipeWire user configs (limited on non-NixOS)
5. Integrate with existing dotfiles using out-of-store symlinks
6. Test and iterate

This research provides the foundation for a production-ready, modular Home Manager setup with a complete audiophile audio stack.
