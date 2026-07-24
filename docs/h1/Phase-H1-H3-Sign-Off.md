# Phase H1/H3 — Sign-off

**Status:** **SIGNED OFF**  
**Date:** 2026-07-20  
**Branch:** `phase-h1-h3-timewarp-window`  
**Vault:** frozen (separate PR)  

---

## Sign-off statement (reviewer)

H1/H3 signed off. Single-binary green on both suites verified (linked 07:05:28, both runs against it; subsequent clean rebuild re-confirmed green); scenario 11 now asserts `nextBits == expectedBits` from independent window math rather than the old tautology; `GetLastAncestorWithAlgo` inclusivity pinned directly; dualalgo green confirms the shared `DgwMinTimespan` floor did not perturb honest retargeting. Consensus logic was verified by code read; tests verified to exercise it — both halves done.

**Locked:**

| Item | Value |
|------|--------|
| Mechanism | Window-span **header reject** (`timewarp-dgw-window`) |
| `TIMEWARP_MIN_WINDOW_SECONDS` | **2160** (multi-algo `T/3`; runtime via `DgwMinTimespan`) |
| `MAX_FUTURE_BLOCK_TIME` | **1800** |
| Adjacent BIP94-style rule | **Dropped** |
| Window MAX ceiling | **Not shipped** (TODO post-testnet) |
| Vault covenant | **Frozen** |

**Upgrade path (locked 2026-07-20):** **coordinated flag-day** (not genesis relaunch) — listing / exchange balances must be preserved.  
**Deploy hold:** **do not merge or activate** until **Cexius** (and other critical node ops) confirm notice period, technical contact, and upgrade ACK. Letter: `Bloodstone-Cexius-Flag-Day-Coordination-Letter.md`.

**Clear to merge** only **after** Cexius coordination inputs are in hand and activation height *H* is agreed. Do not merge as a silent mainnet flip.

**§15.1 vault gate:** signed off ≠ discharged. Discharge only when H1 is **merged and active** on the network (see `vault-threat-model.md` v1.2). Spec reference for §15.1 is **Build Spec v1.2**.

**Ops 2026-07-24:** Cexius main-chain alignment **closed**; LRGK **0.7.6** resolved; intend **GO on 26 Jul** after LRGK NTP receipt — see `Phase-H1-GO-Register-2026-07-26.md`. Flip §15.1 to **discharged** only after flag-day activation + post-crossing check-in (not at GO decision).

---

## Test evidence (single binary)

| Suite | Result |
|-------|--------|
| `timewarp_tests` | Running 11 test cases… **No errors detected** (exit 0) |
| `dualalgo_tests` | Running 4 test cases… **No errors detected** (exit 0) |

Binary path (build tree): `bloodstone-linux-build/src/test/test_spacexpanse`  
(Scenario 11: `BOOST_CHECK_EQUAL(nextBits, expectedBits)`; inclusivity: `GetLastAncestorWithAlgo(algo) == &indexNew`.)

---

## Merge / deploy notes (H0 §6) — flag day

1. **Path locked: flag-day height activation** (relaunch rejected — Cexius listing / live balances).  
   Old peers with `MAX_FUTURE_BLOCK_TIME=7200` and no window reject will diverge on `time-too-new` and `timewarp-dgw-window` after *H*.
2. **Wait for Cexius** before merge/deploy: notice period, tech contact, written upgrade ACK, then freeze *H* (days out).  
   Historical scan (no block would be retro-invalid under new rules) before freezing *H*.
3. **Vault final-gate checklist:** H1/H3 **sign-off** is filed; **§15.1 discharges only after merge + flag-day activation** (rules live on peers including exchange nodes). See `vault-threat-model.md` v1.2 §1 table (Build Spec **v1.2** §15.1).
4. **Do not bundle** vault bit-5 with this flag day.

---

## Still open (non-blocking for H1 / vault §15.1)

| Item | Role |
|------|------|
| **H4** | 64-byte-transaction ban |
| **H5** | Worst-case validation bound |

Pick up before mainnet; do not hold H1 merge.

---

## Vault cross-reference

Value-bearing vaults must not go live on a chain whose per-algo retarget is timewarp-defeasible. H1 closes that hole: max-ease DGW steps require **≥2160 s** of real same-algo endpoint time, so the **960-block** clawback floor retains wall-clock meaning.

*Phase H H1/H3 complete · H4/H5 later · vault code still frozen*
