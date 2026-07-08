package org.bloodstone.plugins.chainmesh;

import android.util.Base64;
import android.util.Log;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

@CapacitorPlugin(name = "BloodstoneChainMesh")
public class ChainMeshPlugin extends Plugin {
    private static final String TAG = "BloodstoneChainMesh";
    private static final int DEFAULT_MAX_CHUNKS = 96;
    private static final int MESH_MAX_CHUNKS = 256;
    private static final int MAX_CHUNK_BYTES = 262144 + 4096;
    private int maxChunks = DEFAULT_MAX_CHUNKS;
    private static final String META_FILE = "chain-mesh-meta.json";
    public static final int DEFAULT_CHUNK_PORT = 18341;

    private ChainMeshHttpServer chunkServer;
    private PeerIpRegistry peerRegistry;
    private static volatile boolean gatewaySharingEnabled = false;

    public static void setGatewaySharingEnabled(boolean enabled) {
        gatewaySharingEnabled = enabled;
    }

    public static boolean isGatewaySharingEnabled() {
        return gatewaySharingEnabled;
    }

    private File storeRoot() {
        File dir = new File(getContext().getFilesDir(), "bloodstone-chain-mesh");
        if (!dir.exists() && !dir.mkdirs()) {
            Log.w(TAG, "failed to create store root");
        }
        return dir;
    }

    private PeerIpRegistry peerRegistry() {
        if (peerRegistry == null) {
            peerRegistry = new PeerIpRegistry(storeRoot());
        }
        return peerRegistry;
    }

    private File chunkFile(String hash) {
        String h = normalizeHash(hash);
        String sub = h.substring(0, 2);
        File subDir = new File(storeRoot(), sub);
        if (!subDir.exists()) {
            subDir.mkdirs();
        }
        return new File(subDir, h + ".bin");
    }

    private File metaFile() {
        return new File(storeRoot(), META_FILE);
    }

    private String normalizeHash(String hash) {
        if (hash == null) {
            throw new IllegalArgumentException("chunk hash required");
        }
        String h = hash.trim().toLowerCase();
        if (h.length() != 64 || !h.matches("[0-9a-f]+")) {
            throw new IllegalArgumentException("invalid chunk hash");
        }
        return h;
    }

    private int countChunks() {
        File root = storeRoot();
        int total = 0;
        File[] subs = root.listFiles();
        if (subs == null) {
            return 0;
        }
        for (File sub : subs) {
            if (!sub.isDirectory()) {
                continue;
            }
            File[] files = sub.listFiles();
            if (files == null) {
                continue;
            }
            for (File f : files) {
                if (f.isFile() && f.getName().endsWith(".bin")) {
                    total += 1;
                }
            }
        }
        return total;
    }

    private long totalBytes() {
        long total = 0;
        File root = storeRoot();
        File[] subs = root.listFiles();
        if (subs == null) {
            return 0;
        }
        for (File sub : subs) {
            if (!sub.isDirectory()) {
                continue;
            }
            File[] files = sub.listFiles();
            if (files == null) {
                continue;
            }
            for (File f : files) {
                if (f.isFile() && f.getName().endsWith(".bin")) {
                    total += f.length();
                }
            }
        }
        return total;
    }

    private void writeMeta(String hash, String sourceFile, long fileOffset, int size) {
        try {
            JSONObject chunkMeta = new JSONObject();
            chunkMeta.put("chunkHash", hash);
            chunkMeta.put("sourceFile", sourceFile != null ? sourceFile : "");
            chunkMeta.put("fileOffset", fileOffset);
            chunkMeta.put("size", size);
            chunkMeta.put("savedAt", System.currentTimeMillis());
            File metaPath = metaFile();
            JSONObject all = new JSONObject();
            if (metaPath.exists()) {
                try (FileInputStream in = new FileInputStream(metaPath)) {
                    byte[] buf = new byte[(int) metaPath.length()];
                    int read = in.read(buf);
                    if (read > 0) {
                        all = new JSONObject(new String(buf, 0, read, StandardCharsets.UTF_8));
                    }
                }
            }
            all.put(hash, chunkMeta);
            try (FileOutputStream out = new FileOutputStream(metaPath)) {
                out.write(all.toString().getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception exc) {
            Log.w(TAG, "writeMeta failed: " + exc.getMessage());
        }
    }

    private boolean evictOldestChunk() {
        try {
            JSONObject allMeta = readAllMeta();
            String oldestHash = null;
            long oldestAt = Long.MAX_VALUE;
            java.util.Iterator<String> keys = allMeta.keys();
            while (keys.hasNext()) {
                String hash = keys.next();
                JSONObject row = allMeta.optJSONObject(hash);
                long savedAt = row != null ? row.optLong("savedAt", 0L) : 0L;
                if (savedAt < oldestAt) {
                    oldestAt = savedAt;
                    oldestHash = hash;
                }
            }
            if (oldestHash == null) {
                return false;
            }
            File file = chunkFile(oldestHash);
            boolean removed = file.exists() && file.delete();
            allMeta.remove(oldestHash);
            try (FileOutputStream out = new FileOutputStream(metaFile())) {
                out.write(allMeta.toString().getBytes(StandardCharsets.UTF_8));
            }
            return removed;
        } catch (Exception exc) {
            Log.w(TAG, "evictOldestChunk failed: " + exc.getMessage());
            return false;
        }
    }

    private JSONObject readAllMeta() {
        File meta = metaFile();
        if (!meta.exists()) {
            return new JSONObject();
        }
        try (FileInputStream in = new FileInputStream(meta)) {
            byte[] buf = new byte[(int) meta.length()];
            int read = in.read(buf);
            if (read <= 0) {
                return new JSONObject();
            }
            return new JSONObject(new String(buf, 0, read, StandardCharsets.UTF_8));
        } catch (Exception exc) {
            Log.w(TAG, "readAllMeta failed: " + exc.getMessage());
            return new JSONObject();
        }
    }

    @PluginMethod
    public void putChunk(PluginCall call) {
        String hash = call.getString("chunkHash");
        String dataB64 = call.getString("dataB64");
        if (hash == null || dataB64 == null || dataB64.isEmpty()) {
            call.reject("chunkHash and dataB64 required");
            return;
        }
        try {
            String normalized = normalizeHash(hash);
            byte[] data = Base64.decode(dataB64, Base64.DEFAULT);
            if (data.length == 0 || data.length > MAX_CHUNK_BYTES) {
                call.reject("invalid chunk size");
                return;
            }
            File dest = chunkFile(normalized);
            if (!dest.exists() && countChunks() >= maxChunks) {
                if (!evictOldestChunk()) {
                    call.reject("chunk capacity reached");
                    return;
                }
            }
            File tmp = new File(dest.getAbsolutePath() + ".tmp");
            try (FileOutputStream out = new FileOutputStream(tmp)) {
                out.write(data);
            }
            if (!tmp.renameTo(dest)) {
                call.reject("failed to store chunk");
                return;
            }
            writeMeta(
                normalized,
                call.getString("sourceFile"),
                call.getLong("fileOffset", 0L),
                call.getInt("size", data.length)
            );
            JSObject ret = new JSObject();
            ret.put("stored", true);
            ret.put("chunkHash", normalized);
            call.resolve(ret);
        } catch (IllegalArgumentException exc) {
            call.reject(exc.getMessage());
        } catch (Exception exc) {
            call.reject("putChunk failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void getChunk(PluginCall call) {
        String hash = call.getString("chunkHash");
        if (hash == null) {
            call.reject("chunkHash required");
            return;
        }
        try {
            String normalized = normalizeHash(hash);
            File file = chunkFile(normalized);
            if (!file.exists()) {
                call.resolve(null);
                return;
            }
            byte[] data;
            try (FileInputStream in = new FileInputStream(file)) {
                data = new byte[(int) file.length()];
                int read = in.read(data);
                if (read <= 0) {
                    call.resolve(null);
                    return;
                }
            }
            JSONObject allMeta = readAllMeta();
            JSONObject chunkMeta = allMeta.optJSONObject(normalized);
            JSObject ret = new JSObject();
            ret.put("chunkHash", normalized);
            ret.put("dataB64", Base64.encodeToString(data, Base64.NO_WRAP));
            ret.put("sourceFile", chunkMeta != null ? chunkMeta.optString("sourceFile", "") : "");
            ret.put("fileOffset", chunkMeta != null ? chunkMeta.optLong("fileOffset", 0L) : 0L);
            ret.put("size", chunkMeta != null ? chunkMeta.optInt("size", data.length) : data.length);
            call.resolve(ret);
        } catch (IllegalArgumentException exc) {
            call.reject(exc.getMessage());
        } catch (Exception exc) {
            call.reject("getChunk failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void listChunks(PluginCall call) {
        try {
            JSONObject allMeta = readAllMeta();
            JSArray chunks = new JSArray();
            List<String> hashes = new ArrayList<>();
            File root = storeRoot();
            File[] subs = root.listFiles();
            if (subs != null) {
                for (File sub : subs) {
                    if (!sub.isDirectory()) {
                        continue;
                    }
                    File[] files = sub.listFiles();
                    if (files == null) {
                        continue;
                    }
                    for (File f : files) {
                        if (!f.isFile() || !f.getName().endsWith(".bin")) {
                            continue;
                        }
                        String hash = f.getName().replace(".bin", "");
                        hashes.add(hash);
                    }
                }
            }
            for (String hash : hashes) {
                JSONObject m = allMeta.optJSONObject(hash);
                JSObject row = new JSObject();
                row.put("chunkHash", hash);
                row.put("sourceFile", m != null ? m.optString("sourceFile", "") : "");
                row.put("fileOffset", m != null ? m.optLong("fileOffset", 0L) : 0L);
                row.put("size", m != null ? m.optInt("size", 0) : 0);
                row.put("savedAt", m != null ? m.optLong("savedAt", 0L) : 0L);
                chunks.put(row);
            }
            JSObject ret = new JSObject();
            ret.put("chunks", chunks);
            ret.put("count", hashes.size());
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("listChunks failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void removeChunk(PluginCall call) {
        String hash = call.getString("chunkHash");
        if (hash == null) {
            call.reject("chunkHash required");
            return;
        }
        try {
            String normalized = normalizeHash(hash);
            File file = chunkFile(normalized);
            boolean removed = file.exists() && file.delete();
            JSObject ret = new JSObject();
            ret.put("removed", removed);
            call.resolve(ret);
        } catch (IllegalArgumentException exc) {
            call.reject(exc.getMessage());
        }
    }

    @PluginMethod
    public void getCapacity(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("maxChunks", maxChunks);
        ret.put("usedChunks", countChunks());
        ret.put("maxBytes", (long) maxChunks * 256L * 1024L);
        ret.put("usedBytes", totalBytes());
        call.resolve(ret);
    }

    @PluginMethod
    public void setMeshCapacity(PluginCall call) {
        String mode = call.getString("mode", "pruned");
        Integer requested = call.getInt("maxChunks");
        if (requested != null && requested > 0) {
            maxChunks = Math.min(512, Math.max(DEFAULT_MAX_CHUNKS, requested));
        } else if ("mesh".equalsIgnoreCase(mode) || "full".equalsIgnoreCase(mode)) {
            maxChunks = MESH_MAX_CHUNKS;
        } else {
            maxChunks = DEFAULT_MAX_CHUNKS;
        }
        JSObject ret = new JSObject();
        ret.put("maxChunks", maxChunks);
        ret.put("mode", mode);
        call.resolve(ret);
    }

    @PluginMethod
    public void startChunkServer(PluginCall call) {
        int port = call.getInt("port", DEFAULT_CHUNK_PORT);
        try {
            if (chunkServer == null) {
                File root = storeRoot();
                chunkServer = new ChainMeshHttpServer(
                    port,
                    hash -> ChainMeshHttpServer.readChunkFile(root, hash),
                    new PacketStore(root),
                    peerRegistry()
                );
                chunkServer.start();
            }
            JSObject ret = new JSObject();
            ret.put("running", true);
            ret.put("port", port);
            ret.put("lanIp", NetworkUtil.lanIpv4(getContext()));
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("startChunkServer failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void stopChunkServer(PluginCall call) {
        try {
            if (chunkServer != null) {
                chunkServer.stop();
                chunkServer = null;
            }
            JSObject ret = new JSObject();
            ret.put("running", false);
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("stopChunkServer failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void getChunkServerStatus(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("running", chunkServer != null);
        ret.put("port", DEFAULT_CHUNK_PORT);
        ret.put("lanIp", NetworkUtil.lanIpv4(getContext()));
        call.resolve(ret);
    }

    @PluginMethod
    public void listPeerIps(PluginCall call) {
        try {
            JSArray peers = new JSArray();
            for (PeerIpRegistry.PeerEndpoint peer : peerRegistry().listPeers()) {
                JSObject row = new JSObject();
                row.put("ip", peer.ip);
                row.put("port", peer.port);
                row.put("deviceId", peer.deviceId);
                row.put("lastSeen", peer.lastSeen);
                row.put("lastSuccess", peer.lastSuccess);
                row.put("failures", peer.failures);
                peers.put(row);
            }
            JSObject ret = new JSObject();
            ret.put("peers", peers);
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("listPeerIps failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void savePeerIp(PluginCall call) {
        String ip = call.getString("ip", "");
        int port = call.getInt("port", DEFAULT_CHUNK_PORT);
        String deviceId = call.getString("deviceId", "");
        try {
            peerRegistry().savePeer(ip, port, deviceId);
            JSObject ret = new JSObject();
            ret.put("saved", true);
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("savePeerIp failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void mergePeerIps(PluginCall call) {
        com.getcapacitor.JSArray peers = call.getArray("peers");
        if (peers == null) {
            call.reject("peers array required");
            return;
        }
        try {
            int merged = peerRegistry().mergePeers(new org.json.JSONArray(peers.toString()));
            JSObject ret = new JSObject();
            ret.put("merged", merged);
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("mergePeerIps failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void recordPeerResult(PluginCall call) {
        String ip = call.getString("ip", "");
        int port = call.getInt("port", DEFAULT_CHUNK_PORT);
        boolean success = call.getBoolean("success", false);
        try {
            if (success) {
                peerRegistry().recordSuccess(ip, port);
            } else {
                peerRegistry().recordFailure(ip, port);
            }
            call.resolve();
        } catch (Exception exc) {
            call.reject("recordPeerResult failed: " + exc.getMessage());
        }
    }
}