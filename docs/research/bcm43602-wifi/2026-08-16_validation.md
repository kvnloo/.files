# BCM43602 on MacBookPro11,5 — what actually unblocks Wi‑Fi

## Decision

Apply `brcmfmac.feature_disable=0x82000` (modprobe.d + GRUB). Do not install `broadcom-wl`. Do not inject a generic CLM blob first. Keep the USB radio as fallback.

## Hypotheses

| ID | Claim | Verdict |
|----|--------|---------|
| H1 | 2.11 waits for firmware 4-way offload that never completes | **Confirmed** |
| H2 | Missing Apple NVRAM/CLM causes this timeout | **Refuted for handshake**; still true for TX/channels |
| H3 | MAC random / PMF / WPA3 alone explains timeout | **Refuted locally** (permanent MAC + PMF off still failed) |
| H4 | Unfixable; USB only | **Under-determined** until 0x82000 is applied (needs sudo) |

## What we measured here

- `wlan0`: Broadcom BCM43602, `brcmfmac`, firmware **Nov 10 2015** `7.35.177.61`
- `wlan1`: TP-Link 8812AU — connects to Mxin and MyPvtNetwork
- wlan0: scan 100%, associate, never 4-way, NM re-asks password
- `wpa_supplicant 2:2.11-5.1`, cmdline has **no** `feature_disable`
- NM-only clone `Mxin-wlan0` (factory MAC `a4:5e:60:e6:15:21`, PMF disable) **still timed out**

## Evidence (triangulated)

1. **Primary / wiki:** ArchWiki Broadcom wireless — BCM43602 / `14e4:43ba` needs `brcmfmac.feature_disable=0x82000` (BBS#298025).
2. **Discussion / same distro:** CachyOS forum — same param on GRUB/Limine “works perfectly fine”.
3. **Industry / Asahi:** wpa_supplicant update broke WPA2/3 on Broadcom FullMAC; workaround is `0x82000`.
4. **BBS primary:** 2.11 commit waits for PORT_AUTHORIZED; 43602 never sends it; param restores 2.11.

Alternate SUCCESS path: NetworkManager `wifi.backend=iwd` (EndeavourOS 2015 MBP, same PCI/subsystem).

## What will not fix this timeout

- Re-entering the PSK (already saved)
- `broadcom-wl-dkms` (wrong family; CachyOS user lost scan)
- Generic `clm_blob` (crash reports on Apple 13,3)
- NVRAM `.txt` alone (range, not 4-way)

## Apply (needs root)

```sh
sudo ./scripts/fix-bcm43602-wifi.sh
```

Then reboot (or reload `brcmfmac_wcc` + `brcmfmac`) and `nmcli device wifi connect Mxin ifname wlan0`.

## Adversarial

- **Could 0x82000 be obsolete after a later wpa_supplicant fix?** Possible; this box is still 2.11-5.1 and still times out, so the bug is live here.
- **Could we just use iwd?** Yes; same root cause (userspace handshake). Kernel param is the wiki-canonical fix and does not replace NM.
- **Could firmware be too old for these APs?** USB works with same APs; after offload disable, 2015 firmware still does WPA2-PSK in userspace.

## Local next experiment (blocked)

No passwordless sudo. Cannot write `/etc/modprobe.d` or GRUB from this session.
