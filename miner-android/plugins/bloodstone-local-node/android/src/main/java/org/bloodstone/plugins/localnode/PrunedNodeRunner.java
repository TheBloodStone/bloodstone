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

final class PrunedNodeRunner {
    private static final String TAG = "BloodstoneNodeRunner";
    private static final String SEED_NODE = "64.188.22.190:17333";
    private static final String SEED_NODE_ALT = "192.119.82.145:17333";
    private static final long LOCK_STALE_MS = 2L * 60L * 1000L;

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
        File binary = resolveBinary();
        if (binary == null || !binary.canExecute()) {
            Log.i(TAG, "no ARM bloodstoned binary — gateway mode");
            activeMode = "gateway";
            return false;
        }
        String effectiveMode = nodeMode;
        if (!NodeStorageUtil.hasAbsoluteMinStorage(context)) {
            Log.w(TAG, "critically low storage — gateway mode");
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
                try {
                    ChainBootstrapInstaller.ensureBootstrap(context, dataDir, effectiveMode);
                } catch (Exception bootstrapExc) {
                    Log.w(
                        TAG,
                        "chain bootstrap failed — continuing with P2P sync: "
                            + bootstrapExc.getMessage()
                    );
                }
            }
            if (new File(dataDir, ".bootstrap-reindex").isFile()) {
                ChainBootstrapInstaller.prepareForReindex(dataDir);
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
            }
            return alive;
        } catch (Exception exc) {
            Log.w(TAG, "start failed: " + exc.getMessage());
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
                copyAsset(assetDir + "/bloodstoned", out);
                out.setExecutable(true, false);
                try {
                    File cxx = new File(context.getFilesDir(), "libc++_shared.so");
                    copyAsset(assetDir + "/libc++_shared.so", cxx);
                    cxx.setReadable(true, false);
                } catch (Exception ignored) {
                    // NDK libc++ not bundled; binary must be fully static.
                }
                Log.i(TAG, "using bloodstoned ABI " + abi);
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
        sb.append("disablewallet=1\n");
        sb.append("rpcbind=127.0.0.1\n");
        sb.append("rpcport=18332\n");
        sb.append("rpcuser=").append(credentials.user()).append("\n");
        sb.append("rpcpassword=").append(credentials.password()).append("\n");
        sb.append("rpcallowip=127.0.0.1\n");
        sb.append("rpcallowip=10.0.0.0/8\n");
        sb.append("rpcallowip=172.16.0.0/12\n");
        sb.append("rpcallowip=192.168.0.0/16\n");
        sb.append("maxmempool=5\n");
        sb.append("maxorphantx=10\n");
        sb.append("par=1\n");
        sb.append("maxuploadtarget=32\n");

        if (new File(dataDir, ".bootstrap-reindex").isFile()) {
            sb.append("reindex=1\n");
        }
        if ("full".equals(effectiveMode)) {
            sb.append("listen=1\n");
            sb.append("port=17333\n");
            sb.append("txindex=1\n");
            sb.append("dbcache=64\n");
            sb.append("maxconnections=8\n");
            sb.append("blocksonly=0\n");
            sb.append("addnode=").append(SEED_NODE).append("\n");
            sb.append("addnode=").append(SEED_NODE_ALT).append("\n");
        } else if (NodeModeUtil.CONSENSUS.equals(effectiveMode)) {
            int pruneTarget = Math.max(550, pruneMiB);
            sb.append("listen=1\n");
            sb.append("port=17333\n");
            sb.append("prune=").append(pruneTarget).append("\n");
            sb.append("txindex=0\n");
            sb.append("dbcache=32\n");
            sb.append("maxconnections=10\n");
            sb.append("blocksonly=1\n");
            sb.append("addnode=").append(SEED_NODE).append("\n");
            sb.append("addnode=").append(SEED_NODE_ALT).append("\n");
        } else if (NodeModeUtil.CONSENSUS_WITNESS.equals(effectiveMode)) {
            int pruneTarget = Math.max(550, pruneMiB);
            sb.append("listen=0\n");
            sb.append("prune=").append(pruneTarget).append("\n");
            sb.append("txindex=0\n");
            sb.append("dbcache=24\n");
            sb.append("maxconnections=6\n");
            sb.append("blocksonly=1\n");
            sb.append("addnode=").append(SEED_NODE).append("\n");
            sb.append("addnode=").append(SEED_NODE_ALT).append("\n");
        } else {
            int pruneTarget = Math.max(550, pruneMiB);
            sb.append("listen=0\n");
            sb.append("prune=").append(pruneTarget).append("\n");
            sb.append("txindex=0\n");
            sb.append("dbcache=48\n");
            sb.append("maxconnections=8\n");
            sb.append("addnode=").append(SEED_NODE).append("\n");
            sb.append("addnode=").append(SEED_NODE_ALT).append("\n");
        }

        try (OutputStreamWriter writer = new OutputStreamWriter(
            new FileOutputStream(conf), StandardCharsets.UTF_8)) {
            writer.write(sb.toString());
        }
    }

    private static void drainLogs(Process proc) {
        try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(proc.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                Log.i(TAG, line);
            }
        } catch (Exception ignored) {
        }
    }
}