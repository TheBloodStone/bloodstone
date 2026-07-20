# Phase H1 — Cexius good-to-go notice

**Date:** 2026-07-20  
**Status:** **Good to go** — upgrade before height **17000**

## Message (send to Cexius)

You are **good to go** to upgrade your Bloodstone node.

- **No private pre-release** — use the public package.
- **Activation height *H* = 17000** (flag-day; not a chain relaunch).
- Upgrade **before** the chain reaches height 17000 so you stay consensus-compatible after activation.
- Deposit addresses, balances, and chain identity are **unchanged**. Only future headers (height ≥ 17000) get the tighter timewarp rules (DGW window-min + 30-minute future-stamp bound). Early history is grandfathered.

### Download (public)

- Node package: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz  
- SHA256 sidecar: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz.sha256  
- Latest alias: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz  
- Index: https://bloodstonewallet.mytunnel.org/downloads/  
- Activation note: https://bloodstonewallet.mytunnel.org/downloads/Phase-H1-Grandfathering-Activation-Height.md  

### What changes at height 17000

| Rule | Before H | At/after H |
|------|----------|------------|
| Same-algo DGW window min (header reject) | off | on (`timewarp-dgw-window`) |
| Future stamp vs network time | 7200 s | 1800 s |

### Ops checklist

1. Install v0.7.6 `bloodstoned` + `bloodstone-cli` and restart.
2. Confirm version shows **0.7.6**.
3. Confirm tip advances; **do not** wipe datadir.
4. Confirm **NTP / clock sync** on all STONE nodes (1800s future bound rejects clocks &gt; ~30 minutes fast).
5. Optional: watch logs around height 17000 for `timewarp-dgw-window` / `time-too-new`.

### Do end-users need a Qt wallet upgrade?

| Audience | Upgrade before H=17000? |
|----------|-------------------------|
| **Your deposit / withdrawal full nodes** | **Yes — required** |
| **Retail web wallet only** | **No** — they use the public web wallet; server nodes enforce rules |
| **Core Qt / GUI that runs a local full node** | **Yes** — local `bloodstoned` must be v0.7.6+ or they can fork after *H* |
| **Watch-only / RPC to an upgraded remote node** | No special wallet migration |

Detail: [Phase-H1-Who-Must-Upgrade.md](Phase-H1-Who-Must-Upgrade.md)

Vault bit-5 is **not** in this release.
