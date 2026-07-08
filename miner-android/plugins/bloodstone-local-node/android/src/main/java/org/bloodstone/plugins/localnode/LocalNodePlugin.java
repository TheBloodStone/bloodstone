package org.bloodstone.plugins.localnode;

import android.Manifest;
import android.app.Activity;
import android.app.ForegroundServiceStartNotAllowedException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.lifecycle.Lifecycle;
import androidx.lifecycle.LifecycleOwner;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

@CapacitorPlugin(name = "BloodstoneLocalNode")
public class LocalNodePlugin extends Plugin {
    private static final String TAG = "BloodstoneLocalNode";
    private static final long FOREGROUND_START_RETRY_MS = 350L;
    private static final int MAX_PENDING_FOREGROUND_RETRIES = 48;
    private static volatile LanDiscovery browseOnlyDiscovery;
    private static volatile PendingForegroundStart pendingForegroundStart;
    private static volatile int pendingForegroundRetries = 0;
    private static final Handler mainHandler = new Handler(Looper.getMainLooper());

    private static final class PendingForegroundStart {
        final String upstreamUrl;
        final int pruneMiB;
        final String nodeMode;

        PendingForegroundStart(String upstreamUrl, int pruneMiB, String nodeMode) {
            this.upstreamUrl = upstreamUrl;
            this.pruneMiB = pruneMiB;
            this.nodeMode = nodeMode;
        }
    }

    @PluginMethod
    public void startLocalNode(PluginCall call) {
        NodeTrafficStatsHolder.appContext = getContext().getApplicationContext();
        String upstreamUrl = call.getString("upstreamUrl", "");
        Integer pruneMiB = call.getInt("pruneMiB", 550);
        String nodeMode = call.getString("nodeMode", "pruned");
        Boolean foreground = call.getBoolean("foreground", false);

        if (upstreamUrl == null || upstreamUrl.isEmpty()) {
            upstreamUrl = NodeSyncPreferences.DEFAULT_UPSTREAM;
        }
        int prune = pruneMiB != null ? pruneMiB : 550;
        String requestedMode = nodeMode != null ? nodeMode.trim().toLowerCase() : "pruned";
        if ("lan-client".equals(requestedMode) || "lan_client".equals(requestedMode)) {
            NodeSyncPreferences prefs = new NodeSyncPreferences(getContext());
            prefs.saveConfig(upstreamUrl, prune, "lan-client");
            ensureLanBrowse();
            LocalNodeForegroundService.publishDormantSnapshot(
                getContext(),
                "lan-client",
                prefs.lastLocalHeight(),
                prefs.lastNetworkHeight(),
                prefs
            );
            call.resolve(statusObject());
            return;
        }

        String mode = PrunedNodeRunner.normalizeMode(nodeMode);

        NodeSyncPreferences prefs = new NodeSyncPreferences(getContext());
        prefs.saveConfig(upstreamUrl, prune, mode);

        boolean runForeground = Boolean.TRUE.equals(foreground);
        if (!runForeground) {
            LocalNodeForegroundService.publishDormantSnapshot(
                getContext(),
                mode,
                prefs.lastLocalHeight(),
                prefs.lastNetworkHeight(),
                prefs
            );
            call.resolve(statusObject());
            return;
        }
        startForegroundNode(call, upstreamUrl, prune, mode);
    }

    private static final int NODE_READY_POLL_MS = 500;
    private static final int NODE_READY_MAX_POLLS = 120;

    private void resolveWhenNodeReady(PluginCall call, int attempt) {
        LocalNodeForegroundService.LocalNodeStatusSnapshot snap =
            LocalNodeForegroundService.status();
        String startError = LocalNodeForegroundService.lastStartError();
        boolean starting = LocalNodeForegroundService.isStarting();
        if (snap.running || attempt >= NODE_READY_MAX_POLLS) {
            call.resolve(statusObject());
            return;
        }
        if (!starting && !snap.running && (!startError.isEmpty() || attempt > 2)) {
            call.resolve(statusObject());
            return;
        }
        getBridge().getWebView().postDelayed(
            () -> resolveWhenNodeReady(call, attempt + 1),
            NODE_READY_POLL_MS
        );
    }

    private boolean hasNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return true;
        }
        return ContextCompat.checkSelfPermission(
            getContext(),
            Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return;
        }
        Activity activity = getActivity();
        if (activity == null) {
            return;
        }
        ActivityCompat.requestPermissions(
            activity,
            new String[] { Manifest.permission.POST_NOTIFICATIONS },
            73422
        );
    }

    private void startForegroundNode(
        PluginCall call,
        String upstreamUrl,
        int pruneMiB,
        String nodeMode
    ) {
        if (LocalNodeForegroundService.isRunning() || LocalNodeForegroundService.isStarting()) {
            LocalNodeForegroundService.noteStartError("");
            call.resolve(statusObject());
            return;
        }
        if (!hasNotificationPermission()) {
            requestNotificationPermission();
            new NodeSyncPreferences(getContext()).setEnabled(false);
            String msg =
                "Allow notifications for Bloodstone (Settings → Apps → Bloodstone → Notifications), then tap Start again";
            LocalNodeForegroundService.noteStartError(msg);
            call.resolve(statusObject());
            return;
        }
        boolean launched = launchForegroundNodeService(upstreamUrl, pruneMiB, nodeMode, false);
        if (!launched && pendingForegroundStart != null) {
            LocalNodeForegroundService.noteStartError(
                "Starting local node when app is in foreground — keep Bloodstone open"
            );
        }
        call.resolve(statusObject());
    }

    private Activity resolveStarterActivity() {
        if (getBridge() != null && getBridge().getActivity() != null) {
            return getBridge().getActivity();
        }
        return getActivity();
    }

    private boolean isActivityForeground(Activity activity) {
        if (activity == null) {
            return false;
        }
        if (activity.isFinishing()) {
            return false;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN_MR1 && activity.isDestroyed()) {
            return false;
        }
        if (activity instanceof LifecycleOwner) {
            Lifecycle.State state = ((LifecycleOwner) activity).getLifecycle().getCurrentState();
            return state.isAtLeast(Lifecycle.State.STARTED);
        }
        return true;
    }

    private Intent buildForegroundNodeIntent(String upstreamUrl, int pruneMiB, String nodeMode) {
        Intent intent = new Intent(getContext(), LocalNodeForegroundService.class);
        intent.putExtra("upstreamUrl", upstreamUrl);
        intent.putExtra("pruneMiB", pruneMiB);
        intent.putExtra("nodeMode", nodeMode);
        return intent;
    }

    private boolean launchForegroundNodeService(
        String upstreamUrl,
        int pruneMiB,
        String nodeMode,
        boolean fromResume
    ) {
        if (LocalNodeForegroundService.isRunning() || LocalNodeForegroundService.isStarting()) {
            pendingForegroundStart = null;
            pendingForegroundRetries = 0;
            LocalNodeForegroundService.noteStartError("");
            return true;
        }
        Activity activity = resolveStarterActivity();
        if (activity == null || !isActivityForeground(activity)) {
            pendingForegroundStart = new PendingForegroundStart(upstreamUrl, pruneMiB, nodeMode);
            pendingForegroundRetries = 0;
            Log.i(TAG, "deferring local node foreground start until activity is visible");
            schedulePendingForegroundStart();
            return false;
        }

        Runnable launch = () -> {
            try {
                Intent intent = buildForegroundNodeIntent(upstreamUrl, pruneMiB, nodeMode);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    ContextCompat.startForegroundService(activity, intent);
                } else {
                    activity.startService(intent);
                }
                pendingForegroundStart = null;
                pendingForegroundRetries = 0;
                LocalNodeForegroundService.noteStartError("");
            } catch (ForegroundServiceStartNotAllowedException exc) {
                pendingForegroundStart = new PendingForegroundStart(upstreamUrl, pruneMiB, nodeMode);
                Log.w(TAG, "foreground service deferred: " + exc.getMessage());
                schedulePendingForegroundStart();
            } catch (Exception exc) {
                Log.w(TAG, "startLocalNode failed: " + exc.getMessage());
                new NodeSyncPreferences(getContext()).setEnabled(false);
                String msg = "startLocalNode failed: " + exc.getMessage();
                LocalNodeForegroundService.noteStartError(msg);
            }
        };

        if (Looper.myLooper() == Looper.getMainLooper()) {
            launch.run();
        } else {
            activity.runOnUiThread(launch);
        }
        return pendingForegroundStart == null;
    }

    private void schedulePendingForegroundStart() {
        mainHandler.removeCallbacks(retryPendingForegroundStart);
        mainHandler.postDelayed(retryPendingForegroundStart, FOREGROUND_START_RETRY_MS);
    }

    private final Runnable retryPendingForegroundStart = new Runnable() {
        @Override
        public void run() {
            PendingForegroundStart pending = pendingForegroundStart;
            if (pending == null) {
                return;
            }
            pendingForegroundRetries++;
            if (pendingForegroundRetries > MAX_PENDING_FOREGROUND_RETRIES) {
                pendingForegroundStart = null;
                pendingForegroundRetries = 0;
                LocalNodeForegroundService.noteStartError(
                    "Could not start local node — open Bloodstone from the app icon, then tap Start"
                );
                return;
            }
            launchForegroundNodeService(
                pending.upstreamUrl,
                pending.pruneMiB,
                pending.nodeMode,
                false
            );
            if (pendingForegroundStart != null) {
                mainHandler.postDelayed(this, FOREGROUND_START_RETRY_MS);
            }
        }
    };

    private void flushPendingForegroundStart(boolean fromResume) {
        PendingForegroundStart pending = pendingForegroundStart;
        if (pending == null) {
            return;
        }
        mainHandler.postDelayed(
            () -> launchForegroundNodeService(
                pending.upstreamUrl,
                pending.pruneMiB,
                pending.nodeMode,
                fromResume
            ),
            fromResume ? FOREGROUND_START_RETRY_MS : 0L
        );
    }

    @Override
    protected void handleOnResume() {
        super.handleOnResume();
        flushPendingForegroundStart(true);
    }

    @Override
    protected void handleOnStart() {
        super.handleOnStart();
        flushPendingForegroundStart(false);
    }

    /** Save node mode/upstream without starting foreground service (fixes UI/native mode drift). */
    @PluginMethod
    public void configureLocalNode(PluginCall call) {
        String upstreamUrl = call.getString("upstreamUrl", "");
        Integer pruneMiB = call.getInt("pruneMiB", 550);
        String nodeMode = call.getString("nodeMode", "full");
        if (upstreamUrl == null || upstreamUrl.isEmpty()) {
            upstreamUrl = NodeSyncPreferences.DEFAULT_UPSTREAM;
        }
        int prune = pruneMiB != null ? pruneMiB : 550;
        String mode = PrunedNodeRunner.normalizeMode(nodeMode);
        NodeSyncPreferences prefs = new NodeSyncPreferences(getContext());
        prefs.saveConfig(upstreamUrl, prune, mode);
        prefs.setEnabled(false);
        NodeSyncScheduler.cancel(getContext());
        LocalNodeForegroundService.stop(getContext());
        LocalNodeForegroundService.publishDormantSnapshot(
            getContext(),
            mode,
            prefs.lastLocalHeight(),
            prefs.lastNetworkHeight(),
            prefs
        );
        call.resolve(statusObject());
    }

    @PluginMethod
    public void stopLocalNode(PluginCall call) {
        Boolean foregroundOnly = call.getBoolean("foregroundOnly", true);
        try {
            if (Boolean.TRUE.equals(foregroundOnly)) {
                LocalNodeForegroundService.stop(getContext());
            } else {
                LocalNodeForegroundService.stop(getContext());
                NodeSyncPreferences prefs = new NodeSyncPreferences(getContext());
                prefs.setEnabled(false);
                NodeSyncScheduler.cancel(getContext());
                LocalNodeForegroundService.publishStoppedSnapshot();
            }
            call.resolve(statusObject());
        } catch (Exception exc) {
            call.reject("stopLocalNode failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void applyMeshChunksToDatadir(PluginCall call) {
        String nodeMode = call.getString("nodeMode", "full");
        String overlayMode = call.getString("overlayMode", "overlay");
        String mode = PrunedNodeRunner.normalizeMode(nodeMode);
        boolean replace = "replace".equalsIgnoreCase(
            overlayMode != null ? overlayMode.trim() : ""
        );
        try {
            LocalNodeForegroundService.stop(getContext());
            java.io.File dataDir = NodeModeUtil.datadir(getContext(), mode);
            MeshDatadirRestorer.Result result = MeshDatadirRestorer.apply(
                getContext(),
                dataDir,
                replace
            );
            JSObject ret = new JSObject();
            ret.put("ok", true);
            ret.put("chunksApplied", result.chunksApplied);
            ret.put("bytesWritten", result.bytesWritten);
            ret.put("filesTouched", result.filesTouched);
            ret.put("reindexRequired", result.reindexRequired);
            ret.put("overlayMode", replace ? "replace" : "overlay");
            call.resolve(ret);
        } catch (Exception exc) {
            Log.w(TAG, "applyMeshChunksToDatadir failed: " + exc.getMessage());
            call.reject("applyMeshChunksToDatadir failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void resetLocalNodeChain(PluginCall call) {
        String nodeMode = call.getString("nodeMode", "full");
        String mode = PrunedNodeRunner.normalizeMode(nodeMode);
        try {
            LocalNodeForegroundService.stop(getContext());
            java.io.File dataDir = NodeModeUtil.datadir(getContext(), mode);
            ChainBootstrapInstaller.invalidateInstalledChain(getContext(), dataDir);
            LocalNodeForegroundService.noteStartError("");
            call.resolve(statusObject());
        } catch (Exception exc) {
            call.reject("resetLocalNodeChain failed: " + exc.getMessage());
        }
    }

    private static void deleteTree(java.io.File dir) {
        if (dir == null || !dir.exists()) {
            return;
        }
        if (dir.isDirectory()) {
            java.io.File[] children = dir.listFiles();
            if (children != null) {
                for (java.io.File child : children) {
                    deleteTree(child);
                }
            }
        }
        dir.delete();
    }

    @PluginMethod
    public void getLocalNodeStatus(PluginCall call) {
        NodeTrafficStatsHolder.appContext = getContext().getApplicationContext();
        call.resolve(statusObject());
    }

    @PluginMethod
    public void getNodeStorageInfo(PluginCall call) {
        long freeBytes = NodeStorageUtil.freeBytes(getContext());
        long prunedBytes = NodeStorageUtil.datadirBytes(getContext(), "bloodstone-pruned");
        long fullBytes = NodeStorageUtil.datadirBytes(getContext(), "bloodstone-full");
        JSObject ret = new JSObject();
        ret.put("freeBytes", freeBytes);
        ret.put("prunedDatadirBytes", prunedBytes);
        ret.put("fullDatadirBytes", fullBytes);
        ret.put("fullNodeMinFreeBytes", NodeStorageUtil.FULL_NODE_MIN_FREE_BYTES);
        ret.put("fullNodeEstimateBytes", NodeStorageUtil.FULL_NODE_ESTIMATE_BYTES);
        ret.put("canRunFullNode", NodeStorageUtil.canRunFullNode(getContext()));
        ret.put("recommendedMode", NodeStorageUtil.recommendedMode(getContext()));
        call.resolve(ret);
    }

    @PluginMethod
    public void startLanBrowse(PluginCall call) {
        ensureLanBrowse();
        call.resolve(statusObject());
    }

    @PluginMethod
    public void discoverLanPeers(PluginCall call) {
        LanDiscovery discovery = LocalNodeForegroundService.discovery();
        if (discovery == null) {
            discovery = ensureLanBrowse();
        }
        LanDiscovery active = discovery;
        getBridge().getWebView().postDelayed(() -> {
            JSObject ret = new JSObject();
            JSONArray peers = active.peersJson();
            ret.put("nodes", peers);
            ret.put("count", peers.length());
            call.resolve(ret);
        }, 2500);
    }

    private LanDiscovery ensureLanBrowse() {
        LanDiscovery serviceDiscovery = LocalNodeForegroundService.discovery();
        if (serviceDiscovery != null) {
            return serviceDiscovery;
        }
        if (browseOnlyDiscovery == null) {
            browseOnlyDiscovery = new LanDiscovery(getContext());
        }
        browseOnlyDiscovery.startBrowse();
        return browseOnlyDiscovery;
    }

    @PluginMethod
    public void createLocalWallet(PluginCall call) {
        String passphrase = call.getString("passphrase", "");
        String label = call.getString("label", "mobile");
        if (passphrase == null || passphrase.length() < 8) {
            call.reject("Passphrase must be at least 8 characters");
            return;
        }
        LocalNodeForegroundService.LocalNodeStatusSnapshot snap =
            LocalNodeForegroundService.status();
        if (!snap.running) {
            call.reject("Start your local node first — wallets are created on-device by bloodstoned");
            return;
        }
        if (!snap.bloodstonedAlive) {
            call.reject("bloodstoned is still starting — wait until the chain panel shows sync progress, then try again");
            return;
        }
        if (!NodeModeUtil.supportsOnDeviceWallet(snap.mode)) {
            call.reject(
                "On-device wallet is not available in "
                    + snap.mode
                    + " mode — switch to Pruned, Full, or Mesh"
            );
            return;
        }
        RpcCredentials credentials = RpcCredentials.loadOrCreate(getContext());
        LocalWalletRpc walletRpc = new LocalWalletRpc(credentials);
        LocalWalletStore store = new LocalWalletStore(getContext());
        String deviceId = hashDeviceId(
            android.provider.Settings.Secure.getString(
                getContext().getContentResolver(),
                android.provider.Settings.Secure.ANDROID_ID
            )
        );
        String walletName = "mobile_" + deviceId.substring(0, Math.min(12, deviceId.length()));
        try {
            if (!walletRpc.walletExists(walletName)) {
                walletRpc.createLegacyWallet(walletName);
            } else {
                walletRpc.ensureWalletLoaded(walletName);
                JSONObject existing = walletRpc.getWalletInfo(walletName);
                if (!existing.optBoolean("private_keys_enabled", true)) {
                    JSONArray unlockParams = new JSONArray();
                    unlockParams.put(passphrase);
                    unlockParams.put(600);
                    walletRpc.callWallet("walletpassphrase", unlockParams, walletName);
                }
            }
            String address = walletRpc.getNewAddress(walletName, label);
            JSONObject info = walletRpc.getWalletInfo(walletName);
            if (info.optBoolean("private_keys_enabled", true)) {
                walletRpc.encryptWallet(walletName, passphrase);
            }
            store.addWallet(walletName, address, "local-node");
            JSObject ret = new JSObject();
            ret.put("ok", true);
            ret.put("wallet", walletName);
            ret.put("address", address);
            ret.put("onDevice", true);
            ret.put("encrypted", true);
            ret.put("note", "Private keys stay in your phone wallet file — never sent to the VPS");
            call.resolve(ret);
        } catch (Exception exc) {
            Log.w(TAG, "createLocalWallet failed: " + exc.getMessage());
            call.reject("createLocalWallet failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void getNewLocalAddress(PluginCall call) {
        String walletName = call.getString("wallet", "");
        String label = call.getString("label", "mobile");
        String passphrase = call.getString("passphrase", "");
        if (walletName == null || walletName.isEmpty()) {
            call.reject("wallet name required");
            return;
        }
        LocalNodeForegroundService.LocalNodeStatusSnapshot snap =
            LocalNodeForegroundService.status();
        if (!snap.running) {
            call.reject("Local node is not running");
            return;
        }
        RpcCredentials credentials = RpcCredentials.loadOrCreate(getContext());
        LocalWalletRpc walletRpc = new LocalWalletRpc(credentials);
        LocalWalletStore store = new LocalWalletStore(getContext());
        try {
            walletRpc.ensureWalletLoaded(walletName);
            if (passphrase != null && passphrase.length() >= 8) {
                JSONArray unlockParams = new JSONArray();
                unlockParams.put(passphrase);
                unlockParams.put(120);
                walletRpc.callWallet("walletpassphrase", unlockParams, walletName);
            }
            String address = walletRpc.getNewAddress(walletName, label);
            store.addAddress(walletName, address);
            JSObject ret = new JSObject();
            ret.put("ok", true);
            ret.put("wallet", walletName);
            ret.put("address", address);
            ret.put("onDevice", true);
            call.resolve(ret);
        } catch (Exception exc) {
            Log.w(TAG, "getNewLocalAddress failed: " + exc.getMessage());
            call.reject("getNewLocalAddress failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void listLocalWallets(PluginCall call) {
        LocalWalletStore store = new LocalWalletStore(getContext());
        JSONArray entries = store.listEntries();
        boolean nodeRunning = LocalNodeForegroundService.status().running;
        JSObject ret = new JSObject();
        ret.put("onDevice", true);
        ret.put("nodeRunning", nodeRunning);
        ret.put("entries", entries);
        ret.put("count", entries.length());
        call.resolve(ret);
    }

    private static String hashDeviceId(String androidId) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(
                ("bloodstone-local-wallet:" + (androidId != null ? androidId : "unknown"))
                    .getBytes(java.nio.charset.StandardCharsets.UTF_8)
            );
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 8; i++) {
                sb.append(String.format("%02x", digest[i]));
            }
            return sb.toString();
        } catch (Exception exc) {
            return "device";
        }
    }

    @PluginMethod
    public void registerLan(PluginCall call) {
        LocalNodeForegroundService service = LocalNodeForegroundService.getInstance();
        if (service != null) {
            try {
                JSONObject result = service.registerLanNow();
                call.resolve(JSObject.fromJSONObject(result));
                return;
            } catch (Exception exc) {
                Log.w(TAG, "registerLan failed: " + exc.getMessage());
                call.reject("registerLan failed: " + exc.getMessage());
                return;
            }
        }
        try {
            JSONObject result = registerLanStandalone(getContext());
            call.resolve(JSObject.fromJSONObject(result));
        } catch (Exception exc) {
            Log.w(TAG, "registerLan standalone failed: " + exc.getMessage());
            call.reject("registerLan failed: " + exc.getMessage());
        }
    }

    private static JSONObject registerLanStandalone(android.content.Context context) throws Exception {
        String lanIp = NetworkUtil.lanIpv4(context);
        if (lanIp == null || lanIp.isEmpty()) {
            JSONObject err = new JSONObject();
            err.put("ok", false);
            err.put("error", "Connect to Wi‑Fi to get a LAN IP");
            return err;
        }
        NodeSyncPreferences prefs = new NodeSyncPreferences(context);
        RpcCredentials credentials = RpcCredentials.loadOrCreate(context);
        LocalNodeForegroundService.LocalNodeStatusSnapshot snap =
            LocalNodeForegroundService.status();
        String mode = snap.running ? snap.mode : prefs.nodeMode();
        int blockHeight = snap.blockHeight > 0 ? snap.blockHeight : prefs.lastLocalHeight();
        boolean pruned = snap.running ? snap.pruned : !"full".equals(mode);
        double syncProgress = snap.syncProgress;
        long chainBytes = snap.chainBytes;
        String serviceName = ("bloodstone-" + credentials.user()).toLowerCase(java.util.Locale.US);
        String registerUrl = LanEndpointUrls.registerUrlFromUpstream(prefs.upstreamUrl());
        JSONObject reg = new JSONObject();
        reg.put("device_id", serviceName);
        reg.put("lan_ip", lanIp);
        reg.put("rpc_port", LocalNodeForegroundService.RPC_PORT);
        boolean hostsStratum = NodeModeUtil.hostsStratum(mode);
        reg.put("stratum_port", hostsStratum ? LocalNodeForegroundService.STRATUM_PORT_NEOSCRYPT : 0);
        reg.put("stratum_port_yespower", hostsStratum ? LocalNodeForegroundService.STRATUM_PORT_YESPOWER : 0);
        reg.put("chunk_port", NodeModeUtil.isConsensusMode(mode) ? 0 : 18341);
        reg.put("rpc_user", credentials.user());
        reg.put("peer_kind", "android");
        reg.put("model", android.os.Build.MODEL != null ? android.os.Build.MODEL : "Android");
        reg.put("mode", mode);
        reg.put("block_height", blockHeight);
        reg.put("pruned", pruned);
        reg.put("consensus_only", NodeModeUtil.isConsensusMode(mode));
        reg.put("sync_progress", syncProgress);
        reg.put("chain_bytes", chainBytes);
        LanRegistrar registrar = new LanRegistrar();
        registrar.configure(registerUrl, reg);
        return registrar.registerNow();
    }

    @PluginMethod
    public void getLanRpcUrl(PluginCall call) {
        LocalNodeForegroundService.LocalNodeStatusSnapshot snap =
            LocalNodeForegroundService.status();
        JSObject ret = new JSObject();
        if (!snap.running || snap.lanIp == null || snap.lanIp.isEmpty()) {
            ret.put("url", "");
            ret.put("user", "");
            ret.put("password", "");
            call.resolve(ret);
            return;
        }
        String url = "http://" + snap.lanIp + ":" + snap.rpcPort + "/";
        ret.put("url", url);
        ret.put("user", snap.rpcUser);
        ret.put("password", snap.rpcPassword);
        call.resolve(ret);
    }

    private JSObject statusObject() {
        LocalNodeForegroundService.LocalNodeStatusSnapshot snap =
            LocalNodeForegroundService.status();
        NodeSyncPreferences prefs = new NodeSyncPreferences(getContext());
        JSObject ret = new JSObject();
        ret.put("running", snap.running);
        String requestedMode = prefs.nodeMode();
        ret.put("requestedMode", requestedMode);
        ret.put("mode", snap.running ? snap.mode : requestedMode);
        String lanIp = snap.lanIp;
        if (lanIp == null || lanIp.isEmpty()) {
            lanIp = NetworkUtil.lanIpv4(getContext());
        }
        ret.put("lanIp", lanIp != null ? lanIp : "");
        ret.put("rpcPort", snap.rpcPort);
        ret.put("stratumPort", snap.stratumPort);
        ret.put("stratumPortYespower", snap.stratumPortYespower);
        ret.put("stratumPortSha256d", snap.stratumPortSha256d);
        JSObject stratumPorts = new JSObject();
        stratumPorts.put("neoscrypt", snap.stratumPort);
        stratumPorts.put("yespower", snap.stratumPortYespower);
        stratumPorts.put("sha256d", snap.stratumPortSha256d);
        ret.put("stratumPorts", stratumPorts);
        ret.put("rpcUser", snap.rpcUser);
        ret.put("rpcPassword", snap.rpcPassword);
        ret.put("pruned", snap.pruned);
        int blockHeight = snap.blockHeight;
        int networkHeight = snap.networkBlockHeight;
        boolean starting = LocalNodeForegroundService.isStarting();
        boolean bootstrapping = ChainBootstrapInstaller.isInProgress();
        if (!snap.running && !starting && !bootstrapping && snap.chainBytes < 512L * 1024L) {
            blockHeight = 0;
        } else if (blockHeight <= 0 && (snap.running || starting || bootstrapping)) {
            blockHeight = prefs.lastLocalHeight();
        }
        if (networkHeight <= 0 && (snap.running || starting || bootstrapping)) {
            networkHeight = prefs.lastNetworkHeight();
        }
        ret.put("blockHeight", blockHeight);
        ret.put("networkBlockHeight", networkHeight);
        ret.put("headerHeight", snap.headerHeight);
        ret.put("syncProgress", snap.syncProgress);
        ret.put("nodeStarting", starting || bootstrapping);
        ret.put("chainBootstrapping", bootstrapping);
        ret.put("chainBootstrapPhase", ChainBootstrapInstaller.phase);
        ret.put("chainBootstrapPct", ChainBootstrapInstaller.progressPct);
        ret.put("chainReindexing", ChainBootstrapInstaller.reindexPending(getContext(), requestedMode));
        if (starting || bootstrapping) {
            ret.put("running", true);
            ret.put("nodeStarting", true);
            ret.put("mode", requestedMode);
        }
        if (snap.running || starting || bootstrapping) {
            ret.put("bloodstonedAlive", snap.bloodstonedAlive);
            ret.put("bloodstonedRestartAttempts", snap.bloodstonedRestartAttempts);
        } else if (NodeModeUtil.runsBloodstoned(requestedMode)) {
            ret.put("bloodstonedAlive", false);
            ret.put("bloodstonedRestartAttempts", 0);
        }
        String startError = LocalNodeForegroundService.lastStartError();
        String failureReason = LocalNodeForegroundService.bloodstonedFailureReason();
        if (startError != null && !startError.isEmpty()) {
            boolean daemonDown = NodeModeUtil.runsBloodstoned(requestedMode) && !snap.bloodstonedAlive;
            if (daemonDown || (!snap.running && !starting && !bootstrapping)) {
                ret.put("startError", startError);
            }
        } else if (
            failureReason != null
            && !failureReason.isEmpty()
            && NodeModeUtil.runsBloodstoned(requestedMode)
            && !snap.bloodstonedAlive
        ) {
            ret.put("startError", failureReason);
        }
        if (failureReason != null && !failureReason.isEmpty()) {
            ret.put("bloodstonedFailureReason", failureReason);
        }
        if (android.os.Build.SUPPORTED_ABIS != null && android.os.Build.SUPPORTED_ABIS.length > 0) {
            ret.put("deviceAbis", String.join(",", android.os.Build.SUPPORTED_ABIS));
        }
        ret.put("chainBytes", snap.chainBytes);
        ret.put("mdnsRegistered", snap.mdnsRegistered);
        ret.put(
            "batteryDormant",
            !starting && (snap.batteryDormant || (!snap.running && prefs.isEnabled()))
        );
        ret.put("syncScheduled", prefs.isEnabled());
        ret.put("syncIntervalMinutes", NodeSyncScheduler.INTERVAL_MINUTES);
        ret.put("lastSyncAt", snap.lastSyncAt > 0 ? snap.lastSyncAt : prefs.lastSyncAt());
        if (snap.running) {
            ret.put("stratumHost", lanIp != null ? lanIp : "");
            if (lanIp != null && !lanIp.isEmpty()) {
                ret.put("rpcUrl", "http://" + lanIp + ":" + snap.rpcPort + "/");
            } else {
                ret.put("rpcUrl", "http://127.0.0.1:" + snap.rpcPort + "/");
            }
        } else {
            ret.put("rpcUrl", "");
            ret.put("stratumHost", "");
        }
        String mode = snap.running ? snap.mode : prefs.nodeMode();
        try {
            ret.put(
                "networkWork",
                JSObject.fromJSONObject(
                    NodeTrafficStats.snapshot(
                        getContext(),
                        mode,
                        snap.running || prefs.isEnabled()
                    )
                )
            );
        } catch (JSONException exc) {
            Log.w(TAG, "networkWork snapshot failed: " + exc.getMessage());
        }
        LanPoolCoordinator coordinator = LocalNodeForegroundService.poolCoordinator();
        if (coordinator != null) {
            try {
                ret.put("poolCoordinator", JSObject.fromJSONObject(coordinator.getStatus()));
            } catch (JSONException exc) {
                Log.w(TAG, "poolCoordinator status failed: " + exc.getMessage());
            }
        }
        return ret;
    }
}