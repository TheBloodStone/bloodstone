# Contributing

## Regenerating the snapshot

Maintainers with access to the deployment VPS can refresh this tree:

```bash
./prepare-bloodstone-oss-repo.sh
git add -A
git commit -m "Sync snapshot $(date -u +%Y-%m-%d)"
```

The script copies source trees from `/root` while excluding secrets, keystores, `node_modules`, `venv`, and build artifacts.

## Publishing to GitHub and GitLab

Default remotes (configured by `/root/push-bloodstone-oss.sh` on the maintainer VPS):

| Remote | URL |
|--------|-----|
| `github` | `git@github.com:TheBloodStone/bloodstone.git` |
| `gitlab` | `git@gitlab.com:TheBloodStone/bloodstone.git` |

### Option A — deploy key (recommended for VPS)

1. Create **empty** repos on GitHub and GitLab (no README/license — repo must be empty).
2. Add the public key in `DEPLOY_KEY.pub` as a **deploy key with write access** on both hosts.
3. On the VPS:

```bash
/root/push-bloodstone-oss.sh
```

### Option B — personal access tokens (one-shot push)

```bash
export GITHUB_TOKEN=ghp_...
export GITLAB_TOKEN=glpat-...
/root/push-bloodstone-oss.sh
```

Override URLs if your org/path differs:

```bash
BLOODSTONE_GITHUB_URL=git@github.com:YourOrg/bloodstone.git \
BLOODSTONE_GITLAB_URL=git@gitlab.com:yourgroup/bloodstone.git \
/root/push-bloodstone-oss.sh
```

Use a private fork first if any component still needs secret scrubbing review.

## Reporting issues

Open GitHub issues for:

- Android miner / local node bugs
- Mining API or stratum regressions
- Chain consensus or mesh federation problems
- Documentation gaps in `docs/`

Include APK version, web bundle version (`1.3.x-web`), and device model for mobile reports.