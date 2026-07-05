package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** Metadata for on-device wallets (addresses only — never private keys). */
final class LocalWalletStore {
    private static final String PREFS = "bloodstone_local_wallets";
    private static final String KEY_WALLETS = "wallets_json";

    private final SharedPreferences prefs;

    LocalWalletStore(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    synchronized void addWallet(String walletName, String address, String source) {
        JSONArray arr = loadArray();
        JSONObject entry = new JSONObject();
        try {
            entry.put("wallet", walletName);
            entry.put("address", address);
            entry.put("source", source != null ? source : "local-node");
            entry.put("createdAt", System.currentTimeMillis());
            arr.put(entry);
            prefs.edit().putString(KEY_WALLETS, arr.toString()).apply();
        } catch (JSONException ignored) {
        }
    }

    synchronized void addAddress(String walletName, String address) {
        JSONArray arr = loadArray();
        try {
            JSONObject entry = new JSONObject();
            entry.put("wallet", walletName);
            entry.put("address", address);
            entry.put("source", "local-node");
            entry.put("createdAt", System.currentTimeMillis());
            arr.put(entry);
            prefs.edit().putString(KEY_WALLETS, arr.toString()).apply();
        } catch (JSONException ignored) {
        }
    }

    synchronized JSONArray listEntries() {
        return loadArray();
    }

    synchronized List<String> addressesForWallet(String walletName) {
        List<String> out = new ArrayList<>();
        JSONArray arr = loadArray();
        for (int i = 0; i < arr.length(); i++) {
            JSONObject row = arr.optJSONObject(i);
            if (row == null) {
                continue;
            }
            if (walletName.equals(row.optString("wallet", ""))) {
                String addr = row.optString("address", "");
                if (!addr.isEmpty()) {
                    out.add(addr);
                }
            }
        }
        return out;
    }

    private JSONArray loadArray() {
        String raw = prefs.getString(KEY_WALLETS, "[]");
        try {
            return new JSONArray(raw);
        } catch (JSONException exc) {
            return new JSONArray();
        }
    }
}