# Raspberry Pi fleet — Blurt convergence bundle {#pi-fleet}

**Version:** v0.36.0-beta (Wave G through Capstone Z)  
**Coordinator:** https://bloodstonewallet.mytunnel.org  
**Downloads:** https://bloodstonewallet.mytunnel.org/downloads/#pi-fleet

---

## Overview

**Blurt / edge Pi test?** Download the **convergence software bundle** — portal + chain mesh + DTN helpers + fleet setup scripts.

The bundle extracts to `/root/` and installs:

- `bloodstone-portal/` — convergence APIs + tenant dashboard (LAN `:8887`)
- `chain_mesh/` — mesh storage, DTN forward queue, gossip
- `ops/bloodstone-pi-fleet/` — setup scripts, systemd units, playbook
- DTN sync helpers (`sync-blurt-convergence.py`, mDNS, TLS proxy)

---

## One-line install (on the Pi)

```bash
curl -fsSLO https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz
sudo tar -xzf bloodstone-pi-fleet-convergence-latest.tar.gz -C /
export DTN_NODE_ID=blurt-pi-01
sudo -E /root/ops/bloodstone-pi-fleet/bloodstone-pi-fleet-setup.sh
```

Replace `blurt-pi-01` with a unique node name for your Pi.

---

## After setup

| Check | Command |
|-------|---------|
| Portal (LAN) | `http://<pi-ip>:8887` |
| Convergence status | `curl -fsS http://127.0.0.1:8887/api/convergence/status` |
| WAN uplink handoff (Wave I) | `curl -fsS http://127.0.0.1:8887/api/convergence/dtn/uplink/status` |

Set `DTN_UPLINK_INTERFACE=eth1` (or `wwan0`, `wlan0`) when you want handoff only while a specific NIC is up. `DTN_STARLINK_INTERFACE` is a legacy alias.

---

## Downloads

| File | URL |
|------|-----|
| **Software bundle (latest)** | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz |
| Versioned bundle | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-fleet-convergence-0.36.0-beta.tar.gz |
| SHA256 | https://bloodstonewallet.mytunnel.org/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz.sha256 |
| **Install walkthrough** | https://bloodstonewallet.mytunnel.org/downloads/Blurt-Pi-Fleet-Install-Instructions.md |
| **Pi fleet playbook** | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Pi-Fleet-Playbook-latest.md |
| Waves A–Z capstone | https://bloodstonewallet.mytunnel.org/downloads/Blurt-Bloodstone-Waves-A-to-Z-Capstone-Summary.md |

### Optional: ARM64 chain node only

Headless `bloodstoned` + `bloodstone-cli` for chain sync on Pi 4/5 — separate from the fleet convergence bundle:

https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-linux-aarch64-latest.tar.gz

### LAN hashrate forwarder

Run on a Pi or PC on the same LAN as ASIC miners:

https://bloodstonewallet.mytunnel.org/downloads/install-lan-miner-forwarder.sh

---

## Build from source (maintainers)

```bash
/root/build-bloodstone-pi-fleet-convergence-package.sh 0.36.0-beta
```

Playbook source: `ops/bloodstone-pi-fleet/README.md` in this repository.

---

## Related docs

- [Blurt Pi Fleet Install Instructions](Blurt-Pi-Fleet-Install-Instructions.md)
- [Blurt Starlink / WAN handoff response](Blurt-Starlink-Handoff-Response.md) — uplink handoff is interface-agnostic
- [Waves A–Z Capstone Summary](Blurt-Bloodstone-Waves-A-to-Z-Capstone-Summary.md)

---

*Bloodstone LLC · Pi fleet convergence bundle · v0.36.0-beta*