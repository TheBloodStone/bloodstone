# Bloodstone monorepo — auditor map

**Problem this solves:** the monorepo is a large multi-product tree. A single “file dump” review mixes chain core, Android miner, pool services, and small shell installers. Use **sections** below so you only open files for the surface under review.

**Last updated:** 2026-07-30 (Phase 1 transparency — GitHub-first policy + MFQ provenance + fork stubs)

---

## Official policy — GitHub first → VPS pull (supply-chain)

**Status:** official builder / auditor policy effective **2026-07-30**.

GitHub is the **source of truth** for code auditors and operators should trust. The build host (VPS) is a **build and deploy** machine, not the canonical repository.

### Required flow (code that ships)

```
1. Develop on a branch
2. Commit + push to GitHub (TheBloodStone/bloodstone or linked public repo)
3. Review / merge to main (or release branch) as required for the surface
4. VPS: git fetch + git pull (or checkout a pinned tag/commit)
5. Build from that tree
6. Publish artifacts + SHA256 (portal and/or GitHub Releases)
7. Manifest / downloads index must match published hashes
```

### Explicitly incomplete (do not treat as “done”)

| Anti-pattern | Why it fails trust |
|--------------|-------------------|
| Build only on VPS, never push | No durable, auditable source |
| Portal-only binary with no GitHub source commit | Integrity of zip ≠ provenance of code |
| `prepare-bloodstone-oss-repo.sh` snapshot as if it *defined* truth | Script may **export** a tree; it must not **replace** git history as authority |
| MFQ daemon pack without `provenance.source_commit` (after v2) | Cannot rebuild or pin what was built |

### VPS role (allowed)

- Pull pinned commits / tags
- Cross-compile (e.g. MinGW for Windows packs)
- Run production services
- Publish **hashes** and download links

### VPS role (not authority)

- Untracked `/root/...` trees as the only place full fork source exists
- Editing production code without a corresponding GitHub commit

### Publication helpers

| Path | Role |
|------|------|
| [`prepare-bloodstone-oss-repo.sh`](prepare-bloodstone-oss-repo.sh) | Historical / opportunistic export into monorepo layout — **subordinate** to git; prefer commit-first workflow |
| Portal downloads | Distribution channel; verify with SHA256 + (v2) provenance |
| Branch `release-downloads` | Binary mirror — not source of installer/consensus logic |

### Future (not claimed complete yet)

- **Phase 1 (now):** GitHub-first policy, MFQ manifest v2 provenance schema, fork path stubs, public roadmap cards
- **Phase 1 CI (next):** GitHub Actions that **verify** portal SHA256s match `manifest.json` (and later PGP)
- **Phase 2:** Deterministic Guix/Gitian/MinGW builds in CI — do not block Phase 1 on this

---

## Section 1 — Linux node installer (Pi / headless)

**Start here for `bloodstone-node-*-linux-*.tar.gz` audits.**

| Path | Role |
|------|------|
| [`packages/linux-node/`](packages/linux-node/) | **Canonical installer scripts + conf template** |
| [`packages/linux-node/MANIFEST.md`](packages/linux-node/MANIFEST.md) | Exact file list for this surface |
| [`packages/linux-node/start-node.sh`](packages/linux-node/start-node.sh) | Conf, seeds, bootstrap hook, exec daemon |
| [`packages/linux-node/install-chain-bootstrap.sh`](packages/linux-node/install-chain-bootstrap.sh) | Download / SHA256 / safe tar extract |
| [`packages/linux-node/bloodstone.conf.example`](packages/linux-node/bloodstone.conf.example) | Default ports, RPC bind, seeds |

**Security remediation notes:** `docs/Bloodstone-Node-0.7.6-Security-Audit-Remediation.md` (also on downloads).

**Not this section:** `ops/bloodstone-stratum*`, `miner-android/`, pool dashboards.

---

## Section 2 — Chain core (Bloodstone parent daemon)

| Path | Role |
|------|------|
| `core/` and/or `chain/` | C++ node (`bloodstoned`, CLI, consensus) |

Build produces the `bin/` files that packagers drop into the tarball. Separate from shell installer logic.

**AuxPoW parent chain id (STONE):** `1899`

---

## Section 2b — Ecosystem fork source trees (LRGK, AZURE, future)

**Layout target (monorepo):**

| Path | Coin | AuxPoW chain id | Status |
|------|------|-----------------|--------|
| [`forks/lrgk/`](forks/lrgk/) | LRGK | **1900** | **Stub** — full core not yet landed (see README) |
| [`forks/azure/`](forks/azure/) | AZURE | **1901** | **Stub** — full core not yet landed (see README) |
| `forks/<ticker>/` | Future | ≥ **1902** (registry) | Allocate via `auxpow_chain_ids` / operator registry |

**Policy:** Prefer these monorepo paths over separate repos unless a fork’s build world truly diverges. If separate, MFQ manifest `provenance` must still pin `source_repo` + `source_commit`.

**Do not** treat operator-only VPS trees as the long-term audit surface. Landing full trees is a tracked roadmap item; stubs lock **paths and identity** first.

---

## Section 2c — Multi-Fork Qt (MFQ) wallet + daemon packs

| Path | Role |
|------|------|
| [`multi-fork-qt/`](multi-fork-qt/) | MFQ Python/PyQt orchestrator + UI (public audit) |
| [`multi-fork-qt/AUDIT.md`](multi-fork-qt/AUDIT.md) | Wallet-focused audit entry |
| [`docs/mfq-daemons-manifest-v2.md`](docs/mfq-daemons-manifest-v2.md) | **Manifest schema v2** (provenance required) |
| [`ops/build-mfq-fork-daemons.sh`](ops/build-mfq-fork-daemons.sh) | Pack build entry (`--coin`); unified script target |
| Portal | `https://bloodstone.rocks/downloads/mfq-daemons/manifest.json` |

**Daemon packs (win64 today):** SHA256 in manifest; v2 adds `provenance` (`source_repo`, `source_path`, `source_commit`, `build_script`, `built_utc`) and `auxpow_chain_id`.

Until `source_commit` is a real monorepo SHA (not `PENDING_*`), treat packs as **integrity-verified binaries** with **incomplete source provenance**.

---

## Section 3 — Pi fleet / Blurt convergence installer

| Path | Role |
|------|------|
| `ops/bloodstone-pi-fleet/` | Fleet setup scripts |
| `docs/Blurt-Pi-Fleet-*` | Operator docs |

Different product from the single-node `linux-node` tarball.

---

## Section 4 — Android miner

| Path | Role |
|------|------|
| `miner-android/` | Capacitor APK |
| `miner-web/` | Pool API + OTA web UI |

---

## Section 5 — Public web / portal

| Path | Role |
|------|------|
| `portal/` | bloodstone.rocks / mytunnel portal |
| `downloads/` | Downloads page template only |
| `explorer/`, `faucet/`, `dex/`, `support/` | Ancillary sites |

---

## Section 6 — VPS pool ops (large flat dump)

| Path | Role |
|------|------|
| `ops/*.py`, `ops/*.sh` (except pi-fleet) | Stratum, watchdogs, publish helpers, QUASAR, federation |

**Do not treat this whole directory as “the installer.”** Only `packages/linux-node/` ships inside the Linux node tarball.

---

## Section 7 — GitHub binary mirror

| Location | Role |
|----------|------|
| Branch `release-downloads` | APKs, tarballs, docs for download links |
| Not source of installer logic | Audit scripts in **Section 1**, not every binary on the branch |

---

## Section 8 — Transparency / supply-chain roadmap

| Path | Role |
|------|------|
| [`docs/Bloodstone-Ecosystem-Transparency-Roadmap.md`](docs/Bloodstone-Ecosystem-Transparency-Roadmap.md) | Phase cards (GitHub Project mirror until org Project is live) |

---

## Quick filter

| If you are reviewing… | Open only… |
|------------------------|------------|
| Node tarball shell security | **Section 1** |
| Consensus / RPC daemon (STONE) | **Section 2** |
| LRGK / AZURE fork source paths | **Section 2b** |
| MFQ wallet / daemon pack provenance | **Section 2c** |
| Pi multi-service fleet | **Section 3** |
| Phone miner | **Section 4** |
| Website | **Section 5** |
| Pool infrastructure | **Section 6** |
| GitHub-first policy / CI plans | **Policy section** + **Section 8** |
