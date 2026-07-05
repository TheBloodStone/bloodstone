package org.bloodstone.plugins.chainmesh;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;

final class PeerIpRegistry {
    private static final String TAG = "BloodstonePeerRegistry";
    private static final String REGISTRY_FILE = "peer-ip-registry.json";
    private static final int MAX_PEERS = 64;
    private static final int MAX_FAILURES = 5;

    private final File registryFile;

    PeerIpRegistry(File storeRoot) {
        registryFile = new File(storeRoot, REGISTRY_FILE);
    }

    synchronized List<PeerEndpoint> listPeers() {
        JSONObject root = readRoot();
        JSONArray peers = root.optJSONArray("peers");
        List<PeerEndpoint> out = new ArrayList<>();
        if (peers == null) {
            return out;
        }
        for (int i = 0; i < peers.length(); i++) {
            JSONObject row = peers.optJSONObject(i);
            if (row == null) {
                continue;
            }
            PeerEndpoint endpoint = PeerEndpoint.fromJson(row);
            if (endpoint != null) {
                out.add(endpoint);
            }
        }
        out.sort(Comparator.comparingLong((PeerEndpoint p) -> p.lastSuccess).reversed());
        return out;
    }

    synchronized void savePeer(String ip, int port, String deviceId) {
        if (ip == null || ip.isEmpty() || port <= 0) {
            return;
        }
        try {
            JSONObject root = readRoot();
            JSONArray peers = root.optJSONArray("peers");
            if (peers == null) {
                peers = new JSONArray();
            }
            long now = System.currentTimeMillis();
            boolean updated = false;
            for (int i = 0; i < peers.length(); i++) {
                JSONObject row = peers.optJSONObject(i);
                if (row == null) {
                    continue;
                }
                if (ip.equals(row.optString("ip", "")) && port == row.optInt("port", 0)) {
                    row.put("device_id", deviceId != null ? deviceId : row.optString("device_id", ""));
                    row.put("last_seen", now);
                    row.put("failures", 0);
                    updated = true;
                    break;
                }
            }
            if (!updated) {
                JSONObject row = new JSONObject();
                row.put("ip", ip);
                row.put("port", port);
                row.put("device_id", deviceId != null ? deviceId : "");
                row.put("last_seen", now);
                row.put("last_success", 0L);
                row.put("failures", 0);
                peers.put(row);
            }
            root.put("peers", trimPeers(peers));
            writeRoot(root);
        } catch (Exception exc) {
            Log.w(TAG, "savePeer failed: " + exc.getMessage());
        }
    }

    synchronized void recordSuccess(String ip, int port) {
        updatePeer(ip, port, true);
    }

    synchronized void recordFailure(String ip, int port) {
        updatePeer(ip, port, false);
    }

    synchronized int mergePeers(JSONArray peers) {
        if (peers == null) {
            return 0;
        }
        int merged = 0;
        for (int i = 0; i < peers.length(); i++) {
            JSONObject row = peers.optJSONObject(i);
            if (row == null) {
                continue;
            }
            String ip = row.optString("ip", "");
            int port = row.optInt("port", 0);
            if (ip.isEmpty() || port <= 0) {
                continue;
            }
            String deviceId = row.optString("device_id", row.optString("deviceId", ""));
            savePeer(ip, port, deviceId);
            merged += 1;
        }
        return merged;
    }

    synchronized JSONObject exportJson() {
        JSONObject root = new JSONObject();
        JSONArray peers = new JSONArray();
        try {
            for (PeerEndpoint peer : listPeers()) {
                JSONObject row = new JSONObject();
                row.put("ip", peer.ip);
                row.put("port", peer.port);
                row.put("device_id", peer.deviceId);
                row.put("last_seen", peer.lastSeen);
                row.put("last_success", peer.lastSuccess);
                row.put("failures", peer.failures);
                peers.put(row);
            }
            root.put("ok", true);
            root.put("peers", peers);
        } catch (Exception exc) {
            Log.w(TAG, "exportJson failed: " + exc.getMessage());
        }
        return root;
    }

    private void updatePeer(String ip, int port, boolean success) {
        try {
            JSONObject root = readRoot();
            JSONArray peers = root.optJSONArray("peers");
            if (peers == null) {
                return;
            }
            long now = System.currentTimeMillis();
            for (int i = 0; i < peers.length(); i++) {
                JSONObject row = peers.optJSONObject(i);
                if (row == null) {
                    continue;
                }
                if (!ip.equals(row.optString("ip", "")) || port != row.optInt("port", 0)) {
                    continue;
                }
                row.put("last_seen", now);
                if (success) {
                    row.put("last_success", now);
                    row.put("failures", 0);
                } else {
                    row.put("failures", row.optInt("failures", 0) + 1);
                }
                break;
            }
            root.put("peers", trimPeers(peers));
            writeRoot(root);
        } catch (Exception exc) {
            Log.w(TAG, "updatePeer failed: " + exc.getMessage());
        }
    }

    private JSONArray trimPeers(JSONArray peers) {
        JSONArray kept = new JSONArray();
        List<JSONObject> rows = new ArrayList<>();
        for (int i = 0; i < peers.length(); i++) {
            JSONObject row = peers.optJSONObject(i);
            if (row == null) {
                continue;
            }
            if (row.optInt("failures", 0) >= MAX_FAILURES) {
                continue;
            }
            rows.add(row);
        }
        rows.sort((a, b) -> Long.compare(
            b.optLong("last_success", b.optLong("last_seen", 0L)),
            a.optLong("last_success", a.optLong("last_seen", 0L))
        ));
        int limit = Math.min(rows.size(), MAX_PEERS);
        for (int i = 0; i < limit; i++) {
            kept.put(rows.get(i));
        }
        return kept;
    }

    private JSONObject readRoot() {
        if (!registryFile.exists()) {
            return new JSONObject();
        }
        try (FileInputStream in = new FileInputStream(registryFile)) {
            byte[] buf = new byte[(int) registryFile.length()];
            int read = in.read(buf);
            if (read <= 0) {
                return new JSONObject();
            }
            return new JSONObject(new String(buf, 0, read, StandardCharsets.UTF_8));
        } catch (Exception exc) {
            Log.w(TAG, "readRoot failed: " + exc.getMessage());
            return new JSONObject();
        }
    }

    private void writeRoot(JSONObject root) {
        try (FileOutputStream out = new FileOutputStream(registryFile)) {
            out.write(root.toString().getBytes(StandardCharsets.UTF_8));
        } catch (Exception exc) {
            Log.w(TAG, "writeRoot failed: " + exc.getMessage());
        }
    }

    static final class PeerEndpoint {
        final String ip;
        final int port;
        final String deviceId;
        final long lastSeen;
        final long lastSuccess;
        final int failures;

        PeerEndpoint(String ip, int port, String deviceId, long lastSeen, long lastSuccess, int failures) {
            this.ip = ip;
            this.port = port;
            this.deviceId = deviceId;
            this.lastSeen = lastSeen;
            this.lastSuccess = lastSuccess;
            this.failures = failures;
        }

        static PeerEndpoint fromJson(JSONObject row) {
            String ip = row.optString("ip", "");
            int port = row.optInt("port", 0);
            if (ip.isEmpty() || port <= 0) {
                return null;
            }
            return new PeerEndpoint(
                ip,
                port,
                row.optString("device_id", ""),
                row.optLong("last_seen", 0L),
                row.optLong("last_success", 0L),
                row.optInt("failures", 0)
            );
        }
    }
}