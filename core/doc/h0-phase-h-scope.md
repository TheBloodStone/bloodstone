# H0 — Phase H scope (timewarp / retarget hygiene)

**Status:** Locked for H1/H3 implementation  
**Date:** 2026-07-20  
**Branch:** `phase-h1-h3-timewarp-window` (separate PR from vault)  
**Vault covenant:** **Frozen** — zero witness v3/v4 / `policy_blob` / U1–U4 edits in this PR.

---

## 1. What Phase H is

Phase H is **consensus hygiene** for multi-algo Dark Gravity Wave (DGW) timestamp manipulation (Verge-class single-lane timewarp), required before value-bearing vault activation (§15.1). It is **not** vault Phase 1–3.

| Sub-phase | Deliverable | This PR |
|-----------|-------------|---------|
| **H0** | Scope + locked parameters (this doc) | Yes |
| **H1** | Consensus: window-min reject + `MAX_FUTURE_BLOCK_TIME` | Yes |
| **H3** | Regtest / unit vectors (scenarios 1–13) | Yes |
| H4 / H5 | Optional follow-ups (monitoring, docs polish) | Later |
| Vault Phases 1–3 | Native vault covenant | **Out of scope** |

---

## 2. Locked parameters (from H2b review)

| Parameter | Value | Notes |
|-----------|-------|-------|
| **TIMEWARP_MIN_WINDOW_SECONDS** | **2160** | Multi-algo `24 × 270 / 3` (= DGW `T/3`) |
| **MAX_FUTURE_BLOCK_TIME** | **1800** | Reduced from 7200; not 900 |
| Window **MAX** ceiling (19440) | **Not shipped** | TODO post-testnet — honest hashrate drops |
| Adjacent BIP94-style bound | **Dropped** | Wrong tool for rolling DGW |

**Implementation binding (condition 3):**  
Reject MIN and DGW clamp floor both call `DgwMinTimespan(nTargetTimespan)` (`nTargetTimespan / 3`). For multi-algo spacing 270, that equals `TIMEWARP_MIN_WINDOW_SECONDS` (`static_assert` + unit test). No second independent floor literal.

---

## 3. H1 consensus rules (summary)

### 3.1 Window-min header reject (primary)

When validating a new header of algo `A`:

1. Build a **synthetic tip** for the new header (same `algo`, `nTime`, `pprev`).
2. Run **`CollectDgwSameAlgoWindow`** (single source of truth — same walk as `GetNextWorkRequired`).
3. If `nCount < 24` → **bootstrap skip** (defined; do not reject; do not crash).  
   `GetNextWorkRequired` already returns powLimit when the window is incomplete.
4. If full window → require  
   `newest.nTime - oldest.nTime >= DgwMinTimespan(24 * GetTargetSpacing(A, height))`  
   else reject reason **`timewarp-dgw-window`**.

### 3.2 Future allowance

`MAX_FUTURE_BLOCK_TIME = 1800` in `chain.h` (was 7200).  
`TIMESTAMP_WINDOW` tracks the same value.

### 3.3 Explicitly not in H1

- Adjacent `B.nTime >= P.nTime - BOUND`
- Window MAX reject (19440)
- Vault covenant / deployment bit 5 value path
- Epoch-based retarget (Bloodstone stays **rolling** per-algo DGW)

---

## 4. Three H1 implementation conditions (met)

| # | Condition | How |
|---|-----------|-----|
| 1 | Single source of truth for the 24-block window | `CollectDgwSameAlgoWindow` used by retarget + reject; H3 scenario 11 asserts oldest index agreement |
| 2 | Bootstrap / insufficient window defined | `nCount < 24` → check returns true; retarget → powLimit; H3 scenario 12 |
| 3 | Clamp floor and reject MIN same constant/helper | `DgwMinTimespan` only; multi-algo value named `TIMEWARP_MIN_WINDOW_SECONDS` |

---

## 5. Architecture (unchanged from H2b)

- Rolling retarget, **no epochs**
- **Per-lane** binding (same-algo walk only)
- MTP inherited (11-block, any algo)
- Cross-algo isolation except shared MTP
- DGW ±3× upper clamp kept; lower clamp bound to timewarp min helper
- Upper **reject** ceiling not shipped

---

## 6. Rebuild / deployment note

This PR changes **consensus header checks** and **`MAX_FUTURE_BLOCK_TIME`**.

- **Full tree rebuild** of `bloodstoned` / libs required before deploy.
- Existing peers on 7200s future skew may diverge on “time-too-new” and “timewarp-dgw-window” once enforced.
- Prefer **genesis / coordinated network upgrade** (or clean relaunch) rather than mixed-rule mainnet.
- `-reindex-chainstate` alone does **not** re-run `ContextualCheckBlockHeader` for all historical headers; plan upgrade path accordingly.

---

## 7. H3 scenario map

| # | Scenario | Coverage |
|---|----------|----------|
| 1 | Compressed window (span min−ε) | Reject |
| 2 | Min legal window (span = min) | Accept |
| 3 | Target window (~6480) | Accept |
| 4 | Multi-step compressed | Reject (no ratchet) |
| 5 | Cross-algo isolation | SHA reject / neo OK |
| 6 | Future bound 1800 | Constant + boundary |
| 7 | Honest multi-algo smoke | All three lanes |
| 8 | (Optional MAX) | Not shipped — skipped |
| 9 | Adjacent +1s but span ≥ min | Accept (not adjacent rule) |
| 10 | Adjacent +1s span short | Reject on window |
| 11 | Single-source oldest agreement | Collect reject vs retarget |
| 12 | Bootstrap insufficient window | Defined skip |
| 13 | Newest inflation +7200 | FUT=1800 blocks; MIN alone does not |

Unit file: `src/test/timewarp_tests.cpp`.

---

## 8. Out of scope (do not mix)

- Vault Phases 0–4 code
- Mesh / coordinator
- LRGK
- Window MAX ceiling
- Adjacent timewarp bound

---

*H0 complete · H1/H3 on branch `phase-h1-h3-timewarp-window` · vault frozen*
