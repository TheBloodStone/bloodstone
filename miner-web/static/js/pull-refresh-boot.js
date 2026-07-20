/**
 * Pull-down to check for updates on Android (beta or stable OTA).
 * Falls back to page reload when the module update path is unavailable.
 */
(function () {
  if (document.body?.dataset?.androidApp !== "1") {
    try {
      if (window.Capacitor?.getPlatform?.() !== "android") return;
    } catch (_) {
      return;
    }
  }

  var THRESHOLD = 72;
  var MAX_PULL = 120;
  var startY = 0;
  var pulling = false;
  var updateInFlight = false;
  var indicator = null;

  function scrollTop() {
    return Math.max(
      window.scrollY || 0,
      document.documentElement?.scrollTop || 0,
      document.body?.scrollTop || 0,
    );
  }

  function ensureIndicator() {
    if (indicator) return indicator;
    indicator = document.createElement("div");
    indicator.id = "bs-pull-refresh";
    indicator.setAttribute("aria-hidden", "true");
    indicator.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:10001;height:0;overflow:hidden;"
      + "display:flex;align-items:flex-end;justify-content:center;"
      + "background:linear-gradient(180deg,#1e2a3d 0%,transparent 100%);"
      + "color:#6eb5ff;font-size:0.82rem;font-weight:600;"
      + "pointer-events:none;transition:height 0.12s ease-out;";
    indicator.textContent = "Pull to check for updates";
    document.body.appendChild(indicator);
    return indicator;
  }

  function setPull(px) {
    var el = ensureIndicator();
    var h = Math.min(MAX_PULL, Math.max(0, px));
    el.style.height = h + "px";
    el.textContent = h >= THRESHOLD ? "Release to update" : "Pull to check for updates";
    el.style.opacity = String(Math.min(1, h / THRESHOLD));
  }

  function resetPull() {
    if (!indicator) return;
    indicator.style.height = "0";
    indicator.style.opacity = "0";
  }

  function reloadPage() {
    setPull(MAX_PULL);
    if (indicator) indicator.textContent = "Reloading…";
    window.location.reload();
  }

  function runPullUpdate() {
    if (updateInFlight) return;
    updateInFlight = true;
    setPull(MAX_PULL);
    if (indicator) indicator.textContent = "Checking for updates…";

    var done = function () {
      updateInFlight = false;
      window.setTimeout(resetPull, 500);
    };

    import("./app-update.js")
      .then(function (mod) {
        if (!mod?.runAndroidUpdateCheck) {
          throw new Error("update module unavailable");
        }
        return mod.runAndroidUpdateCheck({ manual: true, force: true });
      })
      .then(function (result) {
        if (result && result.webBundleUpdated) return;
        if (result && result.error) return;
        if (!result || result.upToDate) {
          if (indicator) indicator.textContent = "Up to date";
        }
      })
      .catch(function () {
        reloadPage();
      })
      .finally(done);
  }

  function onTouchStart(event) {
    if (scrollTop() > 2) return;
    if (event.touches.length !== 1) return;
    startY = event.touches[0].clientY;
    pulling = true;
  }

  function onTouchMove(event) {
    if (!pulling) return;
    if (scrollTop() > 2) {
      pulling = false;
      resetPull();
      return;
    }
    var delta = event.touches[0].clientY - startY;
    if (delta <= 0) {
      resetPull();
      return;
    }
    setPull(delta * 0.55);
    if (delta > 12) event.preventDefault();
  }

  function onTouchEnd() {
    if (!pulling) return;
    pulling = false;
    var h = indicator ? parseInt(indicator.style.height, 10) || 0 : 0;
    if (h >= THRESHOLD) {
      runPullUpdate();
      return;
    }
    resetPull();
  }

  document.addEventListener("touchstart", onTouchStart, { passive: true });
  document.addEventListener("touchmove", onTouchMove, { passive: false });
  document.addEventListener("touchend", onTouchEnd, { passive: true });
  document.addEventListener("touchcancel", onTouchEnd, { passive: true });
})();