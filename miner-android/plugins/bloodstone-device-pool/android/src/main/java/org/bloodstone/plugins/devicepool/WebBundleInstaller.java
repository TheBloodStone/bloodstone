package org.bloodstone.plugins.devicepool;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import com.getcapacitor.plugin.WebView;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

final class WebBundleInstaller {
    private static final String TAG = "BloodstoneWebBundle";
    private static final String PREFS_NAME = "BloodstoneWebBundle";
    private static final String KEY_VERSION = "version";
    private static final String KEY_PATH = "path";
    private static final String BUNDLE_DIR = "cap-web-bundle";

    private WebBundleInstaller() {
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS_NAME, Activity.MODE_PRIVATE);
    }

    static String installedVersion(Context context) {
        return prefs(context).getString(KEY_VERSION, "");
    }

    static String installedPath(Context context) {
        String path = prefs(context).getString(KEY_PATH, "");
        if (path == null || path.trim().isEmpty()) {
            return "";
        }
        File dir = new File(path);
        return dir.exists() && new File(dir, "offline-mine.html").exists() ? path : "";
    }

    static File bundleRoot(Context context) {
        return new File(context.getFilesDir(), BUNDLE_DIR);
    }

    static File downloadZip(Context context, String bundleUrl) throws Exception {
        HttpURLConnection connection = null;
        File cacheZip = new File(context.getCacheDir(), "bloodstone-web-bundle.zip");
        if (cacheZip.exists() && !cacheZip.delete()) {
            Log.w(TAG, "could not delete previous web bundle zip");
        }
        try {
            URL url = new URL(bundleUrl);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(20000);
            connection.setReadTimeout(120000);
            connection.setInstanceFollowRedirects(true);
            connection.connect();
            int code = connection.getResponseCode();
            if (code < 200 || code >= 300) {
                throw new IllegalStateException("Download failed HTTP " + code);
            }
            try (
                InputStream raw = connection.getInputStream();
                BufferedInputStream input = new BufferedInputStream(raw);
                FileOutputStream output = new FileOutputStream(cacheZip)
            ) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    output.write(buffer, 0, read);
                }
                output.flush();
            }
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
        if (!cacheZip.exists() || cacheZip.length() < 256) {
            throw new IllegalStateException("Downloaded web bundle is empty");
        }
        return cacheZip;
    }

    static void verifySha256(File file, String expectedSha256) throws Exception {
        if (expectedSha256 == null || expectedSha256.trim().isEmpty()) {
            return;
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        byte[] hash = digest.digest();
        StringBuilder hex = new StringBuilder(hash.length * 2);
        for (byte value : hash) {
            hex.append(String.format("%02x", value));
        }
        String actual = hex.toString();
        String expected = expectedSha256.trim().toLowerCase();
        if (!actual.equals(expected)) {
            throw new IllegalStateException("Web bundle sha256 mismatch");
        }
    }

    static File extractBundle(Context context, File zipFile, String version) throws Exception {
        String safeVersion = version == null ? "unknown" : version.replaceAll("[^a-zA-Z0-9._-]", "_");
        File targetDir = new File(bundleRoot(context), safeVersion);
        if (targetDir.exists()) {
            deleteRecursive(targetDir);
        }
        if (!targetDir.mkdirs()) {
            throw new IllegalStateException("Could not create bundle directory");
        }

        try (
            FileInputStream raw = new FileInputStream(zipFile);
            ZipInputStream zip = new ZipInputStream(new BufferedInputStream(raw))
        ) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                String name = entry.getName();
                if (name == null || name.contains("..")) {
                    zip.closeEntry();
                    continue;
                }
                File out = new File(targetDir, name);
                if (entry.isDirectory()) {
                    if (!out.mkdirs()) {
                        throw new IllegalStateException("Could not create directory " + name);
                    }
                } else {
                    File parent = out.getParentFile();
                    if (parent != null && !parent.exists() && !parent.mkdirs()) {
                        throw new IllegalStateException("Could not create parent for " + name);
                    }
                    try (FileOutputStream output = new FileOutputStream(out)) {
                        byte[] buffer = new byte[8192];
                        int read;
                        while ((read = zip.read(buffer)) != -1) {
                            output.write(buffer, 0, read);
                        }
                        output.flush();
                    }
                }
                zip.closeEntry();
            }
        }

        if (!new File(targetDir, "offline-mine.html").exists()) {
            deleteRecursive(targetDir);
            throw new IllegalStateException("Bundle missing offline-mine.html");
        }
        return targetDir;
    }

    static void persistActiveBundle(Context context, String version, File bundleDir) {
        SharedPreferences.Editor editor = prefs(context).edit();
        editor.putString(KEY_VERSION, version != null ? version : "");
        editor.putString(KEY_PATH, bundleDir.getAbsolutePath());
        editor.apply();

        SharedPreferences webPrefs = context.getSharedPreferences(
            WebView.WEBVIEW_PREFS_NAME,
            Activity.MODE_PRIVATE
        );
        webPrefs.edit().putString(WebView.CAP_SERVER_PATH, bundleDir.getAbsolutePath()).apply();
    }

    static void pruneOldBundles(Context context, File keepDir) {
        File root = bundleRoot(context);
        File[] children = root.listFiles();
        if (children == null) {
            return;
        }
        String keepPath = keepDir.getAbsolutePath();
        for (File child : children) {
            if (child.isDirectory() && !keepPath.equals(child.getAbsolutePath())) {
                deleteRecursive(child);
            }
        }
    }

    static void deleteRecursive(File file) {
        if (file == null || !file.exists()) {
            return;
        }
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteRecursive(child);
                }
            }
        }
        if (!file.delete()) {
            Log.w(TAG, "could not delete " + file.getAbsolutePath());
        }
    }
}