# Home Manager on CachyOS

This flake manages portable user packages and editable, out-of-store links to
this dotfiles repository. CachyOS continues to manage the kernel, drivers,
Hyprland, portals, and hardware services with pacman.

## Bootstrap

From the repository root:

```sh
./config/nix/bootstrap-cachyos.sh
```

The first run installs Nix and may ask you to log out once after adding your
account to `nix-users`. Run the command again after logging back in.

The profile defaults to `kvn@$(hostname)`. A host can be selected explicitly:

```sh
./config/nix/bootstrap-cachyos.sh mbp
./config/nix/bootstrap-cachyos.sh 0
```

After bootstrap, apply changes with:

```sh
home-manager switch --flake path:$HOME/workspace/.files/config/nix#kvn@mbp
```
