package org.bloodstone.plugins.localnode;

import android.util.Log;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Map;

import fi.iki.elonen.NanoHTTPD;

/** LAN-only HTTP API for pool coordinator peer verification and share replication. */
final class LanPoolHttpServer extends NanoHTTPD {
    private static final String TAG = "BloodstoneLanPoolHttp";

    interface Handler {
        JSONObject handleGet(String path, Map<String, String> params, String remoteIp) throws Exception;

        JSONObject handlePost(String path, String body, String remoteIp) throws Exception;
    }

    private final Handler handler;

    LanPoolHttpServer(int port, Handler handler) {
        super(port);
        this.handler = handler;
    }

    @Override
    public Response serve(IHTTPSession session) {
        try {
            String remoteIp = session.getRemoteIpAddress();
            if (!NetworkUtil.isLanClient(remoteIp)) {
                return json(Response.Status.FORBIDDEN, error("LAN clients only"));
            }
            String uri = session.getUri();
            if (uri == null) {
                uri = "/";
            }
            String path = uri.split("\\?")[0];
            if (session.getMethod() == Method.GET) {
                JSONObject result = handler.handleGet(path, session.getParms(), remoteIp);
                return json(Response.Status.OK, result);
            }
            if (session.getMethod() == Method.POST) {
                Map<String, String> files = new java.util.HashMap<>();
                session.parseBody(files);
                String body = files.get("postData");
                if (body == null) {
                    body = "";
                }
                JSONObject result = handler.handlePost(path, body, remoteIp);
                return json(Response.Status.OK, result);
            }
            return json(Response.Status.METHOD_NOT_ALLOWED, error("GET/POST only"));
        } catch (Exception exc) {
            Log.w(TAG, "serve failed: " + exc.getMessage());
            return json(Response.Status.INTERNAL_ERROR, error(exc.getMessage()));
        }
    }

    private static JSONObject error(String message) {
        JSONObject out = new JSONObject();
        try {
            out.put("ok", false);
            out.put("error", message != null ? message : "error");
        } catch (Exception ignored) {
        }
        return out;
    }

    private static Response json(Response.Status status, JSONObject body) {
        String text = body != null ? body.toString() : "{}";
        long tx = text.getBytes(StandardCharsets.UTF_8).length;
        NodeTrafficStats.recordLanRpc(0L, tx);
        return newFixedLengthResponse(status, "application/json", text);
    }
}