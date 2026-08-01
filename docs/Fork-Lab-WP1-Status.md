# Fork Lab WP1 Status — Burn-triggered launch

**Doc version:** 1.1  
**Date:** 2026-08-01  
**Spec:** [RFQ v1.5](https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-to-Launch-RFQ-v1.5.md) §2–§3c · FL-1 · FL-2 · FL-3  
**Depends on:** WP0 burn addresses (`fork_lab_burn.py`) · §3c fee curve (`fork_lab_fee_curve.py`)

## Status: **Shipped** (vertical slice complete)

| Piece | Status |
|-------|--------|
| Fee freeze from §3c curve at draft open | **Live** |
| Keyless per-draft burn address (WP0) | **Live** |
| 48h open-minimum (10% of frozen fee) | **Live** |
| 90-day draft window + orphan expiry | **Live** |
| Watcher (confirmed cumulative UTXO sum) | **Live** · systemd timer every 5 min |
| Manual reconciliation (Decision #13) | **Live** · public API + portal form |
| Provision → `coins/<TICKER>/` (COIN + PAYMENT v2) | **Live** |
| Seed-registry stub | **Live** · downloads + `/var/lib` |
| Runtime catalog + MFQ daemon-pack queue | **Live** (T+0 queue; pack build still operator) |
| Portal draft UI (burn path default) | **Live** on `/fork-lab/` |
| Portal APIs | **Live** under `/api/fork-lab/wp1/*` |

## Operator CLI

```bash
cd /root/fork-lab-wp1
python3 wp1_cli.py fee-quote
python3 wp1_cli.py draft-open --ticker DEMO --name "Demo" --creator S…
python3 wp1_cli.py watch-once
python3 wp1_cli.py reconcile --draft-id d-… --txid <hex> [--auto-provision]
python3 wp1_cli.py get-draft --draft-id d-…
python3 wp1_cli.py provision --draft-id d-…
python3 wp1_cli.py expire
```

## systemd

| Unit | Role |
|------|------|
| `fork-lab-wp1-watch.timer` | Every 5 minutes |
| `fork-lab-wp1-watch.service` | Oneshoot `watch-once` (+ auto-provision when funded) |

```bash
systemctl status fork-lab-wp1-watch.timer
journalctl -u fork-lab-wp1-watch.service -n 50
```

## Portal API

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/fork-lab/wp1/draft-open` | public |
| GET | `/api/fork-lab/wp1/drafts` | public |
| GET | `/api/fork-lab/wp1/drafts/<id>` | public |
| POST | `/api/fork-lab/wp1/reconcile` | public (draft_id / burn txids) |
| GET | `/api/fork-lab/runtime-catalog` | public |
| POST | `/api/fork-lab/wp1/watch-once` | admin |
| POST | `/api/fork-lab/wp1/expire` | admin |
| POST | `/api/fork-lab/wp1/provision` | admin |
| GET | `/api/fork-lab/fee-curve` | public |

## Status machine

`open` → `funding` (≥ open-min) → `funded` (≥ frozen fee) → `provisioning` → `live`

or `lapsed` (missed 48h open-min) / `expired` (missed 90-day full fee; burns orphaned)

## Artifacts on provision

```
bloodstone-fork-registry/coins/<TICKER>/
  PAYMENT.json     # immutable v2 receipt + burn_txs
  COIN.json        # salt / magic / ports (derived)
  conf/<ticker>.conf.example
  identity.json
  README.md
```

Plus:
- `/var/www/bloodstone/downloads/fork-lab-runtime-catalog.json`
- `/var/lib/bloodstone/fork_lab_mfq_queue.jsonl` (daemon pack queue)
- `/var/www/bloodstone/downloads/fork-lab-seed-registry-stub.json`

## Framing

Watcher + provisioner are **automation with write access**, not a trustless light client. Public framing: **burn-triggered automated launch**.

## Explicitly out of WP1 (next packages)

| Package | Notes |
|---------|--------|
| **WP0 skeptic run** | Needs an **external** machine — not this VPS (audit-adjacent) |
| **WP1.5 fee curve** | Already shipped (`/api/fork-lab/fee-curve`; inert until step boundary) |
| **WP2** | Full MFQ two-speed delivery (daemon pack zip + installer train) |
| **WP3** | Registry repo auto-push bot |
| **WP4** | Lifecycle ledger + vitality dashboard |

## Links

- RFQ: https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-to-Launch-RFQ-v1.5.md  
- WP0 skeptic: https://bloodstone.rocks/downloads/Fork-Lab-WP0-Skeptic-Run.md  
- Constitution: https://bloodstone.rocks/downloads/Bloodstone-Protocol-Constitution-v1.3.md  
- Source: https://github.com/Bloodstone-Team/bloodstone (`fork-lab-wp1/`)
