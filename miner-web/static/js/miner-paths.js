/** Resolve static asset URLs when the app is served under a path prefix (e.g. /mining). */

export function urlPrefix() {
  if (typeof document !== "undefined" && document.body?.dataset?.urlPrefix) {
    return document.body.dataset.urlPrefix;
  }
  if (typeof self !== "undefined" && self.__bloodstoneStaticPrefix !== undefined) {
    return self.__bloodstoneStaticPrefix;
  }
  return "";
}

export function staticUrl(path) {
  const prefix = urlPrefix();
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const relative = `${prefix}${normalized}`;
  const base =
    (typeof self !== "undefined" && self.location?.href) ||
    (typeof window !== "undefined" && window.location?.href) ||
    "";
  return base ? new URL(relative, base).href : relative;
}

function remotePortalBase() {
  if (typeof document !== "undefined") {
    const fromBody = document.body?.dataset?.updateBase || document.body?.dataset?.publicRoot;
    if (fromBody) return String(fromBody).replace(/\/$/, "");
  }
  return "https://bloodstonewallet.mytunnel.org";
}

function defaultApiPrefix() {
  if (typeof document !== "undefined" && document.body?.dataset?.androidApp === "1") {
    return "/mining";
  }
  return "";
}

export function apiUrl(path) {
  const prefix = urlPrefix() || defaultApiPrefix();
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (prefix) return `${remotePortalBase()}${prefix}${normalized}`;
  return `${remotePortalBase()}${normalized}`;
}