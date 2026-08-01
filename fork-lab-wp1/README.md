# Fork Lab WP1 — Burn-triggered launch pipeline

**Status:** Active (fee freeze + 48h open-min + expiry + portal API)  
**Spec:** RFQ v1.5 §2–§3c · FL-1 · FL-2 · FL-3  
**Depends on:** WP0 (`fork_lab_burn.py`) complete · `fork_lab_fee_curve.py` (§3c)

## Components

| Module | Role |
|--------|------|
| `wp1_db.py` | Draft + burn-watch state (SQLite) |
| `wp1_draft.py` | Freeze fee from §3c curve, issue burn address, 48h open-min deadline |
| `wp1_watcher.py` | Sum confirmed UTXOs; open-min / fund / lapse / expire orphans |
| `wp1_provision.py` | Write `coins/<TICKER>/` artifacts into registry repo |
| `wp1_cli.py` | Operator CLI |

## Rules (locked)

1. **Fee freeze at draft** — `fork_lab_fee_curve.current_requirement()` is snapshotted into `fee_freeze_json`; later decay cannot change the bill.
2. **48h open-minimum** — ≥ 10% of frozen fee confirmed within 48h or status → `lapsed` (ticker frees).
3. **90-day window** — full frozen fee or status → `expired` (burns orphaned, no coin).
4. **Keyless burn** — WP0 P2PKH v63 address; no refund path.
5. **Cumulative total only** — no payer ledger.

## Happy path (CLI)

```bash
# Fee quote (live curve, not frozen)
python3 wp1_cli.py fee-quote

# 1) Open draft (freezes fee, prints burn address)
python3 wp1_cli.py draft-open --ticker DEMO --name "Demo Coin" --creator S...

# 2) Watcher tick (scan STONE chain; apply open-min / fund / expire)
python3 wp1_cli.py watch-once

# 3) Inspect
python3 wp1_cli.py get-draft --draft-id <id>
python3 wp1_cli.py list-drafts

# 4) When funded: provision registry row
python3 wp1_cli.py provision --draft-id <id>

# Orphan / open-min only
python3 wp1_cli.py expire
```

Env:
- `FORK_LAB_WP1_DB` — SQLite path (default `/var/lib/bloodstone/fork_lab_wp1.db`)
- `FORK_LAB_BURN_MIN_CONFS` — default `6`
- `FORK_LAB_WP1_AUTO_PROVISION` — `1` to provision immediately on fund
- `FORK_LAB_FEE_DECAY` — `1` enables §3c decay (else START)

## Portal API

| Method | Path | Auth |
|--------|------|------|
| POST | `/api/fork-lab/wp1/draft-open` | public |
| GET | `/api/fork-lab/wp1/drafts` | public |
| GET | `/api/fork-lab/wp1/drafts/<id>` | public |
| POST | `/api/fork-lab/wp1/watch-once` | admin |
| POST | `/api/fork-lab/wp1/expire` | admin |
| POST | `/api/fork-lab/wp1/provision` | admin |
| GET | `/api/fork-lab/fee-curve` | public |

UI: `/fork-lab/` create panel defaults to **Burn-to-launch**.

## Status values

`open` → `funding` (≥ open-min) → `funded` (≥ fee) → `live` (provisioned)  
or `lapsed` (48h miss) / `expired` (90d miss, orphans)

## Not trustless

Watcher + provisioner are automation with repo write access. Framing: **burn-triggered automated launch**.
