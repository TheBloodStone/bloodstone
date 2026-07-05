package org.bloodstone.plugins.localnode;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.util.Log;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

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
    private static volatile LanDiscovery browseOnlyDiscovery;

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
        NodeSyncScheduler.schedule(getContext());

        boolean runForeground = Boolean.TRUE.equals(foreground)
            || "full".equals(mode)
            || "pruned".equals(mode)
            || "mesh".equals(mode)
            || NodeModeUtil.CONSENSUS.equals(mode)
            || NodeModeUtil.CONSENSUS_WITNESS.equals(mode);
        if (runForeground) {
            startForegroundNode(call, upstreamUrl, prune, mode);
            return;
        }

        LocalNodeForegroundService.publishDormantSnapshot(
            getContext(),
            mode,
            prefs.lastLocalHeight(),
            prefs.lastNetworkHeight(),
            prefs
        );
        call.resolve(statusObject());
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
        if (!hasNotificationPermission()) {
            requestNotificationPermission();
            call.reject(
                "Allow notifications for Bloodstone (Settings → Apps → Bloodstone → Notifications), then tap Start again"
            );
            return;
        }
        Intent intent = new Intent(getContext(), LocalNodeForegroundService.class);
        intent.putExtra("upstreamUrl", upstreamUrl);
        intent.putExtra("pruneMiB", pruneMiB);
        intent.putExtra("nodeMode", nodeMode);
        try {
            Context starter = getActivity();
            if (starter == null) {
                starter = getContext();
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                starter.startForegroundService(intent);
            } else {
                starter.startService(intent);
            }
            // Return immediately — bootstrap + bloodstoned boot can take minutes.
            // UI polls getLocalNodeStatus() for progress.
            call.resolve(statusObject());
        } catch (Exception exc) {
            Log.w(TAG, "startLocalNode failed: " + exc.getMessage());
            call.reject("startLocalNode failed: " + exc.getMessage());
        }
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
    public void resetLocalNodeChain(PluginCall call) {
        String nodeMode = call.getString("nodeMode", "full");
        String mode = PrunedNodeRunner.normalizeMode(nodeMode);
        try {
            LocalNodeForegroundService.stop(getContext());
            java.io.File dataDir = NodeModeUtil.datadir(getContext(), mode);
            ChainBootstrapInstaller.prepareForReindex(dataDir);
            deleteTree(new java.io.File(dataDir, "blocks"));
            ChainBootstrapInstaller.clearReindexMarker(dataDir);
            java.io.File heightMarker = new java.io.File(dataDir, ".bootstrap-height");
            if (heightMarker.isFile()) {
                heightMarker.delete();
            }
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
        JSObject stratumPorts = new JSObject();
        stratumPorts.put("neoscrypt", snap.stratumPort);
        stratumPorts.put("yespower", snap.stratumPortYespower);
        ret.put("stratumPorts", stratumPorts);
        ret.put("rpcUser", snap.rpcUser);
        ret.put("rpcPassword", snap.rpcPassword);
        ret.put("pruned", snap.pruned);
        ret.put("blockHeight", snap.blockHeight > 0 ? snap.blockHeight : prefs.lastLocalHeight());
        ret.put("networkBlockHeight", snap.networkBlockHeight > 0
            ? snap.networkBlockHeight
            : prefs.lastNetworkHeight());
        ret.put("headerHeight", snap.headerHeight);
        ret.put("syncProgress", snap.syncProgress);
        boolean starting = LocalNodeForegroundService.isStarting();
        boolean bootstrapping = ChainBootstrapInstaller.isInProgress();
        ret.put("nodeStarting", starting || bootstrapping);
        ret.put("chainBootstrapping", bootstrapping);
        ret.put("chainBootstrapPhase", ChainBootstrapInstaller.phase);
        ret.put("chainBootstrapPct", ChainBootstrapInstaller.progressPct);
        if (starting || bootstrapping) {
            ret.put("running", true);
            ret.put("nodeStarting", true);
            ret.put("mode", requestedMode);
        }
        if (snap.running || starting || bootstrapping) {
            ret.put("bloodstonedAlive", snap.bloodstonedAlive);
            ret.put("bloodstonedRestartAttempts", snap.bloodstonedRestartAttempts);
        }
        String startError = LocalNodeForegroundService.lastStartError();
        if (startError != null && !startError.isEmpty()) {
            ret.put("startError", startError);
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
        return ret;
    }
}