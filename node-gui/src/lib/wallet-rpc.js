const http = require("http");
const { activeRpcCredentials } = require("./config");

const TRANSIENT_RPC_RE =
  /Loading wallet|Verifying blocks|Rescanning|Warmup|initializing|Loading block index|Reindexing|timeout on transient/i;

class WalletRpc {
  constructor(getSettings) {
    this.getSettings = getSettings;
  }

  _endpoint(wallet) {
    const creds = activeRpcCredentials(this.getSettings());
    const auth = `${creds.rpcUser}:${creds.rpcPassword}`;
    const rpcPath = wallet ? `/wallet/${encodeURIComponent(wallet)}` : "/";
    return {
      host: creds.rpcHost,
      port: creds.rpcPort || 18332,
      auth,
      path: rpcPath,
      profile: creds.rpcProfile,
    };
  }

  rpc(method, params = [], wallet = null, retries = 6, retryDelayMs = 2000) {
    let lastError = null;
    const attempt = async (left) => {
      try {
        return await this._rpcOnce(method, params, wallet);
      } catch (err) {
        lastError = err;
        if (left <= 1 || !TRANSIENT_RPC_RE.test(String(err.message || err))) {
          throw err;
        }
        await new Promise((r) => setTimeout(r, retryDelayMs));
        return attempt(left - 1);
      }
    };
    return attempt(retries);
  }

  _rpcOnce(method, params, wallet) {
    const settings = this.getSettings();
    const { host, port, auth, path, profile } = this._endpoint(wallet);
    const body = JSON.stringify({
      jsonrpc: "1.0",
      id: "bloodstone-wallet-gui",
      method,
      params,
    });
    const authHeader = Buffer.from(auth).toString("base64");

    return new Promise((resolve, reject) => {
      const req = http.request(
        {
          hostname: host,
          port,
          path,
          method: "POST",
          headers: {
            "Content-Type": "text/plain",
            Authorization: `Basic ${authHeader}`,
            "Content-Length": Buffer.byteLength(body),
          },
          timeout: 30000,
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => {
            data += chunk;
          });
          res.on("end", () => {
            try {
              const parsed = JSON.parse(data || "{}");
              if (parsed.error) {
                const msg = String(parsed.error.message || parsed.error);
                if (/incorrect rpcuser|rpcpassword|rpc password/i.test(msg)) {
                  const hint =
                    profile === "vps" || (settings.rpcHost && settings.rpcHost !== "127.0.0.1")
                      ? "Wallet VPS RPC credentials are out of date. Reinstall the latest GUI or open Settings → Use VPS."
                      : "Local node RPC password mismatch. Open bloodstone.conf in your data folder and use Settings → Local node, then restart the node.";
                  reject(new Error(`${msg} ${hint}`));
                  return;
                }
                reject(new Error(msg));
              } else {
                resolve(parsed.result);
              }
            } catch (err) {
              reject(err);
            }
          });
        }
      );
      req.on("error", reject);
      req.on("timeout", () => {
        req.destroy();
        reject(new Error("RPC request timed out"));
      });
      req.write(body);
      req.end();
    });
  }

  async ensureWalletLoaded(wallet) {
    const settings = this.getSettings();
    const wallets = await this.rpc("listwallets");
    if (!wallets.includes(wallet)) {
      try {
        await this.rpc("loadwallet", [wallet]);
      } catch (err) {
        if (/already loaded/i.test(String(err.message))) {
          return;
        }
        const msg = String(err.message || err);
        if (/path does not exist/i.test(msg) && (settings.rpcHost || "127.0.0.1") === "127.0.0.1") {
          throw new Error(
            `Wallet "${wallet}" is not on this PC. Open Settings → Use VPS, then sign in again. ` +
              `(VPS-only wallets like "mine" cannot load from a local node.)`
          );
        }
        throw err;
      }
    }
  }

  async walletSummary(wallet) {
    await this.ensureWalletLoaded(wallet);
    const info = await this.rpc("getwalletinfo", [], wallet);
    const balances = await this.rpc("getbalances", [], wallet).catch(() => null);
    const spendable =
      balances?.mine?.trusted ??
      info.balance ??
      0;
    return {
      wallet,
      balance: Number(spendable),
      unconfirmed: Number(balances?.mine?.untrusted_pending ?? info.unconfirmed_balance ?? 0),
      immature: Number(balances?.mine?.immature ?? info.immature_balance ?? 0),
      txcount: info.txcount ?? 0,
      unlocked_until: info.unlocked_until ?? 0,
      private_keys_enabled: info.private_keys_enabled !== false,
    };
  }

  async listTransactions(wallet, count = 20, skip = 0) {
    await this.ensureWalletLoaded(wallet);
    const all = await this.rpc("listtransactions", ["*", 1000, 0, true], wallet);
    const sorted = WalletRpc.sortTransactions(all);
    return sorted.slice(skip, skip + count);
  }

  /**
   * Put real chain activity first (newest at top), stale solo-mined orphans last.
   */
  static sortTransactions(txs) {
    return [...txs].sort((a, b) => {
      const aOrphan = a?.category === "orphan";
      const bOrphan = b?.category === "orphan";
      if (aOrphan !== bOrphan) {
        return aOrphan ? 1 : -1;
      }
      const aHeight = Number(a?.blockheight ?? 0);
      const bHeight = Number(b?.blockheight ?? 0);
      if (bHeight !== aHeight) {
        return bHeight - aHeight;
      }
      const aTime = Number(a?.timereceived ?? a?.time ?? 0);
      const bTime = Number(b?.timereceived ?? b?.time ?? 0);
      return bTime - aTime;
    });
  }

  async listAddresses(wallet) {
    await this.ensureWalletLoaded(wallet);
    const received = await this.rpc("listreceivedbyaddress", [0, true, true], wallet);
    return received.sort((a, b) => (b.amount || 0) - (a.amount || 0));
  }

  async unlockWallet(wallet, passphrase, seconds = 1800) {
    await this.ensureWalletLoaded(wallet);
    await this.rpc("walletpassphrase", [passphrase, seconds], wallet);
  }

  async lockWallet(wallet) {
    await this.ensureWalletLoaded(wallet);
    try {
      await this.rpc("walletlock", [], wallet);
    } catch (_) {
      /* ignore */
    }
  }

  async sendToAddress(wallet, address, amount, comment = "", passphrase = "") {
    await this.ensureWalletLoaded(wallet);
    if (passphrase) {
      await this.unlockWallet(wallet, passphrase, 600);
    }
    const params = [address, amount, comment, "", false, true, null, "unset", false, 100, true];
    return this.rpc("sendtoaddress", params, wallet);
  }

  async getNewAddress(wallet, label = "receive") {
    await this.ensureWalletLoaded(wallet);
    return this.rpc("getnewaddress", [label], wallet);
  }
}

module.exports = { WalletRpc };