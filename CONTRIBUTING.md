# Contributing

## Regenerating the snapshot

Maintainers with access to the deployment VPS can refresh this tree:

```bash
./prepare-bloodstone-oss-repo.sh
git add -A
git commit -m "Sync snapshot $(date -u +%Y-%m-%d)"
```

The script copies source trees from `/root` while excluding secrets, keystores, `node_modules`, `venv`, and build artifacts.

## Publishing to GitHub

```bash
# Create an empty repo on GitHub (e.g. TheBloodStone/bloodstone), then:
git remote add origin git@github.com:TheBloodStone/bloodstone.git
git push -u origin main
```

Use a private fork first if any component still needs secret scrubbing review.

## Reporting issues

Open GitHub issues for:

- Android miner / local node bugs
- Mining API or stratum regressions
- Chain consensus or mesh federation problems
- Documentation gaps in `docs/`

Include APK version, web bundle version (`1.3.x-web`), and device model for mobile reports.