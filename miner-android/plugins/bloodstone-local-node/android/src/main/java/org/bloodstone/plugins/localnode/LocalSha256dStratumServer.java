package org.bloodstone.plugins.localnode;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.math.BigInteger;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * SHA256d stratum for Bitaxe on LAN.
 * Pool password {@code x} relays to the central VPS pool; password {@code solo} mines via local createauxblock.
 */
final class LocalSha256dStratumServer {
    private static final String TAG = "BloodstoneSha256dStratum";
    private static final double DEFAULT_ASIC_SHARE_DIFF = 0.01;

    interface RpcCaller {
        JSONObject call(String method, JSONArray params) throws Exception;
    }

    static final class Job {
        final String jobId;
        final JSONObject auxblock;
        final String txTemplate;
        final String shareTargetHex;
        final String blockTargetHex;
        final String nbitsHex;

        Job(
            String jobId,
            JSONObject auxblock,
            String txTemplate,
            String shareTargetHex,
            String blockTargetHex,
            String nbitsHex
        ) {
            this.jobId = jobId;
            this.auxblock = auxblock;
            this.txTemplate = txTemplate;
            this.shareTargetHex = shareTargetHex;
            this.blockTargetHex = blockTargetHex;
            this.nbitsHex = nbitsHex;
        }
    }

    private final int port;
    private final RpcCaller rpc;
    private final String poolUpstreamHost;
    private final int poolUpstreamPort;
    private final LanPoolCoordinator poolCoordinator;
    private final AtomicInteger jobCounter = new AtomicInteger(1);
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final SecureRandom random = new SecureRandom();
    private ServerSocket serverSocket;
    private Thread acceptThread;

    LocalSha256dStratumServer(int port, RpcCaller rpc, String poolUpstreamHost, int poolUpstreamPort) {
        this(port, rpc, poolUpstreamHost, poolUpstreamPort, null);
    }

    LocalSha256dStratumServer(
        int port,
        RpcCaller rpc,
        String poolUpstreamHost,
        int poolUpstreamPort,
        LanPoolCoordinator poolCoordinator
    ) {
        this.port = port;
        this.rpc = rpc;
        this.poolUpstreamHost = poolUpstreamHost;
        this.poolUpstreamPort = poolUpstreamPort;
        this.poolCoordinator = poolCoordinator;
    }

    void start() throws IOException {
        if (running.get()) {
            return;
        }
        serverSocket = new ServerSocket();
        serverSocket.setReuseAddress(true);
        serverSocket.bind(new java.net.InetSocketAddress(InetAddress.getByName("0.0.0.0"), port), 16);
        running.set(true);
        acceptThread = new Thread(this::acceptLoop, "bloodstone-local-sha256d");
        acceptThread.setDaemon(true);
        acceptThread.start();
        Log.i(TAG, "listening on " + port);
    }

    void stop() {
        running.set(false);
        if (serverSocket != null) {
            try {
                serverSocket.close();
            } catch (IOException ignored) {
            }
            serverSocket = null;
        }
        if (acceptThread != null) {
            acceptThread.interrupt();
            acceptThread = null;
        }
    }

    private void acceptLoop() {
        while (running.get() && serverSocket != null && !serverSocket.isClosed()) {
            try {
                Socket client = serverSocket.accept();
                String remote = client.getInetAddress() != null
                    ? client.getInetAddress().getHostAddress()
                    : "";
                if (!NetworkUtil.isLanClient(remote)) {
                    client.close();
                    continue;
                }
                NodeTrafficStats.recordStratumConnection();
                pool.execute(() -> handleClient(client, remote));
            } catch (IOException exc) {
                if (running.get()) {
                    Log.w(TAG, "accept failed: " + exc.getMessage());
                }
            }
        }
    }

    private void handleClient(Socket client, String remoteIp) {
        long stratumRx = 0L;
        try (
            Socket sock = client;
            BufferedReader reader = new BufferedReader(
                new InputStreamReader(sock.getInputStream(), StandardCharsets.UTF_8)
            );
            BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8)
            )
        ) {
            String firstLine = reader.readLine();
            if (firstLine == null || firstLine.isEmpty()) {
                return;
            }
            stratumRx += firstLine.getBytes(StandardCharsets.UTF_8).length + 1;

            boolean localPoolActive =
                poolCoordinator != null && poolCoordinator.isLocalPoolActive();
            boolean poolRelayConfigured =
                !localPoolActive
                    && poolUpstreamHost != null
                    && !poolUpstreamHost.isEmpty()
                    && poolUpstreamPort > 0;
            String secondLine = null;
            if (poolRelayConfigured) {
                try {
                    sock.setSoTimeout(300);
                    secondLine = reader.readLine();
                } catch (SocketTimeoutException timeout) {
                    // Sequential client: subscribe before authorize.
                } finally {
                    sock.setSoTimeout(0);
                }
            }

            if (secondLine != null && !secondLine.isEmpty()) {
                stratumRx += secondLine.getBytes(StandardCharsets.UTF_8).length + 1;
            }

            boolean soloMode = secondLine != null && isSoloAuthorize(secondLine);
            if (poolRelayConfigured && secondLine != null && !secondLine.isEmpty() && !soloMode) {
                Log.i(TAG, "pool relay → " + poolUpstreamHost + ":" + poolUpstreamPort);
                StratumPoolRelay.relayWithHandshake(sock, poolUpstreamHost, poolUpstreamPort, firstLine, secondLine);
                return;
            }
            // Phone miners authorize only after subscribe reply — relay as soon as
            // we have subscribe so jobs are not created with a broken local path.
            if (poolRelayConfigured && !soloMode && isSubscribeLine(firstLine)) {
                Log.i(TAG, "pool relay (sequential) → " + poolUpstreamHost + ":" + poolUpstreamPort);
                if (secondLine != null && !secondLine.isEmpty()) {
                    StratumPoolRelay.relayWithHandshake(
                        sock, poolUpstreamHost, poolUpstreamPort, firstLine, secondLine
                    );
                } else {
                    StratumPoolRelay.relayWithPrefetchedLine(
                        sock, poolUpstreamHost, poolUpstreamPort, firstLine
                    );
                }
                return;
            }

            String extranonce1 = randomExtranonce1();
            final Job[] lastJob = {null};
            final String[] addressHolder = {""};
            final boolean[] soloHolder = {soloMode};
            processLine(firstLine, writer, extranonce1, lastJob, soloHolder, addressHolder, remoteIp);
            if (secondLine != null && !secondLine.isEmpty()) {
                processLine(secondLine, writer, extranonce1, lastJob, soloHolder, addressHolder, remoteIp);
            }

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    continue;
                }
                stratumRx += line.getBytes(StandardCharsets.UTF_8).length + 1;
                if (!soloHolder[0] && isSoloAuthorize(line)) {
                    soloHolder[0] = true;
                }
                processLine(line, writer, extranonce1, lastJob, soloHolder, addressHolder, remoteIp);
            }
        } catch (Exception exc) {
            Log.w(TAG, "client ended: " + exc.getMessage());
        } finally {
            if (stratumRx > 0L) {
                NodeTrafficStats.recordLanStratum(stratumRx, stratumRx / 2);
            }
        }
    }

    private void processLine(
        String line,
        BufferedWriter writer,
        String extranonce1,
        Job[] lastJob,
        boolean[] soloHolder,
        String[] addressHolder,
        String remoteIp
    ) throws Exception {
        JSONObject req = new JSONObject(line);
        String method = req.optString("method", "");
        JSONArray params = req.optJSONArray("params");
        if (params == null) {
            params = new JSONArray();
        }
        Object id = req.has("id") ? req.get("id") : null;

        if ("mining.subscribe".equals(method)) {
            sendSubscribe(writer, id, extranonce1);
            return;
        }

        if ("mining.authorize".equals(method)) {
            if (params.length() > 0) {
                addressHolder[0] = addressFromWorker(params.optString(0, ""));
            }
            if (params.length() > 1) {
                soloHolder[0] = "solo".equalsIgnoreCase(params.optString(1, ""));
            }
            send(writer, id, true);
            pushJob(writer, addressHolder[0], extranonce1, lastJob, soloHolder[0]);
            return;
        }

        if ("mining.submit".equals(method) && params.length() >= 5) {
            String worker = params.optString(0, addressHolder[0]);
            String jobId = params.optString(1, "");
            String extranonce2 = params.optString(2, "");
            String ntime = params.optString(3, "");
            String nonce = params.optString(4, "");
            String versionHex = params.length() > 5 ? params.optString(5, "01000000") : "01000000";
            boolean accepted = submitShare(
                writer,
                worker,
                jobId,
                extranonce2,
                ntime,
                nonce,
                versionHex,
                lastJob,
                extranonce1,
                soloHolder[0],
                remoteIp
            );
            send(writer, id, accepted);
            return;
        }

        if ("mining.suggest_difficulty".equals(method) || "mining.extranonce.subscribe".equals(method)) {
            send(writer, id, true);
            return;
        }

        sendError(writer, id, "unknown method");
    }

    private boolean submitShare(
        BufferedWriter writer,
        String worker,
        String jobId,
        String extranonce2,
        String ntime,
        String nonce,
        String versionHex,
        Job[] lastJob,
        String extranonce1,
        boolean soloMode,
        String remoteIp
    ) {
        Job job = lastJob[0];
        if (job == null || !job.jobId.equals(jobId)) {
            pushJob(writer, addressFromWorker(worker), extranonce1, lastJob, soloMode);
            return false;
        }
        try {
            byte[] txBytes = hexToBytes(job.txTemplate);
            int insertAt = AuxpowUtil.extranonceOffset(txBytes);
            byte[] en2 = hexToBytes(padHex(extranonce2, 8));
            if (en2.length != 4) {
                return false;
            }
            System.arraycopy(en2, 0, txBytes, insertAt + 4, 4);
            String txHex = bytesToHex(txBytes);
            byte[] header = AuxpowUtil.buildHeaderBytes(txHex, job.nbitsHex, ntime, nonce, versionHex);
            String blockHashHex = AuxpowUtil.doubleHashHex(bytesToHex(header));
            if (blockHashHex.compareTo(job.shareTargetHex) > 0) {
                return false;
            }
            boolean blockFound = blockHashHex.compareTo(job.blockTargetHex) <= 0;
            int jobHeight = job.auxblock.optInt("height", 0);
            String blockHash = job.auxblock.optString("hash", "");
            if (blockFound) {
                String auxpowHex = AuxpowUtil.finishAuxpow(txHex, bytesToHex(header));
                JSONArray submitParams = new JSONArray();
                submitParams.put(blockHash);
                submitParams.put(auxpowHex);
                JSONObject submitResult = rpc.call("submitauxblock", submitParams);
                boolean submitted = submitResult.optBoolean("ok", false);
                Log.i(
                    TAG,
                    "BLOCK submit height="
                        + jobHeight
                        + " ok="
                        + submitted
                        + " worker="
                        + worker
                );
                pushJob(writer, addressFromWorker(worker), extranonce1, lastJob, soloMode);
                if (!soloMode
                    && submitted
                    && poolCoordinator != null
                    && poolCoordinator.isLocalPoolActive()) {
                    poolCoordinator.onBlockFind(
                        "sha256d",
                        jobHeight,
                        blockHash,
                        LanPoolShareUtil.payoutAddress("", worker),
                        worker
                    );
                }
            }
            if (!soloMode && poolCoordinator != null && poolCoordinator.isLocalPoolActive()) {
                poolCoordinator.recordShare(
                    "sha256d",
                    LanPoolShareUtil.payoutAddress("", worker),
                    worker,
                    jobHeight,
                    DEFAULT_ASIC_SHARE_DIFF,
                    remoteIp
                );
            }
            return true;
        } catch (Exception exc) {
            Log.w(TAG, "submit failed: " + exc.getMessage());
            return false;
        }
    }

    private void pushJob(
        BufferedWriter writer,
        String address,
        String extranonce1,
        Job[] lastJob,
        boolean soloMode
    ) {
        try {
            if (address == null || address.isEmpty()) {
                return;
            }
            JSONArray args = new JSONArray();
            args.put(address);
            JSONObject auxblock = rpc.call("createauxblock", args);
            String blockHash = auxblock.optString("hash", "");
            if (blockHash.isEmpty()) {
                return;
            }
            AuxpowUtil.StratumParts parts = AuxpowUtil.buildStratumParts(blockHash, extranonce1);
            String blockTargetHex = auxblock.optString("_target", "");
            BigInteger blockTarget = StratumTargetMath.targetHexToInt(blockTargetHex);
            BigInteger shareTarget = StratumTargetMath.shareTargetInt(
                blockTarget,
                soloMode ? 0.0 : DEFAULT_ASIC_SHARE_DIFF,
                soloMode
            );
            String shareTargetHex = StratumTargetMath.intToCompareHex(shareTarget);
            String blockCompareHex = StratumTargetMath.intToCompareHex(blockTarget);
            int height = auxblock.optInt("height", 0);
            String jobId = String.format(Locale.US, "%x.%x", height, jobCounter.getAndIncrement());
            String nbits = String.format(Locale.US, "%08x", Long.parseLong(auxblock.optString("bits", "1d00ffff"), 16));
            String ntime = String.format(Locale.US, "%08x", System.currentTimeMillis() / 1000L);
            double notifyDiff = soloMode
                ? StratumTargetMath.targetToDifficulty(blockTarget)
                : DEFAULT_ASIC_SHARE_DIFF;

            lastJob[0] = new Job(jobId, auxblock, parts.txHex, shareTargetHex, blockCompareHex, nbits);

            sendNotify(writer, "mining.set_difficulty", new JSONArray().put(notifyDiff));
            JSONArray notify = new JSONArray();
            notify.put(jobId);
            notify.put(parts.prevhash);
            notify.put(parts.coinb1);
            notify.put(parts.coinb2);
            notify.put(new JSONArray());
            notify.put("01000000");
            notify.put(nbits);
            notify.put(ntime);
            notify.put(true);
            sendNotify(writer, "mining.notify", notify);
            Log.i(
                TAG,
                "job " + jobId + " height=" + height + " solo=" + soloMode + " addr=" + address
            );
        } catch (Exception exc) {
            String msg = exc.getMessage() != null ? exc.getMessage() : exc.toString();
            if (msg.contains("bad-block-algo")) {
                try {
                    sendNotify(writer, "mining.stop", new JSONArray());
                } catch (IOException ioExc) {
                    Log.w(TAG, "mining.stop failed: " + ioExc.getMessage());
                }
            }
            Log.w(TAG, "pushJob failed: " + msg);
        }
    }

    private static boolean isSoloAuthorize(String line) {
        try {
            JSONObject req = new JSONObject(line);
            if (!"mining.authorize".equals(req.optString("method", ""))) {
                return false;
            }
            JSONArray params = req.optJSONArray("params");
            return params != null && params.length() > 1
                && "solo".equalsIgnoreCase(params.optString(1, ""));
        } catch (Exception exc) {
            return false;
        }
    }

    private static boolean isSubscribeLine(String line) {
        try {
            JSONObject req = new JSONObject(line);
            return "mining.subscribe".equals(req.optString("method", ""));
        } catch (Exception exc) {
            return false;
        }
    }

    private static String addressFromWorker(String worker) {
        String trimmed = worker == null ? "" : worker.trim();
        int dot = trimmed.indexOf('.');
        return dot > 0 ? trimmed.substring(0, dot) : trimmed;
    }

    private String randomExtranonce1() {
        byte[] bytes = new byte[4];
        random.nextBytes(bytes);
        return bytesToHex(bytes);
    }

    private void sendSubscribe(BufferedWriter writer, Object id, String extranonce1) throws IOException {
        JSONArray caps = new JSONArray();
        JSONArray diffCap = new JSONArray();
        diffCap.put("mining.set_difficulty");
        diffCap.put("bloodstone-local-sha256");
        JSONArray notifyCap = new JSONArray();
        notifyCap.put("mining.notify");
        notifyCap.put("bloodstone-local-sha256");
        caps.put(diffCap);
        caps.put(notifyCap);
        JSONArray result = new JSONArray();
        result.put(caps);
        result.put(extranonce1);
        result.put(4);
        send(writer, id, result);
    }

    private static void sendNotify(BufferedWriter writer, String method, JSONArray params) throws IOException {
        JSONObject msg = new JSONObject();
        try {
            msg.put("id", JSONObject.NULL);
            msg.put("method", method);
            msg.put("params", params);
        } catch (Exception ignored) {
        }
        writer.write(msg.toString());
        writer.write('\n');
        writer.flush();
    }

    private static void send(BufferedWriter writer, Object id, Object result) throws IOException {
        JSONObject out = new JSONObject();
        try {
            out.put("id", id);
            out.put("result", result);
            out.put("error", JSONObject.NULL);
        } catch (Exception ignored) {
        }
        writer.write(out.toString());
        writer.write('\n');
        writer.flush();
    }

    private static void sendError(BufferedWriter writer, Object id, String message) throws IOException {
        JSONObject out = new JSONObject();
        try {
            out.put("id", id);
            out.put("result", JSONObject.NULL);
            JSONObject err = new JSONObject();
            err.put("message", message);
            out.put("error", err);
        } catch (Exception ignored) {
        }
        writer.write(out.toString());
        writer.write('\n');
        writer.flush();
    }

    private static String padHex(String hex, int len) {
        String clean = hex == null ? "" : hex.replaceAll("\\s+", "").toLowerCase(Locale.US);
        if (clean.length() >= len) {
            return clean.substring(clean.length() - len);
        }
        StringBuilder sb = new StringBuilder(len);
        for (int i = clean.length(); i < len; i += 1) {
            sb.append('0');
        }
        sb.append(clean);
        return sb.toString();
    }

    private static byte[] hexToBytes(String hex) {
        String clean = hex.replaceAll("\\s+", "").toLowerCase(Locale.US);
        byte[] out = new byte[clean.length() / 2];
        for (int i = 0; i < clean.length(); i += 2) {
            out[i / 2] = (byte) Integer.parseInt(clean.substring(i, i + 2), 16);
        }
        return out;
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format(Locale.US, "%02x", b));
        }
        return sb.toString();
    }
}