# Packages & installers

This folder holds **installable product surfaces** — small, auditable trees that map 1:1 to what users download.

| Directory | Product | Ships as |
|-----------|---------|----------|
| **`linux-node/`** | Headless full node (x86_64 + ARM64/Pi) | `bloodstone-node-*-linux-*.tar.gz` |

Other installers may be added here later (e.g. `pi-fleet/`, `cloud-mining/`) so they are not lost inside the flat `ops/` dump.

## For auditors

1. Open **`linux-node/MANIFEST.md`** for the node installer file map.  
2. Open **`../AUDITOR-MAP.md`** for monorepo-wide sectioning.  
3. Ignore unrelated `ops/` scripts unless you are auditing VPS pool infrastructure.
