# Fork Lab WP1 — Burn-triggered launch pipeline

**Status:** Active build (demand acknowledged 2026-08-01)  
**Spec:** RFQ v1.5 §2 · FL-1 · FL-3  
**Depends on:** WP0 (`fork_lab_burn.py`) complete

## Components

| Module | Role |
|--------|------|
| `wp1_db.py` | Draft + burn-watch state (SQLite) |
| `wp1_draft.py` | Create/validate draft, freeze fee, issue burn address |
| `wp1_watcher.py` | Sum confirmed UTXOs to draft burn address; fire at threshold |
| `wp1_provision.py` | Write `coins/<TICKER>/` artifacts into registry repo |
| `wp1_cli.py` | Operator CLI |

## Happy path (CLI)

```bash
# 1) Open draft (validates ticker, freezes fee, prints burn address)
python3 wp1_cli.py draft-open --ticker DEMO --name "Demo Coin" --creator S...

# 2) Watcher tick (scan STONE chain for payments to open drafts)
python3 wp1_cli.py watch-once

# 3) When funded: provision registry row
python3 wp1_cli.py provision --draft-id <id>
```

## Not trustless

Watcher + provisioner are automation with repo write access. Framing: **burn-triggered automated launch**.
