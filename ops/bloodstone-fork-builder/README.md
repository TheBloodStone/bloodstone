# Bloodstone Fork Builder (offline)

**Version 1.5.1** — offline toolkit with **individual product packaging**: build only what you need
(`android-full-node` = full node on device/phone, `vps`, `qt`, raw `daemon`/`cli`, …) or the full set.
GUI and menu both expose **“Make a full node on your device or phone”**.

**Resilient builds (1.4+):** when `configure` / `make` fails because a library or tool is missing, Fork Builder **parses the error**, **apt-installs the matching packages**, and **retries** (up to 8 times). It also pre-installs the base toolchain and will **auto-download** the core source tarball into `vendor/` if it is not already on disk (needs network once).

After you register a minable fork on [Fork Lab](https://bloodstonewallet.mytunnel.org/fork-lab/), download that fork’s **manifest JSON** and use this toolkit offline to:

1. Load the manifest  
2. **Edit coin settings before compile** (name, ticker, ports, algos, reward, premine, salt, magic, icon, datadir)  
3. Unpack Bloodstone core source (auto-downloaded if missing)  
4. Patch network ports, magic bytes, branding, and salt  
5. Build `bloodstoned` + `bloodstone-cli` on Linux (or patch then build in WSL on Windows) — missing deps install themselves as errors appear  

Once the core tarball and packages are cached, further builds work fully offline.

## Requirements

| Platform | Needs |
|----------|--------|
| **Linux** (recommended) | Python 3.8+, `sudo`/`apt-get` (or root). Base packages auto-install on first compile; you can also pre-install `build-essential`, `libssl-dev`, `libevent-dev`, `libboost-all-dev`, `libdb5.3++-dev` |
| **Windows** | Python 3.8+ for the GUI/CLI patch step; compile via **WSL2** (Ubuntu) — resilient apt loop runs inside WSL |
| **macOS** | Python 3; use Homebrew deps similar to Bitcoin Core builds (apt auto-install is Linux/WSL only) |

## Quick start (Linux)

```bash
# 1) Unpack this package
tar -xzf bloodstone-fork-builder-1.1.0-offline.tar.gz
cd bloodstone-fork-builder-1.1.0

# 2) Core source: optional manual place in vendor/
#    If missing, prepare/compile will download:
#    https://bloodstonewallet.mytunnel.org/downloads/bloodstone-core-source-latest.tar.gz
mkdir -p vendor

# 3) Save your Fork Lab manifest as my-fork.json
#    GET https://bloodstonewallet.mytunnel.org/api/fork-lab/coins/<fork_id>

# 4) Review settings, then patch + compile
python3 fork_builder.py show --manifest my-fork.json
python3 fork_builder.py all --manifest my-fork.json --interactive
# or non-interactive overrides:
python3 fork_builder.py all --manifest my-fork.json \
  --set ticker=LRGK --set p2p_port=33685 --set block_reward=50
```

GUI (if tkinter is available) — full settings form before compile:

```bash
python3 fork_builder.py gui
# or:
./start-gui.sh
```

Edited settings are saved under `work/coin-settings.json` and `work/edited-manifest.json`.

## Windows (patch offline, build in WSL)

```bat
start-gui.bat
```

1. Use the GUI to **Patch only** with your manifest + core tarball.  
2. Open **WSL**, install build deps, then:

```bash
cd /mnt/c/path/to/bloodstone-fork-builder-1.1.0/work/src-extract/...
./autogen.sh && ./configure --disable-tests --without-gui && make -j$(nproc)
```

## Commands

| Command | Purpose |
|---------|---------|
| `show` | Print editable settings from a manifest |
| `prepare` | Apply settings + extract core + patch |
| `build` | `./configure && make` on a patched tree |
| `all` | prepare + build |
| `compile-local` | Compile + package **selected products** (or default set) |
| `package` | Package selected kits from already-built binaries |
| `gui` | Desktop UI with **settings editor** + compile-local buttons |
| `menu` | Console wizard (**9** = product picker, **a** = Android full-node only) |

### Individual products (pick one or many)

```bash
# ONLY Android full-node starter (start the coin from a phone) — no VPS kit:
python3 fork_builder.py compile-local --manifest my-fork.json --only android-full-node

# Server node only:
python3 fork_builder.py compile-local --manifest my-fork.json --products vps

# Desktop wallet only (needs Qt build):
python3 fork_builder.py compile-local --manifest my-fork.json --products qt --with-gui

# Raw daemon binary only:
python3 fork_builder.py package --work work --products daemon

# Classic full set:
python3 fork_builder.py compile-local --manifest my-fork.json --products full --with-gui
```

| Product id | Kit folder | Purpose |
|------------|------------|---------|
| `android-full-node` | `{ticker}-android-full-node-kit` | **Start coin on phone** — full-node edge profile + import docs |
| `android-pruned-node` | `{ticker}-android-pruned-node-kit` | Lighter on-device node profile |
| `edge-node` | `{ticker}-edge-node-kit` | Multi-device edge profile (phone/desktop/Pi) |
| `vps` | `{ticker}-vps-server-kit` | Daemon + CLI + conf + systemd |
| `qt` | `{ticker}-qt-wallet-kit` | Desktop wallet |
| `daemon` / `cli` | `{ticker}-binaries` | Raw binaries only |
| `full` | `{ticker}-full-distribution` | VPS + Qt + notes |

Also writes `.tar.gz` and `.zip` for each **selected** kit.

### Settings you can change pre-compile

| Field | CLI example |
|-------|-------------|
| Coin name | `--set name="My Coin"` |
| Ticker | `--set ticker=LRGK` |
| P2P / RPC ports | `--set p2p_port=33685 --set rpc_port=53685` |
| Block time / reward / premine | `--set block_time_seconds=90 --set block_reward=100` |
| Network salt / magic | `--set network_salt=... --set message_start_hint=a1b2c3d4` |
| Algorithms | `--set algos=neoscrypt,yespower,sha256d` |
| Local Qt icon | `--local-icon ./my-icon.png` |
| Settings file | `--settings coin-settings.json` |

## What gets patched

- Mainnet P2P port (`p2p_port_hint`)  
- Network magic bytes (`message_start_hint` / salt)  
- Branding strings (name)  
- Writes `fork-coin.conf.example`, `FORK_MANIFEST.json`, `FORK_BUILD_NOTES.txt`  

Production forks should still generate a **unique genesis** using the manifest `network_salt` before a public launch.

## Links

- Fork Lab: https://bloodstonewallet.mytunnel.org/fork-lab/  
- Parent source: https://github.com/TheBloodStone/bloodstone  
- Core tarball: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-core-source-latest.tar.gz  
