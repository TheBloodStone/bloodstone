package org.bloodstone.plugins.localnode;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class UpstreamRpcClient {
    private static final String TAG = "BloodstoneUpstreamRpc";

    private final String upstreamUrl;

    UpstreamRpcClient(String upstreamUrl) {
        this.upstreamUrl = upstreamUrl;
    }

    JSONObject call(String method, JSONArray params, Object id) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("jsonrpc", "1.0");
        payload.put("id", id != null ? id : "local-node");
        payload.put("method", method);
        payload.put("params", params != null ? params : new JSONArray());

        URL url = new URL(upstreamUrl);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(30000);
        conn.setDoOutput(true);
        conn.setRequestProperty("Content-Type", "application/json");
        byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(body);
        }

        int code = conn.getResponseCode();
        BufferedReader reader = new BufferedReader(
            new InputStreamReader(
                code >= 400 ? conn.getErrorStream() : conn.getInputStream(),
                StandardCharsets.UTF_8
            )
        );
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            sb.append(line);
        }
        reader.close();
        conn.disconnect();

        if (sb.length() == 0) {
            throw new Exception("empty upstream response");
        }
        String responseText = sb.toString();
        NodeTrafficStats.recordUpstream(
            responseText.getBytes(StandardCharsets.UTF_8).length,
            body.length
        );
        JSONObject response = new JSONObject(responseText);
        if (response.has("error") && !response.isNull("error")) {
            JSONObject err = response.getJSONObject("error");
            throw new Exception(err.optString("message", "upstream rpc error"));
        }
        return response;
    }
}