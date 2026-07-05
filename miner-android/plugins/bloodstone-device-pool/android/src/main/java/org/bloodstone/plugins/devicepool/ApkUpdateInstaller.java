package org.bloodstone.plugins.devicepool;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

import androidx.core.content.FileProvider;

import android.util.Base64;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

public final class ApkUpdateInstaller {
    private static final String TAG = "BloodstoneApkUpdate";
    private static final String APK_FILE_NAME = "bloodstone-miner-update.apk";

    private ApkUpdateInstaller() {
    }

    public static boolean canInstallPackages(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return true;
        }
        return context.getPackageManager().canRequestPackageInstalls();
    }

    public static void openInstallPermissionSettings(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES);
        intent.setData(Uri.parse("package:" + context.getPackageName()));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);
    }

    static PackageInfo packageInfo(Context context) throws PackageManager.NameNotFoundException {
        PackageManager pm = context.getPackageManager();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return pm.getPackageInfo(
                context.getPackageName(),
                PackageManager.PackageInfoFlags.of(0)
            );
        }
        return pm.getPackageInfo(context.getPackageName(), 0);
    }

    public static File downloadApk(Context context, String apkUrl) throws Exception {
        HttpURLConnection connection = null;
        File outFile = new File(context.getCacheDir(), APK_FILE_NAME);
        if (outFile.exists() && !outFile.delete()) {
            Log.w(TAG, "could not delete previous update apk");
        }
        try {
            URL url = new URL(apkUrl);
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
                FileOutputStream output = new FileOutputStream(outFile)
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
        if (!outFile.exists() || outFile.length() < 1024) {
            throw new IllegalStateException("Downloaded APK is empty");
        }
        return outFile;
    }

    static File writeApkFromBase64(Context context, String dataB64, String expectedSha256) throws Exception {
        if (dataB64 == null || dataB64.trim().isEmpty()) {
            throw new IllegalArgumentException("data_b64 is required");
        }
        byte[] apkBytes = Base64.decode(dataB64.trim(), Base64.DEFAULT);
        if (apkBytes.length < 1024) {
            throw new IllegalStateException("APK payload is empty");
        }
        if (expectedSha256 != null && !expectedSha256.trim().isEmpty()) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(apkBytes);
            StringBuilder hex = new StringBuilder(hash.length * 2);
            for (byte value : hash) {
                hex.append(String.format("%02x", value));
            }
            String actual = hex.toString();
            String expected = expectedSha256.trim().toLowerCase();
            if (!actual.equals(expected)) {
                throw new IllegalStateException("APK sha256 mismatch");
            }
        }
        File outFile = new File(context.getCacheDir(), APK_FILE_NAME);
        if (outFile.exists() && !outFile.delete()) {
            Log.w(TAG, "could not delete previous mesh update apk");
        }
        try (FileOutputStream output = new FileOutputStream(outFile)) {
            output.write(apkBytes);
            output.flush();
        }
        return outFile;
    }

    public static void promptInstall(Context context, File apkFile) {
        Uri uri = FileProvider.getUriForFile(
            context,
            context.getPackageName() + ".fileprovider",
            apkFile
        );
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        if (context instanceof Activity) {
            context.startActivity(intent);
        } else {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        }
    }
}