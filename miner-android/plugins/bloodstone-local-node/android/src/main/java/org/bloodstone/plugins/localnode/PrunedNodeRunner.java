package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.RandomAccessFile;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;

import org.json.JSONArray;

final class PrunedNodeRunner {
    private static final String TAG = "BloodstoneNodeRunner";
    private static final String JNI_BLOODSTONED = "libbloodstoned_node.so";
    private static final String SEED_NODE = "64.188.22.190:17333";
    private static final String SEED_NODE_ALT = "192.119.82.145:17333";
    private static final long LOCK_STALE_MS = 2L * 60L * 1000L;
    private static final int LOG_TAIL_MAX = 8192;

    private final Context context;
    private final RpcCredentials credentials;
    private final int pruneMiB;
    private final String nodeMode;
    private Process process;
    private Thread logThread;
    private Thread exitWatcher;
    private FileLock datadirLock;
    private RandomAccessFile lockFile;
    private String activeMode = "gateway";
    private volatile Integer lastExitCode;
    private volatile long lastExitAt;
    private final StringBuilder logTailBuffer = new StringBuilder();
    private volatile String lastFailureReason = "";

    PrunedNodeRunner(Context context, RpcCredentials credentials, int pruneMiB, String nodeMode) {
        this.context = context;
        this.credentials = credentials;
        this.pruneMiB = pruneMiB;
        this.nodeMode = normalizeMode(nodeMode);
    }

    static String normalizeMode(String mode) {
        return NodeModeUtil.normalize(mode);
    }

    boolean start() {
        stop();
        synchronized (logTailBuffer) {
            logTailBuffer.setLength(0);
        }
        lastFailureReason = "";
        File binary = resolveBinary();
        if (binary == null || !binary.canExecute()) {
            Log.i(TAG, "no ARM bloodstoned binary — gateway mode");
            lastFailureReason = "bloodstoned binary not bundled for this device";
            activeMode = "gateway";
            return false;
        }
        String effectiveMode = nodeMode;
        if (!NodeStorageUtil.hasAbsoluteMinStorage(context)) {
            Log.w(TAG, "critically low storage — gateway mode");
            lastFailureReason = "critically low storage on device";
            activeMode = "gateway";
            return false;
        }
        if ("full".equals(effectiveMode) && !NodeStorageUtil.canRunFullNode(context)) {
            Log.w(
                TAG,
                "free space below recommended full-node minimum — starting full chain anyway (user choice)"
            );
        }
        File dataDir = NodeModeUtil.datadir(context, effectiveMode);
        if (!acquireDatadirLock(dataDir)) {
            Log.w(TAG, "datadir lock busy — another bloodstoned may be running");
            lastFailureReason = "datadir lock busy — stop other node instances first";
            activeMode = "gateway";
            return false;
        }
        try {
            if (!dataDir.exists() && !dataDir.mkdirs()) {
                releaseDatadirLock();
                activeMode = "gateway";
                return false;
            }
            if (ChainBootstrapInstaller.supportsMode(effectiveMode)) {
                int networkHeight = fetchNetworkBlockHeight();
                ChainBootstrapInstaller.prepareForNetworkTip(context, dataDir, networkHeight);
                try {
                    ChainBootstrapInstaller.ensureBootstrap(context, dataDir, effectiveMode);
                } catch (Exception bootstrapExc) {
                    String bootstrapMsg =
                        "chain bootstrap failed: "
                            + (bootstrapExc.getMessage() != null
                                ? bootstrapExc.getMessage()
                                : "unknown");
                    Log.w(TAG, bootstrapMsg + " — continuing with P2P sync");
                    LocalNodeForegroundService.noteStartError(bootstrapMsg);
                }
            }
            if (new File(dataDir, ".bootstrap-reindex").isFile()) {
                ChainBootstrapInstaller.prepareForReindex(dataDir);
            } else if (ChainBootstrapInstaller.needsChainstateReindex(dataDir)) {
                ChainBootstrapInstaller.prepareForChainstateReindex(dataDir);
            }
            writeConfig(dataDir, effectiveMode);
            ProcessBuilder pb = new ProcessBuilder(
                binary.getAbsolutePath(),
                "-datadir=" + dataDir.getAbsolutePath(),
                "-conf=" + new File(dataDir, "bloodstone.conf").getAbsolutePath(),
                "-printtoconsole"
            );
            File libDir = binary.getParentFile();
            if (libDir != null) {
                pb.environment().put("LD_LIBRARY_PATH", libDir.getAbsolutePath());
            }
            pb.redirectErrorStream(true);
            process = pb.start();
            startLogDrain(process);
            startExitWatcher(process);
            Thread.sleep("full".equals(effectiveMode) ? 5000 : 2000);
            boolean alive = process.isAlive();
            activeMode = alive ? effectiveMode : "gateway";
            if (!alive) {
                releaseDatadirLock();
                if (lastFailureReason == null || lastFailureReason.isEmpty()) {
                    lastFailureReason = inferFailureReason(logTail());
                }
            }
            return alive;
        } catch (Exception exc) {
            Log.w(TAG, "start failed: " + exc.getMessage());
            lastFailureReason =
                "bloodstoned start failed: "
                    + (exc.getMessage() != null ? exc.getMessage() : "unknown");
            stop();
            activeMode = "gateway";
            return false;
        }
    }

    void stop() {
        if (exitWatcher != null) {
            exitWatcher.interrupt();
            exitWatcher = null;
        }
        if (logThread != null) {
            logThread.interrupt();
            logThread = null;
        }
        if (process != null) {
            process.destroy();
            try {
                if (!process.waitFor(4, java.util.concurrent.TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                }
            } catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
                process.destroyForcibly();
            }
            process = null;
        }
        releaseDatadirLock();
        activeMode = "gateway";
    }

    boolean isAlive() {
        return process != null && process.isAlive();
    }

    String activeMode() {
        return isAlive() ? activeMode : "gateway";
    }

    boolean isPruned() {
        return isAlive() && !"full".equals(activeMode);
    }

    boolean isConsensusOnly() {
        return isAlive() && NodeModeUtil.isConsensusMode(activeMode);
    }

    Integer lastExitCode() {
        return lastExitCode;
    }

    long lastExitAt() {
        return lastExitAt;
    }

    String lastFailureReason() {
        return lastFailureReason != null ? lastFailureReason : "";
    }

    String logTail() {
        synchronized (logTailBuffer) {
            return logTailBuffer.toString();
        }
    }

    private void startLogDrain(Process proc) {
        logThread = new Thread(() -> drainLogs(proc), "bloodstoned-log");
        logThread.setDaemon(true);
        logThread.start();
    }

    private void startExitWatcher(Process proc) {
        exitWatcher = new Thread(() -> {
            try {
                int code = proc.waitFor();
                lastExitCode = code;
                lastExitAt = System.currentTimeMillis();
                Log.w(TAG, "bloodstoned exited with code " + code);
                if (code != 0) {
                    String reason = inferFailureReason(logTail());
                    if (reason != null && !reason.isEmpty()) {
                        lastFailureReason = reason;
                    }
                }
            } catch (InterruptedException exc) {
                Thread.currentThread().interrupt();
            }
        }, "bloodstoned-exit");
        exitWatcher.setDaemon(true);
        exitWatcher.start();
    }

    private boolean acquireDatadirLock(File dataDir) {
        releaseDatadirLock();
        try {
            if (!dataDir.exists() && !dataDir.mkdirs()) {
                return false;
            }
            File lock = new File(dataDir, ".bloodstoned.lock");
            if (lock.exists() && System.currentTimeMillis() - lock.lastModified() > LOCK_STALE_MS) {
                if (!lock.delete()) {
                    Log.w(TAG, "stale datadir lock could not be cleared");
                }
            }
            lockFile = new RandomAccessFile(lock, "rw");
            datadirLock = lockFile.getChannel().tryLock();
            if (datadirLock == null) {
                closeLockFile();
                return false;
            }
            lockFile.writeBytes("pid=" + android.os.Process.myPid() + "\n");
            return true;
        } catch (Exception exc) {
            Log.w(TAG, "datadir lock failed: " + exc.getMessage());
            releaseDatadirLock();
            return false;
        }
    }

    private void releaseDatadirLock() {
        if (datadirLock != null) {
            try {
                datadirLock.release();
            } catch (Exception ignored) {
            }
            datadirLock = null;
        }
        closeLockFile();
    }

    private void closeLockFile() {
        if (lockFile != null) {
            try {
                lockFile.close();
            } catch (Exception ignored) {
            }
            lockFile = null;
        }
    }

    private File resolveBinary() {
        File fromJni = resolveJniLibsBinary();
        if (fromJni != null) {
            return fromJni;
        }
        // Android 10+ (targetSdk 29+) blocks execve() from the writable app home dir.
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
            Log.w(TAG, "jniLibs bloodstoned missing — cannot execute from app files dir on Android 10+");
            lastFailureReason =
                "bloodstoned not installed in APK native libs — update to the latest miner APK";
            return null;
        }
        return resolveLegacyAssetsBinary();
    }

    private File resolveJniLibsBinary() {
        try {
            String libDirPath = context.getApplicationInfo().nativeLibraryDir;
            if (libDirPath == null || libDirPath.isEmpty()) {
                return null;
            }
            File libDir = new File(libDirPath);
            File binary = new File(libDir, JNI_BLOODSTONED);
            if (!binary.isFile()) {
                Log.w(TAG, "missing jniLibs binary: " + binary.getAbsolutePath());
                return null;
            }
            Log.i(TAG, "using jniLibs bloodstoned at " + binary.getAbsolutePath());
            return binary;
        } catch (Exception exc) {
            Log.w(TAG, "jniLibs bloodstoned lookup failed: " + exc.getMessage());
            return null;
        }
    }

    private File resolveLegacyAssetsBinary() {
        File installed = new File(context.getFilesDir(), "bloodstoned");
        if (installed.isFile() && installed.canExecute()) {
            return installed;
        }
        String[] abis = android.os.Build.SUPPORTED_ABIS;
        if (abis == null || abis.length == 0) {
            abis = new String[] { "arm64-v8a", "armeabi-v7a" };
        }
        Exception lastError = null;
        for (String abi : abis) {
            try {
                String assetDir = "bloodstoned/" + abi;
                File out = new File(context.getFilesDir(), "bloodstoned");
                if (out.exists() && !out.delete()) {
                    Log.w(TAG, "could not replace legacy bloodstoned binary");
                }
                copyAsset(assetDir + "/bloodstoned", out);
                out.setExecutable(true, false);
                try {
                    File cxx = new File(context.getFilesDir(), "libc++_shared.so");
                    copyAsset(assetDir + "/libc++_shared.so", cxx);
                    cxx.setReadable(true, false);
                } catch (Exception ignored) {
                    // NDK libc++ not bundled; binary must be fully static.
                }
                Log.i(TAG, "using legacy assets bloodstoned ABI " + abi);
                return out;
            } catch (Exception exc) {
                lastError = exc;
                Log.i(TAG, "bloodstoned ABI " + abi + " unavailable: " + exc.getMessage());
            }
        }
        if (lastError != null) {
            Log.i(TAG, "binary not bundled: " + lastError.getMessage());
        }
        return null;
    }

    private void copyAsset(String assetPath, File out) throws Exception {
        try (InputStream in = context.getAssets().open(assetPath);
             FileOutputStream fos = new FileOutputStream(out)) {
            byte[] buf = new byte[8192];
            int read;
            while ((read = in.read(buf)) != -1) {
                fos.write(buf, 0, read);
            }
        }
    }

    private void writeConfig(File dataDir, String effectiveMode) throws Exception {
        File conf = new File(dataDir, "bloodstone.conf");
        StringBuilder sb = new StringBuilder();
        sb.append("server=1\n");
        sb.append("daemon=0\n");
        if (!NodeModeUtil.supportsOnDeviceWallet(effectiveMode)) {
            sb.append("disablewallet=1\n");
        }
        sb.append("rpcbind=127.0.0.1\n");
        sb.append("rpcport=18332\n");
        sb.append("rpcuser=").append(credentials.user()).append("\n");
        sb.append("rpcpassword=").append(credentials.password()).append("\n");
        sb.append("rpcallowip=127.0.0.1\n");
        sb.append("rpcallowip=10.0.0.0/8\n");
        sb.append("rpcallowip=172.16.0.0/12\n");
        sb.append("rpcallowip=192.168.0.0/16\n");
        sb.append("maxmempool=12\n");
        sb.append("maxorphantx=40\n");
        sb.append("par=1\n");
        sb.append("maxuploadtarget=32\n");

        if (new File(dataDir, ".bootstrap-reindex").isFile()) {
            sb.append("reindex=1\n");
        } else if (new File(dataDir, ChainBootstrapInstaller.REINDEX_CHAINSTATE_MARKER).isFile()
            || ChainBootstrapInstaller.needsChainstateReindex(dataDir)) {
            sb.append("reindex-chainstate=1\n");
        }
        if ("full".equals(effectiveMode)) {
            sb.append("listen=1\n");
            sb.append("port=17333\n");
            // Bootstrap snapshot is block files only — txindex=1 breaks chainstate on phones.
            boolean bootstrapSnapshot = new File(dataDir, ".bootstrap-height").isFile();
            sb.append("txindex=").append(bootstrapSnapshot ? "0" : "1").append("\n");
            // Phones OOM-kill bloodstoned above ~96 MiB dbcache during chainstate catch-up.
            sb.append("dbcache=32\n");
            sb.append("maxconnections=8\n");
            sb.append("blocksonly=0\n");
            sb.append("maxsigcachesize=8\n");
            appendSeedPeers(sb);
        } else if (NodeModeUtil.CONSENSUS.equals(effectiveMode)) {
            int pruneTarget = Math.max(550, pruneMiB);
            sb.append("listen=1\n");
            sb.append("port=17333\n");
            sb.append("prune=").append(pruneTarget).append("\n");
            sb.append("txindex=0\n");
            sb.append("dbcache=32\n");
            sb.append("maxconnections=10\n");
            sb.append("blocksonly=1\n");
            appendSeedPeers(sb);
        } else if (NodeModeUtil.CONSENSUS_WITNESS.equals(effectiveMode)) {
            int pruneTarget = Math.max(550, pruneMiB);
            sb.append("listen=0\n");
            sb.append("prune=").append(pruneTarget).append("\n");
            sb.append("txindex=0\n");
            sb.append("dbcache=24\n");
            sb.append("maxconnections=6\n");
            sb.append("blocksonly=1\n");
            appendSeedPeers(sb);
        } else {
            int pruneTarget = Math.max(550, pruneMiB);
            sb.append("listen=0\n");
            sb.append("prune=").append(pruneTarget).append("\n");
            sb.append("txindex=0\n");
            sb.append("dbcache=48\n");
            sb.append("maxconnections=8\n");
            appendSeedPeers(sb);
        }

        try (OutputStreamWriter writer = new OutputStreamWriter(
            new FileOutputStream(conf), StandardCharsets.UTF_8)) {
            writer.write(sb.toString());
        }
    }

    private static void appendSeedPeers(StringBuilder sb) {
        sb.append("connect=").append(SEED_NODE).append("\n");
        sb.append("connect=").append(SEED_NODE_ALT).append("\n");
        sb.append("addnode=").append(SEED_NODE).append("\n");
        sb.append("addnode=").append(SEED_NODE_ALT).append("\n");
    }

    private int fetchNetworkBlockHeight() {
        try {
            NodeSyncPreferences prefs = new NodeSyncPreferences(context);
            UpstreamRpcClient client = new UpstreamRpcClient(prefs.upstreamUrl());
            org.json.JSONObject response =
                client.call("getblockcount", new JSONArray(), "bootstrap");
            return response.optInt("result", 0);
        } catch (Exception exc) {
            Log.i(TAG, "network height unavailable for bootstrap refresh: " + exc.getMessage());
            return 0;
        }
    }

    private void appendLogLine(String line) {
        if (line == null) {
            return;
        }
        synchronized (logTailBuffer) {
            logTailBuffer.append(line).append('\n');
            if (logTailBuffer.length() > LOG_TAIL_MAX) {
                logTailBuffer.delete(0, logTailBuffer.length() - LOG_TAIL_MAX);
            }
        }
        String reason = inferFailureReason(line);
        if (reason != null && !reason.isEmpty()) {
            lastFailureReason = reason;
        }
    }

    private static String inferFailureReason(String text) {
        if (text == null || text.isEmpty()) {
            return "";
        }
        if (ChainBootstrapInstaller.looksLikeMerkleCorruption(text)) {
            return "chain merkle corruption detected — reinstall bootstrap";
        }
        if (ChainBootstrapInstaller.looksLikeBlockDatabaseError(text)) {
            return "block database failed — chain data will be reset on next Start";
        }
        String lower = text.toLowerCase();
        if (lower.contains("error initializing block database")) {
            return "block database failed to open";
        }
        if (lower.contains("not enough disk space") || lower.contains("enospc")) {
            return "not enough free storage for chain data";
        }
        if (lower.contains("corrupt") && lower.contains("block")) {
            return "corrupt block data on disk";
        }
        if (lower.contains("out of memory")
            || lower.contains("bad_alloc")
            || lower.contains("oom")
            || lower.contains("cannot allocate")) {
            return "bloodstoned ran out of memory — keep app in front, plug in, tap Stop then Start";
        }
        if (lower.contains("killed") || lower.contains("sigkill")) {
            return "bloodstoned was killed by Android — disable battery saver, keep app open";
        }
        return "";
    }

    private void drainLogs(Process proc) {
        try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(proc.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                Log.i(TAG, line);
                appendLogLine(line);
            }
        } catch (Exception ignored) {
        }
    }
}