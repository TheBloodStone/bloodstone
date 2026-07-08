package org.bloodstone.plugins.devicepool;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;

import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@CapacitorPlugin(name = "BloodstoneDevicePool")
public class DevicePoolPlugin extends Plugin {
    private static final String TAG = "BloodstoneDevicePool";
    private static final String FLEET_ROLE = "decentralized-vps-node";
    private BroadcastReceiver batteryReceiver;
    private Intent lastBatteryIntent;
    private final ExecutorService updateExecutor = Executors.newSingleThreadExecutor();

    @PluginMethod
    public void getIdentity(PluginCall call) {
        String androidId = Settings.Secure.getString(
            getContext().getContentResolver(),
            Settings.Secure.ANDROID_ID
        );
        String deviceId = hashDeviceId(androidId);
        JSObject ret = new JSObject();
        ret.put("deviceId", deviceId);
        ret.put("model", Build.MODEL != null ? Build.MODEL : "Android");
        ret.put("manufacturer", Build.MANUFACTURER != null ? Build.MANUFACTURER : "");
        ret.put("platform", "android");
        ret.put("role", FLEET_ROLE);
        call.resolve(ret);
    }

    @PluginMethod
    public void startFleetNode(PluginCall call) {
        String address = call.getString("address", "");
        String algo = call.getString("algo", "");

        Intent intent = new Intent(getContext(), MiningForegroundService.class);
        intent.putExtra("address", address);
        intent.putExtra("algo", algo);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                getContext().startForegroundService(intent);
            } else {
                getContext().startService(intent);
            }
            JSObject ret = new JSObject();
            ret.put("running", true);
            ret.put("role", FLEET_ROLE);
            call.resolve(ret);
        } catch (Exception exc) {
            Log.w(TAG, "startFleetNode failed: " + exc.getMessage());
            call.reject("startFleetNode failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void stopFleetNode(PluginCall call) {
        try {
            MiningForegroundService.stop(getContext());
            call.resolve();
        } catch (Exception exc) {
            call.reject("stopFleetNode failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void getFleetStatus(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("running", MiningForegroundService.isRunning());
        ret.put("role", FLEET_ROLE);
        call.resolve(ret);
    }

    @Override
    public void load() {
        super.load();
        Intent sticky = stickyBatteryIntent();
        if (sticky != null) {
            lastBatteryIntent = sticky;
        }
        registerBatteryListener();
    }

    @Override
    protected void handleOnDestroy() {
        unregisterBatteryListener();
        updateExecutor.shutdownNow();
        super.handleOnDestroy();
    }

    @PluginMethod
    public void getAppVersion(PluginCall call) {
        try {
            PackageInfo info = ApkUpdateInstaller.packageInfo(getContext());
            JSObject ret = new JSObject();
            ret.put("versionName", info.versionName != null ? info.versionName : "0");
            ret.put("versionCode", info.versionCode);
            ret.put("packageName", info.packageName);
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("getAppVersion failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void canInstallApkUpdates(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("allowed", ApkUpdateInstaller.canInstallPackages(getContext()));
        call.resolve(ret);
    }

    @PluginMethod
    public void requestInstallApkPermission(PluginCall call) {
        try {
            ApkUpdateInstaller.openInstallPermissionSettings(getContext());
            JSObject ret = new JSObject();
            ret.put("requested", true);
            ret.put("allowed", ApkUpdateInstaller.canInstallPackages(getContext()));
            call.resolve(ret);
        } catch (Exception exc) {
            call.reject("requestInstallApkPermission failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void installApkFromBase64(PluginCall call) {
        String dataB64 = call.getString("data_b64", "");
        if (dataB64 == null || dataB64.trim().isEmpty()) {
            call.reject("data_b64 is required");
            return;
        }
        if (!ApkUpdateInstaller.canInstallPackages(getContext())) {
            call.reject("Install unknown apps permission required");
            return;
        }
        String expectedSha256 = call.getString("sha256", "");
        updateExecutor.execute(() -> {
            try {
                File apkFile = ApkUpdateInstaller.writeApkFromBase64(
                    getContext(),
                    dataB64,
                    expectedSha256
                );
                getActivity().runOnUiThread(() -> {
                    try {
                        ApkUpdateInstaller.promptInstall(getActivity(), apkFile);
                        JSObject ret = new JSObject();
                        ret.put("installedPrompt", true);
                        ret.put("bytes", apkFile.length());
                        ret.put("source", "mesh");
                        call.resolve(ret);
                    } catch (Exception exc) {
                        call.reject("install prompt failed: " + exc.getMessage());
                    }
                });
            } catch (Exception exc) {
                call.reject("mesh install failed: " + exc.getMessage());
            }
        });
    }

    @PluginMethod
    public void getWebBundleInfo(PluginCall call) {
        JSObject ret = new JSObject();
        String version = WebBundleInstaller.installedVersion(getContext());
        String path = WebBundleInstaller.installedPath(getContext());
        ret.put("version", version != null ? version : "");
        ret.put("path", path != null ? path : "");
        ret.put("active", path != null && !path.isEmpty());
        call.resolve(ret);
    }

    @PluginMethod
    public void downloadAndApplyWebBundle(PluginCall call) {
        String bundleUrl = call.getString("url", "");
        String version = call.getString("version", "");
        String sha256 = call.getString("sha256", "");
        if (bundleUrl == null || bundleUrl.trim().isEmpty()) {
            call.reject("url is required");
            return;
        }
        if (version == null || version.trim().isEmpty()) {
            call.reject("version is required");
            return;
        }
        String url = bundleUrl.trim();
        String bundleVersion = version.trim();
        updateExecutor.execute(() -> {
            try {
                File zipFile = WebBundleInstaller.downloadZip(getContext(), url);
                WebBundleInstaller.verifySha256(zipFile, sha256);
                File bundleDir = WebBundleInstaller.extractBundle(getContext(), zipFile, bundleVersion);
                WebBundleInstaller.persistActiveBundle(getContext(), bundleVersion, bundleDir);
                WebBundleInstaller.pruneOldBundles(getContext(), bundleDir);
                if (!zipFile.delete()) {
                    Log.w(TAG, "could not delete web bundle zip cache");
                }
                getActivity().runOnUiThread(() -> {
                    try {
                        getBridge().setServerBasePath(bundleDir.getAbsolutePath());
                        JSObject ret = new JSObject();
                        ret.put("version", bundleVersion);
                        ret.put("path", bundleDir.getAbsolutePath());
                        ret.put("bytes", bundleDir.length());
                        call.resolve(ret);
                    } catch (Exception exc) {
                        call.reject("apply web bundle failed: " + exc.getMessage());
                    }
                });
            } catch (Exception exc) {
                call.reject("web bundle download failed: " + exc.getMessage());
            }
        });
    }

    @PluginMethod
    public void reloadApp(PluginCall call) {
        try {
            getBridge().reload();
            call.resolve();
        } catch (Exception exc) {
            call.reject("reload failed: " + exc.getMessage());
        }
    }

    @PluginMethod
    public void downloadReleaseFile(PluginCall call) {
        String fileUrl = call.getString("url", "");
        if (fileUrl == null || fileUrl.trim().isEmpty()) {
            call.reject("url is required");
            return;
        }
        String url = fileUrl.trim();
        if (!ReleaseDownloadHelper.isReleaseDownloadUrl(url)) {
            call.reject("unsupported download URL");
            return;
        }
        if (url.toLowerCase(java.util.Locale.US).contains(".apk")) {
            downloadAndInstallApk(call);
            return;
        }
        updateExecutor.execute(() -> {
            try {
                long downloadId = ReleaseDownloadHelper.enqueuePublicDownload(getContext(), url);
                getActivity().runOnUiThread(() -> {
                    ReleaseDownloadHelper.toastDownloadStarted(getContext(), url);
                    JSObject ret = new JSObject();
                    ret.put("downloadId", downloadId);
                    ret.put("queued", true);
                    call.resolve(ret);
                });
            } catch (Exception exc) {
                call.reject("download failed: " + exc.getMessage());
            }
        });
    }

    @PluginMethod
    public void downloadAndInstallApk(PluginCall call) {
        String apkUrl = call.getString("url", "");
        if (apkUrl == null || apkUrl.trim().isEmpty()) {
            call.reject("url is required");
            return;
        }
        if (!ApkUpdateInstaller.canInstallPackages(getContext())) {
            call.reject("Install unknown apps permission required");
            return;
        }
        String url = apkUrl.trim();
        updateExecutor.execute(() -> {
            try {
                File apkFile = ApkUpdateInstaller.downloadApk(getContext(), url);
                getActivity().runOnUiThread(() -> {
                    try {
                        ApkUpdateInstaller.promptInstall(getActivity(), apkFile);
                        JSObject ret = new JSObject();
                        ret.put("installedPrompt", true);
                        ret.put("bytes", apkFile.length());
                        call.resolve(ret);
                    } catch (Exception exc) {
                        call.reject("install prompt failed: " + exc.getMessage());
                    }
                });
            } catch (Exception exc) {
                call.reject("download failed: " + exc.getMessage());
            }
        });
    }

    @PluginMethod
    public void getSavedPayoutAddress(PluginCall call) {
        MinerPreferences prefs = new MinerPreferences(getContext());
        JSObject ret = new JSObject();
        ret.put("address", prefs.getStonePayoutAddress());
        call.resolve(ret);
    }

    @PluginMethod
    public void setSavedPayoutAddress(PluginCall call) {
        String address = call.getString("address", "");
        new MinerPreferences(getContext()).setStonePayoutAddress(address);
        JSObject ret = new JSObject();
        ret.put("saved", address != null && !address.trim().isEmpty());
        call.resolve(ret);
    }

    @PluginMethod
    public void getPowerStatus(PluginCall call) {
        call.resolve(readPowerStatus());
    }

    @PluginMethod
    public void isBatteryExempt(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("exempt", isIgnoringBatteryOptimizations());
        call.resolve(ret);
    }

    @PluginMethod
    public void requestBatteryExemption(PluginCall call) {
        if (isIgnoringBatteryOptimizations()) {
            JSObject ret = new JSObject();
            ret.put("exempt", true);
            ret.put("requested", false);
            call.resolve(ret);
            return;
        }
        try {
            Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            intent.setData(Uri.parse("package:" + getContext().getPackageName()));
            getActivity().startActivity(intent);
            JSObject ret = new JSObject();
            ret.put("exempt", false);
            ret.put("requested", true);
            call.resolve(ret);
        } catch (Exception exc) {
            Log.w(TAG, "requestBatteryExemption failed: " + exc.getMessage());
            call.reject("requestBatteryExemption failed: " + exc.getMessage());
        }
    }

    private boolean isIgnoringBatteryOptimizations() {
        PowerManager powerManager = (PowerManager) getContext().getSystemService(Context.POWER_SERVICE);
        if (powerManager == null) {
            return false;
        }
        return powerManager.isIgnoringBatteryOptimizations(getContext().getPackageName());
    }

    private void registerBatteryListener() {
        if (batteryReceiver != null) {
            return;
        }
        batteryReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (intent != null) {
                    lastBatteryIntent = intent;
                }
                notifyListeners("powerStateChanged", readPowerStatus(intent));
            }
        };
        IntentFilter filter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getContext().registerReceiver(batteryReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            getContext().registerReceiver(batteryReceiver, filter);
        }
    }

    private void unregisterBatteryListener() {
        if (batteryReceiver == null) {
            return;
        }
        try {
            getContext().unregisterReceiver(batteryReceiver);
        } catch (Exception exc) {
            Log.w(TAG, "unregister battery listener failed: " + exc.getMessage());
        }
        batteryReceiver = null;
    }

    private Intent stickyBatteryIntent() {
        IntentFilter filter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                return getContext().registerReceiver(
                    null,
                    filter,
                    Context.RECEIVER_NOT_EXPORTED
                );
            }
            return getContext().registerReceiver(null, filter);
        } catch (Exception exc) {
            Log.w(TAG, "sticky battery intent failed: " + exc.getMessage());
            return null;
        }
    }

    private JSObject readPowerStatus() {
        Intent intent = stickyBatteryIntent();
        if (intent == null) {
            intent = lastBatteryIntent;
        }
        if (intent != null) {
            return readPowerStatus(intent);
        }
        return readPowerStatusFromBatteryManager();
    }

    private JSObject readPowerStatus(Intent intent) {
        int status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
        int plugged = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0);
        int level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
        int scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100);
        int levelPercent = scale > 0 ? Math.round((level * 100f) / scale) : 0;
        int tempTenths = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1);
        return buildPowerStatus(status, plugged, levelPercent, "sticky", tempTenths);
    }

    private JSObject readPowerStatusFromBatteryManager() {
        BatteryManager batteryManager = (BatteryManager) getContext().getSystemService(Context.BATTERY_SERVICE);
        if (batteryManager == null) {
            return buildPowerStatus(-1, 0, 0, "unavailable", -1);
        }

        int status = batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_STATUS);
        int levelPercent = batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
        if (levelPercent < 0 || levelPercent > 100) {
            levelPercent = 0;
        }

        int plugged = 0;
        boolean charging = false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            charging = batteryManager.isCharging();
        }
        if (!charging) {
            charging = status == BatteryManager.BATTERY_STATUS_CHARGING
                || status == BatteryManager.BATTERY_STATUS_FULL;
        }
        if (charging) {
            plugged = BatteryManager.BATTERY_PLUGGED_USB;
        } else if (status == BatteryManager.BATTERY_STATUS_FULL) {
            plugged = BatteryManager.BATTERY_PLUGGED_AC;
        }

        return buildPowerStatus(status, plugged, levelPercent, "battery-manager", -1);
    }

    private JSObject buildPowerStatus(
        int status,
        int plugged,
        int levelPercent,
        String source,
        int tempTenths
    ) {
        JSObject ret = new JSObject();

        boolean charging = status == BatteryManager.BATTERY_STATUS_CHARGING
            || status == BatteryManager.BATTERY_STATUS_FULL;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            BatteryManager batteryManager = (BatteryManager) getContext().getSystemService(Context.BATTERY_SERVICE);
            if (batteryManager != null) {
                charging = charging || batteryManager.isCharging();
            }
        }

        boolean pluggedAc = plugged == BatteryManager.BATTERY_PLUGGED_AC;
        boolean pluggedUsb = plugged == BatteryManager.BATTERY_PLUGGED_USB;
        boolean pluggedWireless = plugged == BatteryManager.BATTERY_PLUGGED_WIRELESS;
        boolean pluggedIn = plugged != 0;
        boolean allowed = pluggedIn || charging || status == BatteryManager.BATTERY_STATUS_FULL;
        if ("unavailable".equals(source)) {
            allowed = true;
        }

        String plugType = "none";
        if (pluggedAc) {
            plugType = "ac";
        } else if (pluggedUsb) {
            plugType = "usb";
        } else if (pluggedWireless) {
            plugType = "wireless";
        } else if (pluggedIn) {
            plugType = "other";
        }

        ret.put("charging", charging);
        ret.put("plugged", pluggedIn);
        ret.put("allowed", allowed);
        ret.put("plugType", plugType);
        ret.put("levelPercent", levelPercent);
        ret.put("source", source);

        if (tempTenths > 0) {
            ret.put("batteryTempC", tempTenths / 10.0);
        } else {
            ret.put("batteryTempC", -1);
        }

        int thermalStatus = -1;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            PowerManager powerManager =
                (PowerManager) getContext().getSystemService(Context.POWER_SERVICE);
            if (powerManager != null) {
                thermalStatus = powerManager.getCurrentThermalStatus();
            }
        }
        ret.put("thermalStatus", thermalStatus);
        return ret;
    }

    private static String hashDeviceId(String raw) {
        if (raw == null || raw.isEmpty()) {
            return "android-unknown";
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(raw.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 16; i++) {
                sb.append(String.format("%02x", hashed[i]));
            }
            return sb.toString();
        } catch (Exception exc) {
            return raw;
        }
    }
}