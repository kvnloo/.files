# Restore metadata

`restore/p0.toml` describes mutable state that IaC cannot reconstruct from Git.

It stores logical IDs, discovery hints, restore requirements, and verification
methods only. Private data and secret values stay in their actual backup or
secret systems.
