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

### WAN uplink handoff bridge (Wave I)

When a brief WAN uplink appears (Starlink, 4G/5G failover, satellite backhaul, tethered phone, etc.), the bridge probes the coordinator and flushes queued DTN bundles **outside** scheduled UTC flush windows:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/uplink/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/uplink/probe | jq .connected,.latency_ms
curl -X POST http://127.0.0.1:8887/api/convergence/dtn/uplink/handoff
```

**No special Starlink config is required.** This is a generic global handoff bridge for all intermittent traffic types. Works with any network interface — set `DTN_UPLINK_INTERFACE=eth1` (or `wwan0`, `wlan0`, etc.) when you want handoff only while a specific NIC is up. `DTN_STARLINK_INTERFACE` remains a **legacy alias** for `DTN_UPLINK_INTERFACE`. Handoff runs automatically in DTN upkeep when `DTN_STARLINK_ENABLE=1`.

Legacy API paths (`/api/convergence/dtn/starlink/*`) still work unchanged.

### Offline Condenser reader (Wave J)

Browse mesh-hosted Blurt posts **without internet** when chunks are stored locally:

```bash
open http://127.0.0.1:8887/convergence/offline
curl -fsS http://127.0.0.1:8887/api/convergence/condenser/offline/feed | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/condenser/offline/index
```

DTN bundles now include `post-manifests.json` for offline feed sync.

### Planetary quorum (Wave K)

Roll up regional replication quorum across DTN peers and coordinate cross-region heal:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/planetary/status | jq '.rollup.planetary_satisfied, .regions'
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/planetary/regions | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/dtn/planetary/heal
curl -X POST http://127.0.0.1:8887/api/convergence/dtn/planetary/round
```

Gossip exchange (`bloodstone_dtn_gossip/v1`) now carries `quorum_snapshots` for peer votes. Planetary rollup runs automatically in DTN upkeep when `DTN_PLANETARY_ENABLE=1`.

### BLURT↔STONE bridge (Wave L)

HTLC-style atomic swap intents between BLURT and STONE mesh credits:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/bridge/status | jq .
curl -fsS 'http://127.0.0.1:8887/api/convergence/bridge/quote?direction=blurt_to_stone&amount=10&stone_address=STONE...' | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/bridge/initiate \
  -H 'Content-Type: application/json' \
  -d '{"direction":"blurt_to_stone","amount":"10","stone_address":"STONE..."}'
# Fund: send BLURT to @bloodstone-bridge with memo swap:lock:<swap_id>
curl -X POST http://127.0.0.1:8887/api/convergence/bridge/claim \
  -H 'Content-Type: application/json' \
  -d '{"swap_id":"bswap-...","preimage":"<secret from initiate>"}'
```

Bridge lock transfers sync automatically during convergence upkeep when `BRIDGE_SWAP_ENABLE=1`.

### On-device AI routing (Wave M)

Route `inference` compute jobs to local llama.cpp / ONNX / TFLite providers when uplink is down:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/ai/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/ai/providers | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/ai/discover
curl -X POST http://127.0.0.1:8887/api/convergence/ai/submit \
  -H 'Content-Type: application/json' \
  -d '{"stone_address":"STONE...","job_type":"inference","flops_budget":1000000000,"ai_spec":{"runtime":"llama.cpp","model_id":"llama-3.2-1b-q4","prefer_offline":true}}'
```

Run llama.cpp on `:8081` for local dispatch. AI provider discovery uses `_bloodstone-ai._tcp` mDNS and gossip `ai_provider_snapshots`. Upkeep runs automatically when `AI_ROUTING_ENABLE=1`.

Design doc: `bloodstone-docs/Wave-M-On-Device-AI-Routing-Design.md`

### Multi-tenant compute quota (Wave P)

Pi fleets can cap FLOPS per Blurt author on shared edge hardware. Bind authors to STONE pools and enforce at submit/route time:

```bash
curl -X POST http://127.0.0.1:8887/api/convergence/compute/tenant/bind \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"bloodstone","blurt_author":"megadrive","stone_address":"STONE...","flops_cap":5000000000}'
curl -fsS 'http://127.0.0.1:8887/api/convergence/compute/tenant/quota?blurt_author=megadrive' | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/ai/provider/sync
```

### Signed gossip + NPU detect (Wave O)

AI provider gossip snapshots are HMAC-signed (`bloodstone_ai_gossip_snapshot/v1`). Hailo/Coral devices are auto-detected via `/dev` probe on discover/upkeep:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/ai/npu/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/ai/gossip/sign/status | jq .
```

Set `AI_GOSSIP_SIGNING_KEY` on Pi fleet nodes for shared verification. Unsigned snapshots are still accepted while `AI_GOSSIP_ALLOW_UNSIGNED=1` (beta default).

### Wave Q — inference shim + bandwidth tenant + fleet gossip

**llama.cpp inference shim** — OpenAI-compatible HTTP on `:8081`, self-registers with portal:

```bash
sudo systemctl enable --now bloodstone-ai-inference
curl -fsS http://127.0.0.1:8081/health | jq .
curl -X POST http://127.0.0.1:8081/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"llama.cpp","prompt":"hello mesh","max_tokens":32}'
```

Set `LLAMA_SERVER_URL=http://127.0.0.1:8080` to proxy to a local `llama-server` instead of the beta stub.

**Multi-tenant bandwidth quota** — per-author byte caps on DTN export:

```bash
curl -X POST http://127.0.0.1:8887/api/convergence/bandwidth/tenant/bind \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"bloodstone","blurt_author":"megadrive","stone_address":"STONE...","bytes_cap":104857600}'
curl -fsS 'http://127.0.0.1:8887/api/convergence/bandwidth/tenant/quota?blurt_author=megadrive' | jq .
curl -fsS 'http://127.0.0.1:8887/api/convergence/dtn/export?stone_address=STONE...&blurt_author=megadrive' | jq .
```

**Fleet gossip enforcement** — when `AI_GOSSIP_SIGNING_KEY` is set, unsigned snapshots are rejected by default:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/ai/gossip/sign/status | jq '.fleet_key_configured,.enforcement_mode'
```

### Wave R — storage tenant + AI DTN route export

**Multi-tenant storage quota** — per-author byte caps on asset publish:

```bash
curl -X POST http://127.0.0.1:8887/api/convergence/storage/tenant/bind \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"bloodstone","blurt_author":"megadrive","stone_address":"STONE...","bytes_cap":5368709120}'
curl -fsS 'http://127.0.0.1:8887/api/convergence/storage/tenant/quota?blurt_author=megadrive' | jq .
```

**AI DTN route export** — when `AI_DTN_EXPORT_ROUTES=1`, DTN bundles include `ai-route-assignments.json` for stranded inference jobs:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/status | jq '.wave'
curl -fsS 'http://127.0.0.1:8887/api/convergence/dtn/export?include_chunks=0' | jq '.meta.ai_route_count'
```

### Wave S — tenant dashboard + Blurt AI broadcast + ONNX/TFLite delegates

**Unified tenant dashboard** — one view across compute, bandwidth, and storage caps:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/status | jq .
curl -fsS 'http://127.0.0.1:8887/api/convergence/tenant/dashboard?blurt_author=megadrive' | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/tenant/bind \
  -H 'Content-Type: application/json' \
  -d '{"blurt_author":"megadrive","stone_address":"STONE...","flops_cap":5e9,"bandwidth_bytes_cap":1e8,"storage_bytes_cap":5e9}'
```

**Blurt broadcast of AI providers** — publish `bloodstone_ai_provider/v1` to Layer 1:

```bash
curl -X POST http://127.0.0.1:8887/api/convergence/ai/provider/broadcast \
  -H 'Content-Type: application/json' \
  -d '{"provider_id":"pi-shed-01-ai","blurt_author":"megadrive"}'
# Response includes blurt_custom_json — sign and broadcast on Blurt
curl -X POST http://127.0.0.1:8887/api/convergence/ai/provider/sync
```

**ONNX / TFLite inference delegates** — shim routes by `runtime` or model prefix:

```bash
curl -fsS http://127.0.0.1:8081/v1/runtimes | jq .
curl -X POST http://127.0.0.1:8081/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"runtime":"onnx","model":"onnx:gemma","prompt":"hello edge","max_tokens":32}'
```

### Wave T — tenant fleet sync + broadcast queue

**Tenant bindings propagate** across Pi fleet via DTN bundles (`tenant-bindings.json`) and gossip (`tenant_snapshots`):

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/fleet/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/fleet/snapshots | jq '.count'
curl -X POST http://127.0.0.1:8887/api/convergence/dtn/gossip/round
```

**AI broadcast queue** — upkeep prepares Blurt `custom_json` manifests for local providers:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/ai/provider/broadcast/queue | jq .
```

Compute/AI submit auto-resolves `tenant_id` from `DTN_DEFAULT_TENANT` when omitted.

### Wave U — signed tenant fleet + dashboard UI + NPU inference + DTN auto-author

**HMAC-signed tenant snapshots** (reuses `AI_GOSSIP_SIGNING_KEY` when set):

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/fleet/sign/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/fleet/snapshots | jq '.snapshots[0].signature'
```

**Tenant dashboard web UI** at `/convergence/tenant` — per-author compute/bandwidth/storage caps.

**NPU-aware inference shim** — prefers ONNX on Hailo, TFLite on Coral:

```bash
curl -fsS http://127.0.0.1:8081/health | jq '.wave,.npu_runtimes,.delegates'
curl -fsS http://127.0.0.1:8081/v1/runtimes | jq .
```

**DTN export** auto-resolves `blurt_author` from tenant bindings when only `stone_address` is set.

### Wave V — tenant quorum + Blurt manifest broadcast + NPU execution

**Fleet quorum** — N-of-M signed tenant snapshots before bindings apply:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/fleet/quorum/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/fleet/quorum/snapshots | jq .
```

**Blurt tenant manifest** (`bloodstone_tenant_manifest/v1`) broadcast queue:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/broadcast/queue | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/tenant/broadcast \
  -H 'Content-Type: application/json' \
  -d '{"blurt_author":"meshops","flops_cap":5000000,"bandwidth_bytes_cap":100000000}'
curl -X POST http://127.0.0.1:8887/api/convergence/tenant/sync
```

**Hailo/Coral execution** in inference shim (not just detection):

```bash
curl -fsS http://127.0.0.1:8081/health | jq '.wave,.delegates,.npu_hardware'
```

### Wave W — submit quorum gate + tenant NPU models + dashboard quorum panel

**Compute/AI submit** checks fleet quorum when `TENANT_SUBMIT_QUORUM_REQUIRE=1`:

```bash
curl -fsS 'http://127.0.0.1:8887/api/convergence/tenant/submit/check?blurt_author=meshops' | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/quorum/author?blurt_author=meshops | jq .
```

**Per-author NPU model bindings** propagate via tenant manifests and inference shim:

```bash
curl -X POST http://127.0.0.1:8887/api/convergence/tenant/npu/bind \
  -H 'Content-Type: application/json' \
  -d '{"blurt_author":"meshops","runtime":"onnx","model_path":"/var/lib/bloodstone/models/edge.onnx","hardware_kind":"hailo"}'
curl -fsS 'http://127.0.0.1:8887/api/convergence/tenant/npu/resolve?blurt_author=meshops' | jq .
curl -X POST http://127.0.0.1:8081/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"blurt_author":"meshops","prompt":"tenant npu","max_tokens":32}'
```

Dashboard at `/convergence/tenant` shows quorum votes and NPU model rows per author.

### Wave X — tenant AI routing + manifest gossip + NPU model probe

**Tenant-aware AI routing** scores providers by NPU runtime/hardware match:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/ai/route/status | jq .
curl -fsS 'http://127.0.0.1:8887/api/convergence/tenant/ai/route/resolve?blurt_author=meshops' | jq .
```

**Tenant manifest gossip** propagates Blurt manifests across Pi fleet:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/manifest/gossip/status | jq .
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/manifest/gossip/snapshots | jq '.count'
```

**NPU model probe** validates ONNX/TFLite paths before bind:

```bash
curl -X POST http://127.0.0.1:8887/api/convergence/tenant/npu/probe \
  -H 'Content-Type: application/json' \
  -d '{"runtime":"onnx","model_path":"/var/lib/bloodstone/models/edge.onnx"}'
```

### Wave Y — route ledger + coordinator tenant dispatch + unified upkeep

**Route assignment ledger** tracks provider picks per tenant author:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/route/ledger/status | jq .
curl -fsS 'http://127.0.0.1:8887/api/convergence/tenant/route/ledger/assignments?blurt_author=meshops' | jq .
```

**Unified tenant upkeep** — quorum, gossip, broadcast queue in one cycle:

```bash
curl -fsS http://127.0.0.1:8887/api/convergence/tenant/upkeep/status | jq .
curl -X POST http://127.0.0.1:8887/api/convergence/tenant/upkeep/run
```

**NPU probe-on-bind** rejects invalid model paths (`TENANT_NPU_PROBE_ON_BIND=1`).

Coordinator dispatch now includes `tenant_route` + `blurt_author` for cross-node inference.

### Coordinator AI dispatch (Wave N)

When no local provider matches and uplink is stable, edge nodes HTTP-dispatch to the coordinator instead of queue-only fallback:

```bash
curl -fsS https://bloodstonewallet.mytunnel.org/api/convergence/ai/status | jq '.wave,.apis.dispatch,.apis.callback'
curl -X POST https://bloodstonewallet.mytunnel.org/api/convergence/ai/dispatch \
  -H 'Content-Type: application/json' \
  -d '{"job_id":"job-STONE1-infer-01","callback_url":"https://pi.example/api/convergence/ai/callback"}'
```

Android handsets can advertise AI via LAN heartbeat:

```bash
curl -X POST http://127.0.0.1:8887/api/lan/register \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"pixel-8-shed","lan_ip":"192.168.1.55","ai_runtimes":["tflite","cpu-inference"],"ai_inference_port":8090}'
```

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
- `bloodstone-ai-inference.service` — llama.cpp inference shim (:8081)
- `scripts/ai-inference-shim.sh` + `ai-inference-shim.py` — OpenAI-compatible proxy
- `bloodstone-dtn-mdns.service` — mDNS broadcaster
- `bloodstone-convergence-upkeep.service` + `.timer` — Blurt registry + credit sync