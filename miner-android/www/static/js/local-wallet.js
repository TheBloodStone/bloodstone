/** On-device STONE wallets — keys generated and encrypted on the phone (never leave the device). */

import { isCapacitorAndroid } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";
import { apiUrl } from "./miner-paths.js";
import {
  localNodePlugin,
  getLocalNodeStatus,
  startLocalNode,
  getNodeModePreference,
  NODE_MODES,
  shouldHostLocalNode,
} from "./local-node.js";

let _keygenMod = null;
async function loadKeygen() {
  if (_keygenMod) return _keygenMod;
  if (window.BloodstoneKeygen?.generateStoneWallet) {
    _keygenMod = window.BloodstoneKeygen;
    return _keygenMod;
  }
  _keygenMod = await import("./stone-keygen.js");
  return _keygenMod;
}

let _txMod = null;
async function loadTx() {
  if (_txMod) return _txMod;
  _txMod = await import("./stone-tx.js");
  return _txMod;
}

/** In-memory unlock session (cleared after timeout or lock). WIF never persists unlocked. */
let _unlockSession = null;
const UNLOCK_TTL_MS = 5 * 60 * 1000;

function onAndroidApp() {
  return isCapacitorAndroid() || isAndroidAppContext();
}

const PRIMARY_WALLET_KEY = "bloodstone-local-wallet-primary";
const STORE_KEY = "bloodstone-local-wallets-v2";

function b64encode(bytes) {
  let s = "";
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (let i = 0; i < arr.length; i += 1) s += String.fromCharCode(arr[i]);
  return btoa(s);
}

function b64decode(str) {
  const bin = atob(str);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

async function deriveAesKey(passphrase, salt) {
  const enc = new TextEncoder();
  const material = await crypto.subtle.importKey(
    "raw",
    enc.encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 120000, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

async function encryptSecret(plainText, passphrase) {
  const enc = new TextEncoder();
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveAesKey(passphrase, salt);
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    enc.encode(plainText),
  );
  return {
    v: 1,
    salt: b64encode(salt),
    iv: b64encode(iv),
    ct: b64encode(new Uint8Array(ct)),
  };
}

async function decryptSecret(blob, passphrase) {
  if (!blob || !blob.salt || !blob.iv || !blob.ct) {
    throw new Error("Encrypted key missing — re-create the wallet on this phone");
  }
  const salt = b64decode(blob.salt);
  const iv = b64decode(blob.iv);
  const ct = b64decode(blob.ct);
  const key = await deriveAesKey(passphrase, salt);
  try {
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
    return new TextDecoder().decode(pt);
  } catch (_) {
    throw new Error("Wrong passphrase — could not unlock wallet");
  }
}

function clearUnlockSession() {
  if (_unlockSession?.wif) {
    try {
      // best-effort wipe
      _unlockSession.wif = "";
    } catch (_) {
      /* ignore */
    }
  }
  _unlockSession = null;
}

function getUnlockSession() {
  if (!_unlockSession) return null;
  if (Date.now() > (_unlockSession.expiresAt || 0)) {
    clearUnlockSession();
    return null;
  }
  return _unlockSession;
}

function findStoredEntry(address) {
  const store = loadStore();
  const addr = String(address || "").trim();
  return (store.entries || []).find((e) => e.address === addr) || null;
}

export async function unlockLocalWallet(passphrase, address = null) {
  const pass = String(passphrase || "");
  if (pass.length < 8) {
    throw new Error("Enter the wallet passphrase (min 8 characters)");
  }
  const primary = String(address || getPrimaryLocalAddress() || "").trim();
  if (!primary) {
    throw new Error("Create or select a wallet first");
  }
  const entry = findStoredEntry(primary);
  if (!entry?.encryptedWif) {
    throw new Error(
      "This address has no on-device private key (legacy address-only). "
      + "Create a new wallet on this phone to send funds.",
    );
  }
  const wif = await decryptSecret(entry.encryptedWif, pass);
  const tx = await loadTx();
  const decoded = tx.decodeWif(wif);
  if (decoded.address !== primary) {
    clearUnlockSession();
    throw new Error("Unlocked key does not match this address");
  }
  _unlockSession = {
    address: primary,
    wif,
    unlockedAt: Date.now(),
    expiresAt: Date.now() + UNLOCK_TTL_MS,
  };
  return { ok: true, address: primary, expiresAt: _unlockSession.expiresAt };
}

export function lockLocalWallet() {
  clearUnlockSession();
  return { ok: true };
}

export function isLocalWalletUnlocked(address = null) {
  const sess = getUnlockSession();
  if (!sess) return false;
  if (address && sess.address !== String(address).trim()) return false;
  return true;
}

async function fetchJson(url, opts = {}) {
  const cap = window.Capacitor;
  if (cap?.nativePromise) {
    try {
      const response = await cap.nativePromise("CapacitorHttp", "request", {
        url,
        method: opts.method || "GET",
        headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
        data: opts.body ? JSON.parse(opts.body) : undefined,
      });
      const status = Number(response?.status) || 0;
      const raw = response?.data;
      const data = typeof raw === "string" ? JSON.parse(raw) : raw;
      if (status >= 200 && status < 300) return data;
      const err = new Error(data?.error || `HTTP ${status}`);
      err.data = data;
      throw err;
    } catch (e) {
      if (e?.data || String(e?.message || "").startsWith("HTTP")) throw e;
      /* fall through to fetch */
    }
  }
  const res = await fetch(url, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    body: opts.body,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data?.error || `HTTP ${res.status}`);
    err.data = data;
    throw err;
  }
  return data;
}

export async function fetchWalletBalance(address) {
  const addr = String(address || getPrimaryLocalAddress() || "").trim();
  if (!addr) {
    return {
      ok: false,
      address: "",
      chain_balance: null,
      pending_stone: 0,
      paid_stone: 0,
      error: "no address",
    };
  }
  try {
    const data = await fetchJson(
      apiUrl(`/api/wallet/balance?address=${encodeURIComponent(addr)}`),
    );
    return { ok: true, ...data };
  } catch (err) {
    // Fallback: pool balance only
    try {
      const pool = await fetchJson(
        apiUrl(`/api/pool/balance?address=${encodeURIComponent(addr)}`),
      );
      return {
        ok: true,
        address: addr,
        chain_balance: null,
        pending_stone: Number(pool.pending_stone || 0),
        paid_stone: Number(pool.paid_stone || 0),
        chain_error: err?.message || String(err),
      };
    } catch (_) {
      return {
        ok: false,
        address: addr,
        chain_balance: null,
        pending_stone: 0,
        paid_stone: 0,
        error: err?.message || String(err),
      };
    }
  }
}

export async function fetchWalletUtxos(address) {
  const addr = String(address || getPrimaryLocalAddress() || "").trim();
  if (!addr) throw new Error("Address required");
  const data = await fetchJson(
    apiUrl(`/api/wallet/utxos?address=${encodeURIComponent(addr)}`),
  );
  if (!data?.ok) throw new Error(data?.error || "Failed to load UTXOs");
  return data;
}

export async function sendLocalStone({
  toAddress,
  amountStone,
  feeStone = 0.0001,
  passphrase = null,
  address = null,
} = {}) {
  const from = String(address || getPrimaryLocalAddress() || "").trim();
  if (!from) throw new Error("Create a wallet first");

  let sess = getUnlockSession();
  if (!sess || sess.address !== from) {
    if (!passphrase) {
      throw new Error("Unlock the wallet first (enter passphrase)");
    }
    await unlockLocalWallet(passphrase, from);
    sess = getUnlockSession();
  }
  if (!sess?.wif) throw new Error("Wallet is locked");

  const to = String(toAddress || "").trim();
  const amount = Number(amountStone);
  if (!to) throw new Error("Enter a destination address");
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("Enter a positive amount");

  const utxoData = await fetchWalletUtxos(from);
  const txMod = await loadTx();
  if (!txMod.isValidStoneAddress(to)) {
    throw new Error("Invalid destination STONE address");
  }

  const built = await txMod.buildSignedSendTx({
    wif: sess.wif,
    toAddress: to,
    amountStone: amount,
    feeStone: Number(feeStone) || 0.0001,
    utxos: utxoData.utxos || [],
    changeAddress: from,
  });

  // Extend unlock a bit after successful build
  if (_unlockSession) {
    _unlockSession.expiresAt = Date.now() + UNLOCK_TTL_MS;
  }

  const broadcast = await fetchJson(apiUrl("/api/wallet/broadcast"), {
    method: "POST",
    body: JSON.stringify({ hex: built.hex }),
  });
  if (!broadcast?.ok && !broadcast?.txid) {
    throw new Error(broadcast?.error || "Broadcast failed");
  }
  return {
    ok: true,
    txid: broadcast.txid || built.txid,
    amountStone: amount,
    feeStone: built.feeStone,
    fromAddress: from,
    toAddress: to,
  };
}

function loadStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return { entries: [] };
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.entries)) return { entries: [] };
    return parsed;
  } catch (_) {
    return { entries: [] };
  }
}

function saveStore(store) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch (_) {
    /* ignore quota */
  }
}

export function localWalletPlugin() {
  return localNodePlugin();
}

export function getPrimaryLocalAddress() {
  try {
    return (localStorage.getItem(PRIMARY_WALLET_KEY) || "").trim();
  } catch (_) {
    return "";
  }
}

export function setPrimaryLocalAddress(address) {
  const addr = String(address || "").trim();
  if (!addr) return "";
  try {
    localStorage.setItem(PRIMARY_WALLET_KEY, addr);
  } catch (_) {
    /* ignore */
  }
  return addr;
}

/**
 * Create a STONE wallet entirely on-device (secp256k1 P2PKH).
 * Private key is encrypted with the passphrase and stored in app storage only.
 * Does not require bloodstoned wallet support (Android daemon is built NO_WALLET).
 */
export async function createLocalWallet(passphrase, label = "mobile") {
  const pass = String(passphrase || "");
  if (pass.length < 8) {
    throw new Error("Choose a passphrase of at least 8 characters");
  }
  if (!globalThis.crypto?.subtle) {
    throw new Error("Secure crypto unavailable in this WebView — update the app");
  }

  const kg = await loadKeygen();
  const generated = kg.generateStoneWallet();
  if (kg.isValidStoneAddress && !kg.isValidStoneAddress(generated.address)) {
    throw new Error("Key generation produced an invalid address — try again");
  }

  const encrypted = await encryptSecret(generated.wif, pass);
  const entry = {
    wallet: `device_${Date.now().toString(36)}`,
    address: generated.address,
    label: label || "mobile",
    source: "on-device-keygen",
    createdAt: Date.now(),
    publicKeyHex: generated.publicKeyHex,
    encryptedWif: encrypted,
    // never store plaintext WIF
  };

  const store = loadStore();
  store.entries.push(entry);
  saveStore(store);
  setPrimaryLocalAddress(entry.address);

  // Best-effort: also record address metadata via native prefs if present.
  try {
    const plugin = localNodePlugin();
    if (plugin?.listLocalWallets) {
      // no native create — bloodstoned has no wallet; ignore
    }
  } catch (_) {
    /* ignore */
  }

  return {
    ok: true,
    wallet: entry.wallet,
    address: entry.address,
    onDevice: true,
    encrypted: true,
    source: "on-device-keygen",
    // one-shot backup material for the UI (not persisted)
    wifBackup: generated.wif,
    note: "Private key encrypted on this phone — write down the backup WIF now",
  };
}

export async function listLocalWallets() {
  const store = loadStore();
  const entries = (store.entries || []).map((row) => ({
    wallet: row.wallet,
    address: row.address,
    source: row.source || "on-device-keygen",
    createdAt: row.createdAt,
  }));

  // Merge any legacy native metadata addresses (address-only, no keys).
  try {
    if (onAndroidApp()) {
      await whenCapacitorReady(3000);
      const plugin = localNodePlugin();
      if (plugin?.listLocalWallets) {
        const remote = await plugin.listLocalWallets();
        for (const row of remote?.entries || []) {
          const addr = row?.address;
          if (!addr) continue;
          if (entries.some((e) => e.address === addr)) continue;
          entries.push({
            wallet: row.wallet || "legacy",
            address: addr,
            source: row.source || "local-node",
            createdAt: row.createdAt,
          });
        }
      }
    }
  } catch (_) {
    /* ignore */
  }

  let nodeRunning = false;
  try {
    const status = await getLocalNodeStatus();
    nodeRunning = Boolean(status?.running);
  } catch (_) {
    nodeRunning = false;
  }

  return {
    onDevice: true,
    nodeRunning,
    entries,
    count: entries.length,
  };
}

export async function getNewLocalAddress(wallet, passphrase, label = "mobile") {
  // Generate an additional address (new key) for the same passphrase store.
  void wallet;
  void label;
  return createLocalWallet(passphrase, label || "mobile");
}

function forceShow(el) {
  if (!el) return;
  el.hidden = false;
  el.removeAttribute("hidden");
  try {
    el.style.setProperty("display", "block", "important");
    el.style.setProperty("visibility", "visible", "important");
    el.style.setProperty("opacity", "1", "important");
  } catch (_) {
    el.style.display = "block";
    el.style.visibility = "visible";
  }
}

const WALLET_SECTION_HTML = `
<section class="panel local-wallet-section" id="local-wallet-section" style="display:block !important;visibility:visible !important;margin-top:0.85rem;border:1px solid #3d6a5a;border-radius:10px;background:linear-gradient(180deg,#152820 0%,#121820 100%);">
  <div class="panel-head">
    <h3 style="margin:0;color:#7dcea0">Phone wallet · balance · send</h3>
    <p class="panel-sub muted small">
      Keys stay on this device. Unlock with your passphrase to send mined STONE.
    </p>
  </div>
  <div class="panel-body">
    <div class="info-box local-wallet-panel" id="local-wallet-panel" style="margin:0;display:block !important">
      <p class="muted small" id="local-wallet-status" style="margin:0">
        Enter a passphrase (min 8 characters), then tap Create wallet.
      </p>
      <p class="muted small" style="margin:0.35rem 0 0">
        Mining address: <span class="mono" id="local-wallet-primary">—</span>
      </p>
      <div id="local-wallet-balance-box" style="margin-top:0.55rem;padding:0.55rem 0.65rem;border-radius:8px;background:rgba(0,0,0,0.28);border:1px solid #2a4a3c">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:0.5rem;flex-wrap:wrap">
          <span class="muted small">Current balance</span>
          <button type="button" class="btn btn-small btn-ghost" id="local-wallet-refresh-balance-btn" style="padding:0.2rem 0.5rem;font-size:0.75rem">Refresh</button>
        </div>
        <p class="mono" id="local-wallet-balance" style="margin:0.25rem 0 0;font-size:1.15rem;color:#a8e6c3">—</p>
        <p class="muted small" id="local-wallet-balance-detail" style="margin:0.2rem 0 0">On-chain · pool pending</p>
      </div>
      <label class="field" style="margin-top:0.5rem">
        <span class="muted small">Wallet passphrase (create / unlock / send)</span>
        <input type="password" id="local-wallet-passphrase" class="mono" autocomplete="current-password" minlength="8"
          placeholder="Passphrase for this phone only" style="width:100%;box-sizing:border-box;font-size:1rem;padding:0.65rem 0.75rem">
      </label>
      <div class="btn-row" style="margin-top:0.5rem;display:flex;flex-wrap:wrap;gap:0.45rem">
        <button type="button" class="btn btn-small" id="local-wallet-create-btn">Create wallet</button>
        <button type="button" class="btn btn-small btn-ghost" id="local-wallet-use-btn">Use for mining</button>
        <button type="button" class="btn btn-small" id="local-wallet-unlock-btn">Unlock</button>
        <button type="button" class="btn btn-small btn-ghost" id="local-wallet-lock-btn">Lock</button>
        <button type="button" class="btn btn-small btn-ghost" id="local-wallet-start-node-btn" hidden>Start local node</button>
      </div>
      <p class="muted small" id="local-wallet-unlock-status" style="margin:0.4rem 0 0">Locked — unlock to send</p>

      <div id="local-wallet-send-box" style="margin-top:0.75rem;padding-top:0.65rem;border-top:1px solid #2a4a3c">
        <p style="margin:0 0 0.4rem;color:#7dcea0;font-weight:600">Send STONE</p>
        <label class="field" style="margin-top:0.35rem">
          <span class="muted small">To address</span>
          <input type="text" id="local-wallet-send-to" class="mono" autocomplete="off" spellcheck="false"
            placeholder="S…" style="width:100%;box-sizing:border-box;font-size:0.95rem;padding:0.55rem 0.65rem">
        </label>
        <div style="display:flex;gap:0.45rem;flex-wrap:wrap;margin-top:0.35rem">
          <label class="field" style="flex:1;min-width:7rem;margin:0">
            <span class="muted small">Amount (STONE)</span>
            <input type="number" id="local-wallet-send-amount" class="mono" min="0" step="any" inputmode="decimal"
              placeholder="0.0" style="width:100%;box-sizing:border-box;font-size:0.95rem;padding:0.55rem 0.65rem">
          </label>
          <label class="field" style="flex:1;min-width:7rem;margin:0">
            <span class="muted small">Network fee</span>
            <input type="number" id="local-wallet-send-fee" class="mono" min="0" step="any" inputmode="decimal"
              value="0.0001" style="width:100%;box-sizing:border-box;font-size:0.95rem;padding:0.55rem 0.65rem">
          </label>
        </div>
        <div class="btn-row" style="margin-top:0.5rem;display:flex;flex-wrap:wrap;gap:0.45rem">
          <button type="button" class="btn btn-small" id="local-wallet-send-btn">Send</button>
          <button type="button" class="btn btn-small btn-ghost" id="local-wallet-send-max-btn">Max</button>
        </div>
        <p class="muted small" id="local-wallet-send-status" style="margin:0.4rem 0 0"></p>
      </div>

      <div id="local-wallet-list" style="margin-top:0.5rem"></div>
    </div>
  </div>
</section>
`.trim();

function placeWalletSection(section) {
  if (!section) return;
  const addressInput = document.getElementById("miner-address");
  if (addressInput) {
    const field = addressInput.closest("label.field") || addressInput.parentElement;
    if (field?.parentNode) {
      if (section.parentNode !== field.parentNode || section.previousElementSibling !== field) {
        field.parentNode.insertBefore(section, field.nextSibling);
      }
      return;
    }
  }
  const options = document.getElementById("android-options-panel");
  if (options?.parentNode) {
    options.parentNode.insertBefore(section, options);
    return;
  }
  const controls = document.getElementById("android-miner-controls");
  if (controls?.parentNode) {
    controls.parentNode.insertBefore(section, controls.nextSibling);
    return;
  }
  const webMiner = document.getElementById("web-miner")?.querySelector(".panel-body");
  if (webMiner) webMiner.appendChild(section);
}

function ensureWalletDom() {
  let section = document.getElementById("local-wallet-section");
  let panel = document.getElementById("local-wallet-panel");

  // Rebuild when create or send UI is missing (upgrades from older APK/OTA bundles).
  const needsRebuild =
    !section
    || !panel
    || !document.getElementById("local-wallet-create-btn")
    || !document.getElementById("local-wallet-send-btn")
    || !document.getElementById("local-wallet-balance")
    || !document.getElementById("local-wallet-unlock-btn");

  if (needsRebuild) {
    if (section) section.remove();
    const wrap = document.createElement("div");
    wrap.innerHTML = WALLET_SECTION_HTML;
    section = wrap.firstElementChild;
    document.body.appendChild(section);
    panel = document.getElementById("local-wallet-panel");
  }

  placeWalletSection(section);
  forceShow(section);
  forceShow(panel);
  return { section, panel };
}

function showBackupOnce(address, wif) {
  const msg =
    "Wallet created!\n\n"
    + `Address:\n${address}\n\n`
    + "BACKUP PRIVATE KEY (WIF) — write this down offline, then clear this dialog:\n"
    + `${wif}\n\n`
    + "Anyone with this key can spend your STONE. It is encrypted on this phone with your passphrase and is not shown again.";
  try {
    alert(msg);
  } catch (_) {
    /* ignore */
  }
}

export function initLocalWalletPanel({
  panelId = "local-wallet-panel",
  onAddress = null,
} = {}) {
  const bodyAndroid = document.body?.dataset?.androidApp === "1";
  if (!onAndroidApp() && !bodyAndroid) return;

  const { section, panel } = ensureWalletDom();
  if (!panel && !section) return;
  forceShow(panel);
  forceShow(section);
  if (panelId && panelId !== "local-wallet-panel") {
    forceShow(document.getElementById(panelId));
  }

  const statusEl = document.getElementById("local-wallet-status");
  const listEl = document.getElementById("local-wallet-list");
  const passphraseEl = document.getElementById("local-wallet-passphrase");
  const createBtn = document.getElementById("local-wallet-create-btn");
  const useBtn = document.getElementById("local-wallet-use-btn");
  const primaryEl = document.getElementById("local-wallet-primary");
  const startNodeBtn = document.getElementById("local-wallet-start-node-btn");
  const unlockBtn = document.getElementById("local-wallet-unlock-btn");
  const lockBtn = document.getElementById("local-wallet-lock-btn");
  const unlockStatusEl = document.getElementById("local-wallet-unlock-status");
  const balanceEl = document.getElementById("local-wallet-balance");
  const balanceDetailEl = document.getElementById("local-wallet-balance-detail");
  const refreshBalBtn = document.getElementById("local-wallet-refresh-balance-btn");
  const sendToEl = document.getElementById("local-wallet-send-to");
  const sendAmountEl = document.getElementById("local-wallet-send-amount");
  const sendFeeEl = document.getElementById("local-wallet-send-fee");
  const sendBtn = document.getElementById("local-wallet-send-btn");
  const sendMaxBtn = document.getElementById("local-wallet-send-max-btn");
  const sendStatusEl = document.getElementById("local-wallet-send-status");

  let _lastChainBalance = null;

  function fmtStone(n) {
    if (n == null || !Number.isFinite(Number(n))) return "—";
    const v = Number(n);
    if (v === 0) return "0";
    if (Math.abs(v) >= 1) return v.toLocaleString(undefined, { maximumFractionDigits: 8 });
    return v.toFixed(8).replace(/\.?0+$/, "");
  }

  function updateUnlockUi() {
    const primary = getPrimaryLocalAddress();
    const unlocked = isLocalWalletUnlocked(primary);
    if (unlockStatusEl) {
      if (!primary) {
        unlockStatusEl.textContent = "Create a wallet first";
      } else if (unlocked) {
        const sess = getUnlockSession();
        const left = Math.max(0, Math.round(((sess?.expiresAt || 0) - Date.now()) / 1000));
        unlockStatusEl.textContent = `Unlocked · ready to send (${left}s)`;
        unlockStatusEl.style.color = "#7dcea0";
      } else {
        unlockStatusEl.textContent = "Locked — enter passphrase and tap Unlock to send";
        unlockStatusEl.style.color = "";
      }
    }
    if (sendBtn) sendBtn.disabled = !primary;
  }

  async function refreshBalance() {
    const primary = getPrimaryLocalAddress();
    if (!primary) {
      if (balanceEl) balanceEl.textContent = "—";
      if (balanceDetailEl) balanceDetailEl.textContent = "Create a wallet to see balance";
      _lastChainBalance = null;
      return;
    }
    if (balanceEl) balanceEl.textContent = "Loading…";
    const bal = await fetchWalletBalance(primary);
    const chain = bal.chain_balance;
    const pending = Number(bal.pending_stone || 0);
    const paid = Number(bal.paid_stone || 0);
    _lastChainBalance = chain != null && Number.isFinite(Number(chain)) ? Number(chain) : null;

    if (balanceEl) {
      if (_lastChainBalance != null) {
        balanceEl.textContent = `${fmtStone(_lastChainBalance)} STONE`;
      } else {
        balanceEl.textContent = pending > 0
          ? `${fmtStone(pending)} pending (pool)`
          : "—";
      }
    }
    if (balanceDetailEl) {
      const parts = [];
      if (_lastChainBalance != null) {
        parts.push(`On-chain spendable: ${fmtStone(_lastChainBalance)} STONE`);
      } else if (bal.chain_error) {
        parts.push(`On-chain: unavailable (${bal.chain_error})`);
      } else {
        parts.push("On-chain: —");
      }
      parts.push(`Pool pending: ${fmtStone(pending)} · paid: ${fmtStone(paid)}`);
      balanceDetailEl.textContent = parts.join(" · ");
    }
  }

  async function refresh() {
    forceShow(document.getElementById("local-wallet-section"));
    forceShow(document.getElementById("local-wallet-panel"));

    const data = await listLocalWallets();
    const primary = getPrimaryLocalAddress();

    if (statusEl) {
      statusEl.textContent =
        "Create a wallet, mine to it, unlock with your passphrase, then send on-chain STONE. "
        + "Pool pending pays out separately once the pool wallet is funded.";
    }
    if (primaryEl) {
      primaryEl.textContent = primary || "—";
    }
    if (listEl) {
      const entries = data?.entries || [];
      if (!entries.length) {
        listEl.innerHTML = "<p class=\"muted small\">No on-device wallets yet.</p>";
      } else {
        listEl.innerHTML = entries
          .map(
            (row) =>
              `<div class="mono small" style="margin:0.35rem 0">` +
              `<strong>${row.address}</strong><br>` +
              `<span class="muted">${row.source || "on-device"} · ${row.wallet || "—"}</span></div>`,
          )
          .join("");
      }
    }
    if (createBtn) {
      createBtn.disabled = false;
    }
    if (startNodeBtn) {
      startNodeBtn.hidden = true;
    }
    updateUnlockUi();
    void refreshBalance();
  }

  if (createBtn && !createBtn.dataset.walletBound && !window.__bsCreateWalletReady) {
    createBtn.dataset.walletBound = "1";
    createBtn.addEventListener("click", async () => {
      const pass = (passphraseEl?.value || "").trim();
      if (pass.length < 8) {
        alert("Choose a passphrase of at least 8 characters (stored only on this phone).");
        return;
      }
      createBtn.disabled = true;
      if (statusEl) statusEl.textContent = "Generating wallet on this phone…";
      try {
        const result = await createLocalWallet(pass);
        if (passphraseEl) passphraseEl.value = "";
        if (statusEl) {
          statusEl.textContent = `Created ${result.address} — private key encrypted on this device.`;
        }
        if (result.wifBackup) {
          showBackupOnce(result.address, result.wifBackup);
        }
        if (typeof onAddress === "function") {
          onAddress(result.address);
        }
        await refresh();
      } catch (err) {
        const msg = err?.message || String(err);
        if (statusEl) statusEl.textContent = msg;
        alert(msg);
      } finally {
        createBtn.disabled = false;
        await refresh();
      }
    });
  }

  if (useBtn && !useBtn.dataset.walletBound) {
    useBtn.dataset.walletBound = "1";
    useBtn.addEventListener("click", () => {
      const primary = getPrimaryLocalAddress();
      if (!primary) {
        alert("Create an on-device wallet first.");
        return;
      }
      if (typeof onAddress === "function") {
        onAddress(primary);
      }
    });
  }

  if (startNodeBtn && !startNodeBtn.dataset.walletBound) {
    startNodeBtn.dataset.walletBound = "1";
    startNodeBtn.addEventListener("click", async () => {
      startNodeBtn.disabled = true;
      if (statusEl) statusEl.textContent = "Starting local node…";
      try {
        let mode = getNodeModePreference();
        if (!shouldHostLocalNode(mode)) {
          mode = NODE_MODES.PRUNED || "pruned";
        }
        await startLocalNode({
          nodeMode: mode,
          foreground: true,
          waitForStratumMs: 0,
        });
        if (statusEl) {
          statusEl.textContent = "Local node starting.";
        }
      } catch (err) {
        if (statusEl) {
          statusEl.textContent = err?.message || "Could not start local node.";
        }
        alert(err?.message || String(err));
      } finally {
        await refresh();
        startNodeBtn.disabled = false;
      }
    });
  }

  if (unlockBtn && !unlockBtn.dataset.walletBound) {
    unlockBtn.dataset.walletBound = "1";
    unlockBtn.addEventListener("click", async () => {
      const pass = (passphraseEl?.value || "").trim();
      if (pass.length < 8) {
        alert("Enter your wallet passphrase (min 8 characters) to unlock.");
        return;
      }
      unlockBtn.disabled = true;
      try {
        await unlockLocalWallet(pass);
        if (passphraseEl) passphraseEl.value = "";
        if (sendStatusEl) sendStatusEl.textContent = "";
        updateUnlockUi();
      } catch (err) {
        alert(err?.message || String(err));
        updateUnlockUi();
      } finally {
        unlockBtn.disabled = false;
      }
    });
  }

  if (lockBtn && !lockBtn.dataset.walletBound) {
    lockBtn.dataset.walletBound = "1";
    lockBtn.addEventListener("click", () => {
      lockLocalWallet();
      updateUnlockUi();
      if (sendStatusEl) sendStatusEl.textContent = "Wallet locked.";
    });
  }

  if (refreshBalBtn && !refreshBalBtn.dataset.walletBound) {
    refreshBalBtn.dataset.walletBound = "1";
    refreshBalBtn.addEventListener("click", () => {
      void refreshBalance();
    });
  }

  if (sendMaxBtn && !sendMaxBtn.dataset.walletBound) {
    sendMaxBtn.dataset.walletBound = "1";
    sendMaxBtn.addEventListener("click", () => {
      const fee = Number(sendFeeEl?.value || 0.0001) || 0.0001;
      if (_lastChainBalance == null) {
        alert("Refresh balance first (on-chain amount required for Max).");
        return;
      }
      const max = Math.max(0, Number(_lastChainBalance) - fee);
      if (sendAmountEl) sendAmountEl.value = max > 0 ? String(max) : "0";
    });
  }

  if (sendBtn && !sendBtn.dataset.walletBound) {
    sendBtn.dataset.walletBound = "1";
    sendBtn.addEventListener("click", async () => {
      const to = (sendToEl?.value || "").trim();
      const amount = Number(sendAmountEl?.value);
      const fee = Number(sendFeeEl?.value || 0.0001) || 0.0001;
      const pass = (passphraseEl?.value || "").trim();
      if (!to) {
        alert("Enter a destination STONE address.");
        return;
      }
      if (!Number.isFinite(amount) || amount <= 0) {
        alert("Enter a positive amount to send.");
        return;
      }
      if (!confirm(`Send ${amount} STONE to\n${to}\n\nFee ≈ ${fee} STONE?`)) {
        return;
      }
      sendBtn.disabled = true;
      if (sendStatusEl) sendStatusEl.textContent = "Building and broadcasting…";
      try {
        const result = await sendLocalStone({
          toAddress: to,
          amountStone: amount,
          feeStone: fee,
          passphrase: pass || null,
        });
        if (passphraseEl) passphraseEl.value = "";
        if (sendAmountEl) sendAmountEl.value = "";
        if (sendStatusEl) {
          sendStatusEl.textContent = `Sent! txid ${result.txid}`;
          sendStatusEl.style.color = "#7dcea0";
        }
        if (statusEl) {
          statusEl.textContent = `Sent ${result.amountStone} STONE · ${result.txid}`;
        }
        updateUnlockUi();
        await refreshBalance();
      } catch (err) {
        const msg = err?.message || String(err);
        if (sendStatusEl) {
          sendStatusEl.textContent = msg;
          sendStatusEl.style.color = "#e88";
        }
        alert(msg);
        updateUnlockUi();
      } finally {
        sendBtn.disabled = false;
      }
    });
  }

  void refresh();
  setTimeout(() => {
    ensureWalletDom();
    void refresh();
  }, 400);
  setTimeout(() => {
    ensureWalletDom();
    void refresh();
  }, 1500);
  setInterval(() => void refresh(), 20000);
  setInterval(() => updateUnlockUi(), 5000);
}
