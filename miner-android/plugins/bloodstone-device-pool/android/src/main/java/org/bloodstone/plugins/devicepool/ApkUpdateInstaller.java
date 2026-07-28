package org.bloodstone.plugins.devicepool;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
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
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public final class ApkUpdateInstaller {
    private static final String TAG = "BloodstoneApkUpdate";
    private static final String APK_FILE_NAME = "bloodstone-miner-update.apk";

    /** Hosts allowed for OTA APK downloads (WebView + native). */
    private static final Set<String> ALLOWED_APK_HOSTS = new HashSet<>(Arrays.asList(
        "bloodstone.rocks",
        "www.bloodstone.rocks",
        "bloodstonewallet.mytunnel.org",
        "64.188.22.190"
    ));

    private ApkUpdateInstaller() {
    }

    public static boolean isAllowedApkHost(String host) {
        if (host == null || host.trim().isEmpty()) {
            return false;
        }
        String h = host.trim().toLowerCase(Locale.US);
        if (ALLOWED_APK_HOSTS.contains(h)) {
            return true;
        }
        // Allow mytunnel.org / bloodstone.rocks subdomains only
        return h.endsWith(".bloodstone.rocks") || h.endsWith(".mytunnel.org");
    }

    public static boolean isAllowedApkUrl(String apkUrl) {
        try {
            URL url = new URL(apkUrl);
            String scheme = url.getProtocol() != null ? url.getProtocol().toLowerCase(Locale.US) : "";
            if (!"https".equals(scheme) && !"http".equals(scheme)) {
                return false;
            }
            // Prefer HTTPS for public hosts; allow http only to operator IP
            String host = url.getHost() != null ? url.getHost().toLowerCase(Locale.US) : "";
            if ("http".equals(scheme) && !"64.188.22.190".equals(host) && !host.startsWith("192.168.")
                && !host.startsWith("10.") && !host.equals("127.0.0.1")) {
                return false;
            }
            return isAllowedApkHost(host);
        } catch (Exception exc) {
            return false;
        }
    }

    /** SHA-256 hex digests of signing certs for the installed app package. */
    static Set<String> installedSigningCertDigests(Context context) throws Exception {
        PackageManager pm = context.getPackageManager();
        PackageInfo info;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            info = pm.getPackageInfo(
                context.getPackageName(),
                PackageManager.GET_SIGNING_CERTIFICATES
            );
        } else {
            info = pm.getPackageInfo(context.getPackageName(), PackageManager.GET_SIGNATURES);
        }
        return certDigestsFromPackageInfo(info);
    }

    static Set<String> certDigestsFromPackageInfo(PackageInfo info) throws Exception {
        Set<String> out = new HashSet<>();
        if (info == null) {
            return out;
        }
        Signature[] sigs = null;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            SigningInfo si = info.signingInfo;
            if (si != null) {
                sigs = si.hasMultipleSigners()
                    ? si.getApkContentsSigners()
                    : si.getSigningCertificateHistory();
            }
        }
        if (sigs == null) {
            //noinspection deprecation
            sigs = info.signatures;
        }
        if (sigs == null) {
            return out;
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        for (Signature sig : sigs) {
            if (sig == null) {
                continue;
            }
            byte[] hash = digest.digest(sig.toByteArray());
            digest.reset();
            StringBuilder hex = new StringBuilder(hash.length * 2);
            for (byte value : hash) {
                hex.append(String.format("%02x", value));
            }
            out.add(hex.toString());
        }
        return out;
    }

    /**
     * Verify APK is signed with the same certificate(s) as the currently installed app.
     * Rejects re-signed or third-party APKs (authenticity, not just integrity).
     */
    public static void verifyApkSignerMatchesInstalled(Context context, File apkFile) throws Exception {
        if (apkFile == null || !apkFile.exists()) {
            throw new IllegalStateException("APK file missing");
        }
        PackageManager pm = context.getPackageManager();
        PackageInfo apkInfo;
        String path = apkFile.getAbsolutePath();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            apkInfo = pm.getPackageArchiveInfo(
                path,
                PackageManager.PackageInfoFlags.of(PackageManager.GET_SIGNING_CERTIFICATES)
            );
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            apkInfo = pm.getPackageArchiveInfo(path, PackageManager.GET_SIGNING_CERTIFICATES);
        } else {
            //noinspection deprecation
            apkInfo = pm.getPackageArchiveInfo(path, PackageManager.GET_SIGNATURES);
        }
        if (apkInfo == null) {
            throw new IllegalStateException("Could not parse APK package info");
        }
        // Require same package name as this app (prevents sideload of unrelated APKs)
        String expectedPkg = context.getPackageName();
        if (apkInfo.packageName != null && !expectedPkg.equals(apkInfo.packageName)) {
            throw new IllegalStateException(
                "APK package mismatch: " + apkInfo.packageName + " != " + expectedPkg
            );
        }
        Set<String> installed = installedSigningCertDigests(context);
        Set<String> candidate = certDigestsFromPackageInfo(apkInfo);
        if (installed.isEmpty() || candidate.isEmpty()) {
            throw new IllegalStateException("APK signing certificate unavailable");
        }
        boolean match = false;
        for (String dig : candidate) {
            if (installed.contains(dig)) {
                match = true;
                break;
            }
        }
        if (!match) {
            throw new IllegalStateException("APK signing certificate does not match installed app");
        }
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
        if (!isAllowedApkUrl(apkUrl)) {
            throw new IllegalStateException("APK URL host not allowlisted");
        }
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
            // Do not follow redirects off allowlisted hosts
            connection.setInstanceFollowRedirects(false);
            connection.connect();
            int code = connection.getResponseCode();
            if (code >= 300 && code < 400) {
                String loc = connection.getHeaderField("Location");
                if (loc == null || !isAllowedApkUrl(loc)) {
                    throw new IllegalStateException("APK redirect to non-allowlisted host");
                }
                connection.disconnect();
                return downloadApk(context, loc);
            }
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
                long total = 0;
                final long maxBytes = 200L * 1024L * 1024L; // 200 MiB cap
                while ((read = input.read(buffer)) != -1) {
                    total += read;
                    if (total > maxBytes) {
                        throw new IllegalStateException("APK exceeds size limit");
                    }
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
        verifyApkSignerMatchesInstalled(context, outFile);
        return outFile;
    }

    static File writeApkFromBase64(Context context, String dataB64, String expectedSha256) throws Exception {
        if (dataB64 == null || dataB64.trim().isEmpty()) {
            throw new IllegalArgumentException("data_b64 is required");
        }
        if (expectedSha256 == null || expectedSha256.trim().isEmpty()) {
            throw new IllegalArgumentException("expected SHA-256 is required for APK install");
        }
        byte[] apkBytes = Base64.decode(dataB64.trim(), Base64.DEFAULT);
        if (apkBytes.length < 1024) {
            throw new IllegalStateException("APK payload is empty");
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(apkBytes);
        StringBuilder hex = new StringBuilder(hash.length * 2);
        for (byte value : hash) {
            hex.append(String.format("%02x", value));
        }
        String actual = hex.toString();
        String expected = expectedSha256.trim().toLowerCase(Locale.US);
        if (!actual.equals(expected)) {
            throw new IllegalStateException("APK sha256 mismatch");
        }
        File outFile = new File(context.getCacheDir(), APK_FILE_NAME);
        if (outFile.exists() && !outFile.delete()) {
            Log.w(TAG, "could not delete previous mesh update apk");
        }
        try (FileOutputStream output = new FileOutputStream(outFile)) {
            output.write(apkBytes);
            output.flush();
        }
        verifyApkSignerMatchesInstalled(context, outFile);
        return outFile;
    }

    public static void promptInstall(Context context, File apkFile) {
        try {
            verifyApkSignerMatchesInstalled(context, apkFile);
        } catch (Exception exc) {
            Log.e(TAG, "refusing APK install: " + exc.getMessage());
            throw new IllegalStateException("APK signature verification failed: " + exc.getMessage(), exc);
        }
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