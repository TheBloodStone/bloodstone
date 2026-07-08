/**
 * Chain download starter — runs on bundled offline-mine.html before web-miner.js.
 * Retries until native startLocalNode runs or the user gets a visible error.
 */
(function () {
  if (
    document.body?.dataset?.androidApp !== "1"
    && document.body?.dataset?.desktopApp !== "1"
    && !window.__bloodstoneDesktop
    && window.Capacitor?.getPlatform?.() !== "desktop"
  ) {
    return;
  }
  try {
    if (!/offline-mine\.html/i.test(String(location.pathname || ""))) return;
  } catch (_) {
    return;
  }

  var UPSTREAM = "https://bloodstonewallet.mytunnel.org/mining/api/local-node/rpc";
  var MAX_ATTEMPTS = 30;
  var RETRY_MS = 6000;
  var REINDEX_CREEP_MS = 900000;
  var SYNC_CAUGHT_UP_MAX_BEHIND = 64;
  var SYNC_CAUGHT_UP_MIN_RATIO = 0.99;
  var STUCK_AT_99_MS = 120000;
  var SKIP = {};
  var stuckAt99Since = 0;
  var attempt = 0;
  var inFlight = false;
  var kicked = false;
  var postBootstrapSince = 0;
  var downloadPanelPrimed = false;
  var syncDismissed = false;

  window.__bloodstoneChainSyncBoot = {
    version: "1.3.78-web",
    phase: "init",
    attempts: 0,
    lastError: "",
    lastAt: 0,
    bridgeReady: false,
  };

  function stamp(phase, err) {
    var boot = window.__bloodstoneChainSyncBoot;
    boot.phase = phase;
    boot.attempts = attempt;
    boot.lastError = err || "";
    boot.lastAt = Date.now();
    try {
      sessionStorage.setItem("bloodstone-chain-sync-boot", JSON.stringify(boot));
    } catch (_) {
      /* ignore */
    }
  }

  function normalize(raw) {
    if (raw == null) return null;
    if (typeof raw === "string") {
      try {
        return JSON.parse(raw);
      } catch (_) {
        return null;
      }
    }
    if (typeof raw !== "object") return null;
    if (raw.value != null && typeof raw.value === "object") return raw.value;
    return raw;
  }

  function banner(text, kind) {
    var id = "bs-chain-sync-banner";
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement("div");
      el.id = id;
      el.style.cssText =
        "position:sticky;top:0;z-index:10001;margin:-1rem -1rem 10px -1rem;"
        + "padding:10px 12px;border-radius:0;font-size:0.9rem;line-height:1.35;"
        + "box-shadow:0 4px 14px rgba(0,0,0,0.35);";
      var wrap = document.querySelector(".wrap");
      if (wrap) wrap.insertBefore(el, wrap.firstChild);
    }
    if (!el) return;
    el.textContent = text || "";
    el.hidden = !text;
    el.style.background = kind === "error" ? "#3a1212" : "#1a2a3d";
    el.style.borderBottom = kind === "error" ? "2px solid #c44" : "2px solid #6eb5ff";
    el.style.color = kind === "error" ? "#f8d7da" : "#c5d0e0";
  }

  function setNodeStatus(text, kind) {
    var el = document.getElementById("node-only-status");
    if (!el) return;
    el.textContent = text || "";
    el.classList.remove("node-status-error", "node-status-warn", "node-status-ok");
    if (kind === "error") el.classList.add("node-status-error");
    else if (kind === "warn") el.classList.add("node-status-warn");
  }

  function clearDownloadSessionFlags() {
    try {
      sessionStorage.removeItem("bloodstone-node-only-active");
      sessionStorage.removeItem("bloodstone-chain-download-forced");
    } catch (_) {
      /* ignore */
    }
  }

  function isChainCaughtUp(status) {
    if (!status || !status.bloodstonedAlive) return false;
    var local = Number(status.blockHeight) || 0;
    if (local <= 0) return false;
    var tip = Math.max(
      Number(status.networkBlockHeight) || 0,
      Number(status.headerHeight) || 0,
      local,
    );
    if (tip <= 0) return false;
    var behind = Math.max(0, tip - local);
    if (behind <= SYNC_CAUGHT_UP_MAX_BEHIND) return true;
    return local / tip >= SYNC_CAUGHT_UP_MIN_RATIO;
  }

  function showPostSyncActions() {
    var actions = document.getElementById("local-node-sync-actions");
    if (actions) actions.hidden = false;
    if (typeof window.__bloodstoneShowPostSyncMiningCta === "function") {
      window.__bloodstoneShowPostSyncMiningCta();
    }
  }

  function payoutLooksValid(addr) {
    var s = String(addr || "").trim();
    if (!s || /your.*address|example|placeholder/i.test(s)) return false;
    return /^S[1-9A-HJ-NP-Za-km-z]{25,34}$/.test(s) || /^stone1[a-z0-9]{20,}$/i.test(s);
  }

  var postSyncStartTries = 0;
  var POST_SYNC_MAX_TRIES = 120;

  function tryStartMiningAfterSync() {
    var modeEl = document.getElementById("miner-mode");
    var mode = modeEl ? String(modeEl.value || "pool") : "pool";
    if (mode !== "pool") {
      setNodeStatus("Chain synced — switch to Pool mode and tap Start mining", "ok");
      return;
    }
    var addrEl = document.getElementById("miner-address");
    var addr = addrEl ? String(addrEl.value || "").trim() : "";
    if (!payoutLooksValid(addr)) {
      setNodeStatus("Chain synced — enter your STONE payout address, then tap Start mining", "warn");
      if (addrEl) {
        addrEl.focus();
        addrEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return;
    }
    if (typeof window.__bloodstoneStartMining !== "function") {
      postSyncStartTries += 1;
      if (postSyncStartTries < POST_SYNC_MAX_TRIES) {
        setNodeStatus("Chain synced — miner UI loading, will start in a few seconds…", "warn");
        window.setTimeout(tryStartMiningAfterSync, 500);
        return;
      }
      window.__bloodstoneStartMiningQueued = true;
      setNodeStatus("Chain synced — tap Start mining below", "warn");
      return;
    }
    if (!window.__bloodstoneMinerBootReady) {
      postSyncStartTries += 1;
      if (postSyncStartTries < POST_SYNC_MAX_TRIES) {
        setNodeStatus("Chain synced — miner UI loading, will start in a few seconds…", "warn");
        window.setTimeout(tryStartMiningAfterSync, 500);
        return;
      }
      window.__bloodstoneStartMiningQueued = true;
      setNodeStatus("Chain synced — tap Start mining below", "warn");
      return;
    }
    setNodeStatus("Chain synced — starting pool mining…", "ok");
    try {
      var ret = window.__bloodstoneStartMining();
      if (ret && typeof ret.catch === "function") {
        ret.catch(function (err) {
          var msg = String((err && err.message) || err || "Start failed");
          setNodeStatus(msg, "error");
          if (typeof window.__bloodstoneAppendMinerLog === "function") {
            window.__bloodstoneAppendMinerLog(msg, "error");
          }
          if (typeof window.__bloodstoneScrollMinerLog === "function") {
            window.__bloodstoneScrollMinerLog();
          }
        });
      }
    } catch (err) {
      setNodeStatus(String((err && err.message) || err || "Start failed"), "error");
    }
  }

  function dismissDownloadPanel(status) {
    if (syncDismissed) return;
    syncDismissed = true;
    stamp("complete");
    clearDownloadSessionFlags();
    banner("", "warn");
    var wrap = document.getElementById("local-node-sync-wrap");
    if (wrap) {
      wrap.hidden = true;
      wrap.classList.remove("is-starting");
      wrap.classList.add("is-complete");
    }
    setNodeStatus("Chain synced — tap Start mining below", "ok");
    showPostSyncActions();
    try {
      window.dispatchEvent(
        new CustomEvent("bloodstone-chain-sync-complete", { detail: status || null }),
      );
    } catch (_) {
      /* ignore */
    }
    window.setTimeout(tryStartMiningAfterSync, 600);
  }

  function primeDownloadPanel() {
    if (syncDismissed) return;
    try {
      sessionStorage.setItem("bloodstone-node-only-active", "1");
      sessionStorage.setItem("bloodstone-chain-download-forced", "1");
    } catch (_) {
      /* ignore */
    }
    var wrap = document.getElementById("local-node-sync-wrap");
    if (!wrap) return;
    wrap.hidden = false;
    wrap.classList.add("is-starting");
    var phaseEl = document.getElementById("local-node-sync-phase");
    var pctEl = document.getElementById("local-node-sync-pct");
    var label = document.getElementById("local-node-sync-label");
    var detail = document.getElementById("local-node-sync-detail");
    var diskEl = document.getElementById("local-node-sync-disk");
    if (phaseEl) phaseEl.textContent = "Starting";
    if (pctEl) pctEl.textContent = "2%";
    if (label) label.textContent = "Starting chain download…";
    if (detail) {
      detail.textContent = "Keep the app open on Wi‑Fi — progress updates every few seconds.";
    }
    if (diskEl) diskEl.textContent = "—";
    downloadPanelPrimed = true;
  }

  function reindexCreepPct(minPct, maxPct) {
    if (!postBootstrapSince) return minPct;
    var elapsed = Date.now() - postBootstrapSince;
    var ratio = Math.min(1, elapsed / REINDEX_CREEP_MS);
    return Math.round(minPct + (maxPct - minPct) * ratio);
  }

  function chainStartupPanel(status, disk) {
    var bootPct = Number(status.chainBootstrapPct) || 0;
    var bootPhase = String(status.chainBootstrapPhase || "").trim();
    if (status.chainBootstrapping || (status.nodeStarting && disk <= 512 * 1024 && !status.bloodstonedAlive)) {
      var snapPct = bootPct > 0
        ? Math.max(3, Math.min(40, bootPct))
        : reindexCreepPct(6, 28);
      var snapLabel = bootPct > 0
        ? "Installing chain snapshot (" + bootPct + "%)…"
        : bootPhase === "extracting"
          ? "Unpacking chain snapshot…"
          : bootPhase === "verifying"
            ? "Verifying chain snapshot…"
            : "Downloading chain snapshot (~4 MB)…";
      return {
        pct: snapPct,
        phase: "Pre-download",
        label: snapLabel,
        detail: "First sync downloads a chain snapshot — keep app open on Wi‑Fi (can take 2–5 min).",
      };
    }

    var bootstrapDone = disk > 512 * 1024;
    if (bootstrapDone && !postBootstrapSince) postBootstrapSince = Date.now();

    var restarts = Number(status.bloodstonedRestartAttempts) || 0;
    var local = Number(status.blockHeight) || 0;
    var syncPct = Math.round((Number(status.syncProgress) || 0) * 100);
    var reindex = status.chainReindexing === true || (bootstrapDone && local === 0);
    var err = String(status.startError || "").trim();

    if (err) {
      return {
        pct: restarts >= 8 ? 0 : Math.max(3, reindexCreepPct(6, 18)),
        phase: "Failed",
        label: err.length > 120 ? err.slice(0, 117) + "…" : err,
        detail: "Tap Stop, wait 30s, then Start full node. Need APK 1.3.57+ on Wi‑Fi.",
      };
    }

    if (status.bloodstonedAlive) {
      if (local === 0 && (reindex || bootstrapDone)) {
        var loadPct = syncPct > 1
          ? Math.max(42, Math.min(88, syncPct))
          : reindexCreepPct(40, 78);
        return {
          pct: loadPct,
          phase: "Loading",
          label: "Building chain index from pre-downloaded blocks…",
          detail: "Reindex can take 10–15 minutes — keep app in front on Wi‑Fi.",
        };
      }
      var tip = Math.max(Number(status.networkBlockHeight) || 0, Number(status.headerHeight) || 0, local);
      var behind = tip > 0 && local > 0 ? Math.max(0, tip - local) : 0;
      var caughtUp = isChainCaughtUp(status);
      var dlPct = caughtUp
        ? 100
        : syncPct > 1
          ? Math.max(45, Math.min(99, syncPct))
          : reindexCreepPct(42, 70);
      return {
        pct: dlPct,
        phase: caughtUp ? "Complete" : local > 0 ? "Downloading" : "Loading",
        label: caughtUp
          ? "Chain synced — tap Start mining below"
          : behind > SYNC_CAUGHT_UP_MAX_BEHIND && local > 0
            ? "Catching up final blocks (" + behind + " behind)…"
            : local > 0
              ? "Syncing blocks to network tip…"
              : "Loading chain from disk…",
        detail: behind > SYNC_CAUGHT_UP_MAX_BEHIND
          ? "Snapshot installed — bloodstoned is downloading the last " + behind + " blocks via P2P. Keep app on Wi‑Fi 15–30 min."
          : behind > 0
            ? local + " / " + tip + " — " + behind + " behind. Mining unlocks at 99% or within " + SYNC_CAUGHT_UP_MAX_BEHIND + " blocks."
            : "Keep the app open on Wi‑Fi — progress updates every few seconds.",
      };
    }

    if (bootstrapDone) {
      var recoverPct = reindexCreepPct(36, 74);
      if (restarts > 0) {
        return {
          pct: recoverPct,
          phase: "Restarting",
          label: "Restarting bloodstoned (attempt " + restarts + "/8)…",
          detail: err || "Recovering after crash — stay on Wi‑Fi, notifications allowed.",
        };
      }
      if (err) {
        return {
          pct: recoverPct,
          phase: "Restarting",
          label: "Recovering bloodstoned…",
          detail: err,
        };
      }
      return {
        pct: recoverPct,
        phase: "Loading",
        label: "Building chain index — first start after snapshot…",
        detail: "This can take 10–15 minutes on a phone. Keep app open on Wi‑Fi; do not lock screen.",
      };
    }

    return {
      pct: 5,
      phase: "Starting",
      label: "Starting bloodstoned…",
      detail: "Keep the app open on Wi‑Fi — progress updates every few seconds.",
    };
  }

  function refreshDownloadPanel(status) {
    if (!status) return;
    if (isChainCaughtUp(status)) {
      stuckAt99Since = 0;
      dismissDownloadPanel(status);
      return;
    }
    var disk = Number(status.chainBytes) || 0;
    var panelPeek = chainStartupPanel(status, disk);
    if (
      status.bloodstonedAlive
      && panelPeek.pct >= 99
      && (Number(status.blockHeight) || 0) > 0
    ) {
      if (!stuckAt99Since) stuckAt99Since = Date.now();
      if (Date.now() - stuckAt99Since >= STUCK_AT_99_MS) {
        dismissDownloadPanel(status);
        return;
      }
    } else {
      stuckAt99Since = 0;
    }
    if (!downloadPanelPrimed) primeDownloadPanel();
    var panel = panelPeek || chainStartupPanel(status, disk);
    var pctEl = document.getElementById("local-node-sync-pct");
    var phaseEl = document.getElementById("local-node-sync-phase");
    var fill = document.getElementById("local-node-sync-fill");
    var label = document.getElementById("local-node-sync-label");
    var detail = document.getElementById("local-node-sync-detail");
    var diskEl = document.getElementById("local-node-sync-disk");
    var heightEl = document.getElementById("local-node-sync-height");
    var networkEl = document.getElementById("local-node-sync-network");
    var pct = panel.pct;
    if (status.nodeStarting || status.running || status.chainBootstrapping) {
      if (phaseEl) phaseEl.textContent = panel.phase;
      if (label) label.textContent = panel.label;
      if (detail && panel.detail) detail.textContent = panel.detail;
    }
    if (pctEl) pctEl.textContent = pct + "%";
    if (fill) fill.style.width = pct + "%";
    if (pct >= 100) showPostSyncActions();
    if (diskEl) diskEl.textContent = disk > 0 ? formatBootBytes(disk) : "—";
    if (heightEl) {
      heightEl.textContent = Number(status.blockHeight) > 0 ? String(status.blockHeight) : "—";
    }
    if (networkEl) {
      var net = Number(status.networkBlockHeight) || 0;
      networkEl.textContent = net > 0 ? String(net) : "—";
    }
  }

  function formatBootBytes(n) {
    if (n >= 1024 * 1024) return Math.round(n / (1024 * 1024)) + " MB";
    if (n >= 1024) return Math.round(n / 1024) + " KB";
    return String(n) + " B";
  }

  function needsSync(status) {
    if (!status) return true;
    if (status.nodeStarting || status.chainBootstrapping) return false;
    var disk = Number(status.chainBytes) || 0;
    var h = Number(status.blockHeight) || 0;
    if (status.bloodstonedAlive && disk >= 512 * 1024 && h > 0) return false;
    if (!status.bloodstonedAlive) return true;
    return disk < 512 * 1024;
  }

  function bridgeUsable() {
    var cap = window.Capacitor;
    return Boolean(cap && typeof cap.nativePromise === "function");
  }

  function nativeCall(method, args) {
    var cap = window.Capacitor;
    if (!bridgeUsable()) {
      return Promise.reject(new Error("Capacitor bridge not ready"));
    }
    return cap.nativePromise("BloodstoneLocalNode", method, args || {});
  }

  function probeConfigureLocalNode() {
    return nativeCall("configureLocalNode", {
      nodeMode: "full",
      upstreamUrl: UPSTREAM,
      pruneMiB: 550,
    }).then(function (raw) {
      stamp("configured");
      return normalize(raw);
    });
  }

  function saveFullModeConfig() {
    return nativeCall("startLocalNode", {
      nodeMode: "full",
      upstreamUrl: UPSTREAM,
      pruneMiB: 550,
      foreground: false,
    }).then(function (raw) {
      stamp("saved-full-config");
      return normalize(raw);
    });
  }

  function startForegroundFull() {
    return nativeCall("startLocalNode", {
      nodeMode: "full",
      upstreamUrl: UPSTREAM,
      pruneMiB: 550,
      foreground: true,
    }).then(function (raw) {
      return normalize(raw);
    });
  }

  function verifyStarted(status) {
    if (status && status.startError) {
      throw new Error(status.startError);
    }
    if (
      status
      && (status.nodeStarting || status.chainBootstrapping || status.running || status.bloodstonedAlive)
    ) {
      stamp("started");
      banner("Chain download started — keep app open on Wi‑Fi", "warn");
      setNodeStatus("Downloading chain — keep app on Wi‑Fi", "warn");
      refreshDownloadPanel(status);
      return status;
    }
    return nativeCall("getLocalNodeStatus", {}).then(function (raw2) {
      var s2 = normalize(raw2);
      if (s2 && s2.startError) throw new Error(s2.startError);
      if (s2 && (s2.nodeStarting || s2.chainBootstrapping || s2.bloodstonedAlive)) {
        stamp("started-poll");
        banner("Chain download started — keep app open on Wi‑Fi", "warn");
        setNodeStatus("Downloading chain — keep app on Wi‑Fi", "warn");
        refreshDownloadPanel(s2);
        return s2;
      }
      throw new Error(
        "Native node did not start — keep Bloodstone in the foreground, allow notifications, disable battery saver, then retry",
      );
    });
  }

  function tryStartChain() {
    if (inFlight) return Promise.resolve();
    if (!bridgeUsable()) {
      return Promise.reject(new Error("Capacitor bridge not ready"));
    }
    inFlight = true;
    attempt += 1;
    stamp("attempt-" + attempt);
    banner("Chain sync: contacting native node (attempt " + attempt + ")…", "warn");
    setNodeStatus("Starting chain download…", "warn");
    primeDownloadPanel();

    return nativeCall("getLocalNodeStatus", {})
      .then(function (raw) {
        var status = normalize(raw);
        if (!needsSync(status)) {
          stamp("done-already-synced");
          dismissDownloadPanel(status);
          return SKIP;
        }
        if (status && (status.nodeStarting || status.chainBootstrapping)) {
          stamp("already-starting");
          banner("Chain download already in progress — keep app on Wi‑Fi", "warn");
          refreshDownloadPanel(status);
          return status;
        }
        stamp("stopping-scheduler");
        return nativeCall("stopLocalNode", { foregroundOnly: false }).catch(function () {
          return null;
        });
      })
      .then(function (prev) {
        if (prev === SKIP) return SKIP;
        stamp("configure-full");
        return probeConfigureLocalNode().catch(function (err) {
          stamp("configure-fallback", String((err && err.message) || err || ""));
          return saveFullModeConfig();
        });
      })
      .then(function (prev) {
        if (prev === SKIP) return SKIP;
        stamp("start-foreground");
        return startForegroundFull();
      })
      .then(function (prev) {
        if (prev === SKIP) return prev;
        return verifyStarted(prev);
      })
      .catch(function (err) {
        var msg = String((err && err.message) || err || "chain start failed");
        stamp("error", msg);
        banner(msg, "error");
        setNodeStatus(msg, "error");
        throw err;
      })
      .finally(function () {
        inFlight = false;
      });
  }

  function statusPollLoop() {
    if (!bridgeUsable()) return;
    nativeCall("getLocalNodeStatus", {})
      .then(function (raw) {
        refreshDownloadPanel(normalize(raw));
      })
      .catch(function () {
        /* ignore */
      });
  }

  function loop() {
    if (attempt >= MAX_ATTEMPTS) {
      stamp("gave-up", "max attempts");
      banner(
        "Chain sync could not start after " + MAX_ATTEMPTS + " tries — install APK 1.3.50 from Downloads, allow notifications, retry",
        "error",
      );
      return;
    }
    void tryStartChain()
      .then(function (result) {
        if (result === SKIP || (result && typeof result === "object")) return;
        if (attempt < MAX_ATTEMPTS) setTimeout(loop, RETRY_MS);
      })
      .catch(function () {
        if (attempt < MAX_ATTEMPTS) setTimeout(loop, RETRY_MS);
      });
  }

  function waitForAppVisible(maxMs) {
    maxMs = maxMs || 15000;
    if (document.visibilityState === "visible") {
      return Promise.resolve();
    }
    return new Promise(function (resolve) {
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        resolve();
      }
      function onVis() {
        if (document.visibilityState === "visible") {
          document.removeEventListener("visibilitychange", onVis);
          finish();
        }
      }
      document.addEventListener("visibilitychange", onVis);
      setTimeout(finish, maxMs);
    });
  }

  function isDesktopBridge() {
    try {
      return (
        document.body?.dataset?.desktopApp === "1"
        || window.Capacitor?.getPlatform?.() === "desktop"
      );
    } catch (_) {
      return false;
    }
  }

  function waitForUsableBridge(maxMs) {
    maxMs = maxMs || 45000;
    if (bridgeUsable() && (isDesktopBridge() || window.__bloodstoneBridgeState?.ready)) {
      window.__bloodstoneChainSyncBoot.bridgeReady = true;
      return Promise.resolve();
    }
    return new Promise(function (resolve) {
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        window.__bloodstoneChainSyncBoot.bridgeReady = bridgeUsable();
        resolve();
      }
      window.addEventListener(
        "bloodstone-bridge-ready",
        function () {
          finish();
        },
        { once: true },
      );
      var wait =
        typeof window.__bloodstoneWaitForBridge === "function"
          ? window.__bloodstoneWaitForBridge(maxMs)
          : Promise.resolve();
      wait.then(function (state) {
        if (state && state.ready && bridgeUsable()) finish();
      });
      setTimeout(finish, maxMs);
    });
  }

  function waitForOtaSettle(maxMs) {
    maxMs = maxMs || 15000;
    var deadline = Date.now() + maxMs;
    return new Promise(function (resolve) {
      (function tick() {
        if (window.__bloodstoneOtaInFlight) {
          if (Date.now() >= deadline) {
            resolve();
            return;
          }
          setTimeout(tick, 350);
          return;
        }
        resolve();
      })();
    });
  }

  function kickoff() {
    if (kicked) return;
    kicked = true;
    if (isDesktopBridge() && bridgeUsable()) {
      stamp("bridge-ready-desktop");
      banner("Desktop native bridge ready — starting chain…", "warn");
      primeDownloadPanel();
      setInterval(statusPollLoop, 3000);
      setTimeout(loop, 500);
      return;
    }
    stamp("waiting-bridge");
    banner("Waiting for native bridge…", "warn");
    waitForOtaSettle(15000)
      .then(function () {
        return waitForUsableBridge(50000);
      })
      .then(function () {
        return waitForAppVisible(15000);
      })
      .then(function () {
        return new Promise(function (resolve) {
          setTimeout(resolve, 700);
        });
      })
      .then(function () {
      if (!bridgeUsable()) {
        stamp("bridge-missing", "nativePromise unavailable");
        banner(
          isDesktopBridge()
            ? "Desktop native bridge not ready — reinstall Bloodstone Miner desktop from Downloads (v1.3.80+)"
            : "Native bridge not ready — reopen the Bloodstone app icon",
          "error",
        );
        kicked = false;
        setTimeout(kickoff, RETRY_MS);
        return;
      }
      stamp("bridge-ready");
      banner("Starting chain download…", "warn");
      primeDownloadPanel();
      setInterval(statusPollLoop, 3000);
      setTimeout(loop, 500);
    });
  }

  function scheduleKickoff() {
    setTimeout(kickoff, 1200);
  }

  window.addEventListener("bloodstone-bridge-ready", scheduleKickoff);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleKickoff);
  } else {
    scheduleKickoff();
  }
})();