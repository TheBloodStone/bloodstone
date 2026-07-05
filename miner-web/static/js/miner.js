function copyButtonText(btn) {
  const attr = (btn.getAttribute("data-copy") || "").trim();
  if (attr) return attr;
  const row = btn.closest(".copy-row");
  if (row) {
    const code = row.querySelector("code");
    if (code?.textContent?.trim()) return code.textContent.trim();
  }
  const pre = btn.previousElementSibling;
  if (pre?.tagName === "PRE" && pre.textContent?.trim()) {
    return pre.textContent.trim();
  }
  return "";
}

document.querySelectorAll("[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const text = copyButtonText(btn);
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      const prev = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = prev; }, 1200);
    } catch (_) {
      window.prompt("Copy:", text);
    }
  });
});

function apiUrl(path) {
  const prefix = document.body?.dataset?.urlPrefix || "";
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${prefix}${normalized}`;
}

function updateNetworkHashrates(data) {
  const rates = data.network_hashrates || {};
  Object.entries(rates).forEach(([key, entry]) => {
    const el = document.querySelector(`[data-network-hashps="${key}"]`);
    if (el && entry?.formatted) {
      el.textContent = entry.formatted;
    }
  });
  const total = data.network_hashrate_total;
  if (total?.formatted) {
    const totalEl = document.querySelector('[data-network-hashps="total"]');
    if (totalEl) {
      totalEl.textContent = total.formatted;
    }
  }
}

function fmtDiff(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  if (v >= 1) return v.toFixed(2);
  if (v >= 0.01) return v.toFixed(4);
  return v.toExponential(2);
}

function updateSha256RodBlockDiff(pool) {
  const label = document.getElementById("sha256-rod-block-diff-label");
  const shareDiff = document.getElementById("sha256-share-diff");
  const shareNote = document.getElementById("sha256-share-diff-note");
  const minDiff = document.getElementById("sha256-min-share-diff");
  const rod = pool?.rod_block_diff;
  if (!rod) return;
  const enabled = !!rod.rod_block_diff_mode;
  if (label) label.textContent = enabled ? "ON" : "OFF";
  if (shareDiff) shareDiff.textContent = fmtDiff(rod.effective_share_difficulty);
  if (shareNote) {
    shareNote.textContent = enabled ? "(ROD block target)" : "(pool)";
  }
  if (minDiff && rod.asic_diff_min != null) {
    minDiff.textContent = fmtDiff(rod.asic_diff_min);
  }
}

function updatePoolWorkers(pools) {
  Object.entries(pools || {}).forEach(([key, pool]) => {
    const workersEl = document.querySelector(`[data-pool-workers="${key}"]`);
    if (workersEl) {
      workersEl.textContent = String(pool.workers ?? 0);
    }
    const browserEl = document.querySelector(`[data-pool-browser="${key}"]`);
    const browserWrap = document.querySelector(`[data-pool-browser-wrap="${key}"]`);
    const browserCount = pool.browser_workers ?? 0;
    if (browserEl) {
      browserEl.textContent = String(browserCount);
    }
    if (browserWrap) {
      browserWrap.hidden = browserCount <= 0;
    }
    const finderEl = document.querySelector(`[data-pool-block-finder="${key}"]`);
    const poolMinerEl = document.querySelector(`[data-pool-pool-miner="${key}"]`);
    if (finderEl && pool.block_finder) {
      finderEl.textContent = pool.block_finder.active ? "cpuminer-opt pool" : "offline";
      finderEl.classList.toggle("badge-active", !!pool.block_finder.active);
      finderEl.classList.toggle("badge-down", !pool.block_finder.active);
    }
    if (poolMinerEl && pool.pool_miner) {
      poolMinerEl.textContent = pool.pool_miner.active ? "cpuminer-opt pool" : "offline";
      poolMinerEl.classList.toggle("badge-active", !!pool.pool_miner.active);
      poolMinerEl.classList.toggle("badge-down", !pool.pool_miner.active);
    }
    if (key === "sha256d") {
      updateSha256RodBlockDiff(pool);
    }
  });
}

function shortAddr(addr) {
  if (!addr || addr.length < 14) return addr || "—";
  return `${addr.slice(0, 10)}…`;
}

function escAttr(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

let minerEarningsModalBound = false;

function drawMinerEarningsChart(canvas, series) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const pad = { t: 18, r: 12, b: 34, l: 52 };
  ctx.clearRect(0, 0, w, h);
  const values = (series || []).map((row) => Number(row.stone || 0));
  if (!values.length) {
    ctx.fillStyle = "#8b95a8";
    ctx.font = "13px system-ui,sans-serif";
    ctx.fillText("No earnings data in this window.", pad.l, h / 2);
    return;
  }
  const max = Math.max(0.0001, ...values);
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const barGap = 2;
  const barW = Math.max(2, plotW / values.length - barGap);
  ctx.strokeStyle = "#252a36";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, h - pad.b);
  ctx.lineTo(w - pad.r, h - pad.b);
  ctx.stroke();
  values.forEach((value, idx) => {
    const barH = (value / max) * plotH;
    const x = pad.l + idx * (barW + barGap);
    const y = h - pad.b - barH;
    ctx.fillStyle = value > 0 ? "#e53935" : "#2a3144";
    ctx.fillRect(x, y, barW, Math.max(value > 0 ? 2 : 1, barH));
  });
  ctx.fillStyle = "#8b95a8";
  ctx.font = "10px system-ui,sans-serif";
  ctx.textAlign = "right";
  ctx.fillText(`${max.toFixed(4)} STONE`, pad.l - 6, pad.t + 10);
  ctx.textAlign = "center";
  const step = Math.max(1, Math.ceil(values.length / 8));
  series.forEach((row, idx) => {
    if (idx % step !== 0 && idx !== values.length - 1) return;
    const x = pad.l + idx * (barW + barGap) + barW / 2;
    ctx.fillText(String(row.label || ""), x, h - 10);
  });
  ctx.textAlign = "left";
}

function closeMinerEarningsModal() {
  const modal = document.getElementById("miner-earnings-modal");
  if (!modal) return;
  modal.hidden = true;
  document.querySelectorAll(".miner-cross-row.is-selected").forEach((row) => {
    row.classList.remove("is-selected");
  });
}

async function openMinerEarningsModal(row) {
  const modal = document.getElementById("miner-earnings-modal");
  const subtitle = document.getElementById("miner-earnings-subtitle");
  const summary = document.getElementById("miner-earnings-summary");
  const footnote = document.getElementById("miner-earnings-footnote");
  const canvas = document.getElementById("miner-earnings-chart");
  const address = row?.dataset?.address || "";
  const worker = row?.dataset?.worker || "";
  const sourceAlgo = row?.dataset?.sourceAlgo || "";
  if (!modal || !address) return;

  document.querySelectorAll(".miner-cross-row.is-selected").forEach((el) => {
    el.classList.remove("is-selected");
  });
  row.classList.add("is-selected");
  modal.hidden = false;
  if (subtitle) {
    subtitle.textContent =
      `${address}${worker ? ` · ${worker}` : ""}${sourceAlgo ? ` · ${sourceAlgo}` : ""}`;
  }
  if (summary) summary.textContent = "Loading 24h earnings…";
  if (footnote) footnote.textContent = "";
  drawMinerEarningsChart(canvas, []);

  try {
    const res = await fetch(
      apiUrl(`/api/pool/miner-asic-earnings?address=${encodeURIComponent(address)}&hours=24`),
      { cache: "no-store" },
    );
    const data = await res.json();
    if (!res.ok || !data?.ok) throw new Error(data?.error || "unavailable");
    if (summary) {
      summary.textContent =
        `Credited ${Number(data.total_stone || 0).toFixed(4)} STONE` +
        ` from ${Number(data.payout_count || 0)} payout(s) in the last 24 hours.`;
    }
    if (footnote) footnote.textContent = data.note || "";
    drawMinerEarningsChart(canvas, data.series || []);
  } catch (_) {
    if (summary) summary.textContent = "Could not load earnings chart.";
    drawMinerEarningsChart(canvas, []);
  }
}

function initMinerEarningsModal() {
  if (minerEarningsModalBound) return;
  minerEarningsModalBound = true;
  document.getElementById("next-block-grid")?.addEventListener("click", (event) => {
    const row = event.target.closest(".miner-cross-row");
    if (!row) return;
    event.preventDefault();
    void openMinerEarningsModal(row);
  });
  document.querySelectorAll("[data-earnings-close]").forEach((el) => {
    el.addEventListener("click", closeMinerEarningsModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMinerEarningsModal();
  });
}

function updateNextBlockShares(dashboard) {
  const noteEl = document.getElementById("next-block-note");
  if (noteEl && dashboard?.next_block?.note) {
    let text = dashboard.next_block.note;
    const dist = dashboard.next_block.distributable_stone;
    if (dist != null) {
      text = `Distributable if the pool finds a block: ${Number(dist).toFixed(4)} STONE. ${text}`;
    }
    if (dashboard.finder_bonus_stone) {
      text += ` Block finder bonus: ${dashboard.finder_bonus_stone} STONE (off the top).`;
    }
    if (dashboard.staking_block_pct) {
      const stakingAmt = dashboard.staking_contribution_stone ?? 0;
      text += ` Staking pool: ${stakingAmt} STONE (${dashboard.staking_block_pct}% off the top).`;
    }
    const decay = dashboard.share_decay;
    if (decay?.enabled && decay.window_hours) {
      text += ` Pool share weight decays over ${decay.window_hours} h unless you keep mining.`;
    }
    noteEl.textContent = text;
  }

  if (!dashboard?.next_block?.per_algo) return;

  Object.entries(dashboard.next_block.per_algo).forEach(([key, algo]) => {
    const card = document.querySelector(`[data-next-block-algo="${key}"]`);
    if (!card) return;
    const height = card.querySelector('[data-field="nb-height"]');
    const tbody = card.querySelector('[data-field="nb-miners"]');
    const empty = card.querySelector('[data-field="nb-empty"]');
    if (height) {
      height.textContent = algo.job_height ? `round ${algo.job_height}` : "no open round";
    }
    const miners = algo.miners || [];
    const tableWrap = card.querySelector('[data-field="nb-table"]');
    if (tbody) {
      tbody.innerHTML = miners.map((m) => (
        `<tr><td class="mono">${shortAddr(m.address)}</td>` +
        `<td class="mono small">${m.worker || "—"}</td>` +
        `<td>${m.hashrate || "—"}</td>` +
        `<td>${Number(m.weight).toFixed(2)}</td>` +
        `<td><strong>${Number(m.pct).toFixed(2)}%</strong></td>` +
        `<td>${Number(m.estimated_stone).toFixed(4)}</td></tr>`
      )).join("");
    }
    const crossNote = card.querySelector('[data-field="nb-cross-note"]');
    const crossWrap = card.querySelector('[data-field="nb-cross-table"]');
    const crossBody = card.querySelector('[data-field="nb-cross-miners"]');
    const cross = algo.cross_subsidy_miners || [];
    if (crossNote) {
      crossNote.innerHTML = cross.length
        ? `${algo.cross_subsidy_note || "Cross-algo subsidy"}: <span class="muted">Click a row for 24h earnings chart.</span>`
        : "";
      crossNote.hidden = cross.length <= 0;
    }
    if (crossWrap) crossWrap.hidden = cross.length <= 0;
    if (crossBody) {
      crossBody.innerHTML = cross.map((m) => (
        `<tr class="miner-cross-row" data-address="${escAttr(m.address)}"` +
        ` data-worker="${escAttr(m.worker || "")}"` +
        ` data-source-algo="${escAttr(m.source_algo || "")}"` +
        ` title="Show 24h ASIC subsidy earnings">` +
        `<td class="mono">${shortAddr(m.address)}</td>` +
        `<td class="mono small">${m.source_algo || "—"}</td>` +
        `<td>${m.hashrate || "—"}</td>` +
        `<td>${Number(m.weight).toFixed(2)}</td>` +
        `<td><strong>${Number(m.pct).toFixed(2)}%</strong></td>` +
        `<td>${Number(m.estimated_stone).toFixed(4)}</td></tr>`
      )).join("");
    }
    if (tableWrap) tableWrap.hidden = miners.length <= 0;
    if (empty) empty.hidden = miners.length > 0;
  });

  const yourShares = document.querySelector('[data-field="nb-your-shares"]');
  const lookupResult = document.getElementById("pool-lookup-result");
  if (dashboard.miner_balance && lookupResult) {
    lookupResult.hidden = false;
    const pending = Number(dashboard.miner_balance.pending_stone || 0);
    const paid = Number(dashboard.miner_balance.paid_stone || 0);
    lookupResult.textContent =
      `Credited pending: ${pending.toFixed(4)} STONE · Paid: ${paid.toFixed(4)} STONE`;
  } else if (lookupResult) {
    lookupResult.hidden = true;
  }
  if (yourShares) {
    if (!dashboard.miner_balance || !dashboard.miner_next_block) {
      yourShares.textContent = "enter your address above to see pending balance and round share %";
      return;
    }
    const pending = Number(dashboard.miner_balance.pending_stone || 0);
    const roundBits = Object.entries(dashboard.miner_next_block.per_algo || {})
      .filter(([, row]) => Number(row.pct) > 0)
      .map(([key, row]) => (
        `${key} ${Number(row.pct).toFixed(2)}% (~${Number(row.estimated_stone).toFixed(4)} STONE)`
      ));
    let text = `Pending ${pending.toFixed(4)} STONE`;
    if (roundBits.length) {
      text += ` · This round: ${roundBits.join(" · ")}`;
    } else {
      text += " · no shares in open rounds yet";
    }
    yourShares.textContent = text;
  }
}

function shortRod(addr) {
  if (!addr || addr.length < 14) return addr || "not set";
  return `${addr.slice(0, 12)}…`;
}

function fmtDualCount(n) {
  const v = Number(n);
  return Number.isFinite(v) ? String(v) : "—";
}

function applyDualChainBucket(prefix, bucket) {
  const b = bucket || {};
  const submitted = document.getElementById(`${prefix}-submitted`);
  const accepted = document.getElementById(`${prefix}-accepted`);
  const blocks = document.getElementById(`${prefix}-blocks`);
  const jobs = document.getElementById(`${prefix}-jobs`);
  if (submitted) submitted.textContent = fmtDualCount(b.shares_submitted);
  if (accepted) accepted.textContent = fmtDualCount(b.shares_accepted);
  if (blocks) blocks.textContent = fmtDualCount(b.blocks_accepted);
  if (jobs) jobs.textContent = fmtDualCount(b.jobs_ready);
}

function updateDualStats(dashboard) {
  const panel = document.getElementById("dual-chain-stats");
  if (!panel) return;
  const personal = dashboard?.dual_stats;
  const poolWide = dashboard?.rod_earn?.dual_chain_stats_24h;
  const stats = personal?.chains ? personal : poolWide;
  if (!stats?.chains) return;

  applyDualChainBucket("dual-stone", stats.chains.stone);
  applyDualChainBucket("dual-rod", stats.chains.rod);

  const hint = document.getElementById("dual-chain-hint");
  const lookup = (document.getElementById("pool-address-lookup")?.value || "").trim();
  if (hint) {
    if (lookup && personal?.stone_address) {
      const rod = personal.rod_wallet_linked
        ? `linked ROD ${shortRod(personal.rod_address)}`
        : "no ROD wallet linked — register above for dual-submit";
      hint.textContent = `Your STONE address ${shortRod(personal.stone_address)} · ${rod} · last 24h`;
    } else if (stats.chains.stone?.shares_submitted || stats.chains.rod?.shares_submitted) {
      hint.textContent = "Pool-wide dual mining totals (last 24h). Enter your STONE address for your counts.";
    } else {
      hint.textContent = "Enter your STONE payout address above to see your per-chain counts. Pool totals update live.";
    }
  }

  const table = document.getElementById("dual-pool-breakdown");
  const pools = stats.pools || {};
  const rows = Object.entries(pools).filter(([, byChain]) => {
    const stone = byChain?.stone || byChain;
    const rod = byChain?.rod || {};
    const stoneAcc = Number(stone.shares_accepted || 0);
    const rodAcc = Number(rod.shares_accepted || 0);
    return stoneAcc > 0 || rodAcc > 0;
  });
  if (table) {
    if (!rows.length) {
      table.hidden = true;
    } else {
      table.hidden = false;
      table.querySelector("tbody").innerHTML = rows.map(([pool, byChain]) => {
        const stone = byChain?.stone || byChain || {};
        const rod = byChain?.rod || {};
        return (
          `<tr><td>${pool}</td>` +
          `<td><strong>${fmtDualCount(stone.shares_accepted)}</strong></td>` +
          `<td><strong>${fmtDualCount(rod.shares_accepted)}</strong></td></tr>`
        );
      }).join("");
    }
  }
}

function updateRodEarn(dashboard) {
  const r = dashboard?.rod_earn;
  if (!r) return;
  const synced = document.getElementById("rod-node-synced");
  if (synced) synced.textContent = r.rod_node_synced ? "yes" : "syncing";
  const count = document.getElementById("rod-wallet-count");
  if (count && r.registered_wallets != null) {
    count.textContent = String(r.registered_wallets);
  }
  const linked = document.getElementById("rod-wallet-linked");
  const minerRod = dashboard?.miner_rod_wallet;
  if (linked) {
    linked.textContent = minerRod?.registered
      ? shortRod(minerRod.rod_address)
      : "not set";
  }
  const rodInput = document.getElementById("rod-wallet-address");
  if (rodInput && minerRod?.rod_address && !rodInput.value.trim()) {
    rodInput.value = minerRod.rod_address;
  }
  const note = document.getElementById("rod-node-note");
  if (note && r.rod_node_note) note.textContent = r.rod_node_note;
  updateDualStats(dashboard);
}

async function loadRodWalletForStone(stoneAddress) {
  const stone = (stoneAddress || "").trim();
  if (!stone) return;
  try {
    const res = await fetch(
      apiUrl(`/api/pool/rod-wallet?stone_address=${encodeURIComponent(stone)}`),
    );
    if (!res.ok) return;
    const data = await res.json();
    const rodInput = document.getElementById("rod-wallet-address");
    if (rodInput) rodInput.value = data.rod_address || "";
    const linked = document.getElementById("rod-wallet-linked");
    if (linked) linked.textContent = data.rod_address ? shortRod(data.rod_address) : "not set";
  } catch (_) {}
}

async function saveRodWallet() {
  const stone = (document.getElementById("rod-stone-address")?.value || "").trim();
  const rod = (document.getElementById("rod-wallet-address")?.value || "").trim();
  const result = document.getElementById("rod-wallet-result");
  if (!stone) {
    if (result) {
      result.hidden = false;
      result.textContent = "Enter your STONE mining address first.";
    }
    return;
  }
  try {
    const res = await fetch(apiUrl("/api/pool/rod-wallet"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stone_address: stone, rod_address: rod }),
    });
    const data = await res.json();
    if (result) {
      result.hidden = false;
      result.textContent = data.ok
        ? (data.removed
          ? "ROD wallet link removed."
          : `Saved — SHA256 dual-submit and browser ROD mining can use ${data.rod_address}`)
        : (data.error || "Save failed");
    }
    if (data.ok) {
      localStorage.setItem(`bloodstone-rod-wallet:${stone}`, rod || "");
      const poolLookup = document.getElementById("pool-address-lookup");
      if (poolLookup && !poolLookup.value.trim()) poolLookup.value = stone;
      refreshNextBlockShares();
    }
  } catch (_) {
    if (result) {
      result.hidden = false;
      result.textContent = "Could not reach the pool API.";
    }
  }
}

function initRodWalletForm() {
  const stoneInput = document.getElementById("rod-stone-address");
  const poolLookup = document.getElementById("pool-address-lookup");
  const syncStone = () => {
    const stone = (stoneInput?.value || poolLookup?.value || "").trim();
    if (stoneInput && poolLookup?.value.trim() && !stoneInput.value.trim()) {
      stoneInput.value = poolLookup.value.trim();
    }
    if (stone) loadRodWalletForStone(stone);
  };
  stoneInput?.addEventListener("change", syncStone);
  stoneInput?.addEventListener("blur", syncStone);
  poolLookup?.addEventListener("change", () => {
    if (stoneInput && poolLookup.value.trim()) {
      stoneInput.value = poolLookup.value.trim();
      loadRodWalletForStone(poolLookup.value.trim());
    }
  });
  document.getElementById("rod-wallet-save")?.addEventListener("click", saveRodWallet);
  document.getElementById("rod-wallet-clear")?.addEventListener("click", async () => {
    const rodInput = document.getElementById("rod-wallet-address");
    if (rodInput) rodInput.value = "";
    await saveRodWallet();
  });
  syncStone();
}

function formatSubsidyBannerText(data) {
  if (!data) return null;
  const era = data.halving_era ?? data.era ?? data.subsidy_schedule?.era;
  const reward = data.current_reward_stone ?? data.reward_stone ?? data.block_reward_stone;
  const phase = data.subsidy_phase ?? data.phase ?? data.subsidy_schedule?.phase;
  const tipHeight = data.tip_height ?? data.height;
  const nextHalving = data.next_halving_height ?? data.subsidy_schedule?.next_halving_height;
  const source = data.reward_source ?? data.source ?? data.subsidy_schedule?.source;
  if (era == null && reward == null) return null;

  const eraLabel = era != null ? `Era ${era}` : "Current era";
  const phaseLabel = phase ? ` (${phase})` : "";
  const rewardLabel = reward != null ? `${Number(reward).toFixed(reward >= 10 ? 2 : 4)} STONE/block` : "—";
  const sourceNote = source === "chain" ? "from chain" : (source ? `via ${source}` : "");
  let text = `Live: ${eraLabel}${phaseLabel} — ${rewardLabel}`;
  if (sourceNote) text += ` ${sourceNote}.`;

  if (nextHalving != null && tipHeight != null && Number(nextHalving) > Number(tipHeight)) {
    const blocksLeft = Number(nextHalving) - Number(tipHeight);
    text += ` Next halving at block ${Number(nextHalving).toLocaleString()} (${blocksLeft.toLocaleString()} blocks away).`;
  } else if (Number(era) >= 5) {
    text += " Era 5+ uses scaled inflation — deploy Core 0.7.0 network-wide before block 5,270,400.";
  }

  text += " Pool payouts track on-chain subsidy; see release notes for the 0.7.0 fork.";
  return { text, era: Number(era) };
}

function updateSubsidyForkBanner(data) {
  const banner = document.getElementById("subsidy-fork-banner");
  const textEl = document.getElementById("subsidy-fork-banner-text");
  if (!banner || !textEl) return;
  const formatted = formatSubsidyBannerText(data);
  if (!formatted) return;
  textEl.innerHTML = formatted.text.replace(
    /(\d[\d.,]* STONE\/block)/,
    "<strong>$1</strong>",
  );
  banner.classList.toggle("era-warning", formatted.era >= 4);
}

async function refreshSubsidyForkBanner() {
  try {
    const res = await fetch(apiUrl("/api/pool/subsidy-schedule"));
    if (!res.ok) return;
    const data = await res.json();
    if (data?.ok !== false) updateSubsidyForkBanner(data);
  } catch (_) {}
}

function updateAsicMobileSubsidy(dashboard) {
  const s = dashboard?.asic_mobile_subsidy;
  if (!s) return;
  const note = document.querySelector("#asic-mobile-subsidy .panel-sub");
  if (note && s.note) note.textContent = s.note;
  const total = document.getElementById("asic-total-shared");
  if (total) total.textContent = `${Number(s.total_shared_stone || 0).toFixed(4)} STONE`;
  const mobile = document.getElementById("asic-mobile-shared");
  if (mobile) mobile.textContent = `${Number(s.mobile_shared_stone || 0).toFixed(4)} STONE`;
  const shares24 = document.getElementById("asic-mobile-shares-24h");
  if (shares24) shares24.textContent = String(s.mobile_shares_24h ?? 0);
  const miners24 = document.getElementById("asic-mobile-miners-24h");
  if (miners24) miners24.textContent = String(s.mobile_miners_24h ?? 0);
}

function updateBitaxe(dashboard) {
  const panel = document.getElementById("bitaxe-panel");
  const table = document.getElementById("bitaxe-devices");
  const bx = dashboard?.bitaxe;
  const devices = bx?.devices || [];
  if (!panel && !table) return;
  if (panel) panel.hidden = !devices.length;
  if (table && devices.length) {
    table.querySelector("tbody").innerHTML = devices.map((d) => (
      `<tr><td>${d.name || "Bitaxe"}</td>` +
      `<td>${d.online ? "online" : (d.error || "offline")}</td>` +
      `<td><strong>${d.hashrate || "—"}</strong>${d.hashrate_source ? ` <span class="muted small">(${d.hashrate_source})</span>` : ""}</td>` +
      `<td class="mono small">${d.worker || "—"}</td>` +
      `<td title="Firmware share counter (not chain blocks)">${d.device_share_hits ?? d.blocks_found_device ?? "—"} shares</td>` +
      `<td title="Blocks submitted to Bloodstone chain">${d.pool_blocks_found ?? "—"} blocks</td>` +
      `<td>${d.asic_model || "—"}</td></tr>` +
      (d.measurement_warning
        ? `<tr class="bitaxe-stratum-warn"><td colspan="7" class="muted small">${d.measurement_warning}</td></tr>`
        : "") +
      (d.stratum_warning && d.recommended_stratum
        ? `<tr class="bitaxe-stratum-warn"><td colspan="7" class="muted small">` +
          `${d.stratum_warning} Use <span class="mono">${d.recommended_stratum.url}</span> · worker <span class="mono">${d.recommended_stratum.worker || d.worker || ""}</span></td></tr>`
        : "")
    )).join("");
  }
  const fwdEl = document.getElementById("bitaxe-forwarder-status");
  if (fwdEl) {
    const fwdCount = Number(bx?.lan_forwarder_count ?? 0);
    const fwdList = bx?.lan_forwarders || [];
    const needsFwd = Number(bx?.needs_lan_forwarder_count ?? 0);
    if (fwdCount > 0) {
      const latest = fwdList[0];
      const who = latest?.forwarder_id || latest?.reporter_ip || "LAN PC";
      const age = Number(latest?.age_sec ?? 0);
      fwdEl.hidden = false;
      fwdEl.className = "muted small panel-sub flash flash-success";
      fwdEl.textContent =
        `LAN forwarder active (${fwdCount}): ${who} reported ${age < 120 ? `${age}s ago` : "recently"}.`;
    } else if (needsFwd > 0 || devices.some((d) => d.needs_lan_forwarder)) {
      fwdEl.hidden = false;
      fwdEl.className = "muted small panel-sub flash flash-warning";
      fwdEl.textContent =
        "No LAN forwarder reporting — install on a home PC: curl -fsSL https://bloodstonewallet.mytunnel.org/downloads/install-lan-miner-forwarder.sh | bash";
    } else {
      fwdEl.hidden = true;
    }
  }
  const warn = document.getElementById("bitaxe-stratum-alert");
  if (warn) {
    const bad = devices.find((d) => d.stratum_warning && d.recommended_stratum);
    if (bad) {
      warn.hidden = false;
      warn.textContent =
        `${bad.name || "Bitaxe"} is on SV2 — switch pool URL to ${bad.recommended_stratum.url} for real block credit.`;
    } else {
      warn.hidden = true;
    }
  }
}

function updateBlockFinds(dashboard) {
  const panel = document.getElementById("block-finds-panel");
  const lb = document.getElementById("block-find-leaderboard");
  const recent = document.getElementById("recent-block-finds");
  const leaderboard = dashboard?.block_find_leaderboard || [];
  const finds = dashboard?.recent_block_finds || [];
  if (!panel && !lb && !recent) return;
  if (panel) panel.hidden = !leaderboard.length && !finds.length;
  if (lb && leaderboard.length) {
    lb.querySelector("tbody").innerHTML = leaderboard.slice(0, 12).map((row) => (
      `<tr><td class="mono">${String(row.address).slice(0, 14)}…</td>` +
      `<td><strong>${row.total_blocks}</strong></td>` +
      `<td>${row.sha256d || "—"}</td>` +
      `<td>${row["neoscrypt-xaya"] || row.neoscrypt || "—"}</td>` +
      `<td>${row.yespower || "—"}</td></tr>`
    )).join("");
  }
  if (recent && finds.length) {
    recent.querySelector("tbody").innerHTML = finds.slice(0, 8).map((row) => (
      `<tr><td>${row.algo}</td><td>${row.block_height}</td>` +
      `<td class="mono">${String(row.finder_address).slice(0, 14)}…</td>` +
      `<td class="mono small">${row.finder_worker || "—"}</td></tr>`
    )).join("");
  }
}

async function refreshNextBlockShares() {
  const panel = document.getElementById("next-block-shares");
  const asicPanel = document.getElementById("asic-mobile-subsidy");
  const rodPanel = document.getElementById("rod-earn");
  const blockPanel = document.getElementById("block-finds-panel");
  const bitaxePanel = document.getElementById("bitaxe-panel");
  if (!panel && !asicPanel && !rodPanel && !blockPanel && !bitaxePanel) return;
  const input = document.getElementById("pool-address-lookup");
  const payout = (input?.value || "").trim();
  const query = payout ? `?address=${encodeURIComponent(payout)}` : "";
  try {
    const res = await fetch(apiUrl(`/api/pool/dashboard${query}`));
    if (!res.ok) return;
    const data = await res.json();
    if (data.error) return;
    if (data._loading) {
      const note = document.getElementById("next-block-note");
      const waiting = "Loading pool share data…";
      if (note && (!note.textContent || note.textContent === waiting)) {
        note.textContent = waiting;
      }
      window.setTimeout(refreshNextBlockShares, 2000);
      return;
    }
    updateNextBlockShares(data);
    updateSubsidyForkBanner({
      ...data.subsidy_schedule,
      block_reward_stone: data.block_reward_stone,
      halving_era: data.next_block?.halving_era,
      subsidy_phase: data.next_block?.subsidy_phase,
      next_halving_height: data.next_block?.next_halving_height,
      reward_source: data.next_block?.reward_source,
    });
    updateAsicMobileSubsidy(data);
    updateRodEarn(data);
    updateBlockFinds(data);
    updateBitaxe(data);
  } catch (_) {}
}

function formatNetworkNodesBreakdown(data) {
  if (!data) return "";
  const parts = [];
  if (data.chain_p2p_connections > 0) {
    parts.push(`${data.chain_p2p_connections} chain P2P`);
  }
  if (data.mesh_storage_peers > 0) {
    parts.push(`${data.mesh_storage_peers} mesh storage`);
  }
  if (data.local_vps_nodes > 0) {
    parts.push(`${data.local_vps_nodes} local VPS`);
  }
  if (data.fleet_offload_nodes > 0) {
    parts.push(`${data.fleet_offload_nodes} fleet offload`);
  }
  if (data.lan_registered_nodes > 0) {
    parts.push(`${data.lan_registered_nodes} LAN registered`);
  }
  return parts.length ? parts.join(" · ") : "No peers reported yet";
}

async function refreshNetworkNodesPanel() {
  const panel = document.getElementById("network-nodes-panel");
  if (!panel) return;
  try {
    const res = await fetch(apiUrl("/api/network/nodes"));
    if (!res.ok) return;
    const data = await res.json();
    if (!data?.ok) return;

    const total = Number(data.total_connected ?? 0);
    const totalEl = document.getElementById("network-nodes-total");
    const breakdownEl = document.getElementById("network-nodes-breakdown");
    const summaryEl = document.getElementById("network-nodes-summary");
    const chainEl = document.getElementById("network-nodes-chain");
    const meshEl = document.getElementById("network-nodes-mesh");
    const localEl = document.getElementById("network-nodes-local");
    const fleetEl = document.getElementById("network-nodes-fleet");
    const lanEl = document.getElementById("network-nodes-lan");

    if (totalEl) totalEl.textContent = String(total);
    if (chainEl) chainEl.textContent = String(data.chain_p2p_connections ?? "—");
    if (meshEl) meshEl.textContent = String(data.mesh_storage_peers ?? "—");
    if (localEl) localEl.textContent = String(data.local_vps_nodes ?? "—");
    if (fleetEl) {
      fleetEl.textContent = String(data.fleet_offload_nodes ?? data.fleet_active_devices ?? "—");
    }
    if (lanEl) lanEl.textContent = String(data.lan_registered_nodes ?? "—");
    if (breakdownEl) breakdownEl.textContent = formatNetworkNodesBreakdown(data);
    if (summaryEl) {
      summaryEl.textContent = `${total} network node${total === 1 ? "" : "s"} connected — ${formatNetworkNodesBreakdown(data)}`;
    }
  } catch (_) {}
}

function formatBytesShort(n) {
  const b = Number(n) || 0;
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KiB`;
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GiB`;
}

async function refreshChainMeshPanel() {
  const panel = document.getElementById("chain-mesh-panel");
  if (!panel) return;
  try {
    const [statusRes, capsuleRes] = await Promise.all([
      fetch(apiUrl("/api/chain-mesh/status")),
      fetch(apiUrl("/api/chain-mesh/time-capsule/status")),
    ]);
    if (!statusRes.ok) return;
    const data = await statusRes.json();
    const capsule = capsuleRes.ok ? await capsuleRes.json() : {};
    const m = data.manifest || {};
    const heightEl = document.getElementById("chain-mesh-height");
    const chunksEl = document.getElementById("chain-mesh-chunks");
    const archiveEl = document.getElementById("time-capsule-archive");
    const nodeModeEl = document.getElementById("time-capsule-node-mode");
    const peersEl = document.getElementById("chain-mesh-peers");
    const localEl = document.getElementById("chain-mesh-local-nodes");
    const offlineEl = document.getElementById("chain-mesh-offline-ready");
    if (heightEl) heightEl.textContent = m.block_height ? String(m.block_height) : "—";
    if (archiveEl) {
      const cov = capsule.coverage || data.coverage || {};
      archiveEl.textContent = capsule.capsule_complete
        ? `complete · ${cov.have || 0}/${cov.need || 0} chunks on VPS`
        : cov.need
          ? `in progress · ${cov.have || 0}/${cov.need}`
          : "—";
    }
    if (chunksEl) {
      const cov = data.coverage || {};
      const assign = data.assignment || {};
      const pct = assign.backup_pct || 10;
      const totalBytes = capsule.manifest?.total_bytes || m.total_bytes;
      const sizeHint = totalBytes ? ` · ${formatBytesShort(totalBytes)} archived` : "";
      chunksEl.textContent = cov.need
        ? `${cov.have || 0} / ${cov.need} on VPS${sizeHint} · ~${pct}% per device`
        : `${m.chunk_count || "—"} total · ~${pct}% per device`;
    }
    if (nodeModeEl) {
      if (capsule.pruned) {
        nodeModeEl.textContent = `pruned · ~${capsule.prune_target_mib || 550} MiB local`;
      } else if (capsule.txindex_enabled) {
        nodeModeEl.textContent = "full + txindex (history also in capsule)";
      } else {
        nodeModeEl.textContent = "full node (archive ready for prune)";
      }
    }
    if (peersEl) {
      peersEl.textContent = `${data.active_peers || 0} devices · ${data.peer_unique_chunks || 0} chunk replicas`;
    }
    const ln = data.local_nodes || {};
    if (localEl) {
      localEl.textContent = ln.active_local_nodes
        ? `${ln.active_local_nodes} devices extending chain`
        : "—";
    }
    if (offlineEl) {
      offlineEl.textContent = ln.offline_ready_nodes
        ? `${ln.offline_ready_nodes} can mine without VPS`
        : "—";
    }
  } catch (_) {}
}

async function refreshStats() {
  const heightEl = document.getElementById("live-height");
  const blockHeightEl = document.getElementById("chain-block-height");
  try {
    const res = await fetch(apiUrl("/api/status"));
    if (!res.ok) return;
    const data = await res.json();
    const workers = Object.values(data.pools || {}).reduce(
      (n, p) => n + (p.workers || 0),
      0,
    );
    const browserWorkers = Object.values(data.pools || {}).reduce(
      (n, p) => n + (p.browser_workers || 0),
      0,
    );
    updatePoolWorkers(data.pools);
    if (data.height > 0) {
      if (blockHeightEl) {
        blockHeightEl.textContent = String(data.height);
      }
      if (heightEl) {
        const browserNote = browserWorkers ? ` · ${browserWorkers} browser` : "";
        heightEl.textContent = `Height ${data.height} · ${workers} worker(s)${browserNote}`;
      }
      updateNetworkHashrates(data);
    } else if (heightEl) {
      const browserNote = browserWorkers ? ` · ${browserWorkers} browser` : "";
      heightEl.textContent = `${workers} worker(s) connected${browserNote}`;
    }
  } catch (_) {}
}

function initModeTabs() {
  const tabs = document.querySelectorAll("[data-mode-tab]");
  const panels = document.querySelectorAll("[data-mode-panel]");
  if (!tabs.length) return;

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const mode = tab.getAttribute("data-mode-tab");
      tabs.forEach((other) => {
        const active = other === tab;
        other.classList.toggle("active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.hidden = panel.getAttribute("data-mode-panel") !== mode;
      });
    });
  });
}

initModeTabs();
initMinerEarningsModal();
initRodWalletForm();
refreshStats();
refreshSubsidyForkBanner();
refreshChainMeshPanel();
refreshNetworkNodesPanel();
refreshNextBlockShares();
setInterval(refreshStats, 15000);
setInterval(refreshSubsidyForkBanner, 60000);
setInterval(refreshChainMeshPanel, 60000);
setInterval(refreshNetworkNodesPanel, 60000);
setInterval(refreshNextBlockShares, 30000);
document.getElementById("pool-address-btn")?.addEventListener("click", refreshNextBlockShares);
document.getElementById("pool-address-lookup")?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    refreshNextBlockShares();
  }
});