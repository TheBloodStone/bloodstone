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
    /** Off by default — phones sync ~9k blocks from P2P faster than snapshot+reindex. */
    private static final boolean BOOTSTRAP_ENABLED = false;
    private static final String PREFS = "bloodstone_chain_bootstrap";
    private static final String KEY_HEIGHT = "installed_height";
    private static final String DEFAULT_URL =
        "https://bloodstonewallet.mytunnel.org/downloads/bloodstone-chain-bootstrap-latest.tar.gz";
    private static final String DEFAULT_SHA256 =
        "a4c0fc7a866635d496a92b99af0fab3d192231ac82eafcc36ff7ceb4f4d397ca";
    private static final long DOWNLOAD_TIMEOUT_MS = 45_000L;
    private static final long EXTRACT_TIMEOUT_MS = 90_000L;

    static volatile boolean inProgress = false;
    static volatile String phase = "";
    static volatile int progressPct = 0;

    private ChainBootstrapInstaller() {
    }

    static boolean isInProgress() {
        return inProgress;
    }

    static boolean supportsMode(String mode) {
        return "full".equals(NodeModeUtil.normalize(mode));
    }

    static boolean needsBootstrap(File dataDir) {
        return dirEmpty(new File(dataDir, "blocks"));
    }

    static boolean ensureBootstrap(Context context, File dataDir, String nodeMode) throws Exception {
        if (!BOOTSTRAP_ENABLED || !supportsMode(nodeMode) || !needsBootstrap(dataDir)) {
            return false;
        }
        if (!dataDir.exists() && !dataDir.mkdirs()) {
            throw new Exception("cannot create datadir");
        }
        // Drop any partial/corrupt chainstate from a failed prior start.
        deleteTree(new File(dataDir, "chainstate"));
        inProgress = true;
        progressPct = 0;
        phase = "downloading";
        File cacheDir = new File(context.getCacheDir(), "chain-bootstrap");
        if (!cacheDir.exists() && !cacheDir.mkdirs()) {
            throw new Exception("cannot create bootstrap cache");
        }
        File archive = new File(cacheDir, "bloodstone-chain-bootstrap.tar.gz");
        long deadline = System.currentTimeMillis() + DOWNLOAD_TIMEOUT_MS + EXTRACT_TIMEOUT_MS;
        try {
            if (!archive.isFile() || archive.length() < 1024L) {
                download(DEFAULT_URL, archive, deadline);
            } else {
                progressPct = 70;
            }
            phase = "verifying";
            progressPct = 88;
            String digest = sha256(archive);
            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String cachedDigest = prefs.getString("archive_sha256", "");
            if (!DEFAULT_SHA256.isEmpty() && !digest.equalsIgnoreCase(DEFAULT_SHA256)) {
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
            int height = readBootstrapHeight(dataDir);
            if (!new File(dataDir, ".bootstrap-reindex").isFile()) {
                try (FileOutputStream marker = new FileOutputStream(
                    new File(dataDir, ".bootstrap-reindex"))) {
                    marker.write("1\n".getBytes(StandardCharsets.UTF_8));
                }
            }
            prefs.edit().putInt(KEY_HEIGHT, height).apply();
            phase = "complete";
            progressPct = 100;
            Log.i(TAG, "installed pre-downloaded chain at height " + height);
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

    static void prepareForReindex(File dataDir) {
        deleteTree(new File(dataDir, "chainstate"));
    }

    static void clearReindexMarker(File dataDir) {
        File marker = new File(dataDir, ".bootstrap-reindex");
        if (marker.isFile() && !marker.delete()) {
            Log.w(TAG, "could not clear bootstrap reindex marker");
        }
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
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(15000);
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