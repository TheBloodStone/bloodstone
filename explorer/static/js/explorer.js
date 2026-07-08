function apiUrl(path) {
  const prefix = document.body?.dataset?.urlPrefix || "";
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${prefix}${normalized}`;
}

function fmtAmount(val) {
  if (val == null || Number.isNaN(Number(val))) return "—";
  return Number(val)
    .toFixed(8)
    .replace(/\.?0+$/, "")
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function fmtTime(ts) {
  if (!ts) return "—";
  try {
    return new Date(Number(ts) * 1000).toLocaleString("en-US", {
      timeZone: "America/Los_Angeles",
      hour12: true,
    });
  } catch (_) {
    return String(ts);
  }
}

function addressUrl(addr) {
  return apiUrl(`/address/${encodeURIComponent(addr)}`);
}

async function refreshStats() {
  const el = document.getElementById("live-height");
  if (!el) return;
  try {
    const res = await fetch(apiUrl("/api/stats"));
    if (!res.ok) return;
    const data = await res.json();
    el.textContent = `Live height: ${data.height}`;
  } catch (_) {
    /* ignore */
  }
}

function updateQuasarPanel(data) {
  if (!data || !document.getElementById("quasar-panel")) return;
  const status = data.braid_status || "unknown";
  const statusEl = document.getElementById("quasar-braid-status");
  if (statusEl) {
    statusEl.textContent = status;
    statusEl.className = `braid-badge braid-${status}`;
  }
  const confEl = document.getElementById("quasar-deposit-conf");
  if (confEl) {
    confEl.textContent = String(data.confirmations?.recommended_deposit ?? 6);
  }
  const epochEl = document.getElementById("quasar-epoch-blocks");
  if (epochEl) epochEl.textContent = String(data.epoch_blocks ?? 10);
  const vector = data.current_epoch?.braid_vector;
  const vectorEl = document.getElementById("quasar-braid-vector");
  if (vectorEl && vector) {
    vectorEl.textContent = `SHA256d ${vector.sha256d} · neoscrypt ${vector.neoscrypt} · yespower ${vector.yespower}`;
  }
  const reasonEl = document.getElementById("quasar-policy-reason");
  if (reasonEl) reasonEl.textContent = data.confirmations?.reason || "—";
  const updatedEl = document.getElementById("quasar-updated");
  if (updatedEl && data.updated_utc) {
    updatedEl.textContent = `Updated ${data.updated_utc}`;
  }
}

async function refreshQuasar() {
  if (!document.getElementById("quasar-panel")) return;
  try {
    const res = await fetch(apiUrl("/api/quasar/status"));
    if (!res.ok) return;
    const data = await res.json();
    if (data.ok !== false) updateQuasarPanel(data);
  } catch (_) {
    /* ignore */
  }
}

function updateBitaxePanel(bitaxe) {
  const panel = document.getElementById("bitaxe-panel");
  const tbody = document.querySelector("#bitaxe-devices tbody");
  const devices = bitaxe?.devices || [];
  if (!panel || !tbody) return;
  panel.hidden = !devices.length;
  tbody.innerHTML = devices.map((d) => (
    `<tr><td>${d.name || "Bitaxe"}</td>` +
    `<td>${d.online ? '<span class="badge badge-active">online</span>' : `<span class="badge badge-down">${d.error || "offline"}</span>`}</td>` +
    `<td><strong>${d.hashrate || "—"}</strong></td>` +
    `<td class="mono">${d.address ? `<a href="${addressUrl(d.address)}">${d.address}</a>` : "—"}</td>` +
    `<td class="mono small">${d.worker || "—"}</td>` +
    `<td>${d.asic_model || "—"}</td></tr>`
  )).join("");
}

function updateBlockFindLeaderboard(rows) {
  const panel = document.getElementById("block-find-panel");
  const tbody = document.querySelector("#block-find-leaderboard tbody");
  if (!tbody) return;
  const list = rows || [];
  if (panel) panel.hidden = !list.length;
  tbody.innerHTML = list.map((row) => (
    `<tr><td class="mono"><a href="${addressUrl(row.address)}">${row.address}</a></td>` +
    `<td><strong>${row.total_blocks}</strong></td>` +
    `<td>${row.sha256d || "—"}</td>` +
    `<td>${row.neoscrypt || row["neoscrypt-xaya"] || "—"}</td>` +
    `<td>${row.yespower || "—"}</td>` +
    `<td class="muted small">${fmtTime(row.last_found_at)}</td></tr>`
  )).join("");
}

function updateRecentBlockFinds(rows) {
  const panel = document.getElementById("recent-finds-panel");
  const tbody = document.querySelector("#recent-block-finds tbody");
  if (!tbody) return;
  const list = rows || [];
  if (panel) panel.hidden = !list.length;
  tbody.innerHTML = list.map((row) => (
    `<tr><td class="muted small">${fmtTime(row.found_at)}</td>` +
    `<td>${row.algo}</td><td>${row.block_height}</td>` +
    `<td class="mono"><a href="${addressUrl(row.finder_address)}">${row.finder_address}</a></td>` +
    `<td class="mono small">${row.finder_worker || "—"}</td>` +
    `<td>${fmtAmount(row.reward_stone)} STONE</td></tr>`
  )).join("");
}

function perAlgoHashrate(perAlgo, key) {
  const entry = (perAlgo || {})[key];
  return entry?.formatted || "—";
}

function minerHashrateLabel(miner) {
  if (miner?.hashrate && miner.hashrate !== "—") return miner.hashrate;
  if (miner?.connected) return "connected";
  return "—";
}

function updatePoolMiners(rows) {
  const panel = document.getElementById("pool-miners-panel");
  const tbody = document.querySelector("#pool-miners tbody");
  const empty = document.getElementById("pool-miners-empty");
  if (!tbody) return;
  const list = rows || [];
  if (panel) panel.hidden = false;
  if (empty) empty.hidden = list.length > 0;
  tbody.innerHTML = list.map((m) => (
    `<tr><td class="mono"><a href="${addressUrl(m.address)}">${m.address}</a></td>` +
    `<td><strong>${minerHashrateLabel(m)}</strong></td>` +
    `<td>${perAlgoHashrate(m.hashrate_per_algo, "sha256d")}</td>` +
    `<td>${perAlgoHashrate(m.hashrate_per_algo, "neoscrypt-xaya")}</td>` +
    `<td>${perAlgoHashrate(m.hashrate_per_algo, "yespower")}</td>` +
    `<td>${fmtAmount(m.pending_stone)}</td>` +
    `<td>${fmtAmount(m.paid_stone)}</td></tr>`
  )).join("");
}

function updateTopPending(rows) {
  const panel = document.getElementById("top-pending-panel");
  const tbody = document.querySelector("#top-pending tbody");
  if (!tbody) return;
  const list = rows || [];
  if (panel) panel.hidden = !list.length;
  tbody.innerHTML = list.map((row) => (
    `<tr><td class="mono"><a href="${addressUrl(row.address)}">${row.address}</a></td>` +
    `<td><strong>${row.hashrate || "—"}</strong></td>` +
    `<td>${fmtAmount(row.pending_stone)}</td>` +
    `<td>${fmtAmount(row.paid_stone)}</td></tr>`
  )).join("");
}

async function refreshMinersPage() {
  if (!document.getElementById("pool-miners-page")) return;
  const status = document.getElementById("miners-refresh-status");
  try {
    const res = await fetch(apiUrl("/api/pool/miners"));
    if (!res.ok) return;
    const data = await res.json();
    if (data.error) return;
    updateBitaxePanel(data.bitaxe);
    updateBlockFindLeaderboard(data.block_find_leaderboard);
    updateRecentBlockFinds(data.recent_block_finds);
    updatePoolMiners(data.pool_miners);
    updateTopPending(data.top_pending);
    if (status) {
      status.textContent = data.live_enriched_at
        ? `Updated ${fmtTime(data.live_enriched_at)}`
        : "Updated";
    }
  } catch (_) {
    /* ignore */
  }
}

refreshStats();
setInterval(refreshStats, 30000);
refreshQuasar();
setInterval(refreshQuasar, 45000);

if (document.getElementById("pool-miners-page")) {
  refreshMinersPage();
  setInterval(refreshMinersPage, 30000);
}