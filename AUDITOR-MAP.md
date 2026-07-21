# Bloodstone monorepo — auditor map

**Problem this solves:** the monorepo is a large multi-product tree. A single “file dump” review mixes chain core, Android miner, pool services, and small shell installers. Use **sections** below so you only open files for the surface under review.

---

## Section 1 — Linux node installer (Pi / headless)

**Start here for `bloodstone-node-0.7.6-linux-aarch64.tar.gz` audits.**

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

## Section 2 — Chain core (daemon binary)

| Path | Role |
|------|------|
| `core/` | C++ node (`bloodstoned`, CLI, consensus) |

Build produces the `bin/` files that packagers drop into the tarball. Separate from shell installer logic.

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

## Quick filter

| If you are reviewing… | Open only… |
|------------------------|------------|
| Node tarball shell security | **Section 1** |
| Consensus / RPC daemon | **Section 2** |
| Pi multi-service fleet | **Section 3** |
| Phone miner | **Section 4** |
| Website | **Section 5** |
| Pool infrastructure | **Section 6** |
