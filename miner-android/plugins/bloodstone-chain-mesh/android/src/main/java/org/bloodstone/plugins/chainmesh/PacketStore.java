package org.bloodstone.plugins.chainmesh;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/** Local BSM3 packet cache for LAN relay on port 18341. */
final class PacketStore {
    private final File root;

    PacketStore(File storeRoot) {
        root = new File(storeRoot, "packets");
        if (!root.exists()) {
            root.mkdirs();
        }
    }

    synchronized void save(JSONObject packet) throws Exception {
        String packetId = packet.optString("packet_id", "").trim().toLowerCase(Locale.US);
        if (packetId.length() != 64) {
            throw new IllegalArgumentException("packet_id required");
        }
        File file = new File(root, packetId + ".json");
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(packet.toString().getBytes(StandardCharsets.UTF_8));
        }
    }

    synchronized JSONObject read(String packetId) throws Exception {
        String pid = (packetId != null ? packetId : "").trim().toLowerCase(Locale.US);
        if (pid.length() != 64) {
            return null;
        }
        File file = new File(root, pid + ".json");
        if (!file.exists()) {
            return null;
        }
        byte[] data = readAll(file);
        if (data == null || data.length == 0) {
            return null;
        }
        return new JSONObject(new String(data, StandardCharsets.UTF_8));
    }

    synchronized JSONArray inbox(String recipient, int sinceSeq) throws Exception {
        JSONArray out = new JSONArray();
        File[] files = root.listFiles();
        if (files == null) {
            return out;
        }
        List<JSONObject> rows = new ArrayList<>();
        String who = (recipient != null ? recipient : "").trim();
        for (File file : files) {
            if (!file.getName().endsWith(".json")) {
                continue;
            }
            byte[] data = readAll(file);
            if (data == null || data.length == 0) {
                continue;
            }
            JSONObject row = new JSONObject(new String(data, StandardCharsets.UTF_8));
            if (!who.isEmpty()) {
                String recip = row.optString("recipient", "");
                if (!who.equals(recip)) {
                    continue;
                }
            }
            if (sinceSeq > 0 && row.optInt("seq", 0) <= sinceSeq) {
                continue;
            }
            rows.add(row);
        }
        Collections.sort(rows, (a, b) -> Integer.compare(a.optInt("seq", 0), b.optInt("seq", 0)));
        for (JSONObject row : rows) {
            out.put(row);
        }
        return out;
    }

    private static byte[] readAll(File file) throws Exception {
        try (FileInputStream in = new FileInputStream(file)) {
            byte[] data = new byte[(int) file.length()];
            int read = in.read(data);
            if (read <= 0) {
                return null;
            }
            if (read < data.length) {
                byte[] trimmed = new byte[read];
                System.arraycopy(data, 0, trimmed, 0, read);
                return trimmed;
            }
            return data;
        }
    }
}