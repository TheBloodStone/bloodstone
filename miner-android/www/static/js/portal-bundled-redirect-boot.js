/**
 * Portal android pages: redirect in-app WebView to bundled miner; warn when opened in a browser.
 * Remote portal URLs do not receive Capacitor JS (only https://localhost does) — detect in-app
 * via native APK version stamp injected by ResilientBridgeWebViewClient.
 */
(function () {
  if (document.body?.dataset?.androidApp !== "1") return;
  var host = String(location.hostname || "").toLowerCase();
  if (host === "localhost" || host === "127.0.0.1" || host.endsWith(".localhost")) {
    return;
  }

  var redirected = false;

  function bridgeReady() {
    var cap = window.Capacitor;
    if (!cap) return false;
    if (typeof cap.nativePromise === "function") return true;
    try {
      return cap.getPlatform && cap.getPlatform() === "android";
    } catch (_) {
      return false;
    }
  }

  function nativeApkStamp() {
    var body = document.body;
    if (!body) return "";
    return String(
      body.dataset.nativeApkVersion
      || body.getAttribute("data-native-apk-version")
      || "",
    ).trim();
  }

  function inAppWebView() {
    return bridgeReady() || Boolean(nativeApkStamp());
  }

  function redirectBundled() {
    if (redirected) return;
    redirected = true;
    var target = location.protocol + "//localhost/offline-mine.html?app=android";
    try {
      location.replace(target);
    } catch (_) {
      location.href = target;
    }
  }

  function showBrowserOnlyBanner() {
    if (document.getElementById("bs-browser-only-banner")) return;
    var bar = document.createElement("div");
    bar.id = "bs-browser-only-banner";
    bar.style.cssText =
      "position:fixed;inset:0;z-index:20000;background:rgba(8,10,16,0.96);"
      + "display:flex;align-items:center;justify-content:center;padding:20px;box-sizing:border-box;";
    bar.innerHTML =
      '<div style="max-width:24rem;text-align:center;color:#e8ecf4;font-family:system-ui,sans-serif;">'
      + '<p style="margin:0 0 12px;font-size:1.05rem;font-weight:700;color:#ff8a8a;">'
      + "Opened in a phone browser — not the Bloodstone app</p>"
      + '<p style="margin:0 0 16px;font-size:0.92rem;line-height:1.45;color:#c5d0e0;">'
      + "Open your app drawer and tap <strong>Bloodstone Fleet Miner</strong>. "
      + "Full node needs <code style=\"color:#8ec8ff\">localhost/offline-mine.html</code> "
      + "inside the app — the live portal URL cannot run bloodstoned."
      + "</p></div>";
    document.body.appendChild(bar);
  }

  function showInAppPortalBanner() {
    if (document.getElementById("bs-inapp-portal-banner")) return;
    var el = document.createElement("div");
    el.id = "bs-inapp-portal-banner";
    el.style.cssText =
      "margin:0 0 10px;padding:10px 12px;border-radius:8px;font-size:0.9rem;"
      + "background:#1a2a3d;border:1px solid #6eb5ff;color:#c5d0e0;line-height:1.4;";
    el.textContent =
      "In-app portal view — Capacitor bridge is not available here. Redirecting to bundled miner…";
    var sticky = document.getElementById("bs-ota-sticky");
    if (sticky && sticky.parentNode) {
      sticky.parentNode.insertBefore(el, sticky.nextSibling);
    } else {
      document.body.insertBefore(el, document.body.firstChild);
    }
  }

  function tryRedirect() {
    if (redirected) return;
    if (inAppWebView()) {
      showInAppPortalBanner();
      redirectBundled();
      return true;
    }
    return false;
  }

  function kickoff() {
    if (tryRedirect()) return;

    if (document.body) {
      var obs = new MutationObserver(function () {
        if (tryRedirect()) obs.disconnect();
      });
      obs.observe(document.body, {
        attributes: true,
        attributeFilter: ["data-native-apk-version"],
      });
      setTimeout(function () {
        obs.disconnect();
        if (!tryRedirect() && !bridgeReady()) showBrowserOnlyBanner();
      }, 4000);
    }

    window.addEventListener(
      "bloodstone-bridge-ready",
      function () {
        tryRedirect();
      },
      { once: true },
    );

    var wait =
      typeof window.__bloodstoneWaitForBridge === "function"
        ? window.__bloodstoneWaitForBridge(5000)
        : Promise.resolve();
    wait.then(function () {
      if (!tryRedirect() && !inAppWebView()) showBrowserOnlyBanner();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", kickoff);
  } else {
    kickoff();
  }
})();