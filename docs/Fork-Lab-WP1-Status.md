# Fork Lab WP1 Status — Burn-triggered launch

**Doc version:** 1.0  
**Date:** 2026-08-01  
**Spec:** [RFQ v1.5](https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-to-Launch-RFQ-v1.5.md) §2–§3c · FL-1 · FL-2 · FL-3  
**Depends on:** WP0 burn addresses (`fork_lab_burn.py`)

## What shipped

| Piece | Status |
|-------|--------|
| Fee freeze from §3c curve at draft open | **Live** |
| Keyless per-draft burn address (WP0) | **Live** |
| 48h open-minimum (10% of frozen fee) | **Live** |
| 90-day draft window + orphan expiry | **Live** |
| Watcher (confirmed cumulative UTXO sum) | **Live** (operator/cron) |
| Provision → `coins/<TICKER>/` registry | **Live** (funded drafts) |
| Portal draft UI (burn path default) | **Live** on `/fork-lab/` |
| Portal APIs | **Live** under `/api/fork-lab/wp1/*` |

## Operator CLI

```bash
cd /root/fork-lab-wp1
python3 wp1_cli.py fee-quote
python3 wp1_cli.py draft-open --ticker DEMO --name "Demo" --creator S…
python3 wp1_cli.py watch-once
python3 wp1_cli.py get-draft --draft-id d-…
python3 wp1_cli.py provision --draft-id d-…
python3 wp1_cli.py expire
```

## Portal API

| Method | Path |
|--------|------|
| POST | `/api/fork-lab/wp1/draft-open` |
| GET | `/api/fork-lab/wp1/drafts` |
| GET | `/api/fork-lab/wp1/drafts/<draft_id>` |
| POST | `/api/fork-lab/wp1/watch-once` (admin) |
| POST | `/api/fork-lab/wp1/expire` (admin) |
| POST | `/api/fork-lab/wp1/provision` (admin) |
| GET | `/api/fork-lab/fee-curve` |

## Status machine

`open` → `funding` (≥ open-min) → `funded` (≥ frozen fee) → `live` (provisioned)

or `lapsed` (missed 48h open-min) / `expired` (missed 90-day full fee; burns orphaned)

## Framing

Watcher + provisioner are **automation with write access**, not a trustless light client. Public framing: **burn-triggered automated launch**.

## Not in this slice

- Full dual-job merge path into legacy `fork_coins` table  
- Auto-cron systemd unit (run `watch-once` via operator schedule)  
- Early-bird / free-code on burn path (still legacy treasury create)

## Links

- RFQ: https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-to-Launch-RFQ-v1.5.md  
- WP0 skeptic: https://bloodstone.rocks/downloads/Fork-Lab-WP0-Skeptic-Run.md  
- Constitution: https://bloodstone.rocks/downloads/Bloodstone-Constitution-v1.3.md  
- Source: https://github.com/Bloodstone-Team/bloodstone (fork-lab-wp1/)
