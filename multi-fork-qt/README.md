# Bloodstone Multi-Fork Qt Wallet

Desktop **multi-fork** wallet for **STONE** (Bloodstone mainnet) and **every live Fork Lab child coin** (AZURE, LRGK, and any future live launch).

New Fork Lab coins appear automatically from `/var/lib/bloodstone/fork_lab.db` (or `FORK_LAB_DB`).

## Features

- Portfolio sidebar: all chains with online status and balances
- Per-coin **Receive**, **Send**, **History**, **RPC Console**
- Multi-wallet support (`listwallets` / `loadwallet`)
- Wallet unlock (encrypted wallets)
- Settings: RPC conf paths, refresh interval
- Dark Bloodstone theme

## Requirements

- Python 3.8+
- PyQt5 (`python3-pyqt5`)
- `requests`
- Local (or reachable) JSON-RPC nodes with conf files:
  - STONE: `~/.bloodstone/bloodstone.conf` (bloodstoned)
  - LRGK: `lrgk.conf` (lrgkd)
  - AZURE: `azure.conf` (azured)
  - Other forks: set conf path in **Settings**

## Run

```bash
# Debian/Ubuntu
sudo apt-get install -y python3-pyqt5 python3-requests

cd bloodstone-multi-fork-qt
./scripts/run.sh
# or
python3 main.py
```

Headless smoke test (no display):

```bash
QT_QPA_PLATFORM=offscreen python3 main.py --smoke
```

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `FORK_LAB_DB` | `/var/lib/bloodstone/fork_lab.db` | Live fork catalogue |
| `STONE_CONF` | `~/.bloodstone/bloodstone.conf` | STONE RPC conf |
| `LRGK_CONF` | `/root/lrgk-chain/bootstrap-source/lrgk.conf` | LRGK conf |
| `AZURE_CONF` | `/root/azure-chain/bootstrap-source/azure.conf` | AZURE conf |
| `BLOODSTONE_PUBLIC_ROOT` | `https://bloodstone.rocks` | Icons / public URLs |

## Security notes

- This wallet talks to **local JSON-RPC** using credentials from each coin’s conf file. Do not expose RPC ports to the internet.
- Sending requires an unlocked wallet when encryption is enabled.
- Operator/hot-wallet use: prefer dedicated wallets, not treasury labels.

## Windows EXE

Build (on this Linux host):

```bash
bash /root/build-bloodstone-multi-fork-qt-windows.sh
# or
bash scripts/build-windows.sh
```

Published artifacts:

- `bloodstone-multi-fork-qt-<ver>-win64.exe` — NSIS setup (primary)
- `bloodstone-multi-fork-qt-<ver>-win64-setup.exe` — same bits
- `bloodstone-multi-fork-qt-<ver>-win64-portable.zip` — unzip + `launch.bat`
- `bloodstone-multi-fork-qt-win64-latest.exe` — latest alias

Windows users: double-click the EXE, then set each coin’s conf path in **Settings** if auto-detect misses it.

## Version

See `VERSION`.

## Create wallet (in-app)

With the local daemon running for a coin:

1. Select the coin in the sidebar  
2. **Wallet → Create new wallet…** (or **New wallet…** next to the wallet dropdown)  
3. Choose a name and optional encryption passphrase  
4. Save the address + WIF backup (`.md`) when prompted  

