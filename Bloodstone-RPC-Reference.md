# Bloodstone Core JSON-RPC Reference

**Document version:** 1.0 · July 2026  
**Audience:** Exchange backends, integrators, game engines, wallet authors, and operators running `bloodstoned`  
**Coordinator:** https://bloodstonewallet.mytunnel.org

---

## Executive summary

Bloodstone Core (`bloodstoned`) exposes a **Bitcoin Core–compatible JSON-RPC 1.0** interface over HTTP, plus **SpaceXpanse heritage extensions** for on-chain **names**, **multi-algorithm mining**, and **game-aware ZMQ notifications**.

This document is the Bloodstone-specific RPC reference. It covers connection details, Bloodstone-only methods, ZMQ topics, and integration alternatives. For the hundreds of inherited Bitcoin Core wallet/blockchain commands, use `bloodstone-cli help` on a running node or the [Bitcoin Core RPC documentation](https://developer.bitcoin.org/reference/rpc/) as the baseline.

**Bloodstone is not an EVM chain.** `ethers.js`, `web3.js`, and MetaMask do **not** work against STONE RPC. See [§2](#2-not-ethereum-what-to-use-instead).

---

## 1. Quick start

### 1.1 Prerequisites

- A synced **Bloodstone Core** node (`bloodstoned` ≥ 0.7.x)
- RPC enabled in `bloodstone.conf` (default port **18332** on Linux; Android LAN nodes often use **18340**)
- `bloodstone-cli` on the same host, or HTTP access from an allowed subnet

### 1.2 Default network parameters

| Parameter | Mainnet value |
|-----------|---------------|
| P2P port | **17333** |
| RPC port (Linux node) | **18332** |
| RPC port (Android LAN node) | **18340** |
| Currency unit | **STONE** (8 decimals) |
| Legacy address prefix | `S…` (P2PKH) |
| Bech32 HRP | `stone1…` |
| Block time (target) | ~90 seconds |
| PoW algorithms | `neoscrypt`, `yespower`, `sha256d` (merge-mined; chain ID **1899**) |

Live values are also in the [exchange listing pack](https://bloodstonewallet.mytunnel.org/api/exchange) (`/api/exchange`).

### 1.3 `bloodstone-cli` examples

```bash
# Chain status
bloodstone-cli getblockchaininfo
bloodstone-cli getblockcount
bloodstone-cli getblockstats $(bloodstone-cli getblockcount) '["subsidy"]'

# Wallet (requires loaded wallet)
bloodstone-cli getnewaddress
bloodstone-cli getbalance
bloodstone-cli sendtoaddress "SYourAddress..." 1.5

# Names
bloodstone-cli name_show "d/myname"
bloodstone-cli name_scan "" 20

# Mining (solo)
bloodstone-cli creatework "SYourPayoutAddress" "neoscrypt"
bloodstone-cli submitwork "HASH" "DATA"

# Game ZMQ setup
bloodstone-cli trackedgames
bloodstone-cli trackedgames add "mygame"
bloodstone-cli game_sendupdates "mygame" "<from-block-hash>"
```

Use `-conf=/path/to/bloodstone.conf` and `-rpcwallet=walletname` when not using the default datadir.

### 1.4 HTTP JSON-RPC (curl)

Bloodstone uses **JSON-RPC 1.0** (not Ethereum’s 2.0). Authenticate with HTTP basic auth (`rpcuser` / `rpcpassword` from `bloodstone.conf`).

```bash
RPC_USER="bloodstone"
RPC_PASS="your_rpcpassword"
RPC_URL="http://127.0.0.1:18332/"

curl --user "${RPC_USER}:${RPC_PASS}" \
  --data-binary '{"jsonrpc":"1.0","id":"curltest","method":"getblockchaininfo","params":[]}' \
  -H 'content-type: text/plain;' \
  "${RPC_URL}"
```

Named-wallet calls add the `wallet` query parameter (Bitcoin Core convention):

```bash
curl --user "${RPC_USER}:${RPC_PASS}" \
  --data-binary '{"jsonrpc":"1.0","id":"curltest","method":"getnewaddress","params":["deposit-user-42"]}' \
  -H 'content-type: text/plain;' \
  "http://127.0.0.1:18332/wallet/exchange-hot"
```

### 1.5 Security notes

- **RPC is localhost-only** on the public pool coordinator VPS. Exchanges and partners must run their own node ([exchange node package](https://bloodstonewallet.mytunnel.org/downloads/)) or use ElectrumX against a node they control.
- Bind RPC to loopback unless you explicitly extend `rpcallowip` for a trusted backend subnet.
- Never expose `rpcuser` / `rpcpassword` to browsers or mobile clients. Use a backend proxy.

---

## 2. Not Ethereum — what to use instead

| Ethereum stack | Bloodstone |
|----------------|------------|
| `eth_*` methods | `getblockchaininfo`, `sendrawtransaction`, `listunspent`, … |
| `0x…` accounts | **UTXO** model; `S…` / `stone1…` addresses |
| MetaMask / EIP-1193 | Not applicable |
| Smart contracts on STONE | **No EVM** on Bloodstone mainnet |
| `ethers.js` / `web3.js` | Use Bitcoin-style RPC clients or Electrum protocol |

**Recommended integration paths:**

| Goal | Approach |
|------|----------|
| CEX deposits / withdrawals | Own node + `getnewaddress` / `sendtoaddress` / `getrawtransaction` (with `txindex=1`) |
| Lightweight address monitoring | **ElectrumX** — `ssl://bloodstonewallet.mytunnel.org:50002` (see `/api/exchange`) |
| Read-only chain stats in a web app | [Explorer REST API](#9-explorer-rest-api-read-only) |
| Game engines | Core **ZMQ** game topics + `game_sendupdates` |
| Cross-chain ETH escrow (Blurt, etc.) | Separate **Ethereum** integration — not STONE RPC |

MetaMask appears only in **cross-chain** partner flows (ETH-side escrow). It does not speak to `bloodstoned`.

---

## 3. Command index

Run `bloodstone-cli help` for full syntax. Inherited commands follow Bitcoin Core semantics unless noted.

### 3.1 Blockchain (inherited)

`getbestblockhash`, `getblock`, `getblockchaininfo`, `getblockcount`, `getblockfilter`, `getblockhash`, `getblockheader`, `getblockstats`, `getchaintips`, `getchaintxstats`, `getdifficulty`, `getmempoolancestors`, `getmempooldescendants`, `getmempoolentry`, `getmempoolinfo`, `getrawmempool`, `gettxout`, `gettxoutproof`, `gettxoutsetinfo`, `preciousblock`, `pruneblockchain`, `savemempool`, `scantxoutset`, `verifychain`, `verifytxoutproof`

**Bloodstone note:** `getblockstats` includes `subsidy` — use for live block reward verification after subsidy forks.

### 3.2 Control (inherited)

`getmemoryinfo`, `getrpcinfo`, `help`, `logging`, `stop`, `uptime`

### 3.3 Game (Bloodstone / SpaceXpanse)

`game_sendupdates`, `trackedgames`

### 3.4 Generating (inherited + algo)

`generateblock`, `generatetoaddress`, `generatetodescriptor` — optional `"algo"` argument (`neoscrypt`, `yespower`, `sha256d`)

### 3.5 Mining (Bloodstone extensions)

`createauxblock`, `creatework`, `getauxblock`, `getblocktemplate`, `getmininginfo`, `getnetworkhashps`, `getwork`, `prioritisetransaction`, `submitauxblock`, `submitblock`, `submitheader`, `submitwork`

**Algorithms:** pass `"neoscrypt"` or `"yespower"` to `creatework` / `generatetoaddress`. Merge-mined blocks use `sha256d` (SpaceXpanse chain ID **1899**).

### 3.6 Names (Bloodstone / Namecoin heritage)

`dequeuetransaction`, `listqueuedtransactions`, `name_checkdb`, `name_history`, `name_list`, `name_pending`, `name_register`, `name_scan`, `name_show`, `name_update`, `queuerawtransaction`, `sendtoname`

Name namespaces use prefixes such as `d/` (display), `id/`, `g/` (game registry), `p/` (player). Moves for games are embedded in name JSON under `.g[GAMEID]`.

### 3.7 Network (inherited)

`addnode`, `clearbanned`, `disconnectnode`, `getaddednodeinfo`, `getconnectioncount`, `getnettotals`, `getnetworkinfo`, `getnodeaddresses`, `getpeerinfo`, `listbanned`, `ping`, `setban`, `setnetworkactive`

### 3.8 Raw transactions (inherited + name PSBT helpers)

Standard: `createrawtransaction`, `decoderawtransaction`, `fundrawtransaction`, `sendrawtransaction`, PSBT suite, etc.

**Name extensions:** `namepsbt`, `namerawtransaction`

### 3.9 Signer, Util, Wallet (inherited)

Full Bitcoin Core wallet RPC set: `getnewaddress`, `sendtoaddress`, `listunspent`, `walletcreatefundedpsbt`, `signrawtransactionwithwallet`, etc.

Signed messages use Bloodstone magic (`Bloodstone Signed Message:\n`).

### 3.10 Zmq

`getzmqnotifications` — lists active ZMQ publishers configured at daemon start.

---

## 4. Names RPC (detail)

On-chain names power DEX order books, metadata, and game moves. Names are **UTXO-based name outputs**, not EVM contracts.

### 4.1 Read methods

**`name_show "name"`** — current value, owner address, height, txid.

```bash
bloodstone-cli name_show "d/example"
```

**`name_scan "start" count`** — paginated name iterator (explorer uses this).

**`name_list`** — names in loaded wallet.

**`name_history "name"`** — full update history.

**`name_pending "name"`** — mempool state for a name.

### 4.2 Write methods

**`name_register "name" ("value" options)`** — register a new name. Requires wallet passphrase if encrypted.

**`name_update "name" ("value" options)`** — update value or transfer via `destAddress` in options.

**`sendtoname "name" amount`** — send STONE to the name owner’s address.

### 4.3 Options object (common fields)

| Field | Purpose |
|-------|---------|
| `nameEncoding` | `ascii`, `utf8`, or `hex` |
| `valueEncoding` | `ascii`, `utf8`, or `hex` |
| `destAddress` | Send name output to this address |
| `sendCoins` | Additional coin outputs `{address: amount}` |
| `burn` | Burn data `{data: amount}` |

### 4.4 Example: game move via name update

```bash
bloodstone-cli name_update "p/alice" '{"g":{"chess":"e4"}}'
```

Game engines parse moves from name JSON per the [SpaceXpanse game model](https://github.com/SpaceXpanse/rod-core-wallet/blob/master/doc/spacexpanse/games.md) (upstream; applies to Bloodstone heritage).

---

## 5. Mining RPC (detail)

Bloodstone uses **triple-purpose PoW**: standalone Neoscrypt, standalone Yespower, and SHA-256d merge mining (chain ID 1899).

### 5.1 Solo mining workflow

```bash
# 1. Create work unit
bloodstone-cli creatework "SYourPayoutAddress" "neoscrypt"

# 2. Mine externally (your GPU/CPU miner solves "data" for "hash")

# 3. Submit solution
bloodstone-cli submitwork "<block-hash>" "<solution-data>"
```

Repeat with `"yespower"` for the Yespower algorithm.

### 5.2 `getmininginfo` / `getnetworkhashps`

Returns per-algorithm difficulty and network hash rate. Pool stratum on the coordinator VPS is separate from RPC — LAN/Android nodes also expose stratum on **3437** (Neoscrypt), **3438** (Yespower), **3440** (ROD Neoscrypt legacy port label).

### 5.3 `getblocktemplate`

Standard Bitcoin mining RPC; Bloodstone blocks include algorithm metadata. Most pool software uses **stratum**, not GBT, on Bloodstone deployments.

### 5.4 `generatetoaddress`

Regtest/test only on production mainnet policy — documented for completeness:

```bash
bloodstone-cli generatetoaddress 1 "SAddress" 1000000 "neoscrypt"
```

---

## 6. Game RPC and ZMQ (detail)

Game engines keep state in sync with the chain via **ZeroMQ** and optional on-demand catch-up RPC.

### 6.1 Configure game ZMQ at daemon start

```ini
# bloodstone.conf
zmqpubgameblocks=tcp://127.0.0.1:28332
zmqpubgamepending=tcp://127.0.0.1:28332
```

Standard Bitcoin ZMQ topics also apply (`zmqpubhashblock`, `zmqpubhashtx`, `zmqpubrawblock`, `zmqpubrawtx`, `zmqpubsequence`) — see upstream `doc/zmq.md`.

Bloodstone-specific publishers:

| Flag | Topic prefix | Purpose |
|------|--------------|---------|
| `zmqpubgameblocks` | `game-block-attach`, `game-block-detach` | Block connect/disconnect with parsed moves |
| `zmqpubgamepending` | `game-tx-pending` | Mempool game transactions |

### 6.2 `trackedgames`

```bash
bloodstone-cli trackedgames                    # list tracked game IDs
bloodstone-cli trackedgames add "mygame"       # track game ID
bloodstone-cli trackedgames remove "mygame"    # stop tracking
```

Only tracked games receive filtered ZMQ `game-block-*` messages.

### 6.3 `game_sendupdates`

Request on-demand attach/detach notifications between two block hashes (e.g. after reconnecting):

```bash
bloodstone-cli game_sendupdates "mygame" "<from-block-hash>" "<to-block-hash>"
```

Returns `reqtoken`, `ancestor`, and `steps` (`attach` / `detach` counts). Subscribe to ZMQ **before** calling; messages include the `reqtoken` for correlation.

### 6.4 ZMQ message format (game-block-attach)

Multipart ZMQ message:

```
game-block-attach json GAMEID | <JSON-DATA> | <SEQ>
```

`DATA` JSON includes `block` (hash, height, timestamp, `rngseed`, …), `admin`, and `moves[]` with `txid`, `name`, `move`, inputs, outputs.

Full specification: upstream `doc/spacexpanse/interface.md` in [rod-core-wallet](https://github.com/SpaceXpanse/rod-core-wallet).

### 6.5 `getzmqnotifications`

```bash
bloodstone-cli getzmqnotifications
```

Lists each active publisher address and high-water mark.

---

## 7. Exchange and CEX integration

### 7.1 Recommended setup

1. Download [bloodstone-exchange-node](https://bloodstonewallet.mytunnel.org/downloads/) (txindex + hot wallet + setup scripts).
2. Run `setup-exchange-node.sh` and `verify-exchange-node.sh`.
3. Point your backend at `http://127.0.0.1:18332/` with wallet `exchange-hot`.

### 7.2 Credit rules (from listing pack)

| Rule | Value |
|------|-------|
| Deposit confirmations | **6** |
| Withdrawal confirmations | **6** |
| Coinbase maturity | **100** blocks |

### 7.3 Essential RPC calls for CEX

```bash
CLI="./bin/bloodstone-cli"
CONF="/var/lib/bloodstone-exchange/bloodstone.conf"

$CLI -conf=$CONF getblockchaininfo
$CLI -conf=$CONF -rpcwallet=exchange-hot getnewaddress "user-12345"
$CLI -conf=$CONF -rpcwallet=exchange-hot sendtoaddress "S..." 1.5
$CLI -conf=$CONF -rpcwallet=exchange-hot listtransactions
$CLI -conf=$CONF getrawtransaction "TXID" true    # requires txindex=1
$CLI -conf=$CONF scantxoutset start '["addr(S...)"]'  # optional UTXO scan
```

### 7.4 ElectrumX (SPV deposit monitoring)

```ini
DAEMON_URL=http://exchange_rpc:PASSWORD@127.0.0.1:18332/
```

Public SSL endpoint: `ssl://bloodstonewallet.mytunnel.org:50002` (verify against `/api/exchange`).

---

## 8. Configuration reference

### 8.1 Minimal `bloodstone.conf` (RPC + wallet)

```ini
server=1
txindex=1
rpcuser=bloodstone
rpcpassword=<strong-random-password>
rpcport=18332
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
# rpcallowip=10.0.0.0/24   # extend only for trusted backend subnet

wallet=exchange-hot
```

### 8.2 Android / LAN node

Pruned `bloodstoned` on Android exposes RPC on the device LAN IP, typically port **18340**, for household miners and local wallets. Same JSON-RPC methods; bind address follows device network state.

### 8.3 Multi-wallet

Load additional wallets with `loadwallet` or start with multiple `wallet=` lines. RPC URL path `/wallet/<name>` selects the active wallet context.

---

## 9. Explorer REST API (read-only)

The coordinator explorer proxies a **subset** of chain data over HTTPS — not a full RPC replacement.

| Endpoint | Returns |
|----------|---------|
| `GET /explorer/api/stats` | Height, best block hash, difficulty, mempool size |
| `GET /explorer/api/blocks?limit=N` | Recent blocks |
| `GET /explorer/api/mesh-anchors` | BSM1 on-chain anchor index |
| `GET /explorer/health` | Node reachability |

Base URL: https://bloodstonewallet.mytunnel.org/explorer/

These endpoints are suitable for dashboards. **Do not** use them for signing transactions or custodial operations.

---

## 10. Client libraries and upstream references

| Resource | URL |
|----------|-----|
| Bitcoin Core RPC (baseline) | https://developer.bitcoin.org/reference/rpc/ |
| SpaceXpanse game interface (ZMQ) | https://github.com/SpaceXpanse/rod-core-wallet/blob/master/doc/spacexpanse/interface.md |
| SpaceXpanse game model | https://github.com/SpaceXpanse/rod-core-wallet/blob/master/doc/spacexpanse/games.md |
| SpaceXpanse mining design | https://github.com/SpaceXpanse/rod-core-wallet/blob/master/doc/spacexpanse/mining.md |
| Bitcoin ZMQ notifications | https://github.com/bitcoin/bitcoin/blob/master/doc/zmq.md |
| Exchange listing pack (JSON) | https://bloodstonewallet.mytunnel.org/api/exchange |
| Exchange node README | https://bloodstonewallet.mytunnel.org/downloads/ (bloodstone-exchange-node package) |

**Python example (stdlib):**

```python
import json
from urllib.request import Request, urlopen
from base64 import b64encode

def rpc(method, params=None, wallet=None):
    url = "http://127.0.0.1:18332/"
    if wallet:
        url += f"wallet/{wallet}"
    auth = b64encode(b"bloodstone:PASSWORD").decode()
    body = json.dumps({"jsonrpc": "1.0", "id": "py", "method": method, "params": params or []}).encode()
    req = Request(url, data=body, headers={"Authorization": f"Basic {auth}", "Content-Type": "text/plain"})
    return json.loads(urlopen(req).read())["result"]

print(rpc("getblockchaininfo"))
print(rpc("getnewaddress", ["user-1"], wallet="exchange-hot"))
```

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Connection refused` on :18332 | `bloodstoned` not running or RPC bound to 127.0.0.1 only | Start daemon; SSH tunnel or extend `rpcallowip` |
| `401 Unauthorized` | Wrong `rpcuser`/`rpcpassword` | Match `bloodstone.conf` |
| `Method not found` | Typo or wallet-only method without `/wallet/` path | Add wallet path or load wallet |
| `getrawtransaction` fails | `txindex=0` | Enable `txindex=1`, resync |
| Game ZMQ silent | Game ID not tracked | `trackedgames add "gameid"` |
| Help shows `spacexpanse-cli` / port 11998 | Legacy example strings in upstream help text | Use `bloodstone-cli` and port **18332** |

---

## 12. Document maintenance

This reference is generated from Bloodstone Core **0.7.x** shipped on the coordinator. When Core semver advances, re-run:

```bash
bloodstone-cli help > rpc-command-list.txt
```

and diff against §3. Authoritative per-command syntax is always `bloodstone-cli help <command>` on your installed binary.

---

## Related documents

- [Infrastructure Independence White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx)
- [Why No GitHub / Development Velocity](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Why-No-GitHub-Development-Velocity-White-Paper.md)
- [LAN Pool Coordinator Guide](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md)
- [Exchange listing pack](https://bloodstonewallet.mytunnel.org/api/exchange)

---

*Bloodstone · Core JSON-RPC reference · July 2026*