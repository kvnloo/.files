{ config, lib, pkgs, ... }:

{
  options.my.k3sClient.enable = lib.mkEnableOption "user-only Kubernetes client tools";

  config = lib.mkIf config.my.k3sClient.enable {
    # CachyOS owns system services, container runtimes, kernel and GPU drivers.
    home.packages = [ pkgs.kubectl pkgs.k9s ];
  };
}
