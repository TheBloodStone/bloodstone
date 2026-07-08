package org.bloodstone.plugins.localnode;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;

public class LocalNodeForegroundService extends Service {
    public static final String CHANNEL_ID = "bloodstone_local_node";
    public static final int NOTIFICATION_ID = 73422;
    public static final String ACTION_STOP = "org.bloodstone.miner.STOP_LOCAL_NODE";
    public static final int RPC_PORT = 18340;
    public static final int STRATUM_PORT_NEOSCRYPT = 3437;
    public static final int STRATUM_PORT_YESPOWER = 3438;
    public static final int STRATUM_PORT_SHA256D = 3429;

    private static final String TAG = "BloodstoneLocalNode";
    private static volatile boolean running = false;
    private static volatile boolean nodeStarting = false;
    private static volatile String lastStartError = "";
    private static volatile boolean chainResetPending = false;
    private static volatile LocalNodeForegroundService instance;
    private static volatile LanDiscovery activeDiscovery;
    private static final AtomicReference<LocalNodeStatusSnapshot> snapshot =
        new AtomicReference<>(LocalNodeStatusSnapshot.stopped());

    private RpcCredentials credentials;
    private PrunedNodeRunner prunedRunner;
    private LocalRpcHttpServer rpcServer;
    private LocalStratumTcpServer stratumNeoscrypt;
    private LocalStratumTcpServer stratumYespower;
    private LocalSha256dStratumServer stratumSha256d;
    private UpstreamRpcClient upstream;
    private LanDiscovery discovery;
    private LanRegistrar registrar;
    private LanPoolCoordinator poolCoordinator;
    private String upstreamUrl;
    private int pruneMiB = 550;
    private String nodeMode = "pruned";
    private Thread syncPollerThread;
    private static final long SYNC_POLL_MS = 5000L;
    private static final long LAN_PUSH_MIN_MS = 15000L;
    private static final int MAX_BLOODSTONED_RESTARTS = 8;
    private static final long BLOODSTONED_RESTART_COOLDOWN_MS = 20000L;
    private int bloodstonedRestartAttempts = 0;
    private long lastBloodstonedRestartMs = 0L;
    private int lastLanRegisteredHeight = -1;
    private long lastLanPushMs = 0L;

    public static boolean isRunning() {
        return running;
    }

    public static boolean isStarting() {
        return nodeStarting;
    }

    public static String lastStartError() {
        return lastStartError != null ? lastStartError : "";
    }

    public static String bloodstonedFailureReason() {
        LocalNodeForegroundService inst = instance;
        if (inst == null || inst.prunedRunner == null) {
            return "";
        }
        return inst.prunedRunner.lastFailureReason();
    }

    public static void noteStartError(String message) {
        lastStartError = message != null ? message : "";
    }

    public static LocalNodeStatusSnapshot status() {
        return snapshot.get();
    }

    static LanDiscovery discovery() {
        return activeDiscovery;
    }

    static LocalNodeForegroundService getInstance() {
        return instance;
    }

    JSONObject registerLanNow() throws Exception {
        if (!running || registrar == null) {
            JSONObject err = new JSONObject();
            err.put("ok", false);
            err.put("error", "Local node is not running — start offline mining first");
            return err;
        }
        String lanIp = NetworkUtil.lanIpv4(this);
        if (lanIp == null || lanIp.isEmpty()) {
            JSONObject err = new JSONObject();
            err.put("ok", false);
            err.put("error", "Connect to Wi‑Fi to get a LAN IP");
            return err;
        }
        NodeSyncStatus syncStatus = fetchSyncStatus();
        String serviceName = ("bloodstone-" + credentials.user()).toLowerCase(Locale.US);
        JSONObject reg = new JSONObject();
        reg.put("device_id", serviceName);
        putLanRegistrationFields(reg, nodeMode, lanIp, syncStatus.blockHeight, syncStatus);
        registrar.updatePayload(reg);
        return registrar.registerNow();
    }

    static void publishStoppedSnapshot() {
        snapshot.set(LocalNodeStatusSnapshot.stopped());
    }

    static void publishBootingSnapshot(Context context, String mode) {
        RpcCredentials creds = RpcCredentials.loadOrCreate(context);
        String lanIp = NetworkUtil.lanIpv4(context);
        long chainBytes = NodeStorageUtil.datadirBytes(
            context,
            NodeModeUtil.datadir(context, mode).getName()
        );
        snapshot.set(
            new LocalNodeStatusSnapshot(
                true,
                mode,
                lanIp != null ? lanIp : "",
                RPC_PORT,
                STRATUM_PORT_NEOSCRYPT,
                STRATUM_PORT_YESPOWER,
                STRATUM_PORT_SHA256D,
                creds.user(),
                creds.password(),
                0,
                !"full".equals(mode),
                false,
                0.03,
                chainBytes,
                false,
                0,
                0,
                0L,
                false,
                0
            )
        );
    }

    static void publishDormantSnapshot(
        Context context,
        String mode,
        int localHeight,
        int networkHeight,
        NodeSyncPreferences prefs
    ) {
        RpcCredentials credentials = RpcCredentials.loadOrCreate(context);
        snapshot.set(
            new LocalNodeStatusSnapshot(
                false,
                mode,
                "",
                RPC_PORT,
                STRATUM_PORT_NEOSCRYPT,
                STRATUM_PORT_YESPOWER,
                0,
                credentials.user(),
                credentials.password(),
                localHeight,
                !"full".equals(mode),
                false,
                0.0,
                NodeStorageUtil.datadirBytes(
                    context,
                    NodeModeUtil.datadir(context, mode).getName()
                ),
                true,
                networkHeight,
                0,
                prefs.lastSyncAt(),
                false,
                0
            )
        );
    }

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        NodeTrafficStatsHolder.appContext = getApplicationContext();
        createNotificationChannel();
        credentials = RpcCredentials.loadOrCreate(this);
        discovery = new LanDiscovery(this);
        registrar = new LanRegistrar();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            shutdown();
            return START_NOT_STICKY;
        }
        upstreamUrl = intent != null
            ? intent.getStringExtra("upstreamUrl")
            : null;
        if (upstreamUrl == null || upstreamUrl.isEmpty()) {
            upstreamUrl = NodeSyncPreferences.DEFAULT_UPSTREAM;
        }
        upstreamUrl = LanEndpointUrls.normalizeUpstream(upstreamUrl);
        pruneMiB = intent != null ? intent.getIntExtra("pruneMiB", 550) : 550;
        nodeMode = PrunedNodeRunner.normalizeMode(
            intent != null ? intent.getStringExtra("nodeMode") : "pruned"
        );

        startForeground(
            NOTIFICATION_ID,
            buildNotification("Starting local node…", "Preparing bloodstoned on device")
        );
        final String requestedMode = nodeMode;
        final int requestedPrune = pruneMiB;
        if (running) {
            boolean daemonRequired = NodeModeUtil.runsBloodstoned(requestedMode);
            boolean daemonAlive = prunedRunner != null && prunedRunner.isAlive();
            if (requestedMode.equals(nodeMode)
                && requestedPrune == pruneMiB
                && (!daemonRequired || daemonAlive)) {
                Log.i(TAG, "local node already running (" + nodeMode + ")");
                return START_STICKY;
            }
            Log.i(
                TAG,
                daemonAlive
                    ? "restarting local node for mode change " + nodeMode + " -> " + requestedMode
                    : "restarting local node — bloodstoned not alive"
            );
            shutdown();
        }
        if (nodeStarting) {
            Log.i(TAG, "local node already starting");
            return START_STICKY;
        }
        nodeStarting = true;
        lastStartError = "";
        bloodstonedRestartAttempts = 0;
        instance = this;
        publishBootingSnapshot(this, nodeMode);
        final String bootUpstreamUrl = upstreamUrl;
        final int bootPruneMiB = pruneMiB;
        final String bootNodeMode = nodeMode;
        new Thread(() -> {
            try {
                upstreamUrl = bootUpstreamUrl;
                pruneMiB = bootPruneMiB;
                nodeMode = bootNodeMode;
                startNode();
            } catch (Exception exc) {
                Log.w(TAG, "startNode failed: " + exc.getMessage(), exc);
                lastStartError = exc.getMessage() != null ? exc.getMessage() : "startNode failed";
                shutdown();
            } finally {
                nodeStarting = false;
            }
        }, "bloodstone-node-boot").start();
        return START_STICKY;
    }

    private void stopListeners() {
        if (syncPollerThread != null) {
            syncPollerThread.interrupt();
            syncPollerThread = null;
        }
        if (registrar != null) {
            registrar.stop();
            registrar = new LanRegistrar();
        }
        if (discovery != null) {
            discovery.unregister();
        }
        activeDiscovery = null;
        if (stratumNeoscrypt != null) {
            stratumNeoscrypt.stop();
            stratumNeoscrypt = null;
        }
        if (stratumYespower != null) {
            stratumYespower.stop();
            stratumYespower = null;
        }
        if (stratumSha256d != null) {
            stratumSha256d.stop();
            stratumSha256d = null;
        }
        if (poolCoordinator != null) {
            poolCoordinator.stop();
            poolCoordinator = null;
        }
        if (rpcServer != null) {
            rpcServer.stop();
            rpcServer = null;
        }
        if (prunedRunner != null) {
            prunedRunner.stop();
            prunedRunner = null;
        }
    }

    private void startNode() throws Exception {
        File dataDir = NodeModeUtil.datadir(getApplicationContext(), nodeMode);
        ChainBootstrapInstaller.repairIncompleteInstall(getApplicationContext(), dataDir);
        if (shouldResetChainAfterBlockDbFailure(dataDir)) {
            Log.w(TAG, "resetting chain data after block DB recovery loop");
            ChainBootstrapInstaller.invalidateInstalledChain(getApplicationContext(), dataDir);
            lastStartError = "";
            bloodstonedRestartAttempts = 0;
            chainResetPending = false;
        }
        stopListeners();
        upstream = new UpstreamRpcClient(upstreamUrl);
        prunedRunner = new PrunedNodeRunner(this, credentials, pruneMiB, nodeMode);
        boolean prunedAlive = prunedRunner.start();
        String activeMode = prunedAlive ? prunedRunner.activeMode() : "gateway";
        String mode = prunedAlive ? activeMode : nodeMode;

        rpcServer = new LocalRpcHttpServer(RPC_PORT, credentials, this::handleRpc);
        rpcServer.start();

        int stratumNeoPort = 0;
        int stratumYpPort = 0;
        int stratumSha256Port = 0;
        if (NodeModeUtil.hostsStratum(mode)) {
            LocalStratumTcpServer.RpcCaller stratumRpc = (method, params) -> {
                JSONObject response = handleRpc(method, params, "stratum", "127.0.0.1");
                if (response.has("result")) {
                    Object result = response.get("result");
                    if (result instanceof JSONObject) {
                        return (JSONObject) result;
                    }
                }
                if (response.has("error") && !response.isNull("error")) {
                    throw new Exception(response.getJSONObject("error").optString("message", "rpc error"));
                }
                return new JSONObject();
            };
            LocalSha256dStratumServer.RpcCaller sha256Rpc = (method, params) -> {
                JSONObject response = handleRpc(method, params, "stratum-sha256", "127.0.0.1");
                if (response.has("error") && !response.isNull("error")) {
                    throw new Exception(response.getJSONObject("error").optString("message", "rpc error"));
                }
                if (response.has("result")) {
                    Object result = response.get("result");
                    if (result instanceof JSONObject) {
                        return (JSONObject) result;
                    }
                    if (result instanceof Boolean) {
                        JSONObject wrapped = new JSONObject();
                        wrapped.put("ok", (Boolean) result);
                        return wrapped;
                    }
                }
                return new JSONObject();
            };
            String poolHost = PoolUpstreamConfig.poolHostFromUpstreamUrl(upstreamUrl);
            poolCoordinator = LanPoolCoordinator.getInstance(getApplicationContext());
            stratumNeoscrypt = new LocalStratumTcpServer(
                STRATUM_PORT_NEOSCRYPT,
                LocalStratumTcpServer.Algo.NEOSCRYPT,
                stratumRpc,
                poolHost,
                STRATUM_PORT_NEOSCRYPT,
                poolCoordinator
            );
            stratumYespower = new LocalStratumTcpServer(
                STRATUM_PORT_YESPOWER,
                LocalStratumTcpServer.Algo.YESPOWER,
                stratumRpc,
                poolHost,
                STRATUM_PORT_YESPOWER,
                poolCoordinator
            );
            stratumSha256d = new LocalSha256dStratumServer(
                STRATUM_PORT_SHA256D,
                sha256Rpc,
                poolHost,
                STRATUM_PORT_SHA256D,
                poolCoordinator
            );
            stratumNeoscrypt.start();
            stratumYespower.start();
            stratumSha256d.start();
            stratumNeoPort = STRATUM_PORT_NEOSCRYPT;
            stratumYpPort = STRATUM_PORT_YESPOWER;
            stratumSha256Port = STRATUM_PORT_SHA256D;
        }

        String lanIp = NetworkUtil.lanIpv4(this);
        String serviceName = ("bloodstone-" + credentials.user()).toLowerCase(Locale.US);
        if (poolCoordinator != null && NodeModeUtil.hostsStratum(mode)) {
            poolCoordinator.start(serviceName, discovery, lanIp);
        }
        discovery.register(
            serviceName,
            RPC_PORT,
            mode,
            stratumNeoPort,
            stratumYpPort,
            stratumSha256Port
        );
        discovery.startBrowse();
        activeDiscovery = discovery;

        NodeSyncStatus syncStatus = fetchSyncStatus();
        int blockHeight = syncStatus.blockHeight;
        if (poolCoordinator != null) {
            poolCoordinator.updateChainState(
                blockHeight,
                syncStatus.blockHash,
                syncStatus.syncProgress >= 0.999 && blockHeight > 0
            );
        }

        JSONObject reg = new JSONObject();
        reg.put("device_id", serviceName);
        putLanRegistrationFields(reg, mode, lanIp, blockHeight, syncStatus);
        registrar.configure(
            LanEndpointUrls.registerUrlFromUpstream(upstreamUrl),
            reg
        );
        registrar.start();

        NodeTrafficStats.markSessionStart();
        boolean hasLocalChain =
            syncStatus.chainBytes >= 512L * 1024L || syncStatus.blockHeight > 0;
        boolean hostBloodstoned = NodeModeUtil.runsBloodstoned(nodeMode);
        running = hostBloodstoned || prunedAlive || hasLocalChain;
        NodeSyncPreferences syncPrefs = new NodeSyncPreferences(getApplicationContext());
        if (prunedAlive || hasLocalChain) {
            syncPrefs.enableBackgroundSync();
            NodeSyncScheduler.schedule(getApplicationContext());
        } else if (hostBloodstoned) {
            syncPrefs.setEnabled(false);
            NodeSyncScheduler.cancel(getApplicationContext());
        } else {
            syncPrefs.setEnabled(false);
            NodeSyncScheduler.cancel(getApplicationContext());
        }
        bloodstonedRestartAttempts = 0;
        lastBloodstonedRestartMs = 0L;
        if (prunedAlive) {
            lastStartError = "";
        } else if (lastStartError == null || lastStartError.isEmpty()) {
            String runnerReason =
                prunedRunner != null ? prunedRunner.lastFailureReason() : "";
            if (runnerReason != null && !runnerReason.isEmpty()) {
                lastStartError = runnerReason;
            } else {
                Integer exitCode = prunedRunner != null ? prunedRunner.lastExitCode() : null;
                lastStartError = exitCode != null
                    ? "bloodstoned exited (code " + exitCode + ") — keep app open on Wi‑Fi, allow notifications"
                    : "bloodstoned did not start — allow notifications, disable battery saver, tap Stop then Start";
            }
        }
        int networkHeight = resolveNetworkHeight(
            fetchNetworkBlockHeight(),
            syncStatus.headerHeight,
            Math.max(blockHeight, syncStatus.blockHeight)
        );
        publishSnapshot(
            running,
            mode,
            lanIp,
            Math.max(blockHeight, syncStatus.blockHeight),
            syncStatus.syncProgress,
            syncStatus.chainBytes,
            prunedRunner != null && prunedRunner.isPruned(),
            discovery.isRegistered(),
            networkHeight,
            syncStatus.headerHeight,
            0L,
            prunedRunner != null && prunedRunner.isAlive()
        );
        startForeground(
            NOTIFICATION_ID,
            buildNotification(
                notificationTitle(mode, syncStatus),
                notificationBody(lanIp, mode, syncStatus)
            )
        );
        startSyncPoller();
    }

    private void startSyncPoller() {
        if (syncPollerThread != null) {
            syncPollerThread.interrupt();
        }
        syncPollerThread = new Thread(() -> {
            while (running && !Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(SYNC_POLL_MS);
                } catch (InterruptedException exc) {
                    Thread.currentThread().interrupt();
                    break;
                }
                try {
                    refreshSyncSnapshot();
                } catch (Exception exc) {
                    Log.w(TAG, "sync poll failed: " + exc.getMessage());
                }
            }
        }, "bloodstone-sync-poll");
        syncPollerThread.setDaemon(true);
        syncPollerThread.start();
    }

    private void refreshSyncSnapshot() {
        if (!running) {
            return;
        }
        LocalNodeStatusSnapshot prev = snapshot.get();
        NodeSyncStatus syncStatus = fetchSyncStatus();
        if (syncStatus.blockHeight > 0 && prunedRunner != null) {
            ChainBootstrapInstaller.clearReindexMarker(
                NodeModeUtil.datadir(this, prunedRunner.activeMode())
            );
        }
        int networkHeight = resolveNetworkHeight(
            fetchNetworkBlockHeight(),
            syncStatus.headerHeight,
            Math.max(
                prev.networkBlockHeight,
                Math.max(syncStatus.blockHeight, syncStatus.headerHeight)
            )
        );
        boolean bloodstonedAlive = prunedRunner != null && prunedRunner.isAlive();
        if (bloodstonedAlive) {
            bloodstonedRestartAttempts = 0;
            if (prunedRunner != null) {
                ChainBootstrapInstaller.clearChainstateReindexMarker(
                    NodeModeUtil.datadir(this, prunedRunner.activeMode())
                );
            }
        } else {
            bloodstonedAlive = maybeRestartBloodstoned();
            if (!bloodstonedAlive) {
                updateBloodstonedDownError();
            }
        }
        String activeMode = prunedRunner != null ? prunedRunner.activeMode() : "gateway";
        String mode = bloodstonedAlive ? activeMode : nodeMode;
        syncStatus.syncProgress = resolveDisplaySyncProgress(
            syncStatus,
            networkHeight,
            bloodstonedAlive,
            mode
        );
        String lanIp = NetworkUtil.lanIpv4(this);
        if (lanIp == null || lanIp.isEmpty()) {
            lanIp = prev.lanIp;
        }
        boolean pruned = prunedRunner != null && prunedRunner.isPruned();
        boolean mdns = discovery != null && discovery.isRegistered();

        publishSnapshot(
            true,
            mode,
            lanIp,
            syncStatus.blockHeight,
            syncStatus.syncProgress,
            syncStatus.chainBytes,
            pruned,
            mdns,
            networkHeight,
            syncStatus.headerHeight,
            0L,
            bloodstonedAlive,
            bloodstonedRestartAttempts
        );

        if (poolCoordinator != null && NodeModeUtil.hostsStratum(mode)) {
            poolCoordinator.updateChainState(
                syncStatus.blockHeight,
                syncStatus.blockHash,
                syncStatus.syncProgress >= 0.999
                    && syncStatus.blockHeight > 0
                    && bloodstonedAlive
            );
            poolCoordinator.tickVerification();
        }

        if (syncStatus.blockHeight > 0 || networkHeight > 0) {
            NodeSyncPreferences prefs = new NodeSyncPreferences(getApplicationContext());
            prefs.recordCheck(syncStatus.blockHeight, networkHeight);
        }

        if (registrar != null && credentials != null && lanIp != null && !lanIp.isEmpty()) {
            try {
                String serviceName = ("bloodstone-" + credentials.user()).toLowerCase(Locale.US);
                JSONObject reg = new JSONObject();
                reg.put("device_id", serviceName);
                putLanRegistrationFields(reg, mode, lanIp, syncStatus.blockHeight, syncStatus);
                registrar.updatePayload(reg);
                long nowMs = System.currentTimeMillis();
                boolean heightChanged = syncStatus.blockHeight != lastLanRegisteredHeight;
                boolean due = (nowMs - lastLanPushMs) >= LAN_PUSH_MIN_MS;
                if (heightChanged || due) {
                    registrar.registerNow();
                    lastLanRegisteredHeight = syncStatus.blockHeight;
                    lastLanPushMs = nowMs;
                }
            } catch (Exception exc) {
                Log.w(TAG, "LAN registrar refresh failed: " + exc.getMessage());
            }
        }

        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.notify(
                NOTIFICATION_ID,
                buildNotification(
                    notificationTitle(mode, syncStatus),
                    notificationBody(lanIp, mode, syncStatus)
                )
            );
        }
    }

    private int fetchNetworkBlockHeight() {
        if (upstream == null) {
            return 0;
        }
        try {
            JSONObject count = upstream.call("getblockcount", new JSONArray(), "network");
            return count.optInt("result", 0);
        } catch (Exception ignored) {
            return 0;
        }
    }

    private static int resolveNetworkHeight(int upstreamHeight, int headerHeight, int fallback) {
        int tip = Math.max(upstreamHeight, headerHeight);
        return tip > 0 ? tip : fallback;
    }

    private static final int SYNC_CAUGHT_UP_MAX_BEHIND = 64;
    private static final double SYNC_CAUGHT_UP_MIN_RATIO = 0.99;

    private static boolean chainCaughtUp(int height, int tip, boolean bloodstonedAlive) {
        if (!bloodstonedAlive || height <= 0 || tip <= 0) {
            return false;
        }
        int behind = tip - height;
        if (behind <= SYNC_CAUGHT_UP_MAX_BEHIND) {
            return true;
        }
        return (double) height / (double) tip >= SYNC_CAUGHT_UP_MIN_RATIO;
    }

    private static double resolveDisplaySyncProgress(
        NodeSyncStatus sync,
        int networkHeight,
        boolean bloodstonedAlive,
        String mode
    ) {
        double progress = sync.syncProgress;
        int blocks = sync.blockHeight;
        int headers = sync.headerHeight;
        int tip = Math.max(networkHeight, Math.max(headers, blocks));

        if (blocks > 0 && tip > blocks) {
            if (chainCaughtUp(blocks, tip, bloodstonedAlive)) {
                progress = Math.max(progress, 1.0);
            } else {
                progress = Math.max(progress, Math.min(0.995, (double) blocks / (double) tip));
            }
        }
        if (headers > 0 && tip > headers) {
            if (chainCaughtUp(headers, tip, bloodstonedAlive)) {
                progress = Math.max(progress, 1.0);
            } else {
                progress = Math.max(progress, Math.min(0.995, (double) headers / (double) tip));
            }
        }
        if (headers > 0 && headers > blocks) {
            progress = Math.max(progress, Math.min(0.9, (double) blocks / (double) headers));
        }

        long chainBytes = sync.chainBytes;
        if (chainBytes >= 2L * 1024L * 1024L) {
            long estimate = 550L * 1024L * 1024L;
            progress = Math.max(progress, Math.min(0.96, (double) chainBytes / (double) estimate));
            progress = Math.max(progress, 0.02);
        }

        if (bloodstonedAlive && progress < 0.001) {
            progress = 0.02;
        }

        return Math.max(0.0, Math.min(1.0, progress));
    }

    private boolean shouldResetChainAfterBlockDbFailure(File dataDir) {
        if (chainResetPending) {
            return true;
        }
        SharedPreferences prefs = getApplicationContext().getSharedPreferences(
            "bloodstone_chain_bootstrap",
            Context.MODE_PRIVATE
        );
        if (prefs.getBoolean("bootstrap_corrupt", false)) {
            return true;
        }
        String reason = prunedRunner != null ? prunedRunner.lastFailureReason() : "";
        String tail = prunedRunner != null ? prunedRunner.logTail() : "";
        return ChainBootstrapInstaller.looksLikeBlockDatabaseError(reason)
            || ChainBootstrapInstaller.looksLikeBlockDatabaseError(tail)
            || ChainBootstrapInstaller.looksLikeMerkleCorruption(reason);
    }

    private void updateBloodstonedDownError() {
        if (prunedRunner == null || !NodeModeUtil.runsBloodstoned(nodeMode)) {
            return;
        }
        String reason = prunedRunner.lastFailureReason();
        if (reason != null && !reason.isEmpty()) {
            lastStartError = reason;
            return;
        }
        if (bloodstonedRestartAttempts >= MAX_BLOODSTONED_RESTARTS) {
            chainResetPending = true;
            lastStartError =
                "Chain index recovery failed — tap Stop node, wait 5 seconds, then Start "
                    + "(will re-download bootstrap)";
            return;
        }
        Integer exitCode = prunedRunner.lastExitCode();
        if (exitCode != null) {
            lastStartError =
                "bloodstoned exited (code "
                    + exitCode
                    + ") — auto-restart "
                    + bloodstonedRestartAttempts
                    + "/"
                    + MAX_BLOODSTONED_RESTARTS
                    + "; keep app open on Wi‑Fi";
        } else if (lastStartError == null || lastStartError.isEmpty()) {
            lastStartError =
                "bloodstoned not running — auto-restart "
                    + bloodstonedRestartAttempts
                    + "/"
                    + MAX_BLOODSTONED_RESTARTS;
        }
    }

    private boolean maybeRestartBloodstoned() {
        if (prunedRunner == null || !running || nodeStarting) {
            return false;
        }
        if ("lan-client".equals(nodeMode)) {
            return false;
        }
        if (bloodstonedRestartAttempts >= MAX_BLOODSTONED_RESTARTS) {
            return false;
        }
        long now = System.currentTimeMillis();
        if (now - lastBloodstonedRestartMs < BLOODSTONED_RESTART_COOLDOWN_MS) {
            return false;
        }
        lastBloodstonedRestartMs = now;
        bloodstonedRestartAttempts++;
        Integer exitCode = prunedRunner.lastExitCode();
        Log.w(
            TAG,
            "bloodstoned died (exit="
                + (exitCode != null ? exitCode : "?")
                + ") — restart attempt "
                + bloodstonedRestartAttempts
                + "/"
                + MAX_BLOODSTONED_RESTARTS
        );
        try {
            String priorReason = prunedRunner.lastFailureReason();
            File dataDir = NodeModeUtil.datadir(getApplicationContext(), nodeMode);
            if (ChainBootstrapInstaller.looksLikeMerkleCorruption(priorReason)
                || ChainBootstrapInstaller.looksLikeMerkleCorruption(prunedRunner.logTail())) {
                Log.w(TAG, "merkle corruption on restart — invalidating bootstrap");
                ChainBootstrapInstaller.markBootstrapCorrupt(getApplicationContext());
                ChainBootstrapInstaller.invalidateInstalledChain(getApplicationContext(), dataDir);
            } else if (ChainBootstrapInstaller.looksLikeBlockDatabaseError(priorReason)
                || ChainBootstrapInstaller.looksLikeBlockDatabaseError(prunedRunner.logTail())) {
                if (bloodstonedRestartAttempts >= 4) {
                    Log.w(TAG, "block DB errors persist — reinstalling chain bootstrap");
                    ChainBootstrapInstaller.markBootstrapCorrupt(getApplicationContext());
                    ChainBootstrapInstaller.invalidateInstalledChain(getApplicationContext(), dataDir);
                } else {
                    Log.w(TAG, "block DB init failed — rebuilding index from chainstate");
                    ChainBootstrapInstaller.markChainstateReindexRequired(dataDir);
                    ChainBootstrapInstaller.prepareForChainstateReindex(dataDir);
                }
            }
            boolean alive = prunedRunner.start();
            if (alive) {
                lastStartError = "";
                Log.i(TAG, "bloodstoned restarted — resuming chain download");
                return true;
            }
            String reason = prunedRunner.lastFailureReason();
            if (reason != null && !reason.isEmpty()) {
                lastStartError = reason;
            }
        } catch (Exception exc) {
            Log.w(TAG, "bloodstoned restart failed: " + exc.getMessage());
            lastStartError =
                "bloodstoned restart failed: "
                    + (exc.getMessage() != null ? exc.getMessage() : "unknown");
        }
        return false;
    }

    private void publishSnapshot(
        boolean runningFlag,
        String mode,
        String lanIp,
        int blockHeight,
        double syncProgress,
        long chainBytes,
        boolean pruned,
        boolean mdnsRegistered,
        int networkBlockHeight,
        int headerHeight,
        long lastSyncAt,
        boolean bloodstonedAlive
    ) {
        publishSnapshot(
            runningFlag,
            mode,
            lanIp,
            blockHeight,
            syncProgress,
            chainBytes,
            pruned,
            mdnsRegistered,
            networkBlockHeight,
            headerHeight,
            lastSyncAt,
            bloodstonedAlive,
            bloodstonedRestartAttempts
        );
    }

    private void publishSnapshot(
        boolean runningFlag,
        String mode,
        String lanIp,
        int blockHeight,
        double syncProgress,
        long chainBytes,
        boolean pruned,
        boolean mdnsRegistered,
        int networkBlockHeight,
        int headerHeight,
        long lastSyncAt,
        boolean bloodstonedAlive,
        int restartAttempts
    ) {
        snapshot.set(
            new LocalNodeStatusSnapshot(
                runningFlag,
                mode,
                lanIp,
                RPC_PORT,
                STRATUM_PORT_NEOSCRYPT,
                STRATUM_PORT_YESPOWER,
                NodeModeUtil.hostsStratum(mode) ? STRATUM_PORT_SHA256D : 0,
                credentials.user(),
                credentials.password(),
                blockHeight,
                pruned,
                mdnsRegistered,
                syncProgress,
                chainBytes,
                false,
                networkBlockHeight,
                headerHeight,
                lastSyncAt,
                bloodstonedAlive,
                restartAttempts
            )
        );
    }

    private void putLanRegistrationFields(
        JSONObject reg,
        String mode,
        String lanIp,
        int blockHeight,
        NodeSyncStatus syncStatus
    ) throws Exception {
        boolean hostsStratum = NodeModeUtil.hostsStratum(mode);
        reg.put("lan_ip", lanIp != null ? lanIp : "");
        reg.put("rpc_port", RPC_PORT);
        reg.put("stratum_port", hostsStratum ? STRATUM_PORT_NEOSCRYPT : 0);
        reg.put("stratum_port_yespower", hostsStratum ? STRATUM_PORT_YESPOWER : 0);
        reg.put("stratum_port_sha256d", hostsStratum ? STRATUM_PORT_SHA256D : 0);
        reg.put("pool_coordinator_port", hostsStratum ? LanPoolCoordinator.HTTP_PORT : 0);
        reg.put(
            "pool_coordinator_active",
            poolCoordinator != null && poolCoordinator.isLocalPoolActive()
        );
        reg.put("chunk_port", NodeModeUtil.isConsensusMode(mode) ? 0 : 18341);
        reg.put("rpc_user", credentials.user());
        reg.put("peer_kind", "android");
        reg.put("model", Build.MODEL != null ? Build.MODEL : "Android");
        reg.put("mode", mode);
        reg.put("block_height", blockHeight);
        reg.put("pruned", prunedRunner == null || prunedRunner.isPruned());
        reg.put("consensus_only", NodeModeUtil.isConsensusMode(mode));
        reg.put("sync_progress", syncStatus.syncProgress);
        reg.put("chain_bytes", syncStatus.chainBytes);
    }

    private static String notificationTitle(String mode, NodeSyncStatus syncStatus) {
        if ("full".equals(mode)) {
            if (syncStatus.syncProgress >= 0.999) {
                return "Full node active — network peer";
            }
            return String.format(
                Locale.US,
                "Full node syncing (%.0f%%)",
                syncStatus.syncProgress * 100.0
            );
        }
        if ("mesh".equals(mode)) {
            return "Mesh federation node active";
        }
        if (NodeModeUtil.CONSENSUS.equals(mode)) {
            if (syncStatus.syncProgress >= 0.999) {
                return "Consensus node active — validating chain";
            }
            return String.format(
                Locale.US,
                "Consensus node syncing (%.0f%%)",
                syncStatus.syncProgress * 100.0
            );
        }
        if (NodeModeUtil.CONSENSUS_WITNESS.equals(mode)) {
            if (syncStatus.syncProgress >= 0.999) {
                return "Witness node active — consensus only";
            }
            return String.format(
                Locale.US,
                "Witness node syncing (%.0f%%)",
                syncStatus.syncProgress * 100.0
            );
        }
        return "Local VPS node active (" + mode + ")";
    }

    private static String notificationBody(String lanIp, String mode, NodeSyncStatus syncStatus) {
        if (NodeModeUtil.isConsensusMode(mode)) {
            String p2p = NodeModeUtil.CONSENSUS.equals(mode) ? " · P2P :17333" : " · outbound peers only";
            return "Consensus witness · height " + syncStatus.blockHeight
                + " · RPC " + lanIp + ":" + RPC_PORT
                + " · no stratum" + p2p;
        }
        String base = "LAN RPC " + lanIp + ":" + RPC_PORT
            + " · stratum :" + STRATUM_PORT_NEOSCRYPT
            + " / yespower :" + STRATUM_PORT_YESPOWER;
        if ("full".equals(mode)) {
            return base + " · height " + syncStatus.blockHeight
                + " · P2P :17333";
        }
        if ("mesh".equals(mode)) {
            return base + " · pruned tip + mesh block backups";
        }
        return base;
    }

    private NodeSyncStatus fetchSyncStatus() {
        NodeSyncStatus status = new NodeSyncStatus();
        if (prunedRunner == null) {
            return status;
        }
        String activeMode = prunedRunner.activeMode();
        String diskMode = "gateway".equals(activeMode) ? nodeMode : activeMode;
        if (!"gateway".equals(diskMode) && !"lan-client".equals(diskMode)) {
            status.chainBytes = ChainBootstrapInstaller.datadirChainBytes(this, diskMode);
            int markerHeight = ChainBootstrapInstaller.bootstrapHeightFromDatadir(
                NodeModeUtil.datadir(this, diskMode)
            );
            if (markerHeight > status.blockHeight) {
                status.blockHeight = markerHeight;
            }
            int prefsHeight = ChainBootstrapInstaller.installedBootstrapHeight(
                getApplicationContext()
            );
            if (prefsHeight > status.blockHeight) {
                status.blockHeight = prefsHeight;
            }
        }
        if (!prunedRunner.isAlive()) {
            if (status.chainBytes > 512L * 1024L) {
                // Keep bootstrap/marker height for LAN registry; cap progress while daemon is down.
                status.headerHeight = 0;
                status.syncProgress = Math.min(
                    Math.max(status.syncProgress, 0.35),
                    0.92
                );
            } else if (status.syncProgress <= 0.0) {
                status.syncProgress = 0.02;
            }
            return status;
        }
        try {
            JSONObject count = callLocalBloodstoned("getblockcount", new JSONArray(), "status");
            if (count.has("result") && !count.isNull("result")) {
                status.blockHeight = count.optInt("result", 0);
            }
        } catch (Exception ignored) {
        }
        try {
            JSONObject best = callLocalBloodstoned("getbestblockhash", new JSONArray(), "status-hash");
            if (best.has("result") && !best.isNull("result")) {
                status.blockHash = best.optString("result", "");
            }
        } catch (Exception ignored) {
        }
        try {
            JSONObject info = callLocalBloodstoned("getblockchaininfo", new JSONArray(), "status");
            if (info.has("result") && !info.isNull("result")) {
                JSONObject result = info.getJSONObject("result");
                int blocks = result.optInt("blocks", status.blockHeight);
                int headers = result.optInt("headers", 0);
                if (blocks > status.blockHeight) {
                    status.blockHeight = blocks;
                }
                status.headerHeight = headers;
                double verification = result.optDouble("verificationprogress", 0.0);
                double headerRatio = (headers > 0 && blocks >= 0)
                    ? Math.min(1.0, (double) blocks / (double) headers)
                    : 0.0;
                status.syncProgress = Math.max(verification, headerRatio);
                Object sizeOnDisk = result.opt("size_on_disk");
                if (sizeOnDisk instanceof Number) {
                    status.chainBytes = ((Number) sizeOnDisk).longValue();
                } else if (sizeOnDisk instanceof JSONObject) {
                    JSONObject sizeInfo = (JSONObject) sizeOnDisk;
                    long bytes = sizeInfo.optLong("bytes", 0L);
                    if (bytes <= 0L) {
                        bytes = sizeInfo.optLong("blocks", 0L);
                    }
                    status.chainBytes = bytes;
                }
            }
        } catch (Exception ignored) {
        }
        if (status.chainBytes <= 0L) {
            String bytesMode = "gateway".equals(prunedRunner.activeMode())
                ? nodeMode
                : prunedRunner.activeMode();
            status.chainBytes = NodeStorageUtil.datadirBytes(
                this,
                NodeModeUtil.datadir(this, bytesMode).getName()
            );
        }
        return status;
    }

    private JSONObject handleRpc(String method, JSONArray params, Object id, String remoteIp) {
        JSONObject out = new JSONObject();
        try {
            out.put("jsonrpc", "1.0");
            out.put("id", id);
            if (prunedRunner != null && prunedRunner.isAlive()) {
                try {
                    JSONObject local = callLocalBloodstoned(method, params, id);
                    if (!local.has("error") || local.isNull("error")) {
                        return local;
                    }
                    String message = local.getJSONObject("error").optString("message", "");
                    if (!shouldFallbackToUpstream(method, message)) {
                        return local;
                    }
                    Log.i(TAG, "local RPC " + method + " unavailable during sync — upstream fallback");
                } catch (Exception localExc) {
                    Log.i(TAG, "local RPC " + method + " failed: " + localExc.getMessage());
                }
            }
            JSONObject upstreamResponse = upstream.call(method, params, id);
            return upstreamResponse;
        } catch (Exception exc) {
            try {
                out.put("result", JSONObject.NULL);
                JSONObject err = new JSONObject();
                err.put("code", -32000);
                err.put("message", exc.getMessage());
                out.put("error", err);
            } catch (Exception ignored) {
            }
            return out;
        }
    }

    private static boolean shouldFallbackToUpstream(String method, String message) {
        if (method == null) {
            return false;
        }
        String m = method.toLowerCase();
        if (!"creatework".equals(m)
            && !"getblocktemplate".equals(m)
            && !"getmininginfo".equals(m)
            && !"getblockcount".equals(m)) {
            return false;
        }
        if (message == null) {
            return true;
        }
        String lower = message.toLowerCase();
        return lower.contains("verifying")
            || lower.contains("sync")
            || lower.contains("initial")
            || lower.contains("warmup")
            || lower.contains("not connected")
            || lower.contains("loading")
            || lower.contains("rewind")
            || lower.contains("unavailable");
    }

    private JSONObject callLocalBloodstoned(String method, JSONArray params, Object id) throws Exception {
        String url = "http://" + credentials.user() + ":" + credentials.password()
            + "@127.0.0.1:18332/";
        UpstreamRpcClient local = new UpstreamRpcClient(url);
        return local.call(method, params, id);
    }

    private void shutdown() {
        NodeTrafficStats.markSessionEnd(getApplicationContext());
        running = false;
        nodeStarting = false;
        instance = null;
        stopListeners();
        Context app = getApplicationContext();
        NodeSyncPreferences prefs = new NodeSyncPreferences(app);
        if (prefs.isEnabled()) {
            publishDormantSnapshot(
                app,
                prefs.nodeMode(),
                prefs.lastLocalHeight(),
                prefs.lastNetworkHeight(),
                prefs
            );
        } else {
            snapshot.set(LocalNodeStatusSnapshot.stopped());
        }
        stopForeground(true);
        stopSelf();
    }

    @Override
    public void onDestroy() {
        shutdown();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private Notification buildNotification(String title, String body) {
        Intent launch = buildResumeMainIntent();
        PendingIntent contentIntent = PendingIntent.getActivity(
            this,
            0,
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent stopIntent = new Intent(this, LocalNodeForegroundService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPending = PendingIntent.getService(
            this,
            2,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(body)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setOngoing(true)
            .setContentIntent(contentIntent)
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                "Stop",
                stopPending
            )
            .setStyle(new NotificationCompat.BigTextStyle().bigText(
                body + "\nRPC user: " + credentials.user() + " (password in app settings)"
            ))
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
    }

    private Intent buildResumeMainIntent() {
        Intent launch = new Intent(Intent.ACTION_MAIN);
        launch.addCategory(Intent.CATEGORY_LAUNCHER);
        launch.setClassName(getPackageName(), "org.bloodstone.miner.MainActivity");
        launch.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return launch;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Bloodstone local node",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Local Bloodstone node with LAN RPC/stratum for household miners");
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.createNotificationChannel(channel);
        }
    }

    public static void stop(Context context) {
        Intent intent = new Intent(context, LocalNodeForegroundService.class);
        intent.setAction(ACTION_STOP);
        context.startService(intent);
    }

    static final class LocalNodeStatusSnapshot {
        final boolean running;
        final String mode;
        final String lanIp;
        final int rpcPort;
        final int stratumPort;
        final int stratumPortYespower;
        final int stratumPortSha256d;
        final String rpcUser;
        final String rpcPassword;
        final int blockHeight;
        final boolean pruned;
        final boolean mdnsRegistered;
        final double syncProgress;
        final long chainBytes;
        final boolean batteryDormant;
        final int networkBlockHeight;
        final int headerHeight;
        final long lastSyncAt;
        final boolean bloodstonedAlive;
        final int bloodstonedRestartAttempts;

        LocalNodeStatusSnapshot(
            boolean running,
            String mode,
            String lanIp,
            int rpcPort,
            int stratumPort,
            int stratumPortYespower,
            int stratumPortSha256d,
            String rpcUser,
            String rpcPassword,
            int blockHeight,
            boolean pruned,
            boolean mdnsRegistered,
            double syncProgress,
            long chainBytes,
            boolean batteryDormant,
            int networkBlockHeight,
            int headerHeight,
            long lastSyncAt,
            boolean bloodstonedAlive,
            int bloodstonedRestartAttempts
        ) {
            this.running = running;
            this.mode = mode;
            this.lanIp = lanIp;
            this.rpcPort = rpcPort;
            this.stratumPort = stratumPort;
            this.stratumPortYespower = stratumPortYespower;
            this.stratumPortSha256d = stratumPortSha256d;
            this.rpcUser = rpcUser;
            this.rpcPassword = rpcPassword;
            this.blockHeight = blockHeight;
            this.pruned = pruned;
            this.mdnsRegistered = mdnsRegistered;
            this.syncProgress = syncProgress;
            this.chainBytes = chainBytes;
            this.batteryDormant = batteryDormant;
            this.networkBlockHeight = networkBlockHeight;
            this.headerHeight = headerHeight;
            this.lastSyncAt = lastSyncAt;
            this.bloodstonedAlive = bloodstonedAlive;
            this.bloodstonedRestartAttempts = bloodstonedRestartAttempts;
        }

        static LocalNodeStatusSnapshot stopped() {
            return new LocalNodeStatusSnapshot(
                false,
                "stopped",
                "",
                RPC_PORT,
                STRATUM_PORT_NEOSCRYPT,
                STRATUM_PORT_YESPOWER,
                0,
                "",
                "",
                0,
                true,
                false,
                0.0,
                0L,
                false,
                0,
                0,
                0L,
                false,
                0
            );
        }
    }

    private static final class NodeSyncStatus {
        int blockHeight;
        int headerHeight;
        double syncProgress;
        long chainBytes;
        String blockHash = "";
    }

    static LanPoolCoordinator poolCoordinator() {
        LocalNodeForegroundService inst = instance;
        return inst != null ? inst.poolCoordinator : null;
    }
}