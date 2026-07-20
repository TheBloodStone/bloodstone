# Phase H1 Timewarp — Megadrive / Claude handoff

**Date:** 2026-07-20  
**Status:** H2b accepted · H1 implementation in tree · Linux x86_64 node package published  
**Vault:** **Frozen** — this package does **not** add vault recovery keys or vault covenant code  
**Pi miner suite / wallets:** **Unchanged** by this drop

---

## 1. Start here (share these links)

Base URL: `https://bloodstonewallet.mytunnel.org/downloads/`

### Primary handoff (this document)

| What | Link |
|------|------|
| **This handoff (MD)** | https://bloodstonewallet.mytunnel.org/downloads/Phase-H1-Timewarp-Handoff.md |
| **Latest alias** | https://bloodstonewallet.mytunnel.org/downloads/Phase-H1-Timewarp-Handoff-latest.md |

### Analysis (H2 / H2b — read before code review)

| What | Link |
|------|------|
| **H2b window rule + joint future bound** | https://bloodstonewallet.mytunnel.org/downloads/h2b-window-timewarp-and-future-bound.md |
| H2b latest | https://bloodstonewallet.mytunnel.org/downloads/h2b-window-timewarp-and-future-bound-latest.md |
| **H0 scope (what Phase H is / is not)** | https://bloodstonewallet.mytunnel.org/downloads/h0-phase-h-scope.md |
| H0 latest | https://bloodstonewallet.mytunnel.org/downloads/h0-phase-h-scope-latest.md |
| H2 original retarget analysis | https://bloodstonewallet.mytunnel.org/downloads/h2-timewarp-retarget-analysis.md |

### Node binary package (Linux x86_64)

| What | Link |
|------|------|
| **Tarball v0.7.2-h1** | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz |
| **SHA256** | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz.sha256 |
| Latest alias | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz |
| Latest SHA256 | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz.sha256 |

**Contents of tarball:**

- `bloodstoned` — stripped Linux x86_64 daemon (**v0.7.2** version string) with H1 consensus rules  
- `bloodstone-cli` — companion CLI  
- `h0-phase-h-scope.md`, `h2b-window-timewarp-and-future-bound.md`, `BUILD-INFO.txt`

```bash
# verify + extract
curl -fsSL -O https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz
curl -fsSL -O https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz.sha256
sha256sum -c bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz.sha256
tar -xzf bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz
./bloodstone-node-0.7.2-h1-timewarp-linux-x86_64/bloodstoned --version
# expect: Bloodstone version v0.7.2
```

---

## 2. What this is (one paragraph)

Phase **H** is **consensus hygiene** for multi-algo Dark Gravity Wave **timewarp** (Verge-class single-lane timestamp packing). H2/H2b analysis locked the rule; **H1** implements it; **H3** unit vectors live in source. It is a **separate PR** from native vault. **Rolling** per-algo retarget (no epochs). Primary control is a **window endpoint span** reject on the same 24-block same-algo walk DGW uses — **not** an adjacent BIP94-style bound.

---

## 3. Locked parameters (do not re-litigate without review)

| Parameter | Locked value | Notes |
|-----------|--------------|--------|
| `TIMEWARP_MIN_WINDOW_SECONDS` | **2160** | `24 × 270 / 3` = DGW `T/3`; **header reject** |
| `MAX_FUTURE_BLOCK_TIME` | **1800** | Was 7200; **not** 900 |
| Window MAX (e.g. 19440) | **Not shipped** | TODO post-testnet (honest hashrate drops) |
| Adjacent `B ≥ P − BOUND` | **Dropped** | Insufficient vs forward packing |
| Vault covenant / recovery keys | **Frozen / not in package** | Phase 1 vault is a later PR |

---

## 4. Three H1 conditions (implementation contract)

1. **Single source of truth for the window**  
   `CollectDgwSameAlgoWindow` — same `GetLastAncestorWithAlgo` walk for reject and `GetNextWorkRequired`. Synthetic tip for the new header on reject path. H3 scenario 11 asserts oldest-index agreement.

2. **Bootstrap / insufficient window**  
   If fewer than **24** same-algo blocks including the new tip: **skip** MIN reject (defined pass, no crash). Retarget already returns powLimit when the window is incomplete. H3 scenario 12.

3. **One floor helper**  
   Reject MIN and DGW clamp floor both use `DgwMinTimespan(nTargetTimespan)` (`nTargetTimespan / 3`). Multi-algo value equals **2160** (`TIMEWARP_MIN_WINDOW_SECONDS` + `static_assert`).

**Reject reason string:** `timewarp-dgw-window`  
**Not** “accept and clamp only” — compressed windows **do not land on chain**.

---

## 5. What did **not** update (for Megadrive / Pi testing)

| Area | Updated? |
|------|----------|
| Pi miner suite / desktop miner / Android miner APK | **No** |
| Wallet apps (Qt / Electron / APK) | **No** |
| Vault recovery keys on wallet create | **No** |
| Coordinator / mesh roster | **No** |
| LRGK packages | **No** |

**Implication:** running a full Pi suite still uses existing miner/wallet builds. Only the **node** in this tarball carries H1. Miners that stamp absurdly packed same-algo windows may see **reject** once peers enforce H1; normal honest timestamps are fine.

---

## 6. Source locations (for Claude)

| Item | Path |
|------|------|
| Branch | `phase-h1-h3-timewarp-window` |
| Source tree | `/root/bloodstone-chain` |
| Build tree | `/root/bloodstone-linux-build` |
| Core files | `src/pow.h`, `src/pow.cpp`, `src/chain.h`, `src/validation.cpp` |
| H3 tests | `src/test/timewarp_tests.cpp` |
| Docs | `doc/h0-phase-h-scope.md`, `doc/h2b-…`, this handoff |

**Unstripped build note:** full debug `bloodstoned` was linked at  
`/root/bloodstone-linux-build/src/bloodstoned` (~349 MB, BuildID `b267ec17…`).  
Downloads ship a **stripped** binary (~9.4 MB in the tarball).

---

## 7. H3 scenario checklist (for Claude)

| # | Scenario | Expect |
|---|----------|--------|
| 1 | Span = min − ε over 24 same-algo | **Reject** |
| 2 | Span = min (2160 multi-algo) | **Accept** |
| 3 | Span ≈ 6480 | **Accept** |
| 4 | Successive compressed windows | **Reject** (no ratchet) |
| 5 | Cross-algo: compress one lane only | That lane rejects; other OK |
| 6 | Future > 1800 | **time-too-new** |
| 7 | Honest multi-algo smoke | No surprise rejects |
| 8 | Window MAX | **Not shipped** — skip |
| 9 | +1 s adjacent but span ≥ min | **Accept** |
| 10 | +1 s packing span short | **Reject on window** |
| 11 | Single-source oldest agreement | Reject walk ≡ retarget walk |
| 12 | Bootstrap &lt; 24 same-algo | Defined skip |
| 13 | Newest inflation (+7200 style) | Blocked by **FUT=1800** + MTP; MIN alone does not catch inflation |

Run (after full test binary build):

```bash
# from configured build tree
./src/test/test_spacexpanse --run_test=timewarp_tests
# dualalgo regression still expected to pass with shared DgwMinTimespan clamp
./src/test/test_spacexpanse --run_test=dualalgo_tests
```

---

## 8. Deploy / network caution

- H1 changes **header consensus** (`timewarp-dgw-window` + tighter future window).  
- Mixed peers (old 7200 future / no window reject vs H1) can disagree on acceptance.  
- Prefer **coordinated upgrade** or clean relaunch — not silent mixed mainnet.  
- Full tree rebuild noted for any production ship beyond this handoff tarball.  
- `-reindex-chainstate` alone does **not** re-validate all historical headers through `ContextualCheckBlockHeader`.

---

## 9. Suggested message Megadrive can paste to Claude

```text
Phase H1 timewarp handoff (H2b locked). Read first:
https://bloodstonewallet.mytunnel.org/downloads/Phase-H1-Timewarp-Handoff.md

Analysis:
https://bloodstonewallet.mytunnel.org/downloads/h2b-window-timewarp-and-future-bound.md
https://bloodstonewallet.mytunnel.org/downloads/h0-phase-h-scope.md

Linux x86_64 node package:
https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz
SHA256:
https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz.sha256

Locks: MIN window 2160 (header reject), MAX_FUTURE 1800, no window MAX, no adjacent rule, vault frozen.
Branch: phase-h1-h3-timewarp-window under /root/bloodstone-chain
Please: run timewarp_tests + dualalgo_tests; do not add vault code; Pi/wallet packages not in scope.
```

---

## 10. SHA256 (tarball)

```
a4759a659673e410a632a0bc8740ef39ebe89c43c2cb9ffdb3741d3a96c211aa  bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz
```

(Also in the `.sha256` sidecar linked above.)

---

*Handoff for Megadrive · Phase H only · vault / Pi suite / wallet recovery keys not included*
