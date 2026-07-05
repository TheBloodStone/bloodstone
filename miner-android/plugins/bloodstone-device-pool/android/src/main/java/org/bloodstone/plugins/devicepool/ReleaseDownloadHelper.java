package org.bloodstone.plugins.devicepool;

import android.app.DownloadManager;
import android.content.Context;
import android.net.Uri;
import android.os.Environment;
import android.util.Log;
import android.webkit.MimeTypeMap;
import android.widget.Toast;

import java.util.Locale;

/**
 * Saves release artifacts (node tarballs, zips, scripts) to the public Downloads folder.
 */
public final class ReleaseDownloadHelper {
    private static final String TAG = "BloodstoneDownload";

    private static final String[] RELEASE_EXTENSIONS = {
        ".tar.gz",
        ".tgz",
        ".tar.xz",
        ".zip",
        ".apk",
        ".exe",
        ".deb",
        ".rpm",
        ".msi",
        ".dmg",
        ".7z",
        ".sha256",
        ".ps1",
        ".sh",
    };

    private ReleaseDownloadHelper() {
    }

    public static boolean isReleaseDownloadUrl(Uri uri) {
        if (uri == null) {
            return false;
        }
        String path = uri.getPath();
        if (path == null || path.isEmpty()) {
            return false;
        }
        String lower = path.toLowerCase(Locale.US);
        if (lower.contains(".apk/")) {
            return true;
        }
        for (String ext : RELEASE_EXTENSIONS) {
            if (lower.endsWith(ext)) {
                return true;
            }
        }
        return false;
    }

    public static boolean isReleaseDownloadUrl(String url) {
        if (url == null || url.trim().isEmpty()) {
            return false;
        }
        try {
            return isReleaseDownloadUrl(Uri.parse(url.trim()));
        } catch (Exception exc) {
            return false;
        }
    }

    public static long enqueuePublicDownload(Context context, String url) throws Exception {
        Uri uri = Uri.parse(url.trim());
        String fileName = fileNameFromUri(uri);
        DownloadManager dm = (DownloadManager) context.getSystemService(Context.DOWNLOAD_SERVICE);
        if (dm == null) {
            throw new IllegalStateException("DownloadManager unavailable");
        }
        DownloadManager.Request request = new DownloadManager.Request(uri);
        request.setTitle(fileName);
        request.setDescription("Bloodstone release download");
        request.setNotificationVisibility(
            DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
        );
        request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
        request.setAllowedOverMetered(true);
        request.setAllowedOverRoaming(false);
        String mime = guessMimeType(fileName);
        if (mime != null) {
            request.setMimeType(mime);
        }
        long id = dm.enqueue(request);
        Log.i(TAG, "enqueued download id=" + id + " file=" + fileName);
        return id;
    }

    public static void toastDownloadStarted(Context context, String url) {
        String name = fileNameFromUri(Uri.parse(url.trim()));
        Toast.makeText(
            context,
            "Downloading " + name + " — check Notifications / Downloads",
            Toast.LENGTH_LONG
        ).show();
    }

    private static String fileNameFromUri(Uri uri) {
        String path = uri.getPath();
        if (path == null || path.isEmpty()) {
            return "bloodstone-download";
        }
        int slash = path.lastIndexOf('/');
        String name = slash >= 0 ? path.substring(slash + 1) : path;
        if (name.isEmpty()) {
            return "bloodstone-download";
        }
        return name;
    }

    private static String guessMimeType(String fileName) {
        String lower = fileName.toLowerCase(Locale.US);
        if (lower.endsWith(".apk")) {
            return "application/vnd.android.package-archive";
        }
        if (lower.endsWith(".tar.gz") || lower.endsWith(".tgz")) {
            return "application/gzip";
        }
        if (lower.endsWith(".zip")) {
            return "application/zip";
        }
        if (lower.endsWith(".sha256")) {
            return "text/plain";
        }
        String ext = MimeTypeMap.getFileExtensionFromUrl(fileName);
        if (ext != null && !ext.isEmpty()) {
            String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
            if (mime != null) {
                return mime;
            }
        }
        return "application/octet-stream";
    }
}