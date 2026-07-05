/** Admin controls for Time Capsule archive + optional local prune. */

function apiUrl(path) {
  const prefix = document.body?.dataset?.urlPrefix || "";
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${prefix}${normalized}`;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function formatBytes(n) {
  const b = Number(n) || 0;
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KiB`;
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GiB`;
}

async function refreshTimeCapsuleStatus() {
  const statusEl = document.getElementById("time-capsule-status");
  if (!statusEl) return;
  try {
    const res = await fetch(apiUrl("/api/chain-mesh/time-capsule/status"), { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) {
      statusEl.textContent = data.error || "Failed to load status";
      return;
    }
    const cov = data.coverage || {};
    const ready = data.prune_readiness || {};
    const lines = [
      `Height ${data.block_height} · archive ${data.capsule_complete ? "complete" : "incomplete"} (${cov.have || 0}/${cov.need || 0} chunks)`,
      `Blocks on disk: ${formatBytes(data.blocks_bytes)} · pruned: ${data.pruned ? "yes" : "no"} · txindex: ${data.txindex_enabled ? "on" : "off"}`,
      `Mesh peers: ${data.mesh_peers?.active_peers || 0} devices · ${data.mesh_peers?.peer_unique_chunks || 0} chunk replicas`,
    ];
    if (!data.pruned && data.potential_savings_bytes > 0) {
      lines.push(`Potential local savings after prune: ~${formatBytes(data.potential_savings_bytes)}`);
    }
    if (ready.blockers?.length) {
      lines.push(`Prune blockers: ${ready.blockers.join("; ")}`);
    } else if (ready.ready) {
      lines.push("Prune ready — confirm below to enable local prune mode.");
    }
    statusEl.textContent = lines.join("\n");
  } catch (err) {
    statusEl.textContent = err.message || String(err);
  }
}

async function postCapsuleAction(path, body, resultId) {
  setText(resultId, "Working…");
  try {
    const res = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    setText(resultId, data.ok ? JSON.stringify(data, null, 2) : (data.error || JSON.stringify(data)));
    await refreshTimeCapsuleStatus();
  } catch (err) {
    setText(resultId, err.message || String(err));
  }
}

export function initTimeCapsuleAdmin() {
  const panel = document.getElementById("time-capsule-panel");
  if (!panel) return;

  void refreshTimeCapsuleStatus();
  setInterval(() => void refreshTimeCapsuleStatus(), 30000);

  panel.querySelector("#time-capsule-archive-btn")?.addEventListener("click", () => {
    const token = document.getElementById("time-capsule-publish-token")?.value?.trim() || "";
    void postCapsuleAction(
      "/api/chain-mesh/time-capsule/archive",
      { publish_token: token, force: false },
      "time-capsule-archive-result",
    );
  });

  panel.querySelector("#time-capsule-prune-btn")?.addEventListener("click", () => {
    const token = document.getElementById("time-capsule-publish-token")?.value?.trim() || "";
    const confirmed = document.getElementById("time-capsule-prune-confirm")?.checked;
    if (!confirmed) {
      setText("time-capsule-prune-result", "Check the confirm box first.");
      return;
    }
    void postCapsuleAction(
      "/api/chain-mesh/time-capsule/prune",
      { publish_token: token, confirm: true },
      "time-capsule-prune-result",
    );
  });
}