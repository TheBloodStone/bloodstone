package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.util.Log;

import java.io.File;

import org.json.JSONArray;

final class NodeSyncEngine {
    private static final String TAG = "BloodstoneNodeSync";
    static final int BLOCKS_BEHIND_THRESHOLD = 8;
    static final int CAUGHT_UP_BLOCKS = 3;
    static final long MAX_SYNC_MS = 45L * 60L * 1000L;
    static final long POLL_MS = 5000L;
    static final long NODE_BOOT_MS = 2500L;

    enum Outcome {
        SKIPPED_ACTIVE_MINING,
        SKIPPED_UP_TO_DATE,
        SYNCED,
        SYNC_FAILED,
        CHECK_FAILED
    }

    static final class Result {
        final Outcome outcome;
        final int localHeight;
        final int networkHeight;
        final String message;

        Result(Outcome outcome, int localHeight, int networkHeight, String message) {
            this.outcome = outcome;
            this.localHeight = localHeight;
            this.networkHeight = networkHeight;
            this.message = message;
        }
    }

    interface SyncListener {
        void onSyncStarted(int localHeight, int networkHeight);
    }

    static Result runPeriodicCheck(Context context) {
        return runPeriodicCheck(context, null);
    }

    static Result runPeriodicCheck(Context context, SyncListener listener) {
        if (LocalNodeForegroundService.isRunning() || LocalNodeForegroundService.isStarting()) {
            return new Result(
                Outcome.SKIPPED_ACTIVE_MINING,
                0,
                0,
                "foreground node active"
            );
        }

        NodeSyncPreferences prefs = new NodeSyncPreferences(context);
        if (!prefs.isEnabled()) {
            return new Result(Outcome.SKIPPED_UP_TO_DATE, 0, 0, "sync not enabled");
        }

        String upstreamUrl = prefs.upstreamUrl();
        int pruneMiB = prefs.pruneMiB();
        String nodeMode = prefs.nodeMode();
        RpcCredentials credentials = RpcCredentials.loadOrCreate(context);

        int networkHeight;
        try {
            networkHeight = fetchBlockHeight(new UpstreamRpcClient(upstreamUrl));
        } catch (Exception exc) {
            Log.w(TAG, "network height failed: " + exc.getMessage());
            return new Result(Outcome.CHECK_FAILED, 0, 0, exc.getMessage());
        }

        PrunedNodeRunner runner = null;
        int localHeight = prefs.lastLocalHeight();
        try {
            runner = new PrunedNodeRunner(context, credentials, pruneMiB, nodeMode);
            if (runner.start()) {
                Thread.sleep(NODE_BOOT_MS);
                if (runner.isAlive()) {
                    localHeight = fetchLocalBlockHeight(credentials);
                }
            }
        } catch (Exception exc) {
            Log.w(TAG, "local height probe failed: " + exc.getMessage());
        } finally {
            if (runner != null) {
                runner.stop();
            }
        }

        prefs.recordCheck(localHeight, networkHeight);
        int behind = networkHeight - localHeight;
        Log.i(
            TAG,
            "check local=" + localHeight + " network=" + networkHeight + " behind=" + behind
        );

        if (behind < BLOCKS_BEHIND_THRESHOLD) {
            LocalNodeForegroundService.publishDormantSnapshot(
                context,
                nodeMode,
                localHeight,
                networkHeight,
                prefs
            );
            return new Result(
                Outcome.SKIPPED_UP_TO_DATE,
                localHeight,
                networkHeight,
                "within " + (BLOCKS_BEHIND_THRESHOLD - 1) + " blocks"
            );
        }

        if (behind >= ChainBootstrapInstaller.BOOTSTRAP_STALE_BLOCKS
            && ChainBootstrapInstaller.supportsMode(nodeMode)) {
            File dataDir = NodeModeUtil.datadir(context, nodeMode);
            ChainBootstrapInstaller.prepareForNetworkTip(context, dataDir, networkHeight);
            try {
                if (ChainBootstrapInstaller.ensureBootstrap(context, dataDir, nodeMode)) {
                    localHeight = 0;
                    Log.i(TAG, "refreshed chain bootstrap before background sync");
                }
            } catch (Exception exc) {
                Log.w(TAG, "bootstrap refresh during sync check failed: " + exc.getMessage());
            }
        }

        return runShortSync(
            context,
            prefs,
            credentials,
            upstreamUrl,
            pruneMiB,
            nodeMode,
            localHeight,
            networkHeight,
            listener
        );
    }

    private static Result runShortSync(
        Context context,
        NodeSyncPreferences prefs,
        RpcCredentials credentials,
        String upstreamUrl,
        int pruneMiB,
        String nodeMode,
        int localHeight,
        int networkHeight,
        SyncListener listener
    ) {
        if (listener != null) {
            listener.onSyncStarted(localHeight, networkHeight);
        }
        PrunedNodeRunner runner = new PrunedNodeRunner(context, credentials, pruneMiB, nodeMode);
        try {
            if (!runner.start()) {
                return new Result(
                    Outcome.SYNC_FAILED,
                    localHeight,
                    networkHeight,
                    "bloodstoned unavailable"
                );
            }
            Thread.sleep(NODE_BOOT_MS);

            long deadline = System.currentTimeMillis() + MAX_SYNC_MS;
            int bestLocal = localHeight;
            while (System.currentTimeMillis() < deadline && runner.isAlive()) {
                int currentNetwork = fetchBlockHeight(new UpstreamRpcClient(upstreamUrl));
                networkHeight = currentNetwork;
                bestLocal = fetchLocalBlockHeight(credentials);
                int behind = networkHeight - bestLocal;
                Log.i(TAG, "syncing local=" + bestLocal + " network=" + networkHeight);
                if (behind <= CAUGHT_UP_BLOCKS) {
                    NodeTrafficStats.recordSyncSession(Math.max(0, bestLocal - localHeight));
                    prefs.recordSyncComplete(bestLocal, networkHeight);
                    LocalNodeForegroundService.publishDormantSnapshot(
                        context,
                        runner.activeMode(),
                        bestLocal,
                        networkHeight,
                        prefs
                    );
                    return new Result(
                        Outcome.SYNCED,
                        bestLocal,
                        networkHeight,
                        "caught up"
                    );
                }
                Thread.sleep(POLL_MS);
            }

            bestLocal = runner.isAlive() ? fetchLocalBlockHeight(credentials) : bestLocal;
            NodeTrafficStats.recordSyncSession(Math.max(0, bestLocal - localHeight));
            prefs.recordSyncComplete(bestLocal, networkHeight);
            LocalNodeForegroundService.publishDormantSnapshot(
                context,
                runner.activeMode(),
                bestLocal,
                networkHeight,
                prefs
            );
            return new Result(
                Outcome.SYNCED,
                bestLocal,
                networkHeight,
                "sync window ended"
            );
        } catch (Exception exc) {
            Log.w(TAG, "sync failed: " + exc.getMessage());
            return new Result(
                Outcome.SYNC_FAILED,
                localHeight,
                networkHeight,
                exc.getMessage()
            );
        } finally {
            runner.stop();
        }
    }

    private static int fetchBlockHeight(UpstreamRpcClient client) throws Exception {
        org.json.JSONObject response = client.call("getblockcount", new JSONArray(), "sync");
        return response.optInt("result", 0);
    }

    private static int fetchLocalBlockHeight(RpcCredentials credentials) throws Exception {
        String url = "http://" + credentials.user() + ":" + credentials.password()
            + "@127.0.0.1:18332/";
        return fetchBlockHeight(new UpstreamRpcClient(url));
    }
}