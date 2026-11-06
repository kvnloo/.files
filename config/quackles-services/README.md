# quackles-services

Two loopback static servers for the Quackles phone showcase (tailnet-only via
`tailscale serve`, which persists in tailscaled state):

- `quackles-hitl.service` on 127.0.0.1:18760 serves the HITL-NOW compare page.
- `quackles-lineage.service` on 127.0.0.1:18461 serves the lineage timeline export.

Content paths are host-private. Each host writes them to
`~/.config/quackles-services/{hitl,lineage}.env` (`QUACKLES_HITL_DIR=...`,
`QUACKLES_LINEAGE_DIR=...`); the installer refuses to run without them.

Install: `scripts/install-quackles-services --activate`
