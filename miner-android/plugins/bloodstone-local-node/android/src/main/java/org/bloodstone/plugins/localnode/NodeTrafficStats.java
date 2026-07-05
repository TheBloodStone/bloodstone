package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.TrafficStats;
import android.os.Process;

import org.json.JSONObject;

import java.util.concurrent.atomic.AtomicLong;

/** Cumulative network + node work counters for the local full/pruned node. */
final class NodeTrafficStats {
    private static final String PREFS = "bloodstone_node_traffic";
    private static final String KEY_RX = "total_rx_bytes";
    private static final String KEY_TX = "total_tx_bytes";
    private static final String KEY_UP_RX = "upstream_rx_bytes";
    private static final String KEY_UP_TX = "upstream_tx_bytes";
    private static final String KEY_LAN_RX = "lan_rx_bytes";
    private static final String KEY_LAN_TX = "lan_tx_bytes";
    private static final String KEY_RPC_REQUESTS = "rpc_requests";
    private static final String KEY_STRATUM_CONN = "stratum_connections";
    private static final String KEY_BLOCKS_SYNCED = "blocks_synced";
    private static final String KEY_SYNC_SESSIONS = "sync_sessions";
    private static final String KEY_UPTIME_SEC = "node_uptime_sec";
    private static final String KEY_SESSION_STARTED = "session_started_ms";

    private static final AtomicLong SESSION_RX = new AtomicLong(0);
    private static final AtomicLong SESSION_TX = new AtomicLong(0);
    private static volatile long sessionStartedMs = 0L;
    private static volatile long uptimeTickerStartedMs = 0L;

    private NodeTrafficStats() {}

    static void markSessionStart() {
        sessionStartedMs = System.currentTimeMillis();
        uptimeTickerStartedMs = sessionStartedMs;
        SESSION_RX.set(0);
        SESSION_TX.set(0);
        Context ctx = NodeTrafficStatsHolder.appContext;
        if (ctx != null) {
            prefs(ctx).edit().putLong(KEY_SESSION_STARTED, sessionStartedMs).apply();
        }
    }

    static void markSessionEnd(Context context) {
        flushUptime(context);
        sessionStartedMs = 0L;
        uptimeTickerStartedMs = 0L;
    }

    static void recordUpstream(long rxBytes, long txBytes) {
        SESSION_RX.addAndGet(rxBytes);
        SESSION_TX.addAndGet(txBytes);
        Context ctx = NodeTrafficStatsHolder.appContext;
        if (ctx == null) {
            return;
        }
        SharedPreferences p = prefs(ctx);
        p.edit()
            .putLong(KEY_UP_RX, p.getLong(KEY_UP_RX, 0L) + rxBytes)
            .putLong(KEY_UP_TX, p.getLong(KEY_UP_TX, 0L) + txBytes)
            .putLong(KEY_RX, p.getLong(KEY_RX, 0L) + rxBytes)
            .putLong(KEY_TX, p.getLong(KEY_TX, 0L) + txBytes)
            .apply();
    }

    static void recordLanRpc(long rxBytes, long txBytes) {
        SESSION_RX.addAndGet(rxBytes);
        SESSION_TX.addAndGet(txBytes);
        Context ctx = NodeTrafficStatsHolder.appContext;
        if (ctx == null) {
            return;
        }
        SharedPreferences p = prefs(ctx);
        p.edit()
            .putLong(KEY_LAN_RX, p.getLong(KEY_LAN_RX, 0L) + rxBytes)
            .putLong(KEY_LAN_TX, p.getLong(KEY_LAN_TX, 0L) + txBytes)
            .putLong(KEY_RX, p.getLong(KEY_RX, 0L) + rxBytes)
            .putLong(KEY_TX, p.getLong(KEY_TX, 0L) + txBytes)
            .putLong(KEY_RPC_REQUESTS, p.getLong(KEY_RPC_REQUESTS, 0L) + 1L)
            .apply();
    }

    static void recordLanStratum(long rxBytes, long txBytes) {
        SESSION_RX.addAndGet(rxBytes);
        SESSION_TX.addAndGet(txBytes);
        Context ctx = NodeTrafficStatsHolder.appContext;
        if (ctx == null) {
            return;
        }
        SharedPreferences p = prefs(ctx);
        p.edit()
            .putLong(KEY_LAN_RX, p.getLong(KEY_LAN_RX, 0L) + rxBytes)
            .putLong(KEY_LAN_TX, p.getLong(KEY_LAN_TX, 0L) + txBytes)
            .putLong(KEY_RX, p.getLong(KEY_RX, 0L) + rxBytes)
            .putLong(KEY_TX, p.getLong(KEY_TX, 0L) + txBytes)
            .apply();
    }

    static void recordStratumConnection() {
        Context ctx = NodeTrafficStatsHolder.appContext;
        if (ctx == null) {
            return;
        }
        SharedPreferences p = prefs(ctx);
        p.edit()
            .putLong(KEY_STRATUM_CONN, p.getLong(KEY_STRATUM_CONN, 0L) + 1L)
            .apply();
    }

    static void recordSyncSession(int blocksSynced) {
        Context ctx = NodeTrafficStatsHolder.appContext;
        if (ctx == null) {
            return;
        }
        SharedPreferences p = prefs(ctx);
        p.edit()
            .putLong(KEY_SYNC_SESSIONS, p.getLong(KEY_SYNC_SESSIONS, 0L) + 1L)
            .putLong(
                KEY_BLOCKS_SYNCED,
                p.getLong(KEY_BLOCKS_SYNCED, 0L) + Math.max(0, blocksSynced)
            )
            .apply();
    }

    static void tickUptime(Context context) {
        if (uptimeTickerStartedMs <= 0L) {
            return;
        }
        long now = System.currentTimeMillis();
        long deltaSec = Math.max(0L, (now - uptimeTickerStartedMs) / 1000L);
        if (deltaSec <= 0L) {
            return;
        }
        uptimeTickerStartedMs = now;
        SharedPreferences p = prefs(context);
        p.edit()
            .putLong(KEY_UPTIME_SEC, p.getLong(KEY_UPTIME_SEC, 0L) + deltaSec)
            .apply();
    }

    private static void flushUptime(Context context) {
        tickUptime(context);
    }

    static JSONObject snapshot(Context context, String nodeMode, boolean running) {
        if (running) {
            tickUptime(context);
        }
        SharedPreferences p = prefs(context);
        long uidRx = TrafficStats.getUidRxBytes(Process.myUid());
        long uidTx = TrafficStats.getUidTxBytes(Process.myUid());
        if (uidRx < 0) {
            uidRx = 0L;
        }
        if (uidTx < 0) {
            uidTx = 0L;
        }
        JSONObject out = new JSONObject();
        try {
            out.put("nodeMode", nodeMode != null ? nodeMode : "stopped");
            out.put("running", running);
            out.put("sessionRxBytes", SESSION_RX.get());
            out.put("sessionTxBytes", SESSION_TX.get());
            out.put("totalRxBytes", p.getLong(KEY_RX, 0L));
            out.put("totalTxBytes", p.getLong(KEY_TX, 0L));
            out.put("upstreamRxBytes", p.getLong(KEY_UP_RX, 0L));
            out.put("upstreamTxBytes", p.getLong(KEY_UP_TX, 0L));
            out.put("lanRxBytes", p.getLong(KEY_LAN_RX, 0L));
            out.put("lanTxBytes", p.getLong(KEY_LAN_TX, 0L));
            out.put("appUidRxBytes", uidRx);
            out.put("appUidTxBytes", uidTx);
            out.put("rpcRequestsServed", p.getLong(KEY_RPC_REQUESTS, 0L));
            out.put("stratumConnections", p.getLong(KEY_STRATUM_CONN, 0L));
            out.put("blocksSynced", p.getLong(KEY_BLOCKS_SYNCED, 0L));
            out.put("syncSessions", p.getLong(KEY_SYNC_SESSIONS, 0L));
            out.put("nodeUptimeSec", p.getLong(KEY_UPTIME_SEC, 0L));
            out.put(
                "sessionStartedAt",
                sessionStartedMs > 0L ? sessionStartedMs : p.getLong(KEY_SESSION_STARTED, 0L)
            );
        } catch (Exception ignored) {
        }
        return out;
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}