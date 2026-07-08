package org.bloodstone.plugins.chainmesh;

import android.util.Base64;
import android.util.Log;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.util.Locale;

import fi.iki.elonen.NanoHTTPD;

final class ChainMeshHttpServer extends NanoHTTPD {
    private static final String TAG = "BloodstoneChunkServer";

    interface ChunkReader {
        byte[] readChunk(String hash) throws Exception;
    }

    private final ChunkReader reader;
    private final PacketStore packetStore;
    private final PeerIpRegistry peerRegistry;

    ChainMeshHttpServer(int port, ChunkReader reader, PacketStore packetStore, PeerIpRegistry peerRegistry) {
        super(port);
        this.reader = reader;
        this.packetStore = packetStore;
        this.peerRegistry = peerRegistry;
    }

    @Override
    public Response serve(IHTTPSession session) {
        try {
            String remoteIp = session.getRemoteIpAddress();
            if (!NetworkUtil.isLanClient(remoteIp)) {
                return json(Response.Status.FORBIDDEN, error("LAN clients only"));
            }
            Method method = session.getMethod();

            String uri = session.getUri();
            if (uri == null) {
                uri = "/";
            }
            if ("/".equals(uri) || uri.isEmpty()) {
                JSONObject body = new JSONObject();
                body.put("ok", true);
                body.put("service", "bloodstone-chain-mesh");
                return json(Response.Status.OK, body);
            }

            if ("/gateway/status".equals(uri) && method == Method.GET) {
                JSONObject body = new JSONObject();
                body.put("ok", true);
                body.put("sharing", ChainMeshPlugin.isGatewaySharingEnabled());
                body.put("service", "bloodstone-lan-gateway");
                body.put("port", ChainMeshPlugin.DEFAULT_CHUNK_PORT);
                return json(Response.Status.OK, body);
            }

            if ("/gateway/http".equals(uri) && method == Method.POST) {
                if (!ChainMeshPlugin.isGatewaySharingEnabled()) {
                    return json(Response.Status.FORBIDDEN, error("gateway sharing disabled"));
                }
                return handleGatewayHttp(session);
            }

            if ("/peers".equals(uri)) {
                JSONObject body = peerRegistry != null
                    ? peerRegistry.exportJson()
                    : new JSONObject().put("ok", true).put("peers", new org.json.JSONArray());
                return json(Response.Status.OK, body);
            }

            if (uri.startsWith("/packet/inbox/") && method == Method.GET) {
                if (packetStore == null) {
                    return json(Response.Status.NOT_FOUND, error("packet store unavailable"));
                }
                String recipient = uri.substring("/packet/inbox/".length()).trim();
                int sinceSeq = 0;
                try {
                    String q = session.getQueryParameterString();
                    if (q != null && q.contains("since_seq=")) {
                        for (String part : q.split("&")) {
                            if (part.startsWith("since_seq=")) {
                                sinceSeq = Integer.parseInt(part.substring("since_seq=".length()));
                            }
                        }
                    }
                } catch (Exception ignored) {
                    sinceSeq = 0;
                }
                JSONObject body = new JSONObject();
                body.put("ok", true);
                body.put("recipient", recipient);
                body.put("packets", packetStore.inbox(recipient, sinceSeq));
                return json(Response.Status.OK, body);
            }

            if (uri.startsWith("/packet/") && method == Method.GET) {
                if (packetStore == null) {
                    return json(Response.Status.NOT_FOUND, error("packet store unavailable"));
                }
                String packetId = uri.substring("/packet/".length()).trim().toLowerCase(Locale.US);
                if (packetId.length() != 64 || !packetId.matches("[0-9a-f]+")) {
                    return json(Response.Status.BAD_REQUEST, error("invalid packet id"));
                }
                JSONObject pkt = packetStore.read(packetId);
                if (pkt == null) {
                    return json(Response.Status.NOT_FOUND, error("packet not found"));
                }
                JSONObject body = new JSONObject();
                body.put("ok", true);
                body.put("packet", pkt);
                return json(Response.Status.OK, body);
            }

            if ("/packet".equals(uri) && method == Method.POST) {
                if (packetStore == null) {
                    return json(Response.Status.NOT_FOUND, error("packet store unavailable"));
                }
                try {
                    java.util.Map<String, String> files = new java.util.HashMap<>();
                    session.parseBody(files);
                    String raw = files.get("postData");
                    if (raw == null || raw.isEmpty()) {
                        return json(Response.Status.BAD_REQUEST, error("empty packet body"));
                    }
                    JSONObject bodyIn = new JSONObject(raw);
                    JSONObject pkt = bodyIn.optJSONObject("packet");
                    if (pkt == null) {
                        pkt = bodyIn;
                    }
                    packetStore.save(pkt);
                    JSONObject body = new JSONObject();
                    body.put("ok", true);
                    body.put("packet_id", pkt.optString("packet_id", ""));
                    return json(Response.Status.OK, body);
                } catch (Exception exc) {
                    return json(Response.Status.BAD_REQUEST, error("invalid packet body"));
                }
            }

            if (method != Method.GET) {
                return json(Response.Status.METHOD_NOT_ALLOWED, error("GET/POST required"));
            }

            if (uri.startsWith("/chunk/")) {
                String hash = uri.substring("/chunk/".length()).trim().toLowerCase(Locale.US);
                if (hash.length() != 64 || !hash.matches("[0-9a-f]+")) {
                    return json(Response.Status.BAD_REQUEST, error("invalid chunk hash"));
                }
                byte[] data = reader.readChunk(hash);
                if (data == null || data.length == 0) {
                    return json(Response.Status.NOT_FOUND, error("chunk not found"));
                }
                JSONObject body = new JSONObject();
                body.put("ok", true);
                body.put("chunk_hash", hash);
                body.put("size", data.length);
                body.put("data_b64", Base64.encodeToString(data, Base64.NO_WRAP));
                return json(Response.Status.OK, body);
            }

            return json(Response.Status.NOT_FOUND, error("not found"));
        } catch (Exception exc) {
            Log.w(TAG, "serve failed: " + exc.getMessage());
            try {
                return json(Response.Status.INTERNAL_ERROR, error(exc.getMessage()));
            } catch (Exception nested) {
                return newFixedLengthResponse(
                    Response.Status.INTERNAL_ERROR,
                    "application/json",
                    "{\"ok\":false,\"error\":\"internal error\"}"
                );
            }
        }
    }

    private Response json(Response.Status status, JSONObject body) {
        return newFixedLengthResponse(status, "application/json", body.toString());
    }

    private Response handleGatewayHttp(IHTTPSession session) {
        try {
            java.util.Map<String, String> files = new java.util.HashMap<>();
            session.parseBody(files);
            String raw = files.get("postData");
            if (raw == null || raw.isEmpty()) {
                return json(Response.Status.BAD_REQUEST, error("empty gateway request"));
            }
            JSONObject req = new JSONObject(raw);
            String url = req.optString("url", "").trim();
            if (url.isEmpty() || !(url.startsWith("http://") || url.startsWith("https://"))) {
                return json(Response.Status.BAD_REQUEST, error("invalid url"));
            }
            String requestMethod = req.optString("method", "GET").trim().toUpperCase(Locale.US);
            java.net.HttpURLConnection conn =
                (java.net.HttpURLConnection) new java.net.URL(url).openConnection();
            conn.setConnectTimeout(12000);
            conn.setReadTimeout(20000);
            conn.setInstanceFollowRedirects(true);
            conn.setRequestMethod(
                "GET".equals(requestMethod) || "HEAD".equals(requestMethod) ? requestMethod : "GET"
            );
            conn.setRequestProperty("User-Agent", "BloodstoneLanGateway/1.0");
            int status = conn.getResponseCode();
            java.io.InputStream stream =
                status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            byte[] body = new byte[0];
            if (stream != null) {
                body = readAllBytes(stream);
            }
            JSONObject out = new JSONObject();
            out.put("ok", true);
            out.put("status", status);
            out.put("content_type", conn.getContentType() != null ? conn.getContentType() : "");
            out.put("body_b64", Base64.encodeToString(body, Base64.NO_WRAP));
            return json(Response.Status.OK, out);
        } catch (Exception exc) {
            Log.w(TAG, "gateway http failed: " + exc.getMessage());
            return json(Response.Status.INTERNAL_ERROR, error(exc.getMessage()));
        }
    }

    private static byte[] readAllBytes(java.io.InputStream in) throws java.io.IOException {
        java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int read;
        while ((read = in.read(chunk)) != -1) {
            buf.write(chunk, 0, read);
        }
        return buf.toByteArray();
    }

    private JSONObject error(String message) {
        JSONObject body = new JSONObject();
        try {
            body.put("ok", false);
            body.put("error", message != null ? message : "error");
        } catch (Exception exc) {
            Log.w(TAG, "error payload failed: " + exc.getMessage());
        }
        return body;
    }

    static byte[] readChunkFile(File storeRoot, String hash) throws Exception {
        String h = hash.trim().toLowerCase(Locale.US);
        String sub = h.substring(0, 2);
        File file = new File(new File(storeRoot, sub), h + ".bin");
        if (!file.exists()) {
            return null;
        }
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