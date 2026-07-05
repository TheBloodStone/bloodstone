const fs = require("fs");
const path = require("path");
const http = require("http");
const https = require("https");
const { WalletRpc } = require("./wallet-rpc");
const { applyVpsPreset, activeRpcCredentials } = require("./config");

function makeVpsRpc(getSettings) {
  return new WalletRpc(() => applyVpsPreset(getSettings()));
}

function makeLocalRpc(getSettings) {
  return new WalletRpc(() => ({
    ...getSettings(),
    ...activeRpcCredentials({
      ...getSettings(),
      rpcHost: "127.0.0.1",
      rpcProfile: "local",
    }),
  }));
}

async function listWalletsOn(rpc) {
  const dir = await rpc.rpc("listwalletdir");
  const loaded = await rpc.rpc("listwallets");
  const names = new Set();
  for (const entry of dir?.wallets || []) {
    if (entry?.name) {
      names.add(entry.name);
    }
  }
  for (const name of loaded || []) {
    names.add(name);
  }
  return [...names].sort((a, b) => a.localeCompare(b));
}

function requestJson(urlString, body) {
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
        timeout: 120000,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          try {
            resolve({ status: res.statusCode, data: JSON.parse(data || "{}") });
          } catch (err) {
            reject(new Error(`Invalid JSON from server: ${err.message}`));
          }
        });
      }
    );
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Request timed out"));
    });
    req.write(payload);
    req.end();
  });
}

async function fetchDumpViaApi({
  walletWebUrl,
  username,
  password,
  walletName,
  passphrase,
}) {
  const base = (walletWebUrl || "").replace(/\/+$/, "");
  if (!base) {
    throw new Error("Wallet web URL is not configured");
  }
  const { status, data } = await requestJson(`${base}/api/v1/wallet/export`, {
    username,
    password,
    wallet_name: walletName,
    passphrase,
  });
  if (status >= 400 || !data.ok) {
    throw new Error(data.error || data.message || `Export failed (HTTP ${status})`);
  }
  if (!data.content) {
    throw new Error("Export returned no wallet data");
  }
  return data.content;
}

async function collectAddresses(rpc, walletName) {
  const set = new Set();
  const received = await rpc.rpc("listreceivedbyaddress", [0, true, true], walletName);
  for (const row of received || []) {
    if (row.address) {
      set.add(row.address);
    }
  }
  const unspent = await rpc.rpc("listunspent", [0, 9999999, 0, {}, walletName]);
  for (const row of unspent || []) {
    if (row.address) {
      set.add(row.address);
    }
  }
  const txs = await rpc.listTransactions(walletName, 1000);
  for (const tx of txs || []) {
    if (tx.address) {
      set.add(tx.address);
    }
  }
  try {
    const labels = await rpc.rpc("listlabels", [], walletName);
    for (const label of labels || []) {
      const byLabel = await rpc.rpc("getaddressesbylabel", [label], walletName);
      for (const addr of Object.keys(byLabel || {})) {
        set.add(addr);
      }
    }
  } catch (_) {
    /* optional */
  }
  return [...set];
}

async function exportKeysToDumpContent(vpsRpc, walletName, passphrase) {
  await vpsRpc.ensureWalletLoaded(walletName);
  if (passphrase) {
    await vpsRpc.unlockWallet(walletName, passphrase, 600);
  }
  const addresses = await collectAddresses(vpsRpc, walletName);
  const lines = [
    "# Bloodstone wallet dump",
    `# wallet: ${walletName}`,
    `# exported: ${new Date().toISOString()}`,
    "",
  ];
  let count = 0;
  const nowIso = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  for (const addr of addresses) {
    try {
      const wif = await vpsRpc.rpc("dumpprivkey", [addr], walletName);
      lines.push(`${wif} ${nowIso} label=imported # addr=${addr}`);
      count += 1;
    } catch (_) {
      /* skip */
    }
  }
  if (!count) {
    throw new Error(
      "Could not export any keys from VPS. Check the wallet passphrase and try the web export API."
    );
  }
  return `${lines.join("\n")}\n`;
}

async function ensureLocalWallet(rpc, walletName) {
  const dir = await rpc.rpc("listwalletdir");
  const exists = (dir?.wallets || []).some((w) => w.name === walletName);
  const loaded = await rpc.rpc("listwallets");
  if (!exists) {
    await rpc.rpc("createwallet", [walletName, false, false, "", false, false, true]);
    return;
  }
  if (!loaded.includes(walletName)) {
    await rpc.rpc("loadwallet", [walletName]);
  }
}

async function importDumpToLocal(localRpc, walletName, dumpContent, dataDir) {
  const importsDir = path.join(dataDir, "imports");
  fs.mkdirSync(importsDir, { recursive: true });
  const dumpPath = path.join(importsDir, `${walletName}-${Date.now()}.txt`);
  fs.writeFileSync(dumpPath, dumpContent, { encoding: "utf8", mode: 0o600 });
  await ensureLocalWallet(localRpc, walletName);
  await localRpc.rpc("importwallet", [dumpPath], walletName);
  return {
    dumpPath,
    message: `Imported "${walletName}" into local node. Wallet rescan may take several minutes.`,
  };
}

async function importPrivKeysToLocal(localRpc, vpsRpc, walletName, passphrase) {
  await vpsRpc.ensureWalletLoaded(walletName);
  if (passphrase) {
    await vpsRpc.unlockWallet(walletName, passphrase, 600);
  }
  const addresses = await collectAddresses(vpsRpc, walletName);
  await ensureLocalWallet(localRpc, walletName);
  let imported = 0;
  for (let i = 0; i < addresses.length; i += 1) {
    const addr = addresses[i];
    const rescan = i === addresses.length - 1;
    try {
      const wif = await vpsRpc.rpc("dumpprivkey", [addr], walletName);
      await localRpc.rpc("importprivkey", [wif, "", rescan], walletName);
      imported += 1;
    } catch (_) {
      /* skip */
    }
  }
  if (!imported) {
    throw new Error("No private keys could be imported. Check the wallet passphrase.");
  }
  return {
    message: `Imported ${imported} key(s) into local wallet "${walletName}".`,
    keysImported: imported,
  };
}

async function listUserWalletsViaApi(walletWebUrl, username, password) {
  const base = (walletWebUrl || "").replace(/\/+$/, "");
  const { status, data } = await requestJson(`${base}/api/v1/wallets`, {
    username,
    password,
  });
  if (status >= 400 || !data.ok) {
    throw new Error(data.error || data.message || `List wallets failed (HTTP ${status})`);
  }
  return data.wallets || [];
}

async function importWalletFromVps({
  getSettings,
  walletName,
  passphrase,
  username,
  password,
  localNodeReachable,
}) {
  if (!walletName) {
    throw new Error("Wallet name is required");
  }
  if (!localNodeReachable) {
    throw new Error("Local node RPC is not reachable. Start the node first (Node tab → Start Node).");
  }

  const settings = getSettings();
  const vpsRpc = makeVpsRpc(getSettings);
  const localRpc = makeLocalRpc(getSettings);

  await localRpc.rpc("getblockchaininfo");

  let dumpContent = null;
  let method = "api";
  if (username && password && settings.walletWebUrl) {
    try {
      dumpContent = await fetchDumpViaApi({
        walletWebUrl: settings.walletWebUrl,
        username,
        password,
        walletName,
        passphrase,
      });
    } catch (err) {
      method = "rpc-keys";
      dumpContent = await exportKeysToDumpContent(vpsRpc, walletName, passphrase).catch(
        () => {
          throw err;
        }
      );
    }
  } else {
    method = "rpc-keys";
    try {
      dumpContent = await exportKeysToDumpContent(vpsRpc, walletName, passphrase);
    } catch (err) {
      const fallback = await importPrivKeysToLocal(
        localRpc,
        vpsRpc,
        walletName,
        passphrase
      );
      return { ok: true, method: "importprivkey", ...fallback };
    }
  }

  const result = await importDumpToLocal(
    localRpc,
    walletName,
    dumpContent,
    settings.dataDir
  );
  return { ok: true, method, ...result };
}

module.exports = {
  makeVpsRpc,
  makeLocalRpc,
  listWalletsOn,
  listUserWalletsViaApi,
  importWalletFromVps,
};