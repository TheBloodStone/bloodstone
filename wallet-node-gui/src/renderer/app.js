const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
  runIndicator: $("#run-indicator"),
  btnStart: $("#btn-start"),
  btnStop: $("#btn-stop"),
  statBlocks: $("#stat-blocks"),
  statHeaders: $("#stat-headers"),
  statSync: $("#stat-sync"),
  syncBar: $("#sync-bar"),
  statPeers: $("#stat-peers"),
  statChain: $("#stat-chain"),
  statHash: $("#stat-hash"),
  statDiff: $("#stat-diff"),
  statSubver: $("#stat-subver"),
  rpcAlert: $("#rpc-alert"),
  rpcAlertText: $("#rpc-alert-text"),
  syncErrorAlert: $("#sync-error-alert"),
  syncErrorText: $("#sync-error-text"),
  btnRepairSync: $("#btn-repair-sync"),
  btnResetChainDashboard: $("#btn-reset-chain-dashboard"),
  btnResetChainStuck: $("#btn-reset-chain-stuck"),
  btnResetChainSettings: $("#btn-reset-chain-settings"),
  stuckAlert: $("#stuck-alert"),
  syncAlert: $("#sync-alert"),
  syncAlertText: $("#sync-alert-text"),
  logView: $("#log-view"),
  btnClearLogs: $("#btn-clear-logs"),
  settingsForm: $("#settings-form"),
  rpcProfileStatus: $("#rpc-profile-status"),
  btnRpcLocal: $("#btn-rpc-local"),
  btnRpcVps: $("#btn-rpc-vps"),
  legacyMigrationAlert: $("#legacy-migration-alert"),
};

let lastBlocks = null;

const HIDDEN_SETTINGS_KEYS = new Set([
  "rpcUser",
  "rpcPassword",
  "rpcConfigured",
]);

function setRunning(status) {
  const managed = !!(status?.processManaged ?? status);
  els.btnStart.disabled = managed;
  els.btnStop.disabled = !managed;
  if (!status || typeof status !== "object") {
    els.runIndicator.textContent = managed ? "Running" : "Stopped";
    els.runIndicator.className = `pill ${managed ? "pill-on" : "pill-off"}`;
  }
}

function updateRunIndicator(status) {
  const managed = !!status.processManaged;
  const active = !!status.running;
  if (status.error && managed && !status.rpcReachable) {
    els.runIndicator.textContent = "Starting…";
    els.runIndicator.className = "pill pill-sync";
    return;
  }
  if (status.initialBlockDownload) {
    els.runIndicator.textContent = "Syncing";
    els.runIndicator.className = "pill pill-sync";
    return;
  }
  if (active) {
    els.runIndicator.textContent = managed ? "Running" : "Node active";
    els.runIndicator.className = "pill pill-on";
    return;
  }
  els.runIndicator.textContent = "Stopped";
  els.runIndicator.className = "pill pill-off";
}

function formatHeight(status) {
  if (status.blocks == null) {
    return "—";
  }
  if (status.logHeightFallback && !status.rpcReachable) {
    return `${status.blocks} (log)`;
  }
  return String(status.blocks);
}

function updateDashboard(status) {
  if (!status) {
    return;
  }
  setRunning(status);
  updateRunIndicator(status);

  const blocks = status.blocks;
  if (blocks != null) {
    lastBlocks = Number(blocks);
  }
  els.statBlocks.textContent = formatHeight(status);

  const headers = status.headers;
  const showHeaders =
    headers != null &&
    (blocks == null || Number(headers) > Number(blocks) || Number(blocks) === 0);
  if (els.statHeaders) {
    els.statHeaders.classList.toggle("hidden", !showHeaders);
    if (showHeaders) {
      els.statHeaders.textContent = `Headers: ${headers}`;
    }
  }

  els.statSync.textContent =
    status.syncPercent != null ? `${status.syncPercent}%` : "—";
  els.syncBar.style.width = `${status.syncPercent ?? 0}%`;
  els.statPeers.textContent = status.connections ?? (status.error ? "—" : "0");
  els.statChain.textContent = status.chain ?? "main";
  els.statHash.textContent = status.bestBlockHash ?? "—";
  els.statHash.title = status.bestBlockHash ?? "";
  els.statDiff.textContent =
    status.difficulty != null ? Number(status.difficulty).toFixed(4) : "—";
  els.statSubver.textContent = status.subversion ?? "—";

  const peers = Number(status.connections ?? 0);
  const blockNum = Number(blocks ?? lastBlocks ?? 0);
  const headerNum = Number(headers ?? 0);
  const syncing =
    status.initialBlockDownload ||
    (status.syncPercent != null && status.syncPercent < 99.9);
  const nodeActive = !!status.running;
  const showRpcWarning =
    !!status.error && !status.rpcReachable && (nodeActive || status.processManaged);
  if (els.rpcAlert) {
    els.rpcAlert.classList.toggle("hidden", !showRpcWarning);
  }
  if (showRpcWarning && els.rpcAlertText) {
    els.rpcAlertText.textContent =
      `${status.error} — Open Settings → Open bloodstone.conf and confirm RPC port ${document.getElementById("rpcPort")?.value || "18332"} matches. Save settings and restart the node.`;
  }

  const showSyncError = !!status.syncError || !!status.legacyBinary;
  if (els.syncErrorAlert) {
    els.syncErrorAlert.classList.toggle("hidden", !showSyncError);
  }
  if (showSyncError && els.syncErrorText) {
    els.syncErrorText.textContent = status.syncError || "Legacy node binary detected.";
  }
  const genesisTitle = els.syncErrorAlert?.querySelector("strong");
  if (genesisTitle) {
    genesisTitle.textContent = status.genesisMismatch
      ? "Wrong chain data (genesis mismatch)."
      : "Sync blocked.";
  }
  if (els.btnRepairSync) {
    const showRepair =
      showSyncError && !status.syncRecovery && !status.genesisMismatch;
    els.btnRepairSync.classList.toggle("hidden", !showRepair);
    els.btnRepairSync.disabled = !!status.syncRecovery;
  }

  const showStuckWarning =
    !status.error &&
    !showSyncError &&
    nodeActive &&
    headerNum > blockNum &&
    blockNum === 0 &&
    headerNum > 10;
  if (els.stuckAlert) {
    els.stuckAlert.classList.toggle("hidden", !showStuckWarning);
  }
  if (els.btnResetChainStuck) {
    els.btnResetChainStuck.classList.toggle("hidden", !showStuckWarning);
  }

  const showPeerWarning =
    nodeActive && !status.error && peers === 0 && (blockNum === 0 || syncing);
  if (els.syncAlert) {
    els.syncAlert.classList.toggle("hidden", !showPeerWarning);
  }
  if (showPeerWarning && els.syncAlertText) {
    const seed = document.getElementById("addnode")?.value || "64.188.22.190:17333";
    els.syncAlertText.textContent =
      `The node cannot download blocks until it connects to the seed at ${seed}. ` +
      "Open Settings, confirm the seed address, save, then restart the node. " +
      "Allow bloodstoned.exe through Windows Firewall (port 17333).";
  }
}

function appendLog(line) {
  const view = els.logView;
  view.textContent += `${line}\n`;
  view.scrollTop = view.scrollHeight;
}

function switchTab(name) {
  $$(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === name);
  });
  $$(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${name}`);
  });
}

function updateRpcProfileUi(settings) {
  const profile = settings?.rpcProfile || "local";
  const seed = settings?.addnode || "64.188.22.190:17333";
  if (els.rpcProfileStatus) {
    els.rpcProfileStatus.textContent =
      profile === "vps"
        ? `VPS preset active — seed ${seed}, RPC user/password applied (hidden). Web wallet sign-in uses the VPS.`
        : "Local node RPC — chain sync and wallet RPC use this PC. Click Start Node after switching here.";
  }
  if (els.btnRpcLocal) {
    els.btnRpcLocal.classList.toggle("btn-primary", profile === "local");
    els.btnRpcLocal.classList.toggle("btn-ghost", profile !== "local");
  }
  if (els.btnRpcVps) {
    els.btnRpcVps.classList.toggle("btn-primary", profile === "vps");
    els.btnRpcVps.classList.toggle("btn-ghost", profile !== "vps");
  }
}

async function loadSettingsForm() {
  const settings = await window.bloodstone.getSettings();
  for (const [key, value] of Object.entries(settings)) {
    if (HIDDEN_SETTINGS_KEYS.has(key)) {
      continue;
    }
    const input = els.settingsForm.elements.namedItem(key);
    if (!input) {
      continue;
    }
    if (input.type === "checkbox") {
      input.checked = !!value;
    } else {
      input.value = value ?? "";
    }
  }
  updateRpcProfileUi(settings);
}

function readSettingsForm() {
  const form = new FormData(els.settingsForm);
  const next = Object.fromEntries(form.entries());
  next.allowMiningWhenNotConnected = !!els.settingsForm.elements.namedItem(
    "allowMiningWhenNotConnected"
  ).checked;
  next.minimizeToTray = !!els.settingsForm.elements.namedItem("minimizeToTray").checked;
  next.rpcPort = Number(next.rpcPort);
  next.p2pPort = Number(next.p2pPort);
  return next;
}

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

els.btnStart.addEventListener("click", async () => {
  els.btnStart.disabled = true;
  els.runIndicator.textContent = "Starting…";
  els.runIndicator.className = "pill pill-sync";
  try {
    const result = await window.bloodstone.startNode();
    appendLog(`[gui] ${result.message}`);
    switchTab("logs");
    if (!result.ok) {
      alert(result.message);
    }
  } catch (err) {
    const message = err?.message || String(err);
    appendLog(`[gui] Start failed: ${message}`);
    switchTab("logs");
    alert(`Start failed: ${message}`);
  } finally {
    const running = await window.bloodstone.isRunning();
    setRunning({ processManaged: running });
    if (!running) {
      els.runIndicator.textContent = "Stopped";
      els.runIndicator.className = "pill pill-off";
    }
  }
});

els.btnStop.addEventListener("click", async () => {
  await window.bloodstone.stopNode();
});

async function runRepairSync(button) {
  if (button) {
    button.disabled = true;
  }
  appendLog("[gui] Repair sync requested…");
  try {
    const result = await window.bloodstone.repairSync();
    appendLog(`[gui] ${result.message}`);
    if (!result.ok) {
      alert(result.message);
    }
  } catch (err) {
    const message = err?.message || String(err);
    appendLog(`[gui] Repair sync failed: ${message}`);
    alert(`Repair sync failed: ${message}`);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function runResetChainData(button) {
  if (button) {
    button.disabled = true;
  }
  appendLog("[gui] Reset chain data requested…");
  try {
    const result = await window.bloodstone.resetChainData();
    if (result.cancelled) {
      appendLog("[gui] Reset chain data cancelled");
      return;
    }
    appendLog(`[gui] ${result.message}`);
    switchTab("logs");
    if (!result.ok) {
      alert(result.message);
    }
  } catch (err) {
    const message = err?.message || String(err);
    appendLog(`[gui] Reset chain data failed: ${message}`);
    alert(`Reset chain data failed: ${message}`);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

els.btnRepairSync?.addEventListener("click", () => runRepairSync(els.btnRepairSync));
els.btnResetChainDashboard?.addEventListener("click", () =>
  runResetChainData(els.btnResetChainDashboard)
);
els.btnResetChainStuck?.addEventListener("click", () => runResetChainData(els.btnResetChainStuck));
els.btnResetChainSettings?.addEventListener("click", () =>
  runResetChainData(els.btnResetChainSettings)
);

els.btnClearLogs.addEventListener("click", () => {
  els.logView.textContent = "";
});

els.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const next = readSettingsForm();
  const saved = await window.bloodstone.saveSettings(next);
  updateRpcProfileUi(saved);
  appendLog("[gui] Settings saved");
});

els.btnRpcVps?.addEventListener("click", async () => {
  const saved = await window.bloodstone.useVpsRpc();
  await loadSettingsForm();
  appendLog("[gui] VPS preset applied (RPC credentials hidden)");
  updateRpcProfileUi(saved);
});

els.btnRpcLocal?.addEventListener("click", async () => {
  const saved = await window.bloodstone.useLocalRpc();
  await loadSettingsForm();
  appendLog(`[gui] ${saved.message || "Local RPC preset applied"}`);
  updateRpcProfileUi(saved);
  if (saved.message) {
    alert(saved.message);
  }
});

$("#btn-pick-daemon").addEventListener("click", async () => {
  const picked = await window.bloodstone.pickDaemon();
  if (picked) {
    $("#daemonPath").value = picked;
  }
});

$("#btn-pick-datadir").addEventListener("click", async () => {
  const picked = await window.bloodstone.pickDataDir();
  if (picked) {
    $("#dataDir").value = picked;
  }
});

$("#btn-pick-users-db")?.addEventListener("click", async () => {
  const picked = await window.bloodstone.pickUsersDb();
  if (picked) {
    $("#usersDbPath").value = picked;
  }
});

$("#btn-open-datadir").addEventListener("click", () => window.bloodstone.openDataDir());
$("#btn-open-conf").addEventListener("click", () => window.bloodstone.openConf());

window.bloodstone.onLog(appendLog);
window.bloodstone.onStatus(updateDashboard);

(async function init() {
  const settings = await window.bloodstone.getSettings();
  if (settings.showLegacyMigrationNotice && els.legacyMigrationAlert) {
    els.legacyMigrationAlert.classList.remove("hidden");
    appendLog(
      "[gui] Upgraded from Bloodstone Node — your chain data, wallets, and settings were kept. " +
        "Use Settings → Local node for on-PC sync, or Use VPS for web-wallet accounts."
    );
  }
  await loadSettingsForm();
  const running = await window.bloodstone.isRunning();
  setRunning({ processManaged: running });
  const status = await window.bloodstone.getStatus();
  updateDashboard(status);
  appendLog("[gui] Bloodstone Wallet & Node ready — status updates every 4 seconds");
})();