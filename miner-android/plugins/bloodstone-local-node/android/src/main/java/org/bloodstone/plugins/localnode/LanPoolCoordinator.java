package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * LAN pool coordinator: verifies chain/pool state with peers, then serves jobs/shares/payouts locally.
 */
final class LanPoolCoordinator {
    static final int HTTP_PORT = 18342;
    private static final String TAG = "BloodstoneLanPool";
    private static final long VERIFY_INTERVAL_MS = 20000L;

    private static LanPoolCoordinator instance;

    private final Context appContext;
    private final LanPoolDb db;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicBoolean verified = new AtomicBoolean(false);
    private final AtomicInteger peerAgreements = new AtomicInteger(0);
    private final AtomicReference<String> lastPeerHost = new AtomicReference<>("");
    private final AtomicReference<String> verifyDetail = new AtomicReference<>("waiting for peers");

    private LanPoolHttpServer httpServer;
    private Thread verifyThread;
    private LanDiscovery discovery;
    private String deviceId = "";
    private String ownLanIp = "";
    private int blockHeight = 0;
    private String blockHash = "";
    private boolean chainSynced = false;

    private LanPoolCoordinator(Context context) {
        appContext = context.getApplicationContext();
        db = new LanPoolDb(appContext);
    }

    static synchronized LanPoolCoordinator getInstance(Context context) {
        if (instance == null) {
            instance = new LanPoolCoordinator(context);
        }
        return instance;
    }

    void start(String deviceId, LanDiscovery discovery, String ownLanIp) {
        this.deviceId = deviceId != null ? deviceId : "";
        this.ownLanIp = ownLanIp != null ? ownLanIp : "";
        this.discovery = discovery;
        if (running.getAndSet(true)) {
            return;
        }
        startHttpServer();
        verifyThread = new Thread(this::verifyLoop, "bloodstone-lan-pool-verify");
        verifyThread.setDaemon(true);
        verifyThread.start();
        Log.i(TAG, "LAN pool coordinator started on :" + HTTP_PORT);
    }

    void stop() {
        running.set(false);
        verified.set(false);
        peerAgreements.set(0);
        verifyDetail.set("stopped");
        if (verifyThread != null) {
            verifyThread.interrupt();
            verifyThread = null;
        }
        if (httpServer != null) {
            try {
                httpServer.stop();
            } catch (Exception ignored) {
            }
            httpServer = null;
        }
    }

    boolean isLocalPoolActive() {
        return running.get() && verified.get() && chainSynced;
    }

    boolean isVerified() {
        return verified.get();
    }

    int getPeerAgreements() {
        return peerAgreements.get();
    }

    JSONObject getStatus() {
        JSONObject out = new JSONObject();
        try {
            out.put("running", running.get());
            out.put("verified", verified.get());
            out.put("localPoolActive", isLocalPoolActive());
            out.put("peerAgreements", peerAgreements.get());
            out.put("lastPeerHost", lastPeerHost.get());
            out.put("detail", verifyDetail.get());
            out.put("httpPort", HTTP_PORT);
            out.put("blockHeight", blockHeight);
            out.put("blockHash", blockHash != null ? blockHash : "");
            out.put("chainSynced", chainSynced);
            out.put("snapshot", db.buildSnapshot(deviceId, blockHeight, blockHash, chainSynced));
        } catch (Exception ignored) {
        }
        return out;
    }

    void updateChainState(int height, String hash, boolean synced) {
        blockHeight = Math.max(0, height);
        blockHash = hash != null ? hash.trim().toLowerCase(Locale.US) : "";
        chainSynced = synced && blockHeight > 0 && !blockHash.isEmpty();
        if (chainSynced) {
            db.syncOpenRoundJobHeights(blockHeight);
        } else {
            verified.set(false);
            peerAgreements.set(0);
            verifyDetail.set("chain not synced");
        }
    }

    long recordShare(
        String algo,
        String address,
        String worker,
        int jobHeight,
        double weight,
        String peerIp
    ) {
        long shareId = db.recordShare(algo, address, worker, jobHeight, weight, peerIp, null);
        if (shareId > 0 && isLocalPoolActive()) {
            replicateShareToPeers(algo, address, worker, jobHeight, weight, peerIp, shareId);
        }
        return shareId;
    }

    JSONObject onBlockFind(
        String algo,
        int height,
        String hash,
        String finderAddress,
        String finderWorker
    ) {
        JSONObject result = db.distributeBlock(algo, height, hash, finderAddress, finderWorker);
        if (isLocalPoolActive()) {
            broadcastBlockFindToPeers(algo, height, hash, finderAddress, finderWorker);
        }
        return result;
    }

    double pendingBalance(String address) {
        return db.getPendingBalance(address);
    }

    JSONObject localSnapshot() {
        return db.buildSnapshot(deviceId, blockHeight, blockHash, chainSynced);
    }

    private void startHttpServer() {
        httpServer = new LanPoolHttpServer(HTTP_PORT, new LanPoolHttpServer.Handler() {
            @Override
            public JSONObject handleGet(String path, java.util.Map<String, String> params, String remoteIp)
                throws Exception {
                if ("/api/lan-pool/snapshot".equals(path)) {
                    JSONObject snap = db.buildSnapshot(deviceId, blockHeight, blockHash, chainSynced);
                    snap.put("coordinator_active", isLocalPoolActive());
                    snap.put("verified", verified.get());
                    return snap;
                }
                if ("/api/lan-pool/status".equals(path)) {
                    return getStatus();
                }
                if ("/api/lan-pool/balance".equals(path)) {
                    String address = params.get("address");
                    JSONObject out = new JSONObject();
                    out.put("address", address != null ? address : "");
                    out.put("pending_stone", db.getPendingBalance(address));
                    out.put("ok", true);
                    return out;
                }
                JSONObject err = new JSONObject();
                err.put("ok", false);
                err.put("error", "not found");
                return err;
            }

            @Override
            public JSONObject handlePost(String path, String body, String remoteIp) throws Exception {
                JSONObject req = new JSONObject(body != null && !body.isEmpty() ? body : "{}");
                if ("/api/lan-pool/share-import".equals(path)) {
                    long id = db.recordShare(
                        req.optString("algo", ""),
                        req.optString("address", ""),
                        req.optString("worker", ""),
                        req.optInt("job_height", 0),
                        req.optDouble("weight", 1.0),
                        remoteIp,
                        req.optString("import_id", "")
                    );
                    JSONObject out = new JSONObject();
                    out.put("ok", id > 0);
                    out.put("share_id", id);
                    return out;
                }
                if ("/api/lan-pool/block-find".equals(path)) {
                    return db.distributeBlock(
                        req.optString("algo", ""),
                        req.optInt("block_height", 0),
                        req.optString("block_hash", ""),
                        req.optString("finder_address", ""),
                        req.optString("finder_worker", "")
                    );
                }
                JSONObject err = new JSONObject();
                err.put("ok", false);
                err.put("error", "not found");
                return err;
            }
        });
        try {
            httpServer.start();
        } catch (Exception exc) {
            Log.w(TAG, "HTTP server failed: " + exc.getMessage());
        }
    }

    private void verifyLoop() {
        while (running.get()) {
            try {
                tickVerification();
            } catch (Exception exc) {
                Log.w(TAG, "verify tick failed: " + exc.getMessage());
            }
            try {
                Thread.sleep(VERIFY_INTERVAL_MS);
            } catch (InterruptedException exc) {
                break;
            }
        }
    }

    void tickVerification() {
        if (!chainSynced) {
            verified.set(false);
            peerAgreements.set(0);
            verifyDetail.set("sync chain before LAN pool coordinator");
            return;
        }
        if (discovery == null) {
            verifyDetail.set("no LAN discovery");
            return;
        }
        JSONObject local = db.buildSnapshot(deviceId, blockHeight, blockHash, true);
        List<LanDiscovery.DiscoveredPeer> peers = discovery.getDiscoveredPeers();
        int agreements = 0;
        String matchedHost = "";
        String detail = "no LAN peers found";
        for (LanDiscovery.DiscoveredPeer peer : peers) {
            if (peer.host == null || peer.host.isEmpty()) {
                continue;
            }
            if (isOwnHost(peer.host)) {
                continue;
            }
            JSONObject remote = fetchPeerSnapshot(peer.host);
            if (remote == null) {
                continue;
            }
            if (snapshotsAgree(local, remote)) {
                agreements++;
                matchedHost = peer.host;
                detail = "agrees with " + peer.host;
            }
        }
        peerAgreements.set(agreements);
        lastPeerHost.set(matchedHost);
        boolean nowVerified = agreements >= 1;
        if (nowVerified != verified.get()) {
            Log.i(
                TAG,
                "LAN pool coordinator "
                    + (nowVerified ? "ACTIVE" : "inactive")
                    + " — peer agreements="
                    + agreements
            );
        }
        verified.set(nowVerified);
        verifyDetail.set(
            nowVerified
                ? "verified with " + agreements + " peer(s); local pool replaces VPS"
                : detail
        );
    }

    static boolean snapshotsAgree(JSONObject local, JSONObject remote) {
        if (local == null || remote == null) {
            return false;
        }
        if (local.optInt("block_height") != remote.optInt("block_height")) {
            return false;
        }
        String localHash = local.optString("block_hash", "").toLowerCase(Locale.US);
        String remoteHash = remote.optString("block_hash", "").toLowerCase(Locale.US);
        if (localHash.isEmpty() || remoteHash.isEmpty() || !localHash.equals(remoteHash)) {
            return false;
        }
        if (!remote.optBoolean("chain_synced", false)) {
            return false;
        }
        JSONObject localAlgos = local.optJSONObject("algos");
        JSONObject remoteAlgos = remote.optJSONObject("algos");
        if (localAlgos == null || remoteAlgos == null) {
            return false;
        }
        JSONArray names = localAlgos.names();
        if (names == null) {
            return true;
        }
        for (int i = 0; i < names.length(); i++) {
            String algo = names.optString(i, "");
            JSONObject la = localAlgos.optJSONObject(algo);
            JSONObject ra = remoteAlgos.optJSONObject(algo);
            if (la == null || ra == null) {
                return false;
            }
            if (la.optInt("job_height") != ra.optInt("job_height")) {
                return false;
            }
            double lw = la.optDouble("total_weight", 0.0);
            double rw = ra.optDouble("total_weight", 0.0);
            double max = Math.max(lw, rw);
            if (max > 0 && Math.abs(lw - rw) / max > 0.05) {
                return false;
            }
        }
        JSONArray localFinds = local.optJSONArray("recent_block_finds");
        JSONArray remoteFinds = remote.optJSONArray("recent_block_finds");
        if (localFinds != null && remoteFinds != null && localFinds.length() > 0 && remoteFinds.length() > 0) {
            JSONObject lf = localFinds.optJSONObject(0);
            JSONObject rf = remoteFinds.optJSONObject(0);
            if (lf != null && rf != null) {
                if (lf.optInt("height") != rf.optInt("height")) {
                    return false;
                }
                String lh = lf.optString("hash", "").toLowerCase(Locale.US);
                String rh = rf.optString("hash", "").toLowerCase(Locale.US);
                if (!lh.isEmpty() && !rh.isEmpty() && !lh.equals(rh)) {
                    return false;
                }
            }
        }
        return true;
    }

    private JSONObject fetchPeerSnapshot(String host) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL("http://" + host + ":" + HTTP_PORT + "/api/lan-pool/snapshot");
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(4000);
            conn.setRequestMethod("GET");
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                return null;
            }
            StringBuilder sb = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8)
            )) {
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line);
                }
            }
            return new JSONObject(sb.toString());
        } catch (Exception exc) {
            return null;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private void replicateShareToPeers(
        String algo,
        String address,
        String worker,
        int jobHeight,
        double weight,
        String peerIp,
        long shareId
    ) {
        if (discovery == null) {
            return;
        }
        JSONObject payload = new JSONObject();
        try {
            payload.put("algo", algo);
            payload.put("address", address);
            payload.put("worker", worker);
            payload.put("job_height", jobHeight);
            payload.put("weight", weight);
            payload.put("import_id", LanPoolShareUtil.shareImportId(deviceId, shareId));
        } catch (Exception ignored) {
            return;
        }
        for (LanDiscovery.DiscoveredPeer peer : discovery.getDiscoveredPeers()) {
            if (peer.host == null || peer.host.isEmpty() || isOwnHost(peer.host)) {
                continue;
            }
            postJson(peer.host, "/api/lan-pool/share-import", payload);
        }
    }

    private void broadcastBlockFindToPeers(
        String algo,
        int height,
        String hash,
        String finderAddress,
        String finderWorker
    ) {
        if (discovery == null) {
            return;
        }
        JSONObject payload = new JSONObject();
        try {
            payload.put("algo", algo);
            payload.put("block_height", height);
            payload.put("block_hash", hash);
            payload.put("finder_address", finderAddress);
            payload.put("finder_worker", finderWorker);
        } catch (Exception ignored) {
            return;
        }
        for (LanDiscovery.DiscoveredPeer peer : discovery.getDiscoveredPeers()) {
            if (peer.host == null || peer.host.isEmpty() || isOwnHost(peer.host)) {
                continue;
            }
            postJson(peer.host, "/api/lan-pool/block-find", payload);
        }
    }

    private boolean isOwnHost(String host) {
        if (host == null || host.isEmpty()) {
            return true;
        }
        if ("127.0.0.1".equals(host) || "::1".equals(host)) {
            return true;
        }
        return !ownLanIp.isEmpty() && ownLanIp.equals(host);
    }

    private void postJson(String host, String path, JSONObject payload) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL("http://" + host + ":" + HTTP_PORT + path);
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(4000);
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
            try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(conn.getOutputStream(), StandardCharsets.UTF_8)
            )) {
                writer.write(payload.toString());
            }
            conn.getResponseCode();
        } catch (Exception ignored) {
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }
}