package org.bloodstone.plugins.localnode;

import org.json.JSONArray;
import org.json.JSONObject;

/** Wallet RPC against the on-device bloodstoned (127.0.0.1 only). */
final class LocalWalletRpc {
    private final String baseUrl;

    LocalWalletRpc(RpcCredentials credentials) {
        this.baseUrl = "http://" + credentials.user() + ":" + credentials.password()
            + "@127.0.0.1:18332/";
    }

    JSONObject call(String method, JSONArray params) throws Exception {
        return new UpstreamRpcClient(baseUrl).call(method, params, "local-wallet");
    }

    JSONObject callWallet(String method, JSONArray params, String wallet) throws Exception {
        String url = baseUrl;
        if (!url.endsWith("/")) {
            url += "/";
        }
        url += "wallet/" + wallet;
        return new UpstreamRpcClient(url).call(method, params, "local-wallet");
    }

    void createLegacyWallet(String walletName) throws Exception {
        JSONArray params = new JSONArray();
        params.put(walletName);
        params.put(false); // disable_private_keys
        params.put(false); // blank
        params.put(""); // passphrase (encrypt separately)
        params.put(false); // avoid_reuse
        params.put(false); // descriptors
        params.put(true); // load_on_startup
        call("createwallet", params);
    }

    void loadWallet(String walletName) throws Exception {
        JSONArray params = new JSONArray();
        params.put(walletName);
        call("loadwallet", params);
    }

    String getNewAddress(String walletName, String label) throws Exception {
        JSONArray params = new JSONArray();
        params.put(label != null ? label : "mobile");
        JSONObject response = callWallet("getnewaddress", params, walletName);
        return response.getString("result");
    }

    void encryptWallet(String walletName, String passphrase) throws Exception {
        JSONArray params = new JSONArray();
        params.put(passphrase);
        callWallet("encryptwallet", params, walletName);
    }

    JSONArray listWalletDir() throws Exception {
        JSONObject response = call("listwalletdir", new JSONArray());
        JSONObject result = response.getJSONObject("result");
        return result.optJSONArray("wallets");
    }

    JSONArray listWallets() throws Exception {
        JSONObject response = call("listwallets", new JSONArray());
        return response.getJSONArray("result");
    }

    boolean walletExists(String walletName) throws Exception {
        JSONArray wallets = listWalletDir();
        if (wallets == null) {
            return false;
        }
        for (int i = 0; i < wallets.length(); i++) {
            JSONObject entry = wallets.getJSONObject(i);
            if (walletName.equals(entry.optString("name", ""))) {
                return true;
            }
        }
        return false;
    }

    void ensureWalletLoaded(String walletName) throws Exception {
        if (!walletExists(walletName)) {
            createLegacyWallet(walletName);
            return;
        }
        JSONArray loaded = listWallets();
        for (int i = 0; i < loaded.length(); i++) {
            if (walletName.equals(loaded.optString(i, ""))) {
                return;
            }
        }
        loadWallet(walletName);
    }

    JSONObject getWalletInfo(String walletName) throws Exception {
        JSONObject response = callWallet("getwalletinfo", new JSONArray(), walletName);
        return response.getJSONObject("result");
    }
}