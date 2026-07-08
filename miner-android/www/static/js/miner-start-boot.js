/**
 * Early Start mining hook — runs before web-miner.js finishes booting.
 */
(function () {
  if (document.body?.dataset?.androidApp !== "1") return;

  function hint(text, kind) {
    var el = document.getElementById("miner-start-hint");
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || "";
    el.className = "muted small miner-start-hint"
      + (kind === "error" ? " node-status-error" : kind === "warn" ? " node-status-warn" : kind === "ok" ? " node-status-ok" : "");
  }

  function appendMinerLog(text, kind) {
    if (!text) return;
    if (typeof window.__bloodstoneAppendMinerLog === "function") {
      window.__bloodstoneAppendMinerLog(text, kind || "info");
      return;
    }
    var logEl = document.getElementById("miner-log");
    if (!logEl) return;
    var row = document.createElement("div");
    row.className = "log-line log-" + (kind || "info");
    row.textContent = String(text);
    logEl.prepend(row);
  }

  function scrollMinerLog() {
    if (typeof window.__bloodstoneScrollMinerLog === "function") {
      window.__bloodstoneScrollMinerLog();
      return;
    }
    document.getElementById("miner-log-wrap")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function pulse(btn) {
    if (!btn) return;
    btn.classList.add("pulse-highlight");
    setTimeout(function () {
      btn.classList.remove("pulse-highlight");
    }, 2400);
  }

  function hookJustMineButton() {
    var btn = document.getElementById("btn-just-mine");
    if (!btn || btn.dataset.justMineHooked === "1") return;
    btn.dataset.justMineHooked = "1";
    btn.type = "button";

    btn.addEventListener("click", function (event) {
      event.preventDefault();
      pulse(btn);
      scrollMinerLog();
      hint("Just Mine — bypassing safeguards…", "warn");
      appendMinerLog("Just Mine tapped — bypassing battery and thermal checks", "warn");
      if (typeof window.__bloodstoneJustMine === "function") {
        try {
          var ret = window.__bloodstoneJustMine();
          if (ret && typeof ret.catch === "function") {
            ret.catch(function (err) {
              var msg = String((err && err.message) || err || "Just Mine failed");
              hint(msg, "error");
              appendMinerLog(msg);
            });
          }
        } catch (err) {
          var msg = String((err && err.message) || err || "Just Mine failed");
          hint(msg, "error");
          appendMinerLog(msg);
        }
        return;
      }
      window.__bloodstoneJustMineQueued = true;
      var ui = window.__bloodstoneMinerUi || {};
      if (ui.phase === "error" && ui.error) {
        hint("Miner UI failed: " + ui.error, "error");
        appendMinerLog("Miner UI failed: " + ui.error, "error");
        return;
      }
      hint("Miner UI still loading — Just Mine will run when ready", "warn");
      appendMinerLog("Waiting for miner core — Just Mine will auto-start when ready", "info");
    });
  }

  function hookStartButton() {
    var btn = document.getElementById("btn-start");
    if (!btn || btn.dataset.minerStartHooked === "1") return;
    btn.dataset.minerStartHooked = "1";
    btn.type = "button";

    btn.addEventListener("click", function (event) {
      event.preventDefault();
      if (btn.disabled) {
        var reason = btn.title || "Enter a valid STONE payout address above";
        hint(reason, "warn");
        pulse(btn);
        var addr = document.getElementById("miner-address");
        if (addr) {
          addr.focus();
          addr.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        var logEl = document.getElementById("miner-log");
        if (logEl && reason) {
          logEl.textContent = (logEl.textContent ? logEl.textContent + "\n" : "") + reason;
        }
        return;
      }
      hint("Starting mining…", "ok");
      pulse(btn);
      scrollMinerLog();
      appendMinerLog("Start mining tapped", "success");
      if (typeof window.__bloodstoneStartMining === "function") {
        try {
          var ret = window.__bloodstoneStartMining();
          if (ret && typeof ret.catch === "function") {
            ret.catch(function (err) {
              hint(String((err && err.message) || err || "Start failed"), "error");
            });
          }
        } catch (err) {
          hint(String((err && err.message) || err || "Start failed"), "error");
        }
        return;
      }
      window.__bloodstoneStartMiningQueued = true;
      var ui = window.__bloodstoneMinerUi || {};
      if (ui.phase === "error" && ui.error) {
        hint("Miner UI failed: " + ui.error, "error");
        return;
      }
      hint("Miner UI still loading — wait 3–5 seconds and tap Start again", "warn");
    });
  }

  function minerReadyForJustMine() {
    return Boolean(
      window.__bloodstoneMinerCoreReady
      || window.__bloodstoneMinerBootReady,
    );
  }

  function flushQueuedStart() {
    if (window.__bloodstoneJustMineQueued) {
      if (typeof window.__bloodstoneJustMine !== "function") return;
      if (!minerReadyForJustMine()) return;
      window.__bloodstoneJustMineQueued = false;
      try {
        var justRet = window.__bloodstoneJustMine();
        if (justRet && typeof justRet.catch === "function") {
          justRet.catch(function (err) {
            hint(String((err && err.message) || err || "Just Mine failed"), "error");
          });
        }
      } catch (err) {
        hint(String((err && err.message) || err || "Just Mine failed"), "error");
      }
      return;
    }
    if (!window.__bloodstoneStartMiningQueued) return;
    if (typeof window.__bloodstoneStartMining !== "function") return;
    if (!window.__bloodstoneMinerBootReady && !window.__bloodstoneMinerCoreReady) return;
    window.__bloodstoneStartMiningQueued = false;
    try {
      var ret = window.__bloodstoneStartMining();
      if (ret && typeof ret.catch === "function") {
        ret.catch(function (err) {
          hint(String((err && err.message) || err || "Start failed"), "error");
        });
      }
    } catch (err) {
      hint(String((err && err.message) || err || "Start failed"), "error");
    }
  }

  function watchMinerReady() {
    var tries = 0;
    var timer = setInterval(function () {
      tries += 1;
      if (
        typeof window.__bloodstoneStartMining === "function"
        && (window.__bloodstoneMinerBootReady || window.__bloodstoneMinerCoreReady)
      ) {
        clearInterval(timer);
        var hintEl = document.getElementById("miner-start-hint");
        if (hintEl && hintEl.textContent.indexOf("still loading") >= 0) {
          hintEl.textContent = "Miner ready — enter STONE address and tap Start";
          hintEl.className = "muted small miner-start-hint node-status-ok";
        }
        flushQueuedStart();
        return;
      }
      var ui = window.__bloodstoneMinerUi || {};
      if (ui.phase === "error") {
        clearInterval(timer);
        hint(ui.error ? "Miner UI failed: " + ui.error : "Miner UI failed to load", "error");
        return;
      }
      if (tries >= 120) {
        clearInterval(timer);
        hint("Miner UI did not load — tap Check for updates (need 1.3.110-web+)", "error");
      }
    }, 500);
    window.addEventListener("bloodstone-miner-boot-ready", flushQueuedStart, { once: true });
    window.addEventListener("bloodstone-miner-core-ready", flushQueuedStart, { once: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      hookStartButton();
      hookJustMineButton();
      watchMinerReady();
    });
  } else {
    hookStartButton();
    hookJustMineButton();
    watchMinerReady();
  }
})();