package org.bloodstone.plugins.localnode;

import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

final class LanRegistrar {
    private static final String TAG = "BloodstoneLanRegistrar";
    private static final String DEFAULT_REGISTER_URL =
        "https://bloodstonewallet.mytunnel.org/mining/api/local-node/lan-register";

    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
    private final AtomicBoolean active = new AtomicBoolean(false);
    private volatile JSONObject payload = new JSONObject();
    private volatile String registerUrl = DEFAULT_REGISTER_URL;

    void configure(String url, JSONObject body) {
        if (url != null && !url.isEmpty()) {
            registerUrl = url;
        }
        if (body != null) {
            payload = body;
        }
    }

    void updatePayload(JSONObject body) {
        if (body != null) {
            payload = body;
        }
    }

    JSONObject registerNow() {
        try {
            return post();
        } catch (Exception exc) {
            Log.w(TAG, "registerNow failed: " + exc.getMessage());
            JSONObject err = new JSONObject();
            try {
                err.put("ok", false);
                err.put("error", exc.getMessage());
            } catch (org.json.JSONException ignored) {
                /* ignore */
            }
            return err;
        }
    }

    void start() {
        if (active.getAndSet(true)) {
            return;
        }
        scheduler.scheduleAtFixedRate(this::postSafe, 0, 60, TimeUnit.SECONDS);
    }

    void stop() {
        active.set(false);
        scheduler.shutdownNow();
    }

    private void postSafe() {
        try {
            post();
        } catch (Exception exc) {
            Log.w(TAG, "register failed: " + exc.getMessage());
        }
    }

    private JSONObject post() throws Exception {
        URL url = new URL(registerUrl);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(12000);
        conn.setReadTimeout(12000);
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
        Log.i(TAG, "lan-register " + code + " -> " + registerUrl);
        JSONObject result = new JSONObject();
        boolean ok = code >= 200 && code < 300;
        result.put("ok", ok);
        result.put("httpCode", code);
        result.put("registerUrl", registerUrl);
        String responseBody = sb.toString().trim();
        if (!responseBody.isEmpty()) {
            try {
                result.put("response", new JSONObject(responseBody));
            } catch (org.json.JSONException parseErr) {
                result.put("responseText", responseBody);
            }
        }
        if (!ok) {
            result.put(
                "error",
                code == 404
                    ? "LAN register URL not found — update the app bundle"
                    : "LAN register HTTP " + code
            );
        }
        return result;
    }
}