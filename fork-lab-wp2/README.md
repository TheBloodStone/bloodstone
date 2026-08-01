# Fork Lab WP2 — Catalog + MFQ two-speed delivery

**Status:** Active  
**Spec:** RFQ v1.5 §6 · build phasing WP2  
**Depends on:** WP1 provision + MFQ queue

## Two-speed promise

1. **T+0** — coin appears in runtime catalog; daemon pack zip published (real binary or metadata pack).  
2. **T+~24h** — MFQ installer train (`bloodstone-multi-fork-qt-0.2.x`) bundles recent packs.  
3. **Never** rebuild the MFQ Qt binary per coin.

## CLI

```bash
cd /root/fork-lab-wp2
python3 wp2_cli.py catalog-rebuild
python3 wp2_cli.py process-queue
python3 wp2_cli.py publish-pack --ticker LRGK
python3 wp2_cli.py train-status
```

## Public artifacts

| Artifact | Path / URL |
|----------|------------|
| Runtime catalog | `/downloads/fork-lab-runtime-catalog.json` |
| Daemon packs | `/downloads/mfq-daemons/<TICKER>-win64.zip` |
| Pack manifest v2 | `/downloads/mfq-daemons/manifest.json` |
| Installer train | `/downloads/mfq-installer-train.json` |

## APIs

- `GET /api/fork-lab/runtime-catalog`
- `POST /api/fork-lab/wp2/process-queue` (admin)
- `GET /api/fork-lab/wp2/installer-train`
