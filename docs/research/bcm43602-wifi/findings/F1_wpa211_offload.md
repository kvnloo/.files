# F1 — 4-way timeout is wpa_supplicant 2.11 + brcmfmac offload

**Status:** confirmed (external + local)

Local: wlan0 associates then sits in `associated` ~10s, never `4way_handshake`. Same PSK on wlan1 completes immediately.

External: Arch BBS #298025 bisected wpa_supplicant 2.11 commit that waits for driver PORT_AUTHORIZED. BCM43602 `14e4:43ba` + `brcmfmac.feature_disable=0x82000` restores 2.11. ArchWiki documents this exact PCI ID. CachyOS forum (same distro) reports the same kernel param as the fix. Asahi/Manjaro: 0x82000 is the wpa_supplicant 2.11 Broadcom workaround.

This machine has `wpa_supplicant 2:2.11-5.1` and no `feature_disable` on cmdline.
