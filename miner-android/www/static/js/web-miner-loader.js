/**
 * Load web-miner.js and surface module errors on the Start button hint line.
 */
(function () {
  if (document.body?.dataset?.androidApp !== "1") return;

  function minerUrl() {
    var script = document.querySelector('script[src*="web-miner-loader.js"]');
    if (script && script.src) {
      return script.src.replace(/web-miner-loader\.js.*$/, "web-miner.js");
    }
    return (window.location.origin || "") + "/static/js/web-miner.js";
  }

  function setUi(phase, error) {
    window.__bloodstoneMinerUi = { phase: phase, error: error || "", at: Date.now() };
    var hint = document.getElementById("miner-start-hint");
    if (!hint) return;
    if (phase === "loading") {
      hint.hidden = false;
      hint.textContent = "Loading miner controls…";
      hint.className = "muted small miner-start-hint";
      return;
    }
    if (phase === "error") {
      hint.hidden = false;
      hint.textContent = "Miner UI failed to load: " + (error || "unknown error");
      hint.className = "muted small miner-start-hint node-status-error";
      return;
    }
    if (phase === "ready") {
      hint.hidden = false;
      hint.textContent = "Miner ready — enter STONE address and tap Start offline mining";
      hint.className = "muted small miner-start-hint node-status-ok";
    }
  }

  setUi("loading");
  function minerReady() {
    return Boolean(window.__bloodstoneMinerCoreReady || window.__bloodstoneMinerBootReady);
  }

  function flushQueuedStart() {
    if (window.__bloodstoneJustMineQueued && typeof window.__bloodstoneJustMine === "function" && minerReady()) {
      window.__bloodstoneJustMineQueued = false;
      void window.__bloodstoneJustMine();
      return;
    }
    if (!window.__bloodstoneStartMiningQueued) return;
    if (typeof window.__bloodstoneStartMining !== "function") return;
    if (!minerReady()) return;
    window.__bloodstoneStartMiningQueued = false;
    void window.__bloodstoneStartMining();
  }

  function whenStartHandlerReady(onReady, onMissing) {
    if (typeof window.__bloodstoneStartMining === "function") {
      onReady();
      return;
    }
    var done = false;
    function finish() {
      if (done) return;
      done = true;
      if (typeof window.__bloodstoneStartMining === "function") {
        onReady();
      } else if (onMissing) {
        onMissing();
      }
    }
    window.addEventListener("bloodstone-miner-core-ready", finish, { once: true });
    setTimeout(finish, 12000);
  }

  import(/* webpackIgnore: true */ minerUrl())
    .then(function () {
      whenStartHandlerReady(
        function () {
          if (window.__bloodstoneMinerBootReady) {
            setUi("ready");
            flushQueuedStart();
          } else {
            setUi("loading", "");
            var hint = document.getElementById("miner-start-hint");
            if (hint) {
              hint.hidden = false;
              hint.textContent = "Loading miner controls…";
            }
            function onMinerReady() {
              setUi("ready");
              flushQueuedStart();
            }
            window.addEventListener("bloodstone-miner-core-ready", onMinerReady, { once: true });
            window.addEventListener("bloodstone-miner-boot-ready", onMinerReady, { once: true });
          }
        },
        function () {
          setUi("error", "web-miner.js loaded but Start handler missing — tap Check for updates");
        },
      );
    })
    .catch(function (err) {
      var msg = String((err && err.message) || err || "import failed");
      setUi("error", msg);
      if (typeof window.__bloodstoneAppendMinerLog === "function") {
        window.__bloodstoneAppendMinerLog("Miner UI failed to load: " + msg, "error");
      }
      console.error("web-miner load failed", err);
    });
})();