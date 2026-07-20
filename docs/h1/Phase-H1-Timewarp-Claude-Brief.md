# Claude brief — Phase H1 timewarp (H2b locked)

**Audience:** Claude (implementation / test / package follow-through)  
**From:** Bloodstone Phase H handoff after H2b acceptance  
**Vault:** frozen — do not edit vault covenant, witness v3/v4, `policy_blob`, or recovery-key paths  
**Pi miner suite / wallets:** out of scope — do not mix into this PR  

Read the pack files by **filename** (this brief assumes the docs zip or the same tree `doc/` + branch). Prefer local files over any portal.

---

## 1. Read order (filenames only)

| Order | File | Why |
|-------|------|-----|
| 1 | `Phase-H1-Timewarp-Claude-Brief.md` | This brief (what you should do) |
| 2 | `Phase-H1-Timewarp-Handoff.md` | Full handoff: locks, package notes, H3 map, deploy caution |
| 3 | `h0-phase-h-scope.md` | Phase H scope boundaries (H0/H1/H3 vs vault) |
| 4 | `h2b-window-timewarp-and-future-bound.md` | Locked analysis: window rule, attack/defense, joint future bound |
| 5 | `h2-timewarp-retarget-analysis.md` | Earlier H2 (rolling DGW, MTP, per-lane). **Adjacent rule later rejected by H2b** |
| — | `vault-threat-model.md` | Context only if present; **no vault implementation in this work** |

Optional binary package (if provided beside the docs):  
`bloodstone-node-0.7.2-h1-timewarp-linux-x86_64.tar.gz` + matching `.sha256` sidecar.  
Docs zip name if used: `Phase-H1-Timewarp-Docs.zip`.

---

## 2. Locked parameters (do not re-open without explicit review)

```text
TIMEWARP_MIN_WINDOW_SECONDS = 2160   # 24 * 270 / 3 = DGW T/3; HEADER REJECT
MAX_FUTURE_BLOCK_TIME       = 1800   # was 7200; not 900
Window MAX (e.g. 19440)     = NOT SHIPPED   # TODO post-testnet only
Adjacent BIP94-style bound  = DROPPED       # wrong tool for rolling DGW
```

**Primary rule:** same-algo DGW window endpoint span  
`newest.nTime - oldest.nTime` over **24** same-algo headers must be ≥ min timespan.  
Enforce as **header reject** (`timewarp-dgw-window`), not accept-and-clamp alone.

**Why not adjacent-only:** forward packing (+1 s steps) satisfies any adjacent floor while compressing `nActualTimespan` to ~23 s → clamp floor ease. See attack/defense in `h2b-window-timewarp-and-future-bound.md`.

---

## 3. Three required implementation conditions

### Condition 1 — Single source of truth for the window

- Factor the 24-block same-algo walk into **one** function (in tree: `CollectDgwSameAlgoWindow`).
- **Both** header reject and `GetNextWorkRequired` must use that walk (same `GetLastAncestorWithAlgo` stepping, same newest/oldest).
- Reject path: synthetic tip for the new header (`algo`, `nTime`, `pprev`) then collect.
- Add/keep agreement test: same oldest block index for reject vs retarget for the same `B` (H3 scenario 11).

### Condition 2 — Bootstrap / insufficient window

- If fewer than **24** same-algo blocks exist **including** the new tip as newest: **do not** apply MIN reject (defined skip — not crash, not undefined vacuous pass).
- Retarget already returns powLimit when the window is incomplete; keep that aligned.
- Test: H3 scenario 12.

### Condition 3 — One floor for clamp and reject

- DGW `nActualTimespan` clamp floor and reject MIN must share **one** helper/constant path (`DgwMinTimespan(nTargetTimespan)` → `nTargetTimespan / 3`).
- Multi-algo value equals `TIMEWARP_MIN_WINDOW_SECONDS` (2160). No second independent literal that can desync.
- Window **MAX** reject not in first H1 (leave TODO comment only).

---

## 4. Architecture (accepted; do not “fix”)

- Rolling retarget — **no** 2016-style epochs  
- Per-lane (per-algo) binding — not aggregate difficulty  
- MTP inherited (11-block, any algo) — unchanged  
- Cross-algo isolation except shared MTP  
- DGW ±3× formula clamp is **not** by itself a timewarp fix; reject makes min real  
- Phase H = **separate PR** from vault Phases 1–3  

---

## 5. Source map (expected tree)

| Area | Location |
|------|----------|
| Branch | `phase-h1-h3-timewarp-window` |
| Headers / pow | `src/pow.h`, `src/pow.cpp` |
| Future bound | `src/chain.h` (`MAX_FUTURE_BLOCK_TIME = 1800`) |
| Header reject | `src/validation.cpp` (`CheckDgwTimewarpWindow`, reason `timewarp-dgw-window`) |
| Unit tests | `src/test/timewarp_tests.cpp` |
| Dualalgo golden clamp | `src/test/dualalgo_tests.cpp` (use shared `DgwMinTimespan`) |
| Docs | `doc/h0-…`, `doc/h2b-…`, `doc/Phase-H1-…` |

---

## 6. What you should do next

1. Confirm the three conditions still hold in tree (window factoring, bootstrap, shared floor).  
2. Build full unit test binary; run:
   - `timewarp_tests`
   - `dualalgo_tests`  
3. Do **not** implement vault, recovery keys, Pi miner packaging, or window MAX reject unless a new directive says so.  
4. If packaging: ship node only; keep version bump discipline for any operator release; MD first for docs.  
5. Flag consensus deploy risk: mixed peers (old future window / no window reject vs H1) can split; coordinated upgrade or clean relaunch — note in any release notes.

---

## 7. H3 scenarios (filename-local checklist)

| # | Intent | Expect |
|---|--------|--------|
| 1 | Compressed window (span &lt; min) | Reject |
| 2 | Span == min | Accept |
| 3 | Span ≈ target (24×270) | Accept |
| 4 | Successive compressed windows | Reject / no ratchet |
| 5 | Cross-algo: compress one lane | That lane rejects only |
| 6 | Future &gt; 1800 | time-too-new |
| 7 | Honest multi-algo smoke | No surprise rejects |
| 8 | Window MAX | **Not shipped** — skip |
| 9 | Adjacent +1 s but span ≥ min | Accept (proves not adjacent rule) |
| 10 | Adjacent +1 s, span short | Reject on **window** |
| 11 | Single-source oldest agreement | Reject walk ≡ retarget walk |
| 12 | Bootstrap &lt; 24 same-algo | Defined skip |
| 13 | Newest inflation (old +7200 style) | FUT=1800 + MTP; MIN alone does not catch inflation |

---

## 8. Explicit non-goals

- No vault Phase 1+ code  
- No wallet “recovery keys on create”  
- No Pi suite / miner APK refresh as part of H1  
- No adjacent `BOUND = 270` (or 600) as primary control  
- No window MAX reject in first H1  

---

## 9. One-line summary

**Implement and verify Phase H1 only:** reject compressed same-algo DGW windows via the shared 24-block walk (`MIN` = multi-algo 2160 / `DgwMinTimespan`), tighten future time to 1800, test scenarios 1–13 (skip 8), leave vault and Pi/wallet alone. Details and attack trace live in `h2b-window-timewarp-and-future-bound.md` and `Phase-H1-Timewarp-Handoff.md`.
