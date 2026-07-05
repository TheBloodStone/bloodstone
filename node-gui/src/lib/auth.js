const fs = require("fs");
const crypto = require("crypto");
const http = require("http");
const https = require("https");
const path = require("path");
const initSqlJs = require("sql.js");
const { DEFAULT_WALLET_WEB_URL } = require("./paths");

function sqlWasmPath(file) {
  const candidates = [
    path.join(__dirname, "..", "..", "node_modules", "sql.js", "dist", file),
    path.join(process.resourcesPath || "", "app.asar", "node_modules", "sql.js", "dist", file),
    path.join(process.resourcesPath || "", "node_modules", "sql.js", "dist", file),
  ];
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return file;
}

function normalizeWalletWebUrl(apiUrl) {
  const raw = String(apiUrl || "").trim();
  if (!raw) {
    return DEFAULT_WALLET_WEB_URL;
  }
  let base = raw.replace(/\/+$/, "");
  try {
    const parsed = new URL(base);
    const pathName = parsed.pathname.replace(/\/+$/, "") || "";
    if (!pathName || pathName === "/") {
      parsed.pathname = "/wallet";
      return parsed.toString().replace(/\/+$/, "");
    }
    if (!pathName.endsWith("/wallet")) {
      return `${base}/wallet`;
    }
  } catch (_) {
    if (!/\/wallet$/i.test(base)) {
      return `${base}/wallet`;
    }
  }
  return base;
}

function verifyWerkzeugScrypt(pwhash, password) {
  if (!pwhash || typeof password !== "string") {
    return false;
  }
  const parts = pwhash.split("$");
  if (parts.length !== 3) {
    return false;
  }
  const schemeParts = parts[0].split(":");
  if (schemeParts[0] !== "scrypt" || schemeParts.length !== 4) {
    return false;
  }
  const n = Number(schemeParts[1]);
  const r = Number(schemeParts[2]);
  const p = Number(schemeParts[3]);
  const salt = Buffer.from(parts[1], "utf8");
  const expected = Buffer.from(parts[2], "hex");
  if (!n || !salt.length || !expected.length) {
    return false;
  }
  try {
    const derived = crypto.scryptSync(password, salt, expected.length, {
      N: n,
      r,
      p,
      maxmem: 128 * n * r * (p + 2),
    });
    return crypto.timingSafeEqual(derived, expected);
  } catch (_) {
    return false;
  }
}

function publicUser(row) {
  if (!row) {
    return null;
  }
  return {
    id: row.id,
    username: row.username,
    wallet_name: row.wallet_name,
    wallet_encrypted: !!row.wallet_encrypted,
    primary_receive_wallet: row.primary_receive_wallet || row.wallet_name,
    primary_receive_address: row.primary_receive_address || null,
    linked_wallets: row.linked_wallets || [],
  };
}

async function loadUsersDb(dbPath) {
  if (!dbPath || !fs.existsSync(dbPath)) {
    throw new Error(`Users database not found: ${dbPath || "(not set)"}`);
  }
  const SQL = await initSqlJs({ locateFile: sqlWasmPath });
  const db = new SQL.Database(fs.readFileSync(dbPath));
  return db;
}

async function loginWithUsersDb(dbPath, username, password) {
  const db = await loadUsersDb(dbPath);
  const stmt = db.prepare(
    "SELECT id, username, password_hash, wallet_name, wallet_encrypted, primary_receive_wallet, primary_receive_address FROM users WHERE username = ? COLLATE NOCASE LIMIT 1"
  );
  stmt.bind([username.trim()]);
  let row = null;
  if (stmt.step()) {
    row = stmt.getAsObject();
  }
  stmt.free();
  let linked = [];
  if (row?.id) {
    const linkStmt = db.prepare(
      "SELECT wallet_name FROM user_linked_wallets WHERE user_id = ? ORDER BY wallet_name COLLATE NOCASE"
    );
    linkStmt.bind([row.id]);
    while (linkStmt.step()) {
      linked.push(linkStmt.getAsObject().wallet_name);
    }
    linkStmt.free();
  }
  db.close();
  if (!row?.password_hash) {
    return { ok: false, message: "Invalid username or password." };
  }
  if (!verifyWerkzeugScrypt(row.password_hash, password)) {
    return { ok: false, message: "Invalid username or password." };
  }
  if (!row.wallet_name) {
    return { ok: false, message: "No wallet configured for this account." };
  }
  row.linked_wallets = linked;
  return { ok: true, user: publicUser(row) };
}

function requestJsonOnce(urlString, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlString);
    const payload = JSON.stringify(body);
    const lib = url.protocol === "https:" ? https : http;
    const req = lib.request(
      {
        hostname: url.hostname,
        port: url.port || (url.protocol === "https:" ? 443 : 80),
        path: url.pathname + url.search,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
        },
        timeout: 20000,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            body: data,
          });
        });
      }
    );
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Login request timed out — check your internet connection."));
    });
    req.write(payload);
    req.end();
  });
}

async function requestJson(urlString, body, redirectsLeft = 4) {
  const response = await requestJsonOnce(urlString, body);
  const { status, headers, body: raw } = response;
  if (
    redirectsLeft > 0 &&
    status >= 300 &&
    status < 400 &&
    headers.location
  ) {
    const nextUrl = new URL(headers.location, urlString).toString();
    return requestJson(nextUrl, body, redirectsLeft - 1);
  }
  let data = {};
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch (_) {
      if (status === 404) {
        throw new Error(
          "Wallet login API not found. In Settings, set Wallet web URL to " +
            "https://bloodstonewallet.mytunnel.org/wallet (include /wallet)."
        );
      }
      throw new Error(
        `Wallet server returned an unexpected response (HTTP ${status}). ` +
          "Check Wallet web URL in Settings."
      );
    }
  }
  return { status, data };
}

async function loginWithWebApi(apiUrl, username, password) {
  const base = normalizeWalletWebUrl(apiUrl);
  const endpoint = `${base}/api/v1/login`;
  const { status, data } = await requestJson(endpoint, { username, password });
  if (status >= 400 || !data.ok) {
    return {
      ok: false,
      message: data.error || data.message || `Login failed (HTTP ${status}).`,
    };
  }
  if (!data.user?.wallet_name) {
    return { ok: false, message: "No wallet configured for this account." };
  }
  return { ok: true, user: data.user };
}

async function setActiveWalletViaApi(apiUrl, username, password, walletName) {
  const base = normalizeWalletWebUrl(apiUrl);
  const endpoint = `${base}/api/v1/wallet/set-active`;
  const { status, data } = await requestJson(endpoint, {
    username,
    password,
    wallet_name: walletName,
  });
  if (status >= 400 || !data.ok) {
    return {
      ok: false,
      message: data.error || data.message || `Could not switch wallet (HTTP ${status}).`,
    };
  }
  return {
    ok: true,
    walletName: data.wallet_name || walletName,
    address: data.address || null,
    user: data.user || null,
  };
}

async function giftApiRequest(apiUrl, username, password, action, extra = {}) {
  const base = normalizeWalletWebUrl(apiUrl);
  const endpoint = `${base}/api/v1/gift/${action}`;
  const { status, data } = await requestJson(endpoint, {
    username,
    password,
    ...extra,
  });
  if (status >= 400 || !data.ok) {
    return {
      ok: false,
      message: data.error || data.message || `Gift request failed (HTTP ${status}).`,
      needsPassphrase: !!data.needs_passphrase,
    };
  }
  return { ok: true, ...data };
}

async function giftStatusViaApi(apiUrl, username, password) {
  return giftApiRequest(apiUrl, username, password, "status");
}

async function giftListViaApi(apiUrl, username, password) {
  return giftApiRequest(apiUrl, username, password, "list");
}

async function giftCreateViaApi(apiUrl, username, password, amount, passphrase = "") {
  return giftApiRequest(apiUrl, username, password, "create", {
    amount,
    passphrase,
  });
}

async function giftRedeemViaApi(apiUrl, username, password, code) {
  return giftApiRequest(apiUrl, username, password, "redeem", { code });
}

async function referralApiRequest(apiUrl, username, password, action, extra = {}) {
  const base = normalizeWalletWebUrl(apiUrl);
  const endpoint = `${base}/api/v1/referrals/${action}`;
  const { status, data } = await requestJson(endpoint, {
    username,
    password,
    public_base: base,
    ...extra,
  });
  if (status >= 400 || !data.ok) {
    return {
      ok: false,
      message: data.error || data.message || `Referral request failed (HTTP ${status}).`,
    };
  }
  return { ok: true, ...data };
}

async function referralsDashboardViaApi(apiUrl, username, password) {
  return referralApiRequest(apiUrl, username, password, "dashboard");
}

async function referralsLiveViaApi(apiUrl, username, password) {
  return referralApiRequest(apiUrl, username, password, "live");
}

async function referralsDiscordConnectViaApi(apiUrl, username, password) {
  return referralApiRequest(apiUrl, username, password, "discord-connect");
}

async function login(settings, username, password) {
  const trimmedUser = String(username || "").trim();
  if (!trimmedUser || !password) {
    return { ok: false, message: "Enter username and password." };
  }
  if (settings?.usersDbPath) {
    return loginWithUsersDb(settings.usersDbPath, trimmedUser, password);
  }
  const webUrl = normalizeWalletWebUrl(settings?.walletWebUrl);
  return loginWithWebApi(webUrl, trimmedUser, password);
}

module.exports = {
  login,
  loginWithUsersDb,
  loginWithWebApi,
  setActiveWalletViaApi,
  giftStatusViaApi,
  giftListViaApi,
  giftCreateViaApi,
  giftRedeemViaApi,
  referralsDashboardViaApi,
  referralsLiveViaApi,
  referralsDiscordConnectViaApi,
  normalizeWalletWebUrl,
  verifyWerkzeugScrypt,
  publicUser,
};