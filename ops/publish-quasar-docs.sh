#!/usr/bin/env bash
# Publish QUASAR marketing + exchange docs to /downloads and sync worker.
set -euo pipefail

DOCS="/root/bloodstone-docs"
OUT="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
PUBLIC="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"

log() { echo "[quasar-publish] $*"; }

mkdir -p "$OUT"

if [[ -f "$DOCS/generate-quasar-exchange-onepager-doc.js" ]]; then
  log "generating exchange one-pager DOCX..."
  (cd "$DOCS" && node generate-quasar-exchange-onepager-doc.js) || log "docx gen skipped"
fi

if [[ -f "$DOCS/generate-quasar-51-defense-whitepaper-doc.js" ]]; then
  log "generating full white paper DOCX..."
  (cd "$DOCS" && node generate-quasar-51-defense-whitepaper-doc.js) || log "whitepaper docx skipped"
fi

FILES=(
  Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md
  Bloodstone-QUASAR-51-Percent-Defense-White-Paper.docx
  Bloodstone-QUASAR-Exchange-One-Pager.md
  Bloodstone-QUASAR-Exchange-One-Pager.docx
  Bloodstone-QUASAR-Social-Thread.md
  Bloodstone-QUASAR-Social-Thread.txt
  Bloodstone-QUASAR-Exchange-One-Pager.html
)

for f in "${FILES[@]}"; do
  if [[ -f "$DOCS/$f" ]]; then
    cp -f "$DOCS/$f" "$OUT/$f"
    if [[ -f "$OUT/$f" ]]; then
      sha256sum "$OUT/$f" | awk '{print $1}' > "$OUT/${f}.sha256"
    fi
    log "  $f"
  fi
done

if command -v pandoc >/dev/null 2>&1 && [[ -f "$OUT/Bloodstone-QUASAR-Exchange-One-Pager.md" ]]; then
  pandoc "$OUT/Bloodstone-QUASAR-Exchange-One-Pager.md" \
    -o "$OUT/Bloodstone-QUASAR-Exchange-One-Pager.pdf" \
    --pdf-engine=pdflatex 2>/dev/null \
    && sha256sum "$OUT/Bloodstone-QUASAR-Exchange-One-Pager.pdf" | awk '{print $1}' > "$OUT/Bloodstone-QUASAR-Exchange-One-Pager.pdf.sha256" \
    && log "  Bloodstone-QUASAR-Exchange-One-Pager.pdf" \
    || log "PDF skipped (pandoc/pdflatex)"
fi

if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
  /root/sync-bloodstone-downloads-to-worker.sh "${FILES[@]/#/$OUT/}" "$OUT/Bloodstone-QUASAR-Exchange-One-Pager.pdf" 2>/dev/null || true
fi

log "QUASAR hub: ${PUBLIC}/quasar/"
log "Downloads: ${PUBLIC}/downloads/"