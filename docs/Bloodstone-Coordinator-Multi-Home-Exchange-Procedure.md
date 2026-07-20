# Bloodstone Coordinator Multi-Home Status — Exchange / Partner Procedure

**Document version:** 1.0 · July 2026  
**Status:** Live procedure for **Phase 2 / G2** multi-homed tip policy polling  
**Related:**  
- [Ops topology v1.1](Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md)  
- [Live implementation notes](Bloodstone-Coordinator-Federation-Live-Implementation.md)  
- [Fee plan](Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md)  

**Public copy:**  
https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Coordinator-Multi-Home-Exchange-Procedure.md  

---

## 1. Purpose

Exchanges and partners must **not** depend on a single HTTP origin for tip / policy signals. This document defines how to poll **≥2** coordinator status endpoints, compare tips, and apply conservative deposit policy on disagreement or outage.

**This is policy guidance**, not consensus. Nodes still follow most-work / braid rules on their own full node for deposit credit decisions when possible.

---

## 2. Public endpoints (current multi-home set)

| Role | Base | Status URL | Identity |
|------|------|------------|----------|
| **COORD-A** (primary brand) | https://bloodstonewallet.mytunnel.org | `/api/coordinator/status` (tip under `.tip`) **or** `/api/quasar/status` (full QUASAR) | `coord-a-primary` |
| **COORD-B** (lean peer) | https://LRGK.mytunnel.org | `/api/quasar/status` **or** `/api/coordinator/status` | `coord-b-lrgk-01` |

**Machine-readable roster** (signed; may list more members later):  
https://bloodstonewallet.mytunnel.org/downloads/coordinator-roster-latest.json  

**Fee schedule** (informational; open join still gated):  
https://bloodstonewallet.mytunnel.org/downloads/coordinator-fee-schedule-latest.json  

---

## 3. Normalized tip extraction

| Source | Height field | Tip hash field |
|--------|--------------|----------------|
| A `/api/coordinator/status` | `.tip.height` | `.tip.bestblockhash` |
| B `/api/quasar/status` | `.height` or `.tip_height` | `.bestblockhash` or `.tip_hash` |
| A `/api/quasar/status` | Use chain/tip fields if present; prefer coordinator status for simple multi-home | — |

Always lowercase hex hashes before compare. Reject peer if HTTP ≥ 400, timeout, or missing height/hash.

---

## 4. Client algorithm (normative)

```
healthy = []
for each endpoint in roster_or_bootstrap_list:
    fetch JSON with timeout (recommend 5–15s)
    if success and parse tip (height, hash):
        healthy.append(peer)

if len(healthy) < 2:          # C_min default
    status = DEGRADED
    action = raise deposit confirms or halt large deposits

# lag filter: drop peers more than L_max (default 6) blocks behind max height among healthy
max_h = max(p.height for p in healthy)
healthy = [p for p in healthy if max_h - p.height <= 6]

# majority tip hash among remaining
if all same tip hash:
    status = LIVE_AGREE
    action = use standard braid / exchange policy from your node + optional QUASAR fields from A when available
elif disagree:
    status = SPLIT
    action = HALT large deposits until majority stable ≥ 15 minutes
```

**Parameters (defaults from federation design):**

| Symbol | Default | Meaning |
|--------|---------|---------|
| `C_min` | 2 | Min healthy status peers |
| `L_max` | 6 | Max lag vs median/max height |
| `W_req` | 3 | Witness quorum for “live” (mesh capsules; independent of HTTP multi-home) |

---

## 5. Policy mapping

| Condition | Deposit / credit policy |
|-----------|-------------------------|
| ≥2 peers healthy, same tip | Normal (your braid/confirmations policy) |
| 1 peer healthy only | **Degraded** — raise confirms; delay large deposits |
| 0 peers healthy | **Halt** new large deposits until recovery |
| Peers disagree on tip hash | **Halt** large deposits; investigate |
| A returns 5xx, B OK | Use B tip for **observational** multi-home; still verify on **your own node** before credit |

**Never** credit deposits solely because a coordinator HTTP API said so. Prefer:

1. Your own `bloodstoned` / exchange node tip  
2. Multi-home coordinator agreement as **supporting** signal  
3. QUASAR witness quorum when available (`W_req`)

---

## 6. Example: curl multi-home check

```bash
#!/usr/bin/env bash
set -euo pipefail
A=$(curl -fsS --max-time 12 https://bloodstonewallet.mytunnel.org/api/coordinator/status)
B=$(curl -fsS --max-time 12 https://LRGK.mytunnel.org/api/quasar/status)
python3 - <<'PY'
import json,sys
A=json.loads("""$A""")
B=json.loads("""$B""")
# safer: pass via files
PY
```

Prefer the shipped helper:

```bash
python3 /root/coord-multi-home-check.py
# or from downloads after publish:
# curl -fsS https://bloodstonewallet.mytunnel.org/downloads/coord-multi-home-check.py | python3
```

---

## 7. Kill-A drill (executed 2026-07-11)

| Step | Result |
|------|--------|
| Stop `bloodstone-portal` on COORD-A | A `/api/coordinator/status` → **502** |
| Poll B | https://LRGK.mytunnel.org/api/quasar/status → **200**, tip 10834, device `coord-b-lrgk-01` |
| Restart portal | A recovered **200** |

**Conclusion:** Multi-home status path survives primary portal outage for **read tip** from B. Pool/ElectrumX/brand site on A may still be down during full A host failure — status multi-home ≠ full site multi-home.

---

## 8. Bootstrap list for integrators

Hardcode or config-pin at least:

```json
{
  "endpoints": [
    {
      "id": "coord-a-primary",
      "base_url": "https://bloodstonewallet.mytunnel.org",
      "status_path": "/api/coordinator/status",
      "tip_style": "coordinator"
    },
    {
      "id": "coord-b-lrgk-01",
      "base_url": "https://LRGK.mytunnel.org",
      "status_path": "/api/quasar/status",
      "tip_style": "quasar_peer"
    }
  ],
  "c_min": 2,
  "l_max": 6,
  "roster_url": "https://bloodstonewallet.mytunnel.org/downloads/coordinator-roster-latest.json"
}
```

Refresh members from signed roster when G4 client pin ships; until then, use this static list plus roster as advisory.

---

## 9. Honesty / claim guardrails

| Allowed | Forbidden |
|---------|-----------|
| “Partners should poll A and B status URLs” | “Decentralized multi-operator federation complete” |
| “Status multi-home survives portal A outage” | “Network survives full A host loss for pool/downloads” |
| “Two device_ids emit witnesses” | “O_min multi-operator met” (still one `operator_id`) |

---

## 10. Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-11 | Initial multi-home procedure; kill-A portal drill recorded |

---

*Bloodstone LLC · Exchange multi-home status procedure · G2 support artifact*
