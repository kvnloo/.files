# F2 — NVRAM/CLM is range/channels, not this timeout

**Status:** confirmed as separate issue

Missing `clm_blob` / Apple `.txt` is real (dmesg err=-2, country 99). linux-firmware ships only `brcmfmac43602-pcie.bin` and `.ap.bin`. Community NVRAM gist exists. Generic CLM reported to crash Apple 13,3.

Local experiment: permanent MAC + PMF disable still timed out after associate. Handshake is not waiting on NVRAM.

Do not install a random clm_blob as step 1.
