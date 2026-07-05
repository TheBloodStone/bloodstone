/** Stratum transport: native Android TCP or browser WebSocket bridge. */

import { whenCapacitorReady } from "./capacitor-ready.js";
import { resolveLanStratumEndpoint } from "./local-node.js";

function remotePortalBase() {
  if (typeof document !== "undefined") {
    const fromBody = document.body?.dataset?.updateBase || document.body?.dataset?.publicRoot;
    if (fromBody) return String(fromBody).replace(/\/$/, "");
  }
  return "https://bloodstonewallet.mytunnel.org";
}

function isLocalAppHost(host) {
  const h = String(host || "").toLowerCase();
  return !h || h.startsWith("localhost") || h.startsWith("127.0.0.1");
}

function publicStratumHost(raw, fallback) {
  const host = (raw || fallback || "64.188.22.190").trim();
  if (host === "127.0.0.1" || host === "localhost" || host === "::1") {
    return fallback || "64.188.22.190";
  }
  return host;
}

export function stratumEndpoints() {
  const body = document.body?.dataset || {};
  const defaultHost = publicStratumHost(body.stratumHost, "64.188.22.190");
  const hosts = {
    neoscrypt: publicStratumHost(body.stratumHostNeoscrypt, defaultHost),
    yespower: publicStratumHost(body.stratumHostYespower, defaultHost),
    rod_neoscrypt: publicStratumHost(body.stratumHostRodNeoscrypt, defaultHost),
  };
  const ports = {
    neoscrypt: Number(body.stratumNeoscrypt || 3437),
    yespower: Number(body.stratumYespower || 3438),
    rod_neoscrypt: Number(body.stratumRodNeoscrypt || 3440),
    sha256d: Number(body.stratumSha256d || 3429),
  };
  hosts.sha256d = publicStratumHost(body.stratumHostSha256d, defaultHost);
  return { hosts, ports, host: defaultHost };
}

export function canUseNativeStratum() {
  try {
    const cap = window.Capacitor;
    if (!cap || cap.getPlatform?.() !== "android") return false;
    return Boolean(cap.Plugins?.BloodstoneStratum);
  } catch (_) {
    return false;
  }
}

async function nativeStratumAvailable() {
  if (!canUseNativeStratum()) return false;
  const cap = await whenCapacitorReady(3000);
  return Boolean(cap?.Plugins?.BloodstoneStratum);
}

function wsUrl(poolKey) {
  const prefix = document.body?.dataset?.urlPrefix || "";
  let host = window.location.host;
  let proto = window.location.protocol === "https:" ? "wss" : "ws";
  if (isLocalAppHost(host)) {
    const remote = new URL(remotePortalBase());
    host = remote.host;
    proto = remote.protocol === "https:" ? "wss" : "ws";
  }
  const pathPrefix = prefix || "/mining";
  return `${proto}://${host}${pathPrefix}/ws/stratum/${poolKey}`;
}

function createWebSocketTransport(poolKey) {
  let ws = null;
  let onMessage = null;
  let onClose = null;
  let onError = null;

  return {
    kind: "websocket",
    isOpen() {
      return Boolean(ws && ws.readyState === WebSocket.OPEN);
    },
    connect() {
      return new Promise((resolve, reject) => {
        ws = new WebSocket(wsUrl(poolKey));
        ws.onopen = () => resolve();
        ws.onerror = () => {
          onError?.();
          reject(new Error("WebSocket connection failed"));
        };
        ws.onclose = (event) => {
          const detail =
            event.code !== 1000 && event.reason
              ? ` (${event.code}: ${event.reason})`
              : event.code !== 1000
                ? ` (code ${event.code})`
                : "";
          onClose?.(detail);
        };
        ws.onmessage = (event) => onMessage?.(event.data);
      });
    },
    send(payload) {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        throw new Error("stratum not connected");
      }
      ws.send(JSON.stringify(payload));
    },
    close() {
      if (!ws) return;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      try {
        ws.close();
      } catch (_) {
        /* ignore */
      }
      ws = null;
    },
    set onmessage(fn) {
      onMessage = fn;
    },
    set onclose(fn) {
      onClose = fn;
    },
    set onerror(fn) {
      onError = fn;
    },
  };
}

function createNativeTransport(poolKey, lanOverride) {
  const plugin = window.Capacitor.Plugins.BloodstoneStratum;
  const { hosts, ports } = stratumEndpoints();
  const port = lanOverride?.port || ports[poolKey];
  const host = lanOverride?.host || hosts[poolKey] || hosts.neoscrypt;
  if (!port) {
    throw new Error(`unknown pool for native stratum: ${poolKey}`);
  }

  let onMessage = null;
  let onClose = null;
  let onError = null;
  let msgHandle = null;
  let closeHandle = null;
  let open = false;

  async function bindListeners() {
    if (msgHandle) await msgHandle.remove();
    if (closeHandle) await closeHandle.remove();
    msgHandle = await plugin.addListener("stratumMessage", (ev) => {
      if (ev?.line) onMessage?.(ev.line);
    });
    closeHandle = await plugin.addListener("stratumClose", (ev) => {
      open = false;
      onClose?.(ev?.reason ? ` (${ev.reason})` : "");
    });
  }

  return {
    kind: "native-tcp",
    isOpen() {
      return open;
    },
    async connect() {
      await bindListeners();
      await plugin.connect({ host, port });
      open = true;
    },
    async send(payload) {
      if (!open) throw new Error("stratum not connected");
      await plugin.send({ line: JSON.stringify(payload) });
    },
    async close() {
      open = false;
      try {
        await plugin.disconnect();
      } catch (_) {
        /* ignore */
      }
      if (msgHandle) {
        await msgHandle.remove();
        msgHandle = null;
      }
      if (closeHandle) {
        await closeHandle.remove();
        closeHandle = null;
      }
    },
    set onmessage(fn) {
      onMessage = fn;
    },
    set onclose(fn) {
      onClose = fn;
    },
    set onerror(fn) {
      onError = fn;
    },
  };
}

export async function createStratumTransport(poolKey, options = {}) {
  const useNative = await nativeStratumAvailable();
  const localNodeOnly = options.localNodeOnly === true;
  const forceVps = options.forceVps === true;
  const lanPoolRelay =
    !forceVps
    && (options.lanPoolRelay === true
      || (useNative && options.miningMode === "pool" && !forceVps));
  const preferVpsPool =
    forceVps
    || (!localNodeOnly
      && !lanPoolRelay
      && (options.miningMode === "pool" && useNative));
  const lan = preferVpsPool
    ? null
    : await resolveLanStratumEndpoint(poolKey, { localOnly: localNodeOnly });
  if (useNative) {
    const transport = createNativeTransport(poolKey, lan);
    if (lan) {
      transport.lanSource = lan.source;
      transport.lanDisplayHost = lan.displayHost || lan.host;
    }
    return transport;
  }
  return createWebSocketTransport(poolKey);
}