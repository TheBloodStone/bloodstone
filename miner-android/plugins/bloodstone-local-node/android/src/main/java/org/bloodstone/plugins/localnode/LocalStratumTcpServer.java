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
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class LocalStratumTcpServer {
    private static final String TAG = "BloodstoneLocalStratum";
    private static final String ZERO_HASH =
        "0000000000000000000000000000000000000000000000000000000000000000";

    enum Algo {
        NEOSCRYPT("neoscrypt-xaya", "bloodstone-neoscrypt", 1e-8, 65536.0),
        YESPOWER("yespower", "bloodstone-yespower", 6e-8, 65536.0);

        final String createWorkName;
        final String poolName;
        final double defaultShareDiff;
        final double diffScale;

        Algo(String createWorkName, String poolName, double defaultShareDiff, double diffScale) {
            this.createWorkName = createWorkName;
            this.poolName = poolName;
            this.defaultShareDiff = defaultShareDiff;
            this.diffScale = diffScale;
        }
    }

    interface RpcCaller {
        JSONObject call(String method, JSONArray params) throws Exception;
    }

    private final int port;
    private final Algo algo;
    private final RpcCaller rpc;
    private final String poolUpstreamHost;
    private final int poolUpstreamPort;
    private final LanPoolCoordinator poolCoordinator;
    private final AtomicInteger jobCounter = new AtomicInteger(1);
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private final AtomicBoolean running = new AtomicBoolean(false);
    private ServerSocket serverSocket;
    private Thread acceptThread;

    LocalStratumTcpServer(int port, Algo algo, RpcCaller rpc) {
        this(port, algo, rpc, null, 0);
    }

    LocalStratumTcpServer(
        int port,
        Algo algo,
        RpcCaller rpc,
        String poolUpstreamHost,
        int poolUpstreamPort
    ) {
        this(port, algo, rpc, poolUpstreamHost, poolUpstreamPort, null);
    }

    LocalStratumTcpServer(
        int port,
        Algo algo,
        RpcCaller rpc,
        String poolUpstreamHost,
        int poolUpstreamPort,
        LanPoolCoordinator poolCoordinator
    ) {
        this.port = port;
        this.algo = algo;
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
        acceptThread = new Thread(this::acceptLoop, "bloodstone-local-stratum-" + algo.name());
        acceptThread.setDaemon(true);
        acceptThread.start();
        Log.i(TAG, algo.name() + " listening on " + port);
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
                    Log.w(TAG, algo.name() + " accept failed: " + exc.getMessage());
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
                    // Sequential client (solo): answer subscribe before authorize arrives.
                } finally {
                    sock.setSoTimeout(0);
                }
            }

            if (secondLine != null && !secondLine.isEmpty()) {
                stratumRx += secondLine.getBytes(StandardCharsets.UTF_8).length + 1;
            }

            boolean soloMode = secondLine != null && isSoloAuthorize(secondLine);
            if (poolRelayConfigured && secondLine != null && !secondLine.isEmpty() && !soloMode) {
                Log.i(TAG, algo.name() + " pool relay → " + poolUpstreamHost + ":" + poolUpstreamPort);
                StratumPoolRelay.relayWithHandshake(sock, poolUpstreamHost, poolUpstreamPort, firstLine, secondLine);
                return;
            }

            String extranonce1 = Long.toHexString(System.nanoTime());
            final JSONObject[] lastWork = {null};
            final String[] addressHolder = {""};
            processLine(firstLine, writer, extranonce1, lastWork, soloMode, addressHolder, remoteIp);
            if (secondLine != null && !secondLine.isEmpty()) {
                processLine(secondLine, writer, extranonce1, lastWork, soloMode, addressHolder, remoteIp);
            }

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    continue;
                }
                stratumRx += line.getBytes(StandardCharsets.UTF_8).length + 1;
                if (!soloMode && isSoloAuthorize(line)) {
                    soloMode = true;
                }
                processLine(line, writer, extranonce1, lastWork, soloMode, addressHolder, remoteIp);
            }
        } catch (Exception exc) {
            Log.w(TAG, algo.name() + " client ended: " + exc.getMessage());
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
        JSONObject[] lastWork,
        boolean soloMode,
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
                addressHolder[0] = params.optString(0, "");
            }
            send(writer, id, true);
            pushJob(writer, addressHolder[0], extranonce1, lastWork, soloMode);
            return;
        }

        if ("mining.submit".equals(method) && params.length() >= 5) {
            String worker = params.optString(0, addressHolder[0]);
            String submitJobId = params.optString(1, "");
            String extranonce2 = params.optString(2, "");
            String ntime = params.optString(3, "");
            String nonce = params.optString(4, "");
            boolean accepted = submitBlock(
                worker,
                submitJobId,
                extranonce2,
                ntime,
                nonce,
                lastWork[0],
                soloMode,
                remoteIp
            );
            send(writer, id, accepted);
            return;
        }

        if ("mining.suggest_difficulty".equals(method)) {
            send(writer, id, true);
            return;
        }

        sendError(writer, id, "unknown method");
    }

    private static boolean isSoloAuthorize(String line) {
        try {
            JSONObject req = new JSONObject(line);
            if (!"mining.authorize".equals(req.optString("method", ""))) {
                return false;
            }
            JSONArray params = req.optJSONArray("params");
            if (params == null || params.length() < 2) {
                return false;
            }
            return "solo".equalsIgnoreCase(params.optString(1, ""));
        } catch (Exception exc) {
            return false;
        }
    }

    private static String extractAuthorizeAddress(String line) {
        try {
            JSONObject req = new JSONObject(line);
            JSONArray params = req.optJSONArray("params");
            if (params != null && params.length() > 0) {
                return params.optString(0, "");
            }
        } catch (Exception ignored) {
        }
        return "";
    }

    private void sendSubscribe(BufferedWriter writer, Object id, String extranonce1) throws IOException {
        JSONArray result = new JSONArray();
        if (algo == Algo.YESPOWER) {
            JSONArray caps = new JSONArray();
            JSONArray diffCap = new JSONArray();
            diffCap.put("mining.set_difficulty");
            diffCap.put(algo.poolName);
            JSONArray notifyCap = new JSONArray();
            notifyCap.put("mining.notify");
            notifyCap.put(algo.poolName);
            caps.put(diffCap);
            caps.put(notifyCap);
            result.put(caps);
            result.put(extranonce1);
            result.put(2);
        } else {
            result.put("bloodstone-local-node/1.0.0");
            result.put(extranonce1);
        }
        send(writer, id, result);
    }

    private void pushJob(
        BufferedWriter writer,
        String address,
        String extranonce1,
        JSONObject[] lastWork,
        boolean soloMode
    ) {
        try {
            if (address == null || address.isEmpty()) {
                return;
            }
            JSONArray args = new JSONArray();
            args.put(address);
            args.put(algo.createWorkName);
            JSONObject work = rpc.call("creatework", args);
            lastWork[0] = work;

            int height = work.optInt("height", 0);
            String shortId = String.format(
                Locale.US,
                "%x.%x",
                height,
                jobCounter.getAndIncrement()
            );
            String jobId = "00000000" + shortId;
            String header = work.optString("header", "");
            String nbits = work.optString("bits", work.optString("nbits", ""));
            String blockTargetHex = work.optString("target", "");
            String ntime = String.format(
                Locale.US,
                "%08x",
                System.currentTimeMillis() / 1000L
            );

            BigInteger blockTarget = StratumTargetMath.targetHexToInt(blockTargetHex);
            BigInteger shareTarget = StratumTargetMath.shareTargetInt(
                blockTarget,
                algo.defaultShareDiff,
                soloMode
            );
            String shareTargetHex = StratumTargetMath.intToCompareHex(shareTarget);
            double stratumDiff = StratumTargetMath.targetToDifficulty(shareTarget) * algo.diffScale;

            sendNotify(writer, "mining.set_share_target", new JSONArray().put(shareTargetHex));
            sendNotify(writer, "mining.set_difficulty", new JSONArray().put(stratumDiff));
            if (algo == Algo.YESPOWER) {
                sendNotify(
                    writer,
                    "mining.set_block_target",
                    new JSONArray().put(
                        StratumTargetMath.intToCompareHex(blockTarget)
                    ).put(String.valueOf(height))
                );
            }

            JSONArray notify = new JSONArray();
            notify.put(jobId);
            notify.put(ZERO_HASH);
            notify.put(header.length() >= 136 ? header.substring(0, 136) : header);
            notify.put("");
            notify.put(new JSONArray());
            notify.put("00000000");
            notify.put(nbits);
            notify.put(ntime);
            if (algo == Algo.YESPOWER) {
                notify.put(true);
            }
            sendNotify(writer, "mining.notify", notify);
        } catch (Exception exc) {
            Log.w(TAG, algo.name() + " pushJob failed: " + exc.getMessage());
        }
    }

    private boolean submitBlock(
        String worker,
        String jobId,
        String extranonce2,
        String ntime,
        String nonce,
        JSONObject lastWork,
        boolean soloMode,
        String remoteIp
    ) {
        try {
            if (lastWork == null) {
                return false;
            }
            String header = lastWork.optString("header", "");
            if (header.isEmpty()) {
                return false;
            }
            int jobHeight = lastWork.optInt("height", 0);
            boolean blockFound = false;
            String blockHash = "";
            try {
                String blockHex = header + extranonce2 + ntime + nonce;
                JSONArray params = new JSONArray();
                params.put(blockHex);
                rpc.call("submitblock", params);
                blockFound = true;
                blockHash = lastWork.optString("hash", lastWork.optString("blockhash", ""));
            } catch (Exception submitExc) {
                if (soloMode) {
                    Log.w(TAG, algo.name() + " solo submit failed: " + submitExc.getMessage());
                    return false;
                }
            }

            if (!soloMode && poolCoordinator != null && poolCoordinator.isLocalPoolActive()) {
                double weight = algo.defaultShareDiff * algo.diffScale;
                long shareId = poolCoordinator.recordShare(
                    algo.createWorkName,
                    LanPoolShareUtil.payoutAddress("", worker),
                    worker,
                    jobHeight,
                    weight,
                    remoteIp
                );
                if (blockFound && shareId >= 0) {
                    poolCoordinator.onBlockFind(
                        algo.createWorkName,
                        jobHeight,
                        blockHash,
                        LanPoolShareUtil.payoutAddress("", worker),
                        worker
                    );
                    Log.i(TAG, algo.name() + " LAN pool block height=" + jobHeight + " worker=" + worker);
                }
                return shareId > 0 || blockFound;
            }

            if (soloMode) {
                return blockFound;
            }
            return blockFound;
        } catch (Exception exc) {
            Log.w(TAG, algo.name() + " submit failed: " + exc.getMessage());
            return false;
        }
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
}