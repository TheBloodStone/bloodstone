# Blurt Pi Fleet Test — Install Instructions

**For:** @Anthony Fennell / Liquid Goblin (and Blurt ops)  
**Date:** July 8, 2026  
**Stack:** Wave G playbook + Waves H–Z convergence (v0.36.0-beta)  
**Coordinator:** https://bloodstonewallet.mytunnel.org

---

## What you are installing

A **Raspberry Pi edge node** that runs:

- **Bloodstone portal** on LAN HTTP port **8887** (convergence APIs + tenant dashboard)
- **DTN mesh** — offline bundle queue, mDNS peer discovery, TLS peer sync on **8443**
- **Memo rail enforcement** — storage / compute / bandwidth credits from Blurt memos
- **Background upkeep** — syncs Blurt registry, credits, gossip, WAN uplink handoff every ~5 min

This is the same stack described in the **Pi Fleet Playbook (Wave G)** — now bundled with the full convergence mesh through **Capstone Z**.

---

## Before you start

| Item | Requirement |
|------|-------------|
| Hardware | Raspberry Pi 4 or 5, **2 GB+ RAM** (4 GB recommended) |
| OS | **Raspberry Pi OS 64-bit (Bookworm)** or Ubuntu 22.04+ arm64 |
| Network | Wi-Fi or Ethernet on your LAN; brief internet for first install |
| Access | SSH into the Pi as a user with `sudo` |
| Optional | Your Blurt author name + STONE wallet address for memo-rail testing |

Pick a **unique node name** for this Pi, e.g. `blurt-pi-01` or `liquid-goblin-pi`.

---

## Step 1 — Download the convergence bundle

On the Pi (SSH session):

```bash
cd /tmp
curl -fsSLO https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz
curl -fsSLO https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz.sha256
sha256sum -c bloodstone-pi-fleet-convergence-latest.tar.gz.sha256
```

If the checksum fails, stop and contact Bloodstone ops — do not continue.

---

## Step 2 — Extract to `/root`

```bash
sudo mkdir -p /root
cd /
sudo tar -xzf /tmp/bloodstone-pi-fleet-convergence-latest.tar.gz
```

You should now have:

- `/root/bloodstone-portal/`
- `/root/chain_mesh/`
- `/root/ops/bloodstone-pi-fleet/`
- `/root/sync-blurt-convergence.py`
- `/root/setup-dtn-pi-tls.sh`

---

## Step 3 — Set your node identity

Replace `blurt-pi-01` with your chosen name and region label:

```bash
export DTN_NODE_ID=blurt-pi-01
export DTN_DEFAULT_REGION=blurt-lab
```

---

## Step 4 — Run the one-shot installer

```bash
sudo -E /root/ops/bloodstone-pi-fleet/bloodstone-pi-fleet-setup.sh
```

This script will:

1. Install system packages (`python3`, `avahi`, `openssl`, `jq`, etc.)
2. Create the portal Python virtualenv
3. Write `/etc/bloodstone/convergence.env` (memo enforcement **on**)
4. Enable systemd services: portal, mDNS, upkeep timer, TLS proxy, AI inference shim
5. Generate a self-signed TLS cert for HTTPS `:8443`

Expect **2–5 minutes** on a Pi 4.

---

## Step 5 — Verify the node is healthy

Run these on the Pi:

```bash
# Convergence stack alive + memo rails enforced
curl -fsS http://127.0.0.1:8887/api/convergence/status | jq '{ok, roadmap, storage: .storage_rail.enforce_quota, compute: .depin_rails.enforce_compute}'

# DTN + mDNS
curl -fsS http://127.0.0.1:8887/api/convergence/dtn/status | jq '{ok, node_id, wave, mdns: .mdns.enabled}'

# TLS proxy (self-signed cert — -k is expected on first test)
curl -kfsS https://127.0.0.1:8443/api/convergence/status | jq .ok

# AI inference shim (optional, Wave Q+)
curl -fsS http://127.0.0.1:8081/health | jq '{ok, wave}'
```

**Pass criteria:**

- `"ok": true` on convergence and DTN status
- `enforce_quota` / `enforce_compute` are **true**
- `node_id` matches your `DTN_NODE_ID`

---

## Step 6 — Open from another machine on your LAN

Find the Pi IP:

```bash
hostname -I
```

From a laptop on the same network:

```bash
curl -fsS http://<PI_IP>:8887/api/convergence/status | jq .roadmap
```

**Tenant dashboard (browser):** `http://<PI_IP>:8887/convergence/tenant`

---

## Step 7 — Register with the coordinator (optional but recommended)

Tell the public coordinator about your Pi so DTN gossip and handoff can find it.

Replace values with your Pi's LAN-reachable URL (or tunnel if you have one):

```bash
curl -fsS -X POST https://bloodstonewallet.mytunnel.org/api/convergence/dtn/peers/register \
  -H 'Content-Type: application/json' \
  -d '{
    "node_id": "blurt-pi-01",
    "base_url": "http://<PI_LAN_IP>:8887",
    "region": "blurt-lab"
  }'
```

If your Pi is reachable on HTTPS `:8443` from the internet (port-forward or tunnel), use that URL instead for `base_url`.

---

## Step 8 — Test memo rails (Wave G)

Send a small BLURT transfer on Blurt with a structured memo, then wait up to 5 minutes for upkeep to index it.

| Rail | Memo format | Example |
|------|-------------|---------|
| Storage | `storage:<STONE_ADDRESS>:<bytes>` | `storage:STONEabc123:1000000` |
| Compute | `compute:<STONE_ADDRESS>:<job_id>` | `compute:STONEabc123:test-job-001` |
| Bandwidth | `bandwidth:<STONE_ADDRESS>:<bytes>` | `bandwidth:STONEabc123:5000000` |

Check quota on the Pi:

```bash
curl -fsS "http://127.0.0.1:8887/api/convergence/storage/quota?stone_address=STONEabc123" | jq .
```

---

## Useful URLs

| Resource | URL |
|----------|-----|
| Pi fleet bundle | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz |
| Full playbook (MD) | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Pi-Fleet-Playbook-latest.md |
| Waves A–Z summary | https://bloodstonewallet.mytunnel.org/downloads/Blurt-Bloodstone-Waves-A-to-Z-Capstone-Summary.html |
| Coordinator status | https://bloodstonewallet.mytunnel.org/api/convergence/status |

---

## systemd services (for ops)

```bash
sudo systemctl status bloodstone-portal
sudo systemctl status bloodstone-dtn-mdns
sudo systemctl status bloodstone-dtn-tls
sudo systemctl status bloodstone-convergence-upkeep.timer
sudo systemctl status bloodstone-ai-inference
```

Logs:

```bash
journalctl -u bloodstone-portal -f
journalctl -u bloodstone-convergence-upkeep -n 50
```

Manual upkeep run:

```bash
sudo systemctl start bloodstone-convergence-upkeep.service
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `curl :8887` connection refused | `sudo systemctl restart bloodstone-portal` then check `journalctl -u bloodstone-portal` |
| `enforce_quota: false` | Check `/etc/bloodstone/convergence.env` has `STORAGE_CREDIT_ENFORCE=1` etc., then restart portal |
| mDNS not advertising | `sudo systemctl restart avahi-daemon bloodstone-dtn-mdns` |
| TLS `:8443` fails | `sudo /root/setup-dtn-pi-tls.sh` then `sudo systemctl restart bloodstone-dtn-tls` |
| No Blurt credits indexed | Confirm Pi has internet; wait 5 min for upkeep timer; check `BLURT_REGISTRY_RPC_NODES` in convergence.env |

---

## What to report back to Bloodstone

When your test is up, please send:

1. Your `DTN_NODE_ID`
2. Pi model + OS version (`uname -a`)
3. Output of: `curl -s http://127.0.0.1:8887/api/convergence/status | jq '{ok, roadmap, wave: .dtn.wave}'`
4. Whether LAN access from another device works
5. Any errors from `journalctl -u bloodstone-portal -n 30`

---

*Bloodstone LLC · Blurt x Bloodstone Convergence · Pi Fleet Playbook v0.36.0-beta*