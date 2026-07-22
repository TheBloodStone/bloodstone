# Linux node installer package (headless)

**What auditors should read first.** This directory is the **only** place that defines the scripts shipped inside:

- `bloodstone-node-*-linux-x86_64.tar.gz`
- `bloodstone-node-*-linux-aarch64.tar.gz` (Raspberry Pi / ARM64)

Everything else in the monorepo (portal, Android miner, stratum, fleet, etc.) is **not** in the tarball unless explicitly listed below.

---

## Two install paths (DeepSeek / transparency)

| Path | Who it’s for | Trust model |
|------|----------------|-------------|
| **A. Prebuilt tarball** | Most operators (fast) | Trust published binary + **SHA-256** (optional PGP when `.asc` present) |
| **B. From source** | Maximum transparency | You **clone** `https://github.com/TheBloodStone/bloodstone` and **compile** `bloodstoned` on your machine |

### A — Prebuilt (convenience)

```bash
# Download (example ARM64)
curl -fsSLO https://bloodstone.rocks/downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz
curl -fsSLO https://bloodstone.rocks/downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz.sha256

# Verify checksum (and PGP if a .asc file exists)
./verify-release.sh bloodstone-node-0.7.6-linux-aarch64.tar.gz

tar -xzf bloodstone-node-0.7.6-linux-aarch64.tar.gz
cd bloodstone-node-0.7.6-linux-aarch64
./start-node.sh
```

### B — From source (see the open-source repo pulled and built)

```bash
# From a git checkout of this monorepo:
cd packages/linux-node
./install-from-source.sh

# Wait until install-from-source finishes successfully (creates bin/bloodstoned).
# Then (stay in packages/linux-node — do not cd into a missing subfolder):
./start-node.sh
```


**If you see** `No core/ under 'HEAD is now at…'` or similar — that was git/log stdout captured into the source path (fixed on latest `main`). Pull again and re-run `./install-from-source.sh`. Diverged work clones under `~/bloodstone-src-build` are hard-reset to `origin/<ref>`.

**If you see** `bin/bloodstoned: No such file or directory` — the compile/install step did not finish (or failed). `start-node.sh` does **not** build the node; run `./install-from-source.sh` again and confirm `ls -la bin/bloodstoned` before starting. On a Pi this can take hours.

`install-from-source.sh` installs `bin/bloodstoned` (and CLI) **into this package directory** by default, next to the existing `start-node.sh`. There is **no** `bloodstone-node-from-source-linux-aarch64` (or `…-x86_64`) folder unless you set one yourself:

```bash
PREFIX=$HOME/bloodstone-node ./install-from-source.sh
cd $HOME/bloodstone-node && ./start-node.sh
```

What you will see:

1. `git clone https://github.com/TheBloodStone/bloodstone` (or update an existing clone)  
2. `./autogen.sh` / `./configure` / `make` in `core/`  
3. Binaries installed next to `start-node.sh` (default: `packages/linux-node/bin/`)  
4. `BUILD-PROVENANCE.txt` / `BUILD-INFO.txt` with **git commit + daemon SHA-256**

On a Raspberry Pi this can take **hours**. Use path A if you need the node up quickly; use B when you want to watch/trust the compile.

---

## RPC credentials (production)

| Fact | Detail |
|------|--------|
| Default in **example** conf | `rpcpassword=CHANGE_ME` (template only) |
| What `start-node.sh` does | Generates a **random** `rpcpassword` on first run and sets conf to mode **`600`** |
| Before production / shared hosts | Confirm `~/.bloodstone/bloodstone.conf` is not world-readable; change `rpcuser`/`rpcpassword` if you exposed RPC |

Do **not** expose RPC to the internet without a firewall and strong credentials.

---

## PGP signatures (release authenticity)

| Item | Detail |
|------|--------|
| **Public key** | [`bloodstone-release-key.asc`](bloodstone-release-key.asc) — also https://bloodstone.rocks/downloads/bloodstone-release-key.asc |
| **Fingerprint** | `326795FA0B4E7C975276AB9FF6255B970D6642AD` |
| **What we sign** | The **`.sha256` checksum file** → produces **`.sha256.asc`** (Bitcoin-style) |
| **Verify** | `./verify-release.sh artifact.tar.gz` (PGP then SHA-256) |
| **Strict fleet** | `BLOODSTONE_REQUIRE_PGP=1 ./verify-release.sh …` |
| **Docs** | `docs/Bloodstone-PGP-Release-Signing.md` |

SHA-256 alone is not enough if the download server is compromised. PGP on the checksum closes that gap.

---

## Shipped files (tarball contents)

| File in package | Source in monorepo | Role |
|-----------------|--------------------|------|
| `bin/bloodstoned` | Built from `core/` (or your from-source build) | Full node daemon |
| `bin/bloodstone-cli` | Built from `core/` | RPC CLI |
| `start-node.sh` | **`packages/linux-node/start-node.sh`** | First-run conf + bootstrap + start (+ install log, no duplicate daemon) |
| `install-chain-bootstrap.sh` | **`packages/linux-node/install-chain-bootstrap.sh`** | Tip snapshot download/verify/extract |
| `install-from-source.sh` | **`packages/linux-node/install-from-source.sh`** | Clone monorepo + compile (default **immutable tag** `v0.7.6-h1`) |
| `verify-release.sh` | **`packages/linux-node/verify-release.sh`** | SHA-256 (+ optional PGP) check |
| `bloodstone-health.sh` | **`packages/linux-node/bloodstone-health.sh`** | Health: daemon, RPC, peers, disk, bootstrap |
| `bloodstone-node.service` | **`packages/linux-node/bloodstone-node.service`** | Hardened systemd unit |
| `install-systemd.sh` | **`packages/linux-node/install-systemd.sh`** | Install unit + system user + datadir |
| `BUILD-INFO.txt` | Generated by packager / from-source | Commit, arch, toolchain, binary SHA-256 |
| `bloodstone.conf.example` | **`packages/linux-node/bloodstone.conf.example`** | Template conf |
| `README.txt` | Generated by packager | Human quick start |

## Not in this package

- `ops/*` pool/stratum/watchdog scripts  
- `miner-android/`, `miner-web/`, `portal/`, `pi-fleet`  
- `release-downloads` binary mirror branch  

## How the tarball is built (CI / VPS)

| Arch | Packager | Output |
|------|----------|--------|
| ARM64 / Pi | `build-bloodstone-node-arm64-package.sh` | `bloodstone-node-VERSION-linux-aarch64.tar.gz` |
| x86_64 | `build-bloodstone-node-distribution.sh` | `bloodstone-node-VERSION-linux-x86_64.tar.gz` |

## Security remediation & production audit

| Doc | Role |
|-----|------|
| `docs/Bloodstone-Node-0.7.6-Security-Audit-Remediation.md` | Prior high-severity remediations |
| [Bloodstone-Linux-Node-Installer-Security-Audit-Final.md](https://bloodstone.rocks/downloads/Bloodstone-Linux-Node-Installer-Security-Audit-Final.md) | **Final verdict: PASS 9.1/10 Production Ready** |

High-severity items already fixed: conf mode `600`, safe tar extract, HTTPS curl, seed overrides, random RPC password.

### systemd (production)

```bash
# From extracted package (root):
sudo ./install-systemd.sh
systemctl status bloodstone-node
journalctl -u bloodstone-node -f
bloodstone-health
```

### Health check

```bash
./bloodstone-health.sh
# or after systemd install:
bloodstone-health
```

Logs: `$BLOODSTONE_DATADIR/logs/install.log` and `bootstrap.log`.

### Operator env

| Variable | Effect |
|----------|--------|
| `BLOODSTONE_DATADIR` | Data directory (default `~/.bloodstone`) |
| `BLOODSTONE_SEEDS` / `BLOODSTONE_SEED_NODES` | Override default seed peers |
| `BLOODSTONE_SKIP_BOOTSTRAP` | Skip tip snapshot (full IBD) |
| `BLOODSTONE_FORCE_BOOTSTRAP` | Re-download tip snapshot |
| `BLOODSTONE_PUBLIC_ROOT` | Base URL for bootstrap download |
| `BLOODSTONE_GIT_URL` / `BLOODSTONE_GIT_REF` | Override monorepo URL/ref for from-source (default tag **`v0.7.6-h1`**) |
| `BLOODSTONE_VERIFY_TAG` | Attempt `git verify-tag` after checkout (default `1`) |
| `BLOODSTONE_REQUIRE_SIGNED_REF` | Fail from-source if tag/commit not signed (`1` = strict) |
| `PREFIX` | Install prefix for from-source layout |
| `MAKE_JOBS` | Parallel compile jobs |

## Quick smoke

```bash
bash -n start-node.sh install-chain-bootstrap.sh install-from-source.sh verify-release.sh \
  bloodstone-health.sh install-systemd.sh
```
