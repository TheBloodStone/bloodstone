package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;

final class ChainBootstrapInstaller {
    private static final String TAG = "BloodstoneChainBootstrap";
    /** Pre-download chain snapshot on first full-node start — avoids hours of P2P on phones. */
    private static final boolean BOOTSTRAP_ENABLED = true;
    private static final String PREFS = "bloodstone_chain_bootstrap";
    private static final String KEY_HEIGHT = "installed_height";
    private static final String KEY_CORRUPT = "bootstrap_corrupt";
    private static final String DEFAULT_URL =
        "https://bloodstonewallet.mytunnel.org/downloads/bloodstone-chain-bootstrap-latest.tar.gz";
    private static final String SHA256_URL = DEFAULT_URL + ".sha256";
    private static final long EXPECTED_BLK_BYTES = 16L * 1024L * 1024L;
    /** Fallback when .sha256 sidecar fetch fails — keep in sync with published bootstrap. */
    private static final String DEFAULT_SHA256 =
        "23fa8e78e45aee9c92861ede187595a266ce3716fc5ad2de806f9aa53510b6fd";
    /** Re-download snapshot when local install is more than this many blocks behind tip. */
    static final int BOOTSTRAP_STALE_BLOCKS = 20;
    private static final long DOWNLOAD_TIMEOUT_MS = 300_000L;
    private static final long EXTRACT_TIMEOUT_MS = 240_000L;
    private static final long MIN_BLOCK_BYTES = 1024L * 1024L;
    private static final long MIN_INDEX_BYTES = 256L * 1024L;
    static final String REINDEX_CHAINSTATE_MARKER = ".bootstrap-reindex-chainstate";
    static final String INCLUDES_INDEX_MARKER = ".bootstrap-includes-index";

    static volatile boolean inProgress = false;
    static volatile String phase = "";
    static volatile int progressPct = 0;

    private ChainBootstrapInstaller() {
    }

    static boolean isInProgress() {
        return inProgress;
    }

    static boolean supportsMode(String mode) {
        String m = NodeModeUtil.normalize(mode);
        return "full".equals(m) || "mesh".equals(m) || "pruned".equals(m);
    }

    static boolean needsBootstrap(File dataDir) {
        File blocks = new File(dataDir, "blocks");
        if (dirEmpty(blocks)) {
            return true;
        }
        return !hasValidBlockFiles(blocks);
    }

    static boolean hasValidBlockFiles(File blocksDir) {
        if (blocksDir == null || !blocksDir.isDirectory()) {
            return false;
        }
        File[] blks = blocksDir.listFiles(
            (dir, name) -> name.startsWith("blk") && name.endsWith(".dat")
        );
        if (blks == null || blks.length == 0) {
            return false;
        }
        long total = 0L;
        for (File blk : blks) {
            total += blk.length();
        }
        return total >= MIN_BLOCK_BYTES;
    }

    static void repairIncompleteInstall(Context context, File dataDir) {
        File blocks = new File(dataDir, "blocks");
        if (dirEmpty(blocks) || hasValidBlockFiles(blocks)) {
            return;
        }
        Log.w(TAG, "removing incomplete bootstrap blocks before retry");
        invalidateInstalledChain(context, dataDir);
    }

    static boolean bootstrapStale(Context context, int networkBlockHeight) {
        if (networkBlockHeight <= 0) {
            return false;
        }
        int installed = installedBootstrapHeight(context);
        return installed > 0 && networkBlockHeight > installed + BOOTSTRAP_STALE_BLOCKS;
    }

    static void refreshIfIndexBundleRequired(Context context, File dataDir) {
        if (!hasValidChainstate(dataDir)) {
            return;
        }
        if (hasSubstantialBlocksIndex(dataDir)
            || new File(dataDir, INCLUDES_INDEX_MARKER).isFile()) {
            return;
        }
        Log.i(TAG, "installed bootstrap lacks blocks/index — refreshing snapshot");
        invalidateInstalledChain(context, dataDir);
    }

    static void prepareForNetworkTip(Context context, File dataDir, int networkBlockHeight) {
        refreshIfIndexBundleRequired(context, dataDir);
        refreshStaleBootstrap(context, dataDir, networkBlockHeight);
    }

    static void refreshStaleBootstrap(Context context, File dataDir, int networkBlockHeight) {
        if (!bootstrapStale(context, networkBlockHeight)) {
            return;
        }
        Log.i(
            TAG,
            "bootstrap height "
                + installedBootstrapHeight(context)
                + " is behind network "
                + networkBlockHeight
                + " — refreshing snapshot"
        );
        invalidateInstalledChain(context, dataDir);
    }

    static boolean ensureBootstrap(Context context, File dataDir, String nodeMode) throws Exception {
        return ensureBootstrap(context, dataDir, nodeMode, false);
    }

    static boolean ensureBootstrap(
        Context context,
        File dataDir,
        String nodeMode,
        boolean forceFreshDownload
    ) throws Exception {
        repairIncompleteInstall(context, dataDir);
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (prefs.getBoolean(KEY_CORRUPT, false)) {
            forceFreshDownload = true;
        }
        if (!BOOTSTRAP_ENABLED || !supportsMode(nodeMode) || !needsBootstrap(dataDir)) {
            return false;
        }
        if (!dataDir.exists() && !dataDir.mkdirs()) {
            throw new Exception("cannot create datadir");
        }
        // Drop any partial/corrupt chainstate from a failed prior start.
        deleteTree(new File(dataDir, "chainstate"));
        inProgress = true;
        progressPct = 3;
        phase = "downloading";
        File cacheDir = new File(context.getCacheDir(), "chain-bootstrap");
        if (!cacheDir.exists() && !cacheDir.mkdirs()) {
            throw new Exception("cannot create bootstrap cache");
        }
        File archive = new File(cacheDir, "bloodstone-chain-bootstrap.tar.gz");
        long deadline = System.currentTimeMillis() + DOWNLOAD_TIMEOUT_MS + EXTRACT_TIMEOUT_MS;
        try {
            String expectedSha = resolveExpectedSha256();
            if (forceFreshDownload && archive.isFile() && !archive.delete()) {
                Log.w(TAG, "could not delete bootstrap cache for fresh download");
            }
            String cachedDigest = prefs.getString("archive_sha256", "");
            boolean cacheUsable = archive.isFile()
                && archive.length() > 1024L
                && !forceFreshDownload
                && (expectedSha.isEmpty() || cachedDigest.equalsIgnoreCase(expectedSha));
            if (!cacheUsable) {
                download(DEFAULT_URL, archive, deadline);
            } else {
                progressPct = 70;
            }
            phase = "verifying";
            progressPct = 88;
            String digest = sha256(archive);
            if (!expectedSha.isEmpty() && !digest.equalsIgnoreCase(expectedSha)) {
                if (!archive.delete()) {
                    Log.w(TAG, "could not delete stale bootstrap cache");
                }
                throw new Exception("bootstrap checksum mismatch");
            }
            if (!cachedDigest.isEmpty() && !cachedDigest.equalsIgnoreCase(digest)) {
                if (!archive.delete()) {
                    Log.w(TAG, "could not delete outdated bootstrap cache");
                }
                throw new Exception("bootstrap archive outdated — retry");
            }
            prefs.edit().putString("archive_sha256", digest).apply();
            if (System.currentTimeMillis() > deadline) {
                throw new Exception("bootstrap timed out before extract");
            }
            phase = "extracting";
            progressPct = 92;
            TarGzExtractor.extract(archive, dataDir);
            boolean bundledIndex = hasSubstantialBlocksIndex(dataDir)
                || new File(dataDir, INCLUDES_INDEX_MARKER).isFile();
            if (!bundledIndex) {
                stripBlocksIndex(dataDir);
            } else {
                clearChainstateReindexMarker(dataDir);
                Log.i(TAG, "bootstrap includes blocks/index — skipping chainstate reindex");
            }
            verifyExtractedBlocks(dataDir);
            int height = readBootstrapHeight(dataDir);
            boolean bundledChainstate = hasValidChainstate(dataDir);
            File reindexMarker = new File(dataDir, ".bootstrap-reindex");
            if (bundledChainstate) {
                if (reindexMarker.isFile() && !reindexMarker.delete()) {
                    Log.w(TAG, "could not clear reindex marker after chainstate install");
                }
                if (!bundledIndex) {
                    markChainstateReindexRequired(dataDir);
                }
            } else if (!reindexMarker.isFile()) {
                try (FileOutputStream marker = new FileOutputStream(reindexMarker)) {
                    marker.write("1\n".getBytes(StandardCharsets.UTF_8));
                }
            }
            prefs.edit()
                .putInt(KEY_HEIGHT, height)
                .putBoolean(KEY_CORRUPT, false)
                .apply();
            phase = "complete";
            progressPct = 100;
            Log.i(
                TAG,
                "installed pre-downloaded chain at height "
                    + height
                    + (bundledChainstate ? " with chainstate" : " (reindex required)")
            );
            return true;
        } finally {
            inProgress = false;
            phase = "";
            progressPct = 0;
        }
    }

    static int installedBootstrapHeight(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getInt(KEY_HEIGHT, 0);
    }

    static int bootstrapHeightFromDatadir(File dataDir) {
        return readBootstrapHeight(dataDir);
    }

    static long datadirChainBytes(Context context, String nodeMode) {
        File dataDir = NodeModeUtil.datadir(context, nodeMode);
        return NodeStorageUtil.datadirBytes(context, dataDir.getName());
    }

    static void prepareForReindex(File dataDir) {
        deleteTree(new File(dataDir, "chainstate"));
        stripBlocksIndex(dataDir);
        clearChainstateReindexMarker(dataDir);
    }

    static void prepareForChainstateReindex(File dataDir) {
        stripBlocksIndex(dataDir);
    }

    static void stripBlocksIndex(File dataDir) {
        deleteTree(new File(dataDir, "blocks/index"));
    }

    static void markChainstateReindexRequired(File dataDir) {
        File marker = new File(dataDir, REINDEX_CHAINSTATE_MARKER);
        try (FileOutputStream out = new FileOutputStream(marker)) {
            out.write("1\n".getBytes(StandardCharsets.UTF_8));
        } catch (Exception exc) {
            Log.w(TAG, "could not write chainstate reindex marker: " + exc.getMessage());
        }
    }

    static void clearChainstateReindexMarker(File dataDir) {
        File marker = new File(dataDir, REINDEX_CHAINSTATE_MARKER);
        if (marker.isFile() && !marker.delete()) {
            Log.w(TAG, "could not clear chainstate reindex marker");
        }
    }

    static boolean looksLikeMerkleCorruption(String text) {
        if (text == null || text.isEmpty()) {
            return false;
        }
        String lower = text.toLowerCase(Locale.US);
        return lower.contains("bad-txnmrklroot")
            || lower.contains("hashmerkleroot mismatch")
            || lower.contains("hashmerkleroot");
    }

    static boolean hasValidChainstate(File dataDir) {
        File chainstate = new File(dataDir, "chainstate");
        if (!chainstate.isDirectory()) {
            return false;
        }
        String[] entries = chainstate.list();
        return entries != null && entries.length > 0;
    }

    static boolean hasSubstantialBlocksIndex(File dataDir) {
        File index = new File(dataDir, "blocks/index");
        return index.isDirectory() && directoryBytes(index) >= MIN_INDEX_BYTES;
    }

    static boolean needsChainstateReindex(File dataDir) {
        if (new File(dataDir, REINDEX_CHAINSTATE_MARKER).isFile()) {
            return true;
        }
        return hasValidChainstate(dataDir) && !hasSubstantialBlocksIndex(dataDir);
    }

    static boolean looksLikeBlockDatabaseError(String text) {
        if (text == null || text.isEmpty()) {
            return false;
        }
        String lower = text.toLowerCase(Locale.US);
        // Do not match intentional reindex-chainstate=1 startup — that is recovery, not failure.
        return lower.contains("error initializing block database")
            || lower.contains("failed to open block database")
            || lower.contains("block database corruption")
            || (lower.contains("flushstatetodisk")
                && lower.contains("0 coins")
                && lower.contains("shutdown: done"));
    }

    static void markBootstrapCorrupt(Context context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_CORRUPT, true)
            .apply();
    }

    static void invalidateInstalledChain(Context context, File dataDir) {
        deleteTree(new File(dataDir, "blocks"));
        deleteTree(new File(dataDir, "chainstate"));
        File reindex = new File(dataDir, ".bootstrap-reindex");
        if (reindex.isFile() && !reindex.delete()) {
            Log.w(TAG, "could not delete reindex marker");
        }
        clearChainstateReindexMarker(dataDir);
        File height = new File(dataDir, ".bootstrap-height");
        if (height.isFile() && !height.delete()) {
            Log.w(TAG, "could not delete bootstrap height marker");
        }
        File cacheDir = new File(context.getCacheDir(), "chain-bootstrap");
        File archive = new File(cacheDir, "bloodstone-chain-bootstrap.tar.gz");
        if (archive.isFile() && !archive.delete()) {
            Log.w(TAG, "could not delete cached bootstrap archive");
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .remove("archive_sha256")
            .remove(KEY_HEIGHT)
            .putBoolean(KEY_CORRUPT, true)
            .apply();
        Log.w(TAG, "invalidated corrupt bootstrap chain data");
    }

    private static String resolveExpectedSha256() {
        String remote = fetchRemoteSha256();
        if (remote != null && !remote.isEmpty()) {
            return remote;
        }
        return DEFAULT_SHA256 != null ? DEFAULT_SHA256 : "";
    }

    private static String fetchRemoteSha256() {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(SHA256_URL);
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(12000);
            conn.setReadTimeout(12000);
            conn.setInstanceFollowRedirects(true);
            if (conn.getResponseCode() < 200 || conn.getResponseCode() >= 300) {
                return "";
            }
            try (InputStream in = conn.getInputStream()) {
                byte[] buf = new byte[128];
                int read = in.read(buf);
                if (read <= 0) {
                    return "";
                }
                String line = new String(buf, 0, read, StandardCharsets.UTF_8).trim();
                int space = line.indexOf(' ');
                return (space > 0 ? line.substring(0, space) : line).trim().toLowerCase(Locale.US);
            }
        } catch (Exception exc) {
            Log.i(TAG, "remote bootstrap sha unavailable: " + exc.getMessage());
            return "";
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private static void verifyExtractedBlocks(File dataDir) throws Exception {
        File blocks = new File(dataDir, "blocks");
        if (!hasValidBlockFiles(blocks)) {
            throw new Exception("bootstrap extract produced no block files");
        }
        File[] blks = blocks.listFiles(
            (dir, name) -> name.startsWith("blk") && name.endsWith(".dat")
        );
        if (blks == null) {
            throw new Exception("bootstrap blocks unreadable");
        }
        for (File blk : blks) {
            if (blk.length() < EXPECTED_BLK_BYTES / 4L) {
                throw new Exception("bootstrap block file too small: " + blk.getName());
            }
        }
    }

    static void clearReindexMarker(File dataDir) {
        File marker = new File(dataDir, ".bootstrap-reindex");
        if (marker.isFile() && !marker.delete()) {
            Log.w(TAG, "could not clear bootstrap reindex marker");
        }
    }

    static boolean reindexPending(Context context, String nodeMode) {
        if (context == null || nodeMode == null) {
            return false;
        }
        File dataDir = NodeModeUtil.datadir(context, NodeModeUtil.normalize(nodeMode));
        return new File(dataDir, ".bootstrap-reindex").isFile();
    }

    private static long directoryBytes(File dir) {
        if (dir == null || !dir.exists()) {
            return 0L;
        }
        if (dir.isFile()) {
            return dir.length();
        }
        long total = 0L;
        File[] children = dir.listFiles();
        if (children == null) {
            return 0L;
        }
        for (File child : children) {
            total += directoryBytes(child);
        }
        return total;
    }

    private static void deleteTree(File dir) {
        if (dir == null || !dir.exists()) {
            return;
        }
        if (dir.isDirectory()) {
            File[] children = dir.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteTree(child);
                }
            }
        }
        if (!dir.delete()) {
            Log.w(TAG, "could not delete " + dir.getAbsolutePath());
        }
    }

    private static boolean dirEmpty(File dir) {
        if (dir == null || !dir.isDirectory()) {
            return true;
        }
        String[] entries = dir.list();
        return entries == null || entries.length == 0;
    }

    private static int readBootstrapHeight(File dataDir) {
        File marker = new File(dataDir, ".bootstrap-height");
        if (!marker.isFile()) {
            return 0;
        }
        try (InputStream in = new FileInputStream(marker)) {
            byte[] buf = new byte[32];
            int read = in.read(buf);
            if (read <= 0) {
                return 0;
            }
            String raw = new String(buf, 0, read).trim();
            return Integer.parseInt(raw.replaceAll("[^0-9]", ""));
        } catch (Exception exc) {
            Log.w(TAG, "bootstrap height marker unreadable: " + exc.getMessage());
            return 0;
        }
    }

    private static void download(String urlString, File dest, long deadlineMs) throws Exception {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(urlString);
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(20000);
            conn.setReadTimeout(45000);
            conn.setInstanceFollowRedirects(true);
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                throw new Exception("download HTTP " + code);
            }
            long total = conn.getContentLengthLong();
            try (InputStream in = conn.getInputStream();
                 FileOutputStream out = new FileOutputStream(dest)) {
                byte[] buf = new byte[16384];
                long done = 0L;
                int read;
                while ((read = in.read(buf)) >= 0) {
                    if (System.currentTimeMillis() > deadlineMs) {
                        throw new Exception("bootstrap download timed out");
                    }
                    out.write(buf, 0, read);
                    done += read;
                    if (total > 0L) {
                        progressPct = (int) Math.min(85L, (done * 85L) / total);
                    }
                }
            }
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buf = new byte[16384];
            int read;
            while ((read = in.read(buf)) >= 0) {
                digest.update(buf, 0, read);
            }
        }
        byte[] hash = digest.digest();
        StringBuilder sb = new StringBuilder(hash.length * 2);
        for (byte b : hash) {
            sb.append(String.format(Locale.US, "%02x", b));
        }
        return sb.toString();
    }
}