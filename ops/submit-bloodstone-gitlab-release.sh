#!/usr/bin/env bash
# Gated GitLab release submission — never runs from ordinary build scripts unless opted in.
#
# Usage:
#   ./submit-bloodstone-gitlab-release.sh 0.7.3
#   ./submit-bloodstone-gitlab-release.sh 0.7.3 --notes "Qt wallet + beta channels"
#   BLOODSTONE_GITLAB_DRY_RUN=1 ./submit-bloodstone-gitlab-release.sh 0.7.3
#
# Credentials (chmod 600): /root/.bloodstone/gitlab.credentials
#   GITLAB_TOKEN=glpat-...   # required — GitLab no longer accepts account passwords for git push
#   GITLAB_HTTPS_URL=https://gitlab.com/TheBloodStone/bloodstone.git
set -euo pipefail

VERSION="${1:-}"
NOTES="${BLOODSTONE_RELEASE_NOTES:-}"
FORCE="${BLOODSTONE_GITLAB_FORCE:-0}"
DRY_RUN="${BLOODSTONE_GITLAB_DRY_RUN:-0}"
REPO="${BLOODSTONE_OSS_REPO:-/root/bloodstone-repo}"
BRANCH="${BLOODSTONE_GIT_BRANCH:-main}"
PREPARE="${BLOODSTONE_GITLAB_PREPARE:-1}"
PUSH_GITHUB="${BLOODSTONE_GITLAB_PUSH_GITHUB:-0}"

source /root/bloodstone-gitlab-lib.sh

log() { echo "[gitlab-submit] $*" >&2; }

usage() {
  cat <<'EOF' >&2
Usage: submit-bloodstone-gitlab-release.sh <version> [--notes "message"] [--force]

Submits a Bloodstone OSS snapshot to GitLab (tagged release). Gated so ordinary
build attempts do not push. Skips if the same version was already submitted unless --force.

Requires GITLAB_TOKEN in /root/.bloodstone/gitlab.credentials (Personal Access Token
with write_repository scope). Account passwords are not accepted by GitLab for git push.

Optional:
  BLOODSTONE_GITLAB_MIN_HOURS=6     Minimum hours between submissions (default 6)
  BLOODSTONE_GITLAB_DRY_RUN=1       Show actions without pushing
  BLOODSTONE_GITLAB_PUSH_GITHUB=1   Also push to GitHub remote
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage ;;
    --force) FORCE=1; shift ;;
    --notes)
      NOTES="${2:-}"
      shift 2
      ;;
    *)
      if [[ -z "$VERSION" ]]; then
        VERSION="$1"
      fi
      shift
      ;;
  esac
done

[[ -n "$VERSION" ]] || usage
[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+)+([-.][0-9A-Za-z]+)?$ ]] || {
  log "invalid version: $VERSION"
  exit 1
}

bloodstone_gitlab_load_credentials
if [[ -z "${GITLAB_TOKEN:-}" && "$DRY_RUN" != "1" ]]; then
  log "ERROR: GITLAB_TOKEN missing in $(bloodstone_gitlab_credentials_file)"
  log "Create a token: GitLab → Preferences → Access Tokens → write_repository"
  log "Then add: GITLAB_TOKEN=glpat-... to the credentials file"
  exit 1
fi

if [[ "$FORCE" != "1" ]]; then
  if [[ "$(bloodstone_gitlab_already_submitted "$VERSION")" == "yes" ]]; then
    log "skip — version $VERSION already submitted (use --force to override)"
    exit 0
  fi
  if bloodstone_gitlab_too_soon; then
    log "skip — last submission was less than $(bloodstone_gitlab_min_hours_between)h ago (use --force)"
    exit 0
  fi
fi

TAG="v${VERSION}"
COMMIT_MSG="Release ${VERSION}"
if [[ -n "$NOTES" ]]; then
  COMMIT_MSG="${COMMIT_MSG}: ${NOTES}"
else
  COMMIT_MSG="${COMMIT_MSG} — OSS snapshot $(date -u +%Y-%m-%d)"
fi

if [[ "$PREPARE" == "1" && -x /root/prepare-bloodstone-oss-repo.sh ]]; then
  log "preparing OSS snapshot..."
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] would run prepare-bloodstone-oss-repo.sh"
  else
    /root/prepare-bloodstone-oss-repo.sh
  fi
fi

[[ -d "$REPO/.git" ]] || { log "missing git repo at $REPO"; exit 1; }
cd "$REPO"

GITLAB_URL="$(bloodstone_gitlab_auth_url)"
if [[ "$DRY_RUN" == "1" ]]; then
  log "[dry-run] would push tag ${TAG} to GitLab (${GITLAB_HTTPS_URL})"
  log "[dry-run] commit message: ${COMMIT_MSG}"
  exit 0
fi

if ! git remote get-url gitlab &>/dev/null; then
  git remote add gitlab "$GITLAB_URL"
else
  git remote set-url gitlab "$GITLAB_URL"
fi

if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -m "$COMMIT_MSG"
elif ! git rev-parse "HEAD^{commit}" >/dev/null 2>&1; then
  git add -A
  git commit -m "$COMMIT_MSG" --allow-empty
fi

COMMIT_SHA="$(git rev-parse HEAD)"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  log "tag $TAG exists locally — moving to $COMMIT_SHA"
  git tag -f "$TAG"
else
  git tag -a "$TAG" -m "$COMMIT_MSG"
fi

log "pushing $BRANCH -> gitlab"
git push -u gitlab "$BRANCH"
log "pushing tag $TAG -> gitlab"
git push -u gitlab "$TAG"

if [[ "$PUSH_GITHUB" == "1" && -x /root/push-bloodstone-oss.sh ]]; then
  log "also pushing to GitHub"
  BLOODSTONE_GIT_BRANCH="$BRANCH" /root/push-bloodstone-oss.sh
fi

bloodstone_gitlab_record_submission "$VERSION" "$TAG" "$COMMIT_SHA"
log "done — GitLab updated for release $VERSION ($TAG @ ${COMMIT_SHA:0:12})"