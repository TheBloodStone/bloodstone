# Bloodstone Pi Fleet Playbook

Operations guide for **Raspberry Pi edge nodes** in the Blurt–Bloodstone convergence mesh (Layer 2 DTN + Layer 3 DePIN).

## Fleet role

Each Pi is an **offline-capable DTN capsule** that:

- Runs the convergence portal on LAN HTTP `:8887`
- Advertises `_bloodstone-dtn._tcp` via mDNS for peer discovery
- Proxies HTTPS `:8443` for TLS peer sync
- Enforces **memo rails** (storage / compute / bandwidth BLURT→STONE credits)
- Queues DTN bundles and flushes on brief uplink windows

## Prerequisites

| Item | Notes |
|------|-------|
| Hardware | Raspberry Pi 4/5 (2 GB+ RAM), SD or NVMe |
| OS | Raspberry Pi OS 64-bit (Bookworm) or Ubuntu 22.04+ arm64 |
| Network | LAN with mDNS (Avahi) or Zeroconf Python package |
| Upstream | Brief internet for Blurt RPC + coordinator sync (optional for pure LAN) |

## Quick start (one-shot)

```bash
export DTN_NODE_ID=pi-shed-01
export DTN_DEFAULT_REGION=lan-west
sudo ./bloodstone-pi-fleet-setup.sh
```

Verify:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/status | jq '.storage_rail.enforce_quota, .depin_rails'
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/status | jq '.node_id, .mdns'
curl -kfsS https://127.0.0.1:8443/api/convergence/status | jq .ok
```

## Manual setup

### 1. Install packages

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip avahi-daemon avahi-utils openssl rsync
```

### 2. Deploy portal + chain_mesh

Copy from coordinator or OSS release:

- `/root/bloodstone-portal/` (portal app + venv)
- `/root/chain_mesh/` (convergence modules)
- `/root/sync-blurt-convergence.py`
- `/root/bloodstone-dtn-mdns.py`
- `/root/bloodstone-dtn-tls-proxy.py`
- `/root/setup-dtn-pi-tls.sh`

### 3. Convergence environment

```bash
sudo mkdir -p /etc/bloodstone
sudo cp convergence.env.example /etc/bloodstone/convergence.env
sudo nano /etc/bloodstone/convergence.env   # set DTN_NODE_ID, region
```

Memo rail enforcement (Wave G) — all default **on**:

| Variable | Effect |
|----------|--------|
| `STORAGE_CREDIT_ENFORCE=1` | Deny asset publish without `storage:<STONE>:<bytes>` credits |
| `COMPUTE_CREDIT_ENFORCE=1` | Deny compute job submit without quota or memo |
| `BANDWIDTH_CREDIT_ENFORCE=1` | Deny DTN export when `stone_address` set and quota exceeded |

### 4. systemd units

```bash
sudo cp bloodstone-portal-pi.service /etc/systemd/system/bloodstone-portal.service
sudo cp bloodstone-dtn-mdns.service /etc/systemd/system/
sudo cp bloodstone-convergence-upkeep.timer bloodstone-convergence-upkeep.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bloodstone-portal bloodstone-dtn-mdns bloodstone-convergence-upkeep.timer
```

### 5. TLS proxy

```bash
sudo DTN_NODE_ID=pi-shed-01 ./setup-dtn-pi-tls.sh
sudo systemctl enable --now bloodstone-dtn-tls
```

Pi peers use `DTN_TLS_PEER=1` and `DTN_TLS_VERIFY=0` (or install coordinator CA).

## Memo rails (pay before use)

Send BLURT to outpost accounts with structured memos:

| Rail | Outpost | Memo format |
|------|---------|-------------|
| Storage | `@bloodstone-storage` | `storage:<STONE_ADDRESS>:<bytes>` |
| Compute | `@bloodstone-depin` | `compute:<STONE_ADDRESS>:<job_id>` |
| Bandwidth | `@bloodstone-depin` | `bandwidth:<STONE_ADDRESS>:<bytes>` |

Check quota:

```bash
curl "http://127.0.0.1:8887/api/convergence/storage/quota?stone_address=STONE..."
curl "http://127.0.0.1:8887/api/convergence/compute/quota?stone_address=STONE..."
curl "http://127.0.0.1:8887/api/convergence/bandwidth/quota?stone_address=STONE..."
```

Convergence upkeep syncs memos from Blurt every 5 minutes (timer) or via coordinator upkeep.

## Fleet registration

### mDNS auto-discovery

`bloodstone-dtn-mdns.service` publishes `_bloodstone-dtn._tcp` with properties:

- `node_id`, `region`, `tls`, `tls_port` (8443 when TLS proxy running)

Browsing peers registers them in the LAN DTN peer table (`/api/convergence/dtn/peers`).

### Gossip rumor exchange (Wave H)

Beyond mDNS, nodes exchange peer tables via `bloodstone_dtn_gossip/v1`:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/gossip/status | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/dtn/gossip/round
```

Gossip runs automatically during DTN upkeep when `DTN_GOSSIP_ENABLE=1` (default).

### Starlink handoff bridge (Wave I)

When a brief satellite uplink appears (Starlink, LTE failover, etc.), the bridge probes the coordinator and flushes queued DTN bundles **outside** scheduled UTC flush windows:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/starlink/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/starlink/probe | jq .connected,.latency_ms
curl -X POST http://127.0.0.1:8887/api/convergence/dtn/starlink/handoff
```

Set `DTN_STARLINK_INTERFACE=eth1` on Pi nodes wired through a Starlink dish router. Handoff runs automatically in DTN upkeep when `DTN_STARLINK_ENABLE=1`.

### Offline Condenser reader (Wave J)

Browse mesh-hosted Blurt posts **without internet** when chunks are stored locally:

```bash
open http://127.0.0.1:8887/convergence/offline
curl -fsS http://127.0.0.1:8887/api/convergence/condenser/offline/feed | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/condenser/offline/index
```

DTN bundles now include `post-manifests.json` for offline feed sync.

### Manual peer register

```bash
curl -X POST http://127.0.0.1:8887/api/convergence/dtn/peer/register \
  -H 'Content-Type: application/json' \
  -d '{"node_id":"pi-shed-02","base_url":"https://192.168.1.42:8443","region":"lan-west","tls":true}'
```

## DTN operations

| Action | Endpoint |
|--------|----------|
| Export bundle | `GET /api/convergence/dtn/export?stone_address=STONE...` |
| Import bundle | `POST /api/convergence/dtn/import` |
| Queue forward | `POST /api/convergence/dtn/forward/submit` |
| Flush uplink | `POST /api/convergence/dtn/forward/flush` |
| Replication heal | automatic when `DTN_AUTO_HEAL=1` |
| Alerts | `GET /api/convergence/dtn/alerts` |

## Coordinator integration

Point Pi upstream at the VPS coordinator for flush + registry sync:

```bash
# /etc/bloodstone/convergence.env
DTN_UPSTREAM_URL=https://bloodstonewallet.mytunnel.org
```

Coordinator runs the same convergence stack with `DTN_NODE_ID=coordinator-vps`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `enforce_quota: false` in status | Check `EnvironmentFile=/etc/bloodstone/convergence.env` in portal unit |
| mDNS peers empty | `sudo systemctl restart avahi-daemon bloodstone-dtn-mdns` |
| TLS peer reject | Set `DTN_TLS_VERIFY=0` or copy `/etc/bloodstone/dtn/tls.crt` |
| 403 on compute submit | Pay `compute:<STONE>:<job_id>` memo or lower `flops_budget` |
| 403 on DTN export | Pay `bandwidth:<STONE>:<bytes>` or omit `stone_address` for LAN-only export |

## Files in this package

- `bloodstone-pi-fleet-setup.sh` — automated installer
- `convergence.env.example` — memo rail + DTN env template
- `bloodstone-portal-pi.service` — portal unit (LAN :8887)
- `bloodstone-dtn-mdns.service` — mDNS broadcaster
- `bloodstone-convergence-upkeep.service` + `.timer` — Blurt registry + credit sync