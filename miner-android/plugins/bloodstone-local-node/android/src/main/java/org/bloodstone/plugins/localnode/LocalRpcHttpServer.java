package org.bloodstone.plugins.localnode;

import android.util.Base64;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

import fi.iki.elonen.NanoHTTPD;

final class LocalRpcHttpServer extends NanoHTTPD {
    private static final String TAG = "BloodstoneLocalRpc";

    interface Handler {
        JSONObject handle(String method, JSONArray params, Object id, String remoteIp) throws Exception;
    }

    private final RpcCredentials credentials;
    private final Handler handler;

    LocalRpcHttpServer(int port, RpcCredentials credentials, Handler handler) {
        super(port);
        this.credentials = credentials;
        this.handler = handler;
    }

    @Override
    public Response serve(IHTTPSession session) {
        try {
            if (session.getMethod() != Method.POST) {
                return json(Response.Status.METHOD_NOT_ALLOWED, errorBody(null, "POST required"));
            }
            String remoteIp = session.getRemoteIpAddress();
            if (!NetworkUtil.isLanClient(remoteIp)) {
                return json(Response.Status.FORBIDDEN, errorBody(null, "LAN clients only"));
            }
            if (!authorized(session)) {
                return json(Response.Status.UNAUTHORIZED, errorBody(null, "Unauthorized"));
            }

            Map<String, String> files = new HashMap<>();
            session.parseBody(files);
            String body = files.get("postData");
            if (body == null || body.isEmpty()) {
                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                int read;
                byte[] buf = new byte[4096];
                while ((read = session.getInputStream().read(buf)) > 0) {
                    baos.write(buf, 0, read);
                }
                body = baos.toString(StandardCharsets.UTF_8.name());
            }

            JSONObject req = new JSONObject(body);
            String method = req.optString("method", "");
            JSONArray params = req.optJSONArray("params");
            if (params == null) {
                params = new JSONArray();
            }
            Object id = req.has("id") ? req.get("id") : null;

            JSONObject result = handler.handle(method, params, id, remoteIp);
            String responseBody = result.toString();
            long rx = body != null ? body.getBytes(StandardCharsets.UTF_8).length : 0L;
            long tx = responseBody.getBytes(StandardCharsets.UTF_8).length;
            NodeTrafficStats.recordLanRpc(rx, tx);
            return json(Response.Status.OK, result);
        } catch (Exception exc) {
            Log.w(TAG, "serve failed: " + exc.getMessage());
            return json(Response.Status.INTERNAL_ERROR, errorBody(null, exc.getMessage()));
        }
    }

    private boolean authorized(IHTTPSession session) {
        String header = session.getHeaders().get("authorization");
        if (header != null && header.toLowerCase(Locale.US).startsWith("basic ")) {
            String encoded = header.substring(6).trim();
            String decoded = new String(Base64.decode(encoded, Base64.DEFAULT), StandardCharsets.UTF_8);
            int colon = decoded.indexOf(':');
            if (colon > 0) {
                String user = decoded.substring(0, colon);
                String pass = decoded.substring(colon + 1);
                return credentials.user().equals(user) && credentials.password().equals(pass);
            }
        }
        Map<String, String> params = session.getParms();
        String user = params.get("user");
        String pass = params.get("pass");
        return credentials.user().equals(user) && credentials.password().equals(pass);
    }

    private static JSONObject errorBody(Object id, String message) {
        JSONObject out = new JSONObject();
        try {
            out.put("jsonrpc", "1.0");
            out.put("id", id);
            out.put("result", JSONObject.NULL);
            JSONObject err = new JSONObject();
            err.put("code", -32000);
            err.put("message", message != null ? message : "error");
            out.put("error", err);
        } catch (Exception ignored) {
        }
        return out;
    }

    private static Response json(Response.Status status, JSONObject body) {
        return newFixedLengthResponse(status, "application/json", body.toString());
    }
}