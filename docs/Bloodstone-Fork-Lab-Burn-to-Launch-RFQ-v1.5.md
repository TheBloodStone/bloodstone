# Bloodstone Fork Lab — Burn-to-Launch System
## Build Specification / RFQ · v1.5 (frozen)

**Status:** Ready to scope and quote. This is the canonical spec; where it conflicts with any prior draft (Grok, GPT/Qwen, or the original vision doc), this document wins.

**Changelog v1.4 → v1.5:** (a) **Salvage removed from the platform entirely** — no payout, no leaderboard, no badges, no graveyard, no farm-lock. §7 is now bare lifecycle tracking (registry hygiene only); **§7a deleted** (no platform payout → no money-pump → no constraint needed). (b) **Goblin Magic reframed as LRGK's off-platform canary experiment** (§12.4) — it is a *coin-provided* capability on LRGK's surface, not a platform feature. (c) **Locked Decision #15 added: platform neutrality principle** — the rule that resolved Azure Spells, PQ Cover, and salvage; platform capabilities are universal + neutrally named, coin capabilities live on the coin's surface. (d) Azure Spells flagged for a coin-neutral rename (Fork Shield / Ward Mesh) since it's now confirmed platform-neutral. This is the biggest *simplification* in the spec's history: a whole subsystem and its hardest constraint both removed.

**Changelog v1.3 → v1.4:** WP0/§3c hardened from live chain data. (a) **§3a: the four STONE constants are filled** (version byte 63→`S`, Base58Check double-SHA256, bech32 HRP `stone` with legacy P2PKH canonical burn, Hash160) and the **domain-separator byte layout is fully locked** (tag byte + length-prefixed structured pair) — closing the concatenation-ambiguity risk. Smoke samples explicitly marked non-final. (b) **§3c: STEP_BLOCKS resolved to 350,640** (one *design*-year at STONE's ~90s target) after live data showed 52,560 ≈ 55 days, not a year. Anchored to the design clock deliberately, since the difficulty gate already handles a slow/thin network. STONE block-time and genesis-height notes added. (c) WP0 restated as **verifier-first**.

**Changelog v1.0 → v1.1:** (a) Made the separate-repo decision explicit throughout and **removed the `core/` prefix** — coins now live at `coins/<TICKER>/` at the *registry repo root*. `core/` was only ever meaningful inside the main Bloodstone codebase and its reuse here was an ambiguity trap. (b) Added **§3a — Burn-address generation build parameters** with the deterministic keyless-payload construction and the four chain constants the builder must supply.

**Changelog v1.1 → v1.2:** Added **§3b — Partial payments (cumulative-threshold burns)**. The watcher moves from exact-match to cumulative-sum-to-threshold against the per-draft burn address. Non-custodial, at the payer's own risk, no pooling of third-party funds, no refunds, no crowdfunding framing. Stall policy locked to **expiring draft + orphaned burns**. Watcher trigger in §2 and WP1 updated accordingly.

**Changelog v1.2 → v1.3:** (a) Added **§3c — Fee decay curve (maturity-based, oracle-free)**: height-stepped decay anchored to **STONE's post-genesis height** with a **STONE difficulty gate** and a permanent **100k floor**, frozen at draft-open. Corrects the clock after reviewing the LRGK/AZURE emission implementation — must NOT reuse child-coin eras or absolute-height indexing. (b) Locked **90-day draft window**, **minimum-first-burn to open a draft (10% of current requirement)**, and **open-draft/partial minimums as a percentage of the frozen requirement**. (c) Added **§7a — Salvage payout hard constraint** closing a money-pump risk in Goblin Magic's Scrap Smelt against the new floor. (d) Added **§12 — Spells & Magic surrounding systems**: retail naming (drop "Hex"→"Ward of Six"), and the operational consequences (Force Lance brake, Scrap Smelt cap, score-integrity).

**One-line description:** A burn-triggered automated launchpad for real minable PoW coins. A creator earns/buys STONE, permanently burns a fixed amount against a validated draft, and an automated pipeline provisions the coin's registry entry, on-chain-anchored payment receipt, and catalog listing — with no manual approval on the happy path.

**Naming note (read first):** This is *not* "fully autonomous" or "trustless." A payment watcher plus a bot with repo write access is neither. The correct public framing is **"burn-triggered automated launch."** Remaining trust (repo availability, honest provisioning) is *minimized* through deterministic parameters and reproducible builds, not eliminated. Do not market it as trustless.

---

## 1. Locked decisions (non-negotiable)

These were settled upstream. Do not reopen them in implementation.

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **100% burn. No treasury split.** | Narrative strength + zero custody obligation + no "operator collects fees for issuing coins" regulatory smell. |
| 2 | **Revenue comes from optional add-on services**, priced separately in STONE — not from the launch fee. | Keeps the launch trustless while funding ops. |
| 3 | **No exchange/trading monitoring anywhere.** | Requires an oracle. The burn itself is the only proof needed. |
| 4 | **No contribution/eligibility gate.** | You cannot burn 1M STONE without first acquiring it — the burn *is* the contribution proof. A gate can't verify trades without an oracle and perversely rewards dilutive mining over demand-creating buying. |
| 5 | **Validate BEFORE the burn, never after.** | Burns are irreversible. Draft → validate → commit → burn. |
| 6 | **Per-draft deterministic burn address is the commitment.** | The address *is* the binding to one spec. No OP_RETURN/datacarrier dependency. |
| 7 | **Deterministic derivation of salt/magic/ports from the burn txid.** | Collision-free, third-party-reproducible. |
| 8 | **Burn address must be provably unspendable, with published derivation.** | Otherwise "burn" is indistinguishable from "payment to the operator." This is the load-bearing trust element. |
| 9 | **Separate `bloodstone-fork-registry` repo — NOT the main Bloodstone repo — mirrored to Chain-Mesh. Coins live at `coins/<TICKER>/` at that repo's root (no `core/` prefix).** | Stops unbounded growth in the canonical codebase and contains the blast radius of an abusive/illegal submission. Chain-Mesh mirror keeps the sovereignty thesis intact. The `core/` prefix is dropped because it only meant something inside the main repo and reusing it here invites "which repo?" confusion. |
| 10 | **One MFQ binary + runtime registry. No per-coin rebuild.** | 200 coins ≠ 200 binary releases. |
| 11 | **Lifecycle ledger: keep (registry hygiene). Salvage: removed entirely from the platform.** | No platform payout, leaderboard, or graveyard. Salvage runs only as LRGK's off-platform canary (§7, §12.4). Superseded the earlier "salvage credits cut / cultural-only" position — now removed outright. |
| 12 | **Vitality score is a display metric, never a lever.** | A vitality-driven fee is gameable and makes launch cost non-deterministic. |
| 13 | **Manual txid reconciliation path is mandatory.** | Irreversible payments demand a human fallback when the watcher is down. |
| 14 | **All Fork Lab pricing is STONE-denominated in user-facing copy — fee, decay, promo. No USD figures.** Any nominal rate shown (e.g. "$0.0001") must be captioned "nominal reference only, not a live rate." | STONE trades on one thin venue (Cexius), so USD pricing needs a price oracle — the exact dependency the whole system refuses. Dollar-pricing also adds noise to the demand signal ("was the price too high, or did nobody see it?"). Fix the current page: the first-coin promo becomes **"200,000 STONE — first 10 only (normally 1,000,000)."** Drop the "$20"/"$100"/"$0.0001". |
| 15 | **Platform neutrality: platform-provided capabilities are universal and neutrally named (available to every fork); coin-provided capabilities belong to that coin and live on that coin's surface, not the platform's. The platform never favours specific coins. This rule cannot be overridden by adding a coin-specific payout, feature, or perk later.** | The launchpad's core promise is an equal plane. Resolved Azure Spells (→ neutral defense mesh, every fork), PQ Cover (→ platform-neutral, any fork strengthens it), and salvage (→ removed from platform; runs as LRGK's own off-platform canary). The test for any future feature: *is the platform giving this, or is a coin building it?* Platform → universal + neutral name. Coin → that coin's surface only. |

---

## 2. Canonical launch pipeline

```
EARN        Mine or buy ≥ launch fee in STONE (natural rate-limit; no gate)
   │
DRAFT       Free, off-chain. Creator submits name, ticker, block time, reward,
   │        premine, QUASAR flag. STONE creator address only — no GitHub login.
   │
VALIDATE    System checks ticker/name against rules + registry (see §4).
   │        Reads the current fee via §3c and FREEZES it for this draft.
   │        On pass: issues draft_id + a UNIQUE per-draft burn address.
   │        Name/ticker soft-reserved until the 90-day expiry deadline.
   │
BURN        Creator sends the frozen fee to that draft's burn address — in ONE tx
   │        or SEVERAL over 90 days (partial payments; see §3b). Must send the
   │        open-minimum (10% of frozen fee) within 48h or the draft lapses.
   │        Own risk, no refund.
   │
WATCH       Watcher sums confirmed UTXOs to the draft address (≥ N confs each).
   │        Fires when cumulative total ≥ frozen fee. Matches address → draft.
   │        If 90-day expiry passes before threshold: draft expires,
   │        name/ticker frees, already-burned STONE stays burned (orphaned).
   │
DERIVE      salt / magic / ports derived deterministically from the burn txid.
   │        Collision check vs registry; re-derive with counter on collision.
   │
PROVISION   Registry row: status provisioning → live.
   │        Write coins/<TICKER>/ artifacts (§5) in the separate registry repo.
   │        Append-only receipt.
   │
PUBLISH     T+0:  catalog API + daemon pack live immediately (discoverable/mineable)
   │        T+~24h: batched MFQ installer release train (Windows one-click)
   │
LIVE        Lifecycle ledger entry (live). Continuous state monitoring begins.
```

**Human intervention only for:** abuse, illegal/slur names, contested trademarks, chain attacks. Never on the happy path.

---

## 3. Burn address & commitment (the trust core)

- **Per-draft address.** Each validated draft gets its own burn address; the address itself binds the burn to exactly one spec. No memo parsing required.
- **Provably unspendable.** Use a construction with no known private-key preimage. **Publish the derivation method and let any third party independently verify no key exists.** This must ship before anything else is credible.
- **Deterministic network params.** After confirmation, derive `network_salt`, `magic`, `p2p_port`, `rpc_port` deterministically from the burn `txid` (e.g. domain-separated hash → mapped into a safe high port range). Publish the derivation so anyone can reproduce a coin's manifest from its txid alone.
- **Reconciliation.** If the watcher misses confirmed burns, the creator can submit the draft (or any of its burn txids) on the site and be reconciled into the same pipeline. Idempotent on the **draft/address**, not a single txid: one live coin per draft, ever, regardless of how many burn txs funded it.

---

## 3a. Burn-address generation — build parameters

A burn address is defined by the **absence** of a spendable key, not by a spec. The build task is to construct addresses that (a) any wallet will *send to* as valid, and (b) no one can *spend from*, provably by inspection.

### Chosen construction: deterministic keyless-payload family

Each burn address is a normal P2PKH-format address whose 20-byte payload is a **hash output — never `Hash160(pubkey)`.** Because no one can invert the hash to a pubkey that produces that payload, the coins are permanently frozen. Because the per-draft variant folds in `draft_id`, each is unique and reproducible by anyone.

### The four STONE constants — FILLED (from chainparams.cpp mainnet)

| # | Constant | STONE mainnet value |
|---|----------|---------------------|
| 1 | **P2PKH version byte** | **63 (0x3f)** → addresses lead with `S`. *(Proven empirically on the smoke path — all generated samples round-tripped as valid `S…`; the WP0 verifier must re-confirm this, not assume it.)* |
| 2 | **Checksum** | Standard Base58Check = **double-SHA256, first 4 bytes** of `version‖payload`. |
| 3 | **Bech32/segwit** | Enabled, HRP `stone` (`stone1…`). **Canonical burn uses legacy P2PKH (`S…`)** so every wallet send-path works. |
| 4 | **Address hash H** | **Hash160 = RIPEMD160(SHA256(x))** → 20 bytes. |

### LOCKED byte layout (deriver and verifier MUST match exactly)

Raw `DOMAIN_SEP ‖ draft_id` is underspecified — variable-length fields can collide across the boundary. The commitment scheme uses a tag byte + length-prefixed structured pair:

```
DOMAIN_SEP = UTF-8 of exactly "bloodstone/fork-lab/burn/v1"
             (fixed; never truncated or version-appended without a NEW DOMAIN_SEP)

tag        = 0x01  # canonical global burn (no draft)
           | 0x02  # per-draft burn

material   = tag
           || u32be(len(DOMAIN_SEP)) || DOMAIN_SEP
           || [ if tag==0x02:  u32be(len(draft_id_utf8)) || draft_id_utf8 ]

payload_20 = Hash160(material)                       # RIPEMD160(SHA256(material))
burn_addr  = Base58Check(version=63, payload_20)     # checksum = SHA256d(version||payload)[:4]
```

Rules (locked):
- `draft_id` is UTF-8; the length prefix is the only boundary (no NUL games).
- Canonical address uses tag `0x01` only (no empty draft field). Per-draft uses `0x02` + length-prefixed `draft_id`.
- Changing `DOMAIN_SEP` or any tag byte = a **new scheme version** (new domain string), never a silent tweak.
- Deriver and verifier that disagree on this layout = invalid. One implementation of `material()`, shared.

**Smoke samples are NOT final vectors.** Earlier samples (`ScTQ4vuj…`, `SaVP5mNi…`) used naive concatenation and only proved "S + Hash160 + Base58Check round-trips." Production canonical + sample-draft addresses are **regenerated under the locked layout** in the WP0 deliverable.

### WP0 deliverables (verifier-first — this section = WP0 scope)

The verifier is the load-bearing artifact. Anyone can mint an `S…` string; credibility is a third party proving keylessness with no access to your infra.

| Deliverable | Role |
|-------------|------|
| `verify_burn_address(addr, [draft_id], canonical) -> ok/fail + proof` | **The credibility anchor.** Recomputes `material` under the locked layout, confirms `decode(addr).payload == Hash160(material)`, hence payload is a hash commitment, not `Hash160(pubkey)`. |
| `derive_burn_address(...)` | Convenience (we use it; so can others). |
| Canonical address + derivation shown in the open | Eyeball trust anchor. |
| Verifier + canonical addr + short doc, **same commit/package** | Trust demonstrated, not asserted. |

The verifier must print at least: version byte, payload hex, recomputed `material` hex, Hash160 match, Base58Check OK, and the keyless rationale; exit non-zero on mismatch. No portal/DB dependency — runnable standalone.

### Guardrails

- **Never** derive a burn payload from `HASH160(pubkey)` — that would be a spendable address.
- **Never** store or generate a private key "for" a burn address. There isn't one; the absence is the point.
- Keep `DOMAIN_SEP` and the derivation fully public. Secrecy here would defeat verifiability.
- The canonical burn address must be reproducible by a third party from published inputs alone.

---

## 3b. Partial payments (cumulative-threshold burns)

The fee may be paid in **one transaction or several over time**, accumulating against the draft's burn address until the threshold is met. This is **non-custodial and at the payer's own risk**: it is a single creator funding their own launch in installments, not crowdfunding, not pooling of third-party money, and there are **no refunds** (burns have no key — see §3a).

### Watcher logic

- **Cumulative sum, not exact match.** The watcher sums all confirmed UTXOs sent to the draft's burn address (each with ≥ N confirmations) and fires provisioning when `cumulative_total ≥ fee`.
- **Track the address balance, never a payer ledger.** Bind on the *draft's address total* only — do not attempt to identify or track individual payers. On UTXO, "same payer" is fuzzy (multiple input addresses, change outputs); the per-draft address is already the binding. This also neutralizes dust-griefing: a stranger sending dust merely adds to the total and can never corrupt a per-contributor count, because there is no such count.
- **Overpayment** beyond the threshold is burned like the rest — no change is returned (no key to return it from). The UI must warn against overpaying.

### Stall policy — LOCKED: expiring draft + orphaned burns

- Each draft carries a **90-day expiry deadline** set at validation, and a frozen fee requirement (§3c).
- **Minimum first burn to open:** the creator must send at least **10% of the frozen requirement** to the draft address within **48h** of validation, or the draft lapses and the name frees. This stops popular tickers being reserved for 90 days on zero skin-in.
- If the cumulative total has **not** reached the frozen requirement by the 90-day expiry: the **draft expires**, its **name/ticker reservation is released**, and any STONE already sent to that address **remains permanently burned — orphaned, unrecoverable, no coin created.**
- This keeps the registry clean and matches the non-custodial "your risk" framing. Its harshness is deliberate and must be disclosed relentlessly (below).

### Mandatory disclosure (this is what makes "own risk" hold)

The irreversibility must be stated **at the moment of each send**, not buried in a ToS:

> "**X of [frozen requirement] STONE burned toward <TICKER>. This is permanent.** If this draft is not fully funded by <EXPIRY>, this STONE is gone, the name is released, and no coin is created. Burns cannot be refunded."

Show, at all times on the draft page: **frozen requirement**, **confirmed total**, **remaining to threshold**, **90-day expiry countdown**, and the **burn address with its §3a verification link**.

### Explicitly still out of scope (unchanged from prior decisions)

- No escrow, no keyed holding address, no refunds — that would reintroduce custody and the managed-investment-scheme profile.
- No pooling framed as community crowdfunding, no contributor rewards, no profit expectation. If the product ever moves toward pooled third-party contributions expecting a token back, that requires securities advice **before** implementation (same pattern flagged in the Klingex evaluation).

---

## 3c. Fee decay curve (maturity-based, oracle-free)

**Problem being solved:** a fee fixed in STONE floats in real cost. If STONE appreciates (which the burn is designed to cause), a flat 1M fee eventually prices out all launches. The fix decays the *requirement* as the **network matures**, using on-chain maturity signals — **never price, never an oracle.**

### The clock is STONE's, not the child coin's — this is critical

Reviewing the live LRGK/AZURE emission implementation surfaced three traps. The curve below avoids all three:

1. **Do NOT use the child coin's emission eras.** Child intervals are wildly inconsistent (LRGK 1,054,080 vs AZURE 9,000 — ~117×). A per-child clock makes the launch fee decay at incomparable rates. The launch fee must decay with the **parent (STONE)** maturing — one consistent clock for all creators. (Also: the coin doesn't exist yet at draft time, so it has no height.)
2. **Do NOT use absolute-height era indexing.** The live code's `halvings = h // interval` skips era 0 on short intervals (AZURE shows era 1 at genesis). Use **post-genesis elapsed height**: `steps = (stone_height - stone_genesis_height) // STEP_BLOCKS`.
3. **Do NOT mirror subsidy shape.** After era 4 the child curves switch to an *inflationary* SpaceXpanse tail (`pow(1.02956, …)`) — mirroring it would make the fee eventually *rise*. The fee curve is its own monotonic step-decay to a hard floor, independent of subsidy.

### The curve (portal-layer function — NOT consensus)

```
requirement(stone_height, stone_diff) =
    steps      = max(0, (stone_height - STONE_GENESIS_HEIGHT) // STEP_BLOCKS)
    scheduled  = max(FLOOR, START * (DECAY ** steps))
    # difficulty gate: a downward step only "unlocks" once STONE difficulty
    # has crossed that step's threshold; else hold at the prior step's value
    gated      = max(scheduled, gate_hold(steps, stone_diff))
    return round_to_unit(gated)
```

- `START = 1,000,000 STONE`
- `DECAY = 0.90` per step (locked; gentler curve, ~10% requirement drop per unlocked step)
- `FLOOR = 100,000 STONE` (permanent minimum; never zero)
- `STEP_BLOCKS = 350,640` — **one *design*-year at STONE's ~90s target spacing** (≈ 394,470/yr rounded to the step; see clock note below). One consistent cadence for all creators.
- `STONE_GENESIS_HEIGHT = 0` (confirm against the node — assumed 0).
- **Difficulty gate:** each scheduled downward step is withheld until STONE's difficulty has crossed that step's threshold — suggested `hold step n until diff ≥ genesis_diff × 2^n` (or a log schedule), rate-capped to **1 step-unlock per epoch**. So a chain that advances height on wall-clock alone (few miners, weak network) does *not* get cheaper launches. This is the load-bearing clamp.

**Clock note (why 350,640, not 52,560):** live STONE data at height ~17,754 shows ~90s *design* spacing but ~240–280s *empirical* pace (thin neoscrypt/yespower). 52,560 blocks ≈ 55 days at design / ~158 days at live — **not** a year. STEP_BLOCKS is anchored to the **design clock deliberately**: the difficulty gate already absorbs a slow/thin network, so height sets the *schedule* and difficulty sets the *permission*. Anchoring the step to empirical (slow) pace would double-count the network's weakness. Practical consequence to expect: early on, height will cross step boundaries while the gate holds the fee at 1M — that is the clamp working, not a bug. At height ~17,754 the chain is a fraction into step 0, so the requirement is the full 1M START today, which is correct for a ~58-day-old chain.

### Freeze-at-draft (interacts with §3b — do not skip)

The requirement is **read once, at draft validation, and frozen for that draft's entire life.** Do not recompute mid-draft as STONE height advances — a 90-day partial-payment draft (§3b) must have a fixed target its payers are aiming at. The frozen number is written into the draft record and every disclosure ("X of [frozen target]").

### Parameter interaction with §3b (locked)

- **Draft window: 90 days.**
- **Minimum first burn to OPEN a draft: 10% of the frozen requirement** (not a fixed 100k). Percentage, so it scales down with the decay and never collapses the installment path — at floor that's 10k to open, leaving 90k to fund, preserving §3b installments at every fee level.
- This pairing was deliberate: a fixed 100k open-minimum would equal the floor and silently kill partial payments at the low end. Percentage avoids the collision.

### What to avoid (from the emission review)

- No difficulty-only curve without the height schedule (multipools swing difficulty).
- No external price oracle (Cexius is a single thin feed — dangerous).
- No every-block recompute with no floor (confusing UX, and breaks freeze-at-draft).
- This function lives at the **portal/registry layer** (like the emission *dashboard* replica) — it must never touch `GetBlockSubsidy` or require a node rebuild.

---

## 4. Validation rules (pre-burn)

Fold in from the drafts, tightened:

- **Ticker:** 3–8 uppercase A–Z. Must be unique vs the live registry.
- **Name:** 3–20 alphanumeric. Must be unique.
- **Reserved blocklist:** `BLOODSTONE`, `STONE`, `ROD`, `BTC`, `ADMIN`, `TEST`, and a maintained list of core/protocol terms + obvious abuse strings.
- **Params in range:** block time, reward, premine within policy bounds (reuse existing premine policy).
- **Uniqueness is checked against the registry, not just the repo directory**, to avoid race conditions between concurrent drafts.
- **Natural rate limit:** the burn cost is the anti-spam mechanism. An optional per-address cooldown is cheap insurance but not required.

---

## 5. Repo artifacts

Layout at the **root of the separate `bloodstone-fork-registry` repo** (mirrored to Chain-Mesh). Note: no `core/` prefix — this is not the main Bloodstone repo.

```
bloodstone-fork-registry/          # separate repo, mirrored to Chain-Mesh
  coins/
    <TICKER>/
      PAYMENT.json     # immutable, append-only, never rewritten
      COIN.json        # technical params + disclosures
      conf/<ticker>.conf.example
      README.md
      icon.png         # optional, set/changed later via manage token
```

**PAYMENT.json** (immutable receipt — supports single or partial payments):
```json
{
  "schema": "bloodstone/fork-lab-payment/v2",
  "burn_address": "…",
  "amount_stone_required": "1000000",
  "amount_stone_total": "1000000",
  "burn_txs": [
    { "txid": "…", "amount_stone": "400000", "confirmed_height": 17702 },
    { "txid": "…", "amount_stone": "600000", "confirmed_height": 17765 }
  ],
  "creator_address": "S…",
  "ticker": "FOO",
  "draft_id": "…",
  "threshold_met_height": 17765,
  "created_utc": "…"
}
```
For a single-payment launch, `burn_txs` simply has one entry. The receipt records every burn tx that counted toward the threshold.

**COIN.json** (technical params + transparency):
```json
{
  "schema": "bloodstone/fork-lab-coin/v1",
  "ticker": "FOO",
  "name": "…",
  "genesis": "…",
  "magic": "…",
  "p2p_port": 0,
  "rpc_port": 0,
  "network_salt": "…",
  "auxpow_parent": "STONE-SHA256d",
  "block_time_s": 90,
  "reward": "…",
  "premine": { "amount": "…", "address": "…", "vesting": "…" },
  "quasar_enabled": false
}
```

**Rules:**
- PAYMENT.json is written once and never modified.
- **Premine, if any, is disclosed in COIN.json.** No hidden allocations.
- **Never commit secrets to the repo.** (Note: MFQ is the wallet *application* — a release *includes* the coin; there is no per-coin keypair or seed generated, so there is nothing sensitive to leak here. This guardrail is stated only to prevent a future implementer from reintroducing one.)

---

## 6. MFQ delivery (two-speed)

**MFQ = Multi-Fork Qt wallet application.** A release *includes* a coin in its dropdown; it is not a keypair.

- **T+0 — instant, no rebuild:** the new coin is written to the runtime **catalog API** and its **daemon pack** (`<TICKER>-win64.zip`) is published. The single MFQ binary reads the catalog at runtime, so the coin appears in the dropdown and is mineable immediately.
- **T+~24h — batched:** an MFQ installer release train (`bloodstone-multi-fork-qt-0.2.x`) bundles recent daemon packs so Windows users get a one-click installer.
- **Rebuild the MFQ binary only when the *wallet code* changes** — never per coin.
- Offline single-coin compilation via the existing Fork Builder remains available and unchanged.

**Public promise:** "Launch triggers catalog + daemon pack immediately; the MFQ installer train tags within ~24h." Do **not** promise a full Qt rebuild per coin.

---

## 7. Lifecycle tracking (no platform salvage)

- **Lifecycle ledger:** append-only, tip-hash anchored. States: `live → declining → inactive`. Tracked by probing known RPC endpoints. This is **registry hygiene only** — it stops the registry/MFQ catalog claiming dead coins are live. It is not a graveyard, a salvage board, or a cultural surface.
- **No platform salvage. No salvage payout. No salvage leaderboard.** Salvage in every form is removed from Bloodstone/Fork Lab. There is no economic credit, no status/badge system, no public salvage board, and no money-pump surface — because there is nothing to pump. (This deletes the former §7a constraint entirely; with no payout, no constraint is needed.)
- **Goblin Magic is not a platform feature.** Salvage/graveyard is being run as **LRGK's own canary experiment on LRGK's own surface**, off the Fork Lab launchpad. It must not appear in Fork Lab's "what you get" framing, APIs, or pages. See §12.
- **Vitality score:** if kept at all, it is a display-only metric of active-fork/core-chain health — **no salvage input**, drives nothing.

---

## 8. Add-on services (the revenue line)

Launch stays 100% burn; money comes from optional convenience services, priced in STONE to treasury.

- **Model:** master-account **aggregator** on a crypto-tolerant host (Hivelocity / Latitude.sh / Servers.com / BuyVM class) — not Hetzner or Vultr, whose AUPs ban crypto node/mining workloads and can take down every customer in one enforcement action. Deploy your golden Fork-Lab-node image via the host API; bill customers yourself.
- **Why aggregator over white-label reseller:** the product isn't "a VPS," it's a pre-configured Fork Lab node. The value is the golden image + coin-specific boot config, not panel branding.
- **Pricing guardrails on the ~$10→$49–99 spread:**
  - **Cap disk explicitly per tier and price overage.** Chains grow monotonically — this is the margin killer. Ship a pruning default in the image.
  - Budget for support load: one 30-min ticket/month against a $49 plan is real margin.
- **Positioning:** a convenience tier for people who won't run hardware — **never** the recommended path. Must reconcile with the "compile offline / sovereign" thesis: the customer funds their own instance; you never host their chain data on the registry VPS.
- **Before committing to any host:** get their AUP position **in writing** in a support ticket using the phrase "full node, no mining." A sales verbal is worthless when automated I/O monitoring flags you months later.

---

## 9. Explicitly out of scope (considered and rejected)

- Liquidity-injector / DEX-pairing of the fee — breaks pure burn; needs a DEX/contract.
- Any burn/treasury split (50/50 or otherwise) — breaks the locked 100%-burn narrative.
- Bond-with-slashing — needs an oracle/governance to judge "malicious."
- Contribution/eligibility gate (mining shares, exchange-volume fingerprint) — cut; unverifiable without an oracle; the burn is the proof.
- OP_RETURN carrying ticker/username — superseded by the per-draft burn address.
- Tiered ladder (Spark/Forge/Empire) — scope creep ahead of demand; park for post-traction.
- Seasonal events / bonus multipliers — park.
- Writing forks into the main Bloodstone repo — replaced by the separate registry repo.
- Per-coin MFQ binary rebuilds — replaced by runtime catalog.

---

## 10. Build phasing (work packages for quoting)

**WP0 — Burn address credibility (do first, blocks everything). Verifier-first.**
Implement the §3a locked byte layout once (shared `material()`). Ship, in one package/commit: `verify_burn_address` (the credibility anchor — proves keylessness standalone, no infra), `derive_burn_address`, the regenerated canonical burn address + one sample-draft address under the locked layout, and a short MD on downloads. Verifier must re-confirm all-`S` under version 63 empirically. No portal/DB dependency.

**WP1 — Watcher + draft/validate + receipt (first vertical slice).**
Draft & validation service (§4) with a **90-day expiry** and **frozen fee read from §3c** per draft → per-draft burn address → **cumulative-threshold** payment watcher (§3b: sums confirmed UTXOs ≥ N confs, fires at total ≥ frozen fee, 48h open-minimum, expires + orphans on deadline miss) → registry DB row (provisioning→live) → PAYMENT.json (v2) + COIN.json artifacts + seed-registry stub + MFQ daemon-pack queue. Per-send irreversibility disclosure UI (§3b). Manual reconciliation path. GitHub repo automation can be stubbed here.

**WP1.5 — Fee decay curve.**
Portal-layer `requirement(stone_height, stone_diff)` per §3c: STONE-height stepped decay, difficulty gate, 100k floor, freeze-at-draft. Not consensus, no rebuild. (No salvage-ceiling gate — salvage is removed from the platform; the decay curve no longer depends on any salvage check.)

**WP2 — Catalog + MFQ two-speed delivery.**
Runtime catalog API; T+0 daemon pack publish; batched MFQ installer release train.

**WP3 — Repo provisioning bot.**
Automated `coins/<TICKER>/` creation at the root of the separate `bloodstone-fork-registry` repo + Chain-Mesh mirror. (Provision manually until coin volume justifies this.)

**WP4 — Lifecycle ledger + vitality dashboard.**
Append-only ledger (live → declining → inactive), RPC state probing for registry hygiene, optional vitality metric (display only, no salvage input). No salvage board — salvage is removed from the platform (§7, §12.4).

**WP5 — Add-on services.**
Aggregator host integration, golden image, disk-capped tiers, billing.

---

## 11. Open decisions still needing your call

Most parameters are now set with defaults. What remains is confirmation, not design:

1. **Confirm three node facts (quick):** `STONE_GENESIS_HEIGHT = 0`, the WP0 verifier reproduces all-`S` addresses under version 63, and the empirical STONE difficulty value to seed `genesis_diff` in the gate.
2. **Confirmation depth N.** Suggested **6**, or **12** for conservative reorg margin under QUASAR. Pick one.
3. **Demand-first gate (the real one):** 2 live coins, both free-code, discounted slots unclaimed. Before WP1, the priority remains **sell the discounted slots** — a rail without demand is ahead of product-market fit.

**Closed:** salvage — removed from the platform entirely; runs as LRGK's own off-platform canary (§7, §12.4). The former §7a money-pump constraint and farm-lock classifier are dropped with it (no platform payout to bound).

**Resolved in v1.4:** DECAY → 0.90 · STEP_BLOCKS → 350,640 (design-year) · §3a constants filled + byte layout locked · smoke samples marked non-final.
**Resolved earlier:** fee START → 1M with §3c decay · floor → 100k · draft window → 90 days · open-minimum → 10% of frozen fee within 48h · naming → Ward of Six / Cursed Auction.

---

## 12. Surrounding systems: Azure Spells & Goblin Magic

These are pre-existing systems that sit *around* the chain (pool / portal / witnesses), not consensus. They interact with Fork Lab and carry both a naming decision and real operational consequences.

### 12.1 Retail naming (LOCKED)

Drop occult/curse framing that reads badly next to FSP-registered finance and misreads as harm for a defense system. Keep the grimoire flavour.

**Defense layer only — Goblin Magic is no longer a platform system (see 12.4).**

| Layer | Old | New (locked) |
|-------|-----|-------------|
| Defense family | Azure Spells | **Azure Spells** (unchanged) |
| Collective | the Hex of Six | **the Ward of Six** (aka the Six Wards) |
| Rite V (LRGK only) | Damned Auction | **Cursed Auction** *(LRGK's surface, not Fork Lab's)* |

- **Six Wards (unchanged names):** Force Shield · Force Lance · Aegis Mirror · Chrono Bastion · Null Ward · Oathstone.
- **Neutrality note:** "Azure Spells" reads as AZURE-owned, but the defense mesh is a **platform-neutral** capability every fork benefits from (per Locked Decision #15). Prefer a coin-neutral public name (e.g. **Fork Shield / Ward Mesh**); AZURE is "first coin in the mesh," not its owner.
- **One-liner:** *Azure Spells — the Ward of Six.* (Goblin Magic is no longer paired here — it's LRGK's own thing.)
- Replace "Hex"/"Hex of Six" everywhere: grimoire pages, API labels, status tiers, operator docs, downloads. The API *paths* can stay for compatibility, but user-facing strings change.

### 12.2 Operational consequences (must be handled)

**A — Force Lance needs a brake (highest priority).** It is the only *active* ward: it raises SHA256d share difficulty and can freeze anomalous weight on tripwire. Two live risks: (1) false positives punish honest miners (a legitimate new-pool hashrate spike looks like a rental flood); (2) over-eager throttling on the SHA256d lane **degrades the mandatory STONE merge-mining that Fork Lab economics depend on**. Requirements: a documented, published trigger threshold; a rate cap on how aggressively it can raise difficulty; and a **manual override / human brake**. An automated economic-penalty system with no off-switch generates disputes and, for an FSP operator, scrutiny. Containment "pool policy only, ASIC wire format unchanged" is correct — keep it.

**B — Score integrity.** The wards expose live status APIs (protection tier, etc.). Because these are *marketed as protection*, a status that claims full strength while a ward is stale or a sister tip is down is a verifiable false claim on a security system. Requirement: every published tier/score must be computed from **real liveness**, with a stale/degraded state shown honestly — never a default "healthy".

### 12.3 Scope note

Six wards + live APIs + grimoire pages is significant surface area around a launchpad with 2 live coins and unclaimed discount slots. The defense lore is a genuine differentiator — but it is **decoration until there is launch volume to protect**, and every ward is something that can display "down". Prioritise WP0 (burn-address credibility), the §3c curve, and the Force-Lance brake; treat ward expansion as post-traction. This is the scope-expansion pattern to keep counterbalanced.

### 12.4 Salvage / Goblin Magic — REMOVED from platform (LRGK canary)

**Decision (locked):** Salvage is **removed entirely from Bloodstone/Fork Lab** — no payout (any coin), no leaderboard, no badges, no public graveyard, no farm-lock classifier. The only thing retained platform-side is bare lifecycle tracking for registry hygiene (§7).

**Goblin Magic now lives with LRGK as its own canary experiment**, on LRGK's own surface, off the launchpad. Rationale:
- **Neutrality:** a platform that salvages/pays around dead forks favours whichever coin it pays — moving it to LRGK's surface makes it a *coin-provided* capability (Locked Decision #15), not a platform one.
- **Attack surface:** with no platform payout, the burner-chain money-pump cannot exist platform-side — nothing to farm, nothing to cap, no §7a needed.
- **Canary value:** LRGK gets to test whether a status-only (or otherwise) salvage culture works, in isolation, without putting the platform's neutrality or the STONE settlement layer at risk.

**Build implication:** retire Scrap Smelt's LRGK-redeem path and any salvage payout from the platform; if LRGK continues it, it's on LRGK's pages/APIs and must not be surfaced in Fork Lab framing, catalog, or docs. The former §7a constraint and the farm-lock classifier are both dropped — there is no platform payout to bound.

---

*Bloodstone Fork Lab Build Specification / RFQ · v1.5 (frozen) · canonical.*
