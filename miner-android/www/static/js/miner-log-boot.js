/**
 * Early miner log — works before web-miner.js loads.
 */
(function () {
  if (document.body?.dataset?.androidApp !== "1") return;

  function appendMinerLog(msg, kind) {
    var text = String(msg || "").trim();
    if (!text) return;
    var wrap = document.getElementById("miner-log-wrap");
    var el = document.getElementById("miner-log");
    if (!el) return;
    if (wrap) {
      wrap.hidden = false;
      wrap.classList.add("has-entries");
    }
    var row = document.createElement("div");
    row.className = "log-line log-" + (kind || "info");
    var ts = "";
    try {
      ts = new Date().toLocaleTimeString();
    } catch (_) {
      /* ignore */
    }
    row.textContent = ts ? "[" + ts + "] " + text : text;
    el.prepend(row);
    while (el.children.length > 80) {
      el.removeChild(el.lastChild);
    }
    try {
      el.scrollTop = 0;
    } catch (_) {
      /* ignore */
    }
  }

  function scrollMinerLogIntoView() {
    var wrap = document.getElementById("miner-log-wrap");
    if (!wrap) return;
    wrap.hidden = false;
    wrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  window.__bloodstoneAppendMinerLog = appendMinerLog;
  window.__bloodstoneScrollMinerLog = scrollMinerLogIntoView;

  function prime() {
    appendMinerLog("Miner log ready — tap Start or Just mine to see live status", "info");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", prime);
  } else {
    prime();
  }
})();