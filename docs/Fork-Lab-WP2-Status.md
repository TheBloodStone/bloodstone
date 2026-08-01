# Fork Lab WP2 Status — Catalog + MFQ two-speed

**Doc version:** 1.0  
**Date:** 2026-08-01  
**Spec:** [RFQ v1.5](https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-to-Launch-RFQ-v1.5.md) §6  
**Depends on:** WP1 provision + MFQ queue

## Status: **Shipped** (server path + MFQ 0.2.34 remote catalog)

| Piece | Status |
|-------|--------|
| Runtime catalog merge (fork_lab + WP1 + registry + packs) | **Live** |
| `GET /api/fork-lab/runtime-catalog` | **Live** (auto-refresh ≤5m) |
| T+0 daemon pack publish | **Live** · real packs for STONE/LRGK/AZURE; metadata packs for burn coins without binaries |
| mfq-daemons manifest v2 update | **Live** |
| Installer train tracker | **Live** · `mfq-installer-train.json` |
| MFQ client remote catalog | **0.2.34** (source tarball; Windows build separate) |
| systemd timer (15m) | **Live** · `fork-lab-wp2-catalog.timer` |

## Public promise (RFQ)

> Launch triggers catalog + daemon pack immediately; the MFQ installer train tags within ~24h.

**Never** rebuild the Multi-Fork Qt binary per coin.

## Two speeds

### T+0
1. Coin listed in `fork-lab-runtime-catalog.json`  
2. `/downloads/mfq-daemons/<TICKER>-win64.zip` published  
   - **Wallet-usable** when real node binaries exist (STONE / LRGK / AZURE today)  
   - **Metadata-only** pack (COIN/PAYMENT/conf/README) for burn-launched coins until offline Fork Builder / custom win64 attach — `usable_for_wallets: false`  
3. Manifest + installer-train pending updated  

### T+~24h (operator)
Tag next `bloodstone-multi-fork-qt-0.2.x` installer that bundles recent daemon packs (no per-coin Qt rebuild). Mark train shipped:

```bash
python3 /root/fork-lab-wp2/wp2_cli.py train-shipped --version 0.2.35
```

## CLI

```bash
cd /root/fork-lab-wp2
python3 wp2_cli.py catalog-rebuild
python3 wp2_cli.py process-queue
python3 wp2_cli.py publish-pack --ticker DEMO
python3 wp2_cli.py train-status
```

## APIs

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/fork-lab/runtime-catalog` | public |
| GET | `/api/fork-lab/wp2/installer-train` | public |
| POST | `/api/fork-lab/wp2/process-queue` | admin |
| POST | `/api/fork-lab/wp2/publish-pack` | admin |

## Artifacts

| File | URL |
|------|-----|
| Runtime catalog | https://bloodstone.rocks/downloads/fork-lab-runtime-catalog.json |
| Packs manifest | https://bloodstone.rocks/downloads/mfq-daemons/manifest.json |
| Installer train | https://bloodstone.rocks/downloads/mfq-installer-train.json |
| MFQ 0.2.34 source | https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.34.tar.gz |

## Framing

Metadata packs are **not** fake renamed bloodstoned binaries. Child coins without a real build stay non-wallet until a genuine pack is attached.

## Next (WP3+)

- WP3: registry repo auto-push bot  
- Attach real win64 builds for burn-launched tickers when Fork Builder outputs exist  
- Windows MFQ 0.2.34 installer rebuild when ready (source catalog change ships first)
