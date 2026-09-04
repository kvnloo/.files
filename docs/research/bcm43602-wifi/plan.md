# Plan — make BCM43602 work on MacBookPro11,5 / CachyOS

- Date: 2026-08-16
- Decision: get `wlan0` (Apple BCM43602 `14e4:43ba`) to complete WPA2 handshake
- Genre: validation + decision
- Machine facts: CachyOS 7.1.3, wpa_supplicant 2.11-5.1, brcmfmac firmware 7.35.177.61 (2015), wlan1 USB already works

## Hypotheses

1. H1: wpa_supplicant 2.11 waits for firmware 4-way offload `PORT_AUTHORIZED`; BCM43602 never sends it. `feature_disable=0x82000` makes userspace do the handshake.
2. H2: Missing Apple NVRAM/CLM is why handshake fails.
3. H3: MAC randomization / PMF / WPA3 mixed mode is sufficient to explain timeout.
4. H4: Chip is unfixable on this AP; USB is the only path.

## Opposition queries

- Does feature_disable break 5 GHz or scan?
- Does generic clm_blob crash Apple 43602?
- Does iwd succeed without kernel param?

## Stop criteria

- Primary fix identified with ≥3 independent source types, and local experiment either applies it or is blocked only on sudo.
