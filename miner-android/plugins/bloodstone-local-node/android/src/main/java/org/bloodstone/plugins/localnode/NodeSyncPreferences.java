package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.content.SharedPreferences;

final class NodeSyncPreferences {
    private static final String PREFS = "bloodstone_node_sync";
    private static final String KEY_ENABLED = "enabled";
    private static final String KEY_UPSTREAM_URL = "upstream_url";
    private static final String KEY_PRUNE_MIB = "prune_mib";
    private static final String KEY_NODE_MODE = "node_mode";
    private static final String KEY_LAST_LOCAL_HEIGHT = "last_local_height";
    private static final String KEY_LAST_NETWORK_HEIGHT = "last_network_height";
    private static final String KEY_LAST_SYNC_AT = "last_sync_at";
    private static final String KEY_LAST_CHECK_AT = "last_check_at";

    static final String DEFAULT_UPSTREAM =
        "https://bloodstonewallet.mytunnel.org/mining/api/local-node/rpc";

    private final SharedPreferences prefs;

    NodeSyncPreferences(Context context) {
        prefs = context.getApplicationContext()
            .getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    void saveConfig(String upstreamUrl, int pruneMiB, String nodeMode) {
        prefs.edit()
            .putBoolean(KEY_ENABLED, true)
            .putString(KEY_UPSTREAM_URL, LanEndpointUrls.normalizeUpstream(upstreamUrl))
            .putInt(KEY_PRUNE_MIB, pruneMiB)
            .putString(KEY_NODE_MODE, normalizeStoredMode(nodeMode))
            .apply();
    }

    void setEnabled(boolean enabled) {
        prefs.edit().putBoolean(KEY_ENABLED, enabled).apply();
    }

    boolean isEnabled() {
        return prefs.getBoolean(KEY_ENABLED, false);
    }

    String upstreamUrl() {
        String raw = prefs.getString(KEY_UPSTREAM_URL, DEFAULT_UPSTREAM);
        String normalized = LanEndpointUrls.normalizeUpstream(raw);
        if (!normalized.equals(raw)) {
            prefs.edit().putString(KEY_UPSTREAM_URL, normalized).apply();
        }
        return normalized;
    }

    int pruneMiB() {
        return prefs.getInt(KEY_PRUNE_MIB, 550);
    }

    String nodeMode() {
        return normalizeStoredMode(prefs.getString(KEY_NODE_MODE, "pruned"));
    }

    private static String normalizeStoredMode(String mode) {
        if (mode == null) {
            return "pruned";
        }
        String m = mode.trim().toLowerCase();
        if ("lan-client".equals(m) || "lan_client".equals(m)) {
            return "lan-client";
        }
        return PrunedNodeRunner.normalizeMode(mode);
    }

    int lastLocalHeight() {
        return prefs.getInt(KEY_LAST_LOCAL_HEIGHT, 0);
    }

    int lastNetworkHeight() {
        return prefs.getInt(KEY_LAST_NETWORK_HEIGHT, 0);
    }

    long lastSyncAt() {
        return prefs.getLong(KEY_LAST_SYNC_AT, 0L);
    }

    long lastCheckAt() {
        return prefs.getLong(KEY_LAST_CHECK_AT, 0L);
    }

    void recordCheck(int localHeight, int networkHeight) {
        prefs.edit()
            .putInt(KEY_LAST_LOCAL_HEIGHT, localHeight)
            .putInt(KEY_LAST_NETWORK_HEIGHT, networkHeight)
            .putLong(KEY_LAST_CHECK_AT, System.currentTimeMillis())
            .apply();
    }

    void recordSyncComplete(int localHeight, int networkHeight) {
        prefs.edit()
            .putInt(KEY_LAST_LOCAL_HEIGHT, localHeight)
            .putInt(KEY_LAST_NETWORK_HEIGHT, networkHeight)
            .putLong(KEY_LAST_SYNC_AT, System.currentTimeMillis())
            .putLong(KEY_LAST_CHECK_AT, System.currentTimeMillis())
            .apply();
    }
}