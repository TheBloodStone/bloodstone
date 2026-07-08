package org.bloodstone.miner;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;

import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;

import org.bloodstone.plugins.devicepool.ApkUpdateInstaller;
import org.bloodstone.plugins.devicepool.ReleaseDownloadHelper;

import java.io.File;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Retries the remote miner URL during brief VPS restarts instead of immediately
 * falling back to the bundled offline shell (which looks like an app restart).
 *
 * Intercepts release download links (.apk, .tar.gz, .zip, …) so the WebView does
 * not try to render binaries — that flash looks like a download screen closing.
 */
public class ResilientBridgeWebViewClient extends BridgeWebViewClient {

    private static final String TAG = "BloodstoneWebView";
    private static final int MAX_RETRIES = 10;
    private static final long RETRY_BASE_MS = 1200;
    private static final long RETRY_MAX_MS = 12000;

    private final Bridge bridge;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService downloadExecutor = Executors.newSingleThreadExecutor();
    private int retryCount = 0;
    private Runnable pendingRetry;
    private SwipeRefreshLayout swipeRefreshLayout;

    public ResilientBridgeWebViewClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
    }

    public void setSwipeRefreshLayout(SwipeRefreshLayout layout) {
        this.swipeRefreshLayout = layout;
    }

    private void stopRefreshing() {
        if (swipeRefreshLayout != null) {
            swipeRefreshLayout.setRefreshing(false);
        }
    }

    private static final String BUNDLED_MINER_URL =
        "https://localhost/offline-mine.html?app=android";

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        if (request != null && request.isForMainFrame()) {
            Uri uri = request.getUrl();
            if (uri != null) {
                if (shouldRedirectToBundledMiner(uri.toString())) {
                    view.loadUrl(BUNDLED_MINER_URL);
                    return true;
                }
                if (handleReleaseDownload(view, uri.toString())) {
                    return true;
                }
            }
        }
        return super.shouldOverrideUrlLoading(view, request);
    }

    @Override
    @SuppressWarnings("deprecation")
    public boolean shouldOverrideUrlLoading(WebView view, String url) {
        if (url != null) {
            if (shouldRedirectToBundledMiner(url)) {
                view.loadUrl(BUNDLED_MINER_URL);
                return true;
            }
            if (handleReleaseDownload(view, url)) {
                return true;
            }
        }
        return super.shouldOverrideUrlLoading(view, url);
    }

    private boolean handleReleaseDownload(WebView view, String url) {
        if (!ReleaseDownloadHelper.isReleaseDownloadUrl(url)) {
            return false;
        }
        if (isApkDownloadUrl(Uri.parse(url))) {
            startApkInstall(view, url);
            return true;
        }
        startReleaseDownload(view, url);
        return true;
    }

    @Override
    public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
        if (shouldRetryRemoteLoad(view, request, -1)) {
            scheduleRetry(view);
            return;
        }
        stopRefreshing();
        super.onReceivedError(view, request, error);
    }

    @Override
    public void onReceivedHttpError(
        WebView view,
        WebResourceRequest request,
        WebResourceResponse errorResponse
    ) {
        int status = errorResponse != null ? errorResponse.getStatusCode() : -1;
        if (shouldRetryRemoteLoad(view, request, status)) {
            scheduleRetry(view);
            return;
        }
        stopRefreshing();
        super.onReceivedHttpError(view, request, errorResponse);
    }

    @Override
    public void onPageFinished(WebView view, String url) {
        if (isRemoteMinerUrl(url)) {
            retryCount = 0;
            cancelPendingRetry();
        }
        stopRefreshing();
        if (shouldRedirectToBundledMiner(url)) {
            view.loadUrl(BUNDLED_MINER_URL);
            return;
        }
        injectInstalledAppVersion(view);
        super.onPageFinished(view, url);
    }

    private void startApkInstall(WebView view, String apkUrl) {
        Context context = view.getContext();
        if (!ApkUpdateInstaller.canInstallPackages(context)) {
            ApkUpdateInstaller.openInstallPermissionSettings(context);
            return;
        }
        downloadExecutor.execute(() -> {
            try {
                File apkFile = ApkUpdateInstaller.downloadApk(context, apkUrl);
                view.post(() -> {
                    Activity activity = bridge.getActivity();
                    Context launchContext = activity != null ? activity : context;
                    try {
                        ApkUpdateInstaller.promptInstall(launchContext, apkFile);
                    } catch (Exception exc) {
                        Log.w(TAG, "apk prompt failed: " + exc.getMessage());
                        openApkExternally(launchContext, apkUrl);
                    }
                });
            } catch (Exception exc) {
                Log.w(TAG, "apk download failed: " + exc.getMessage());
                view.post(() -> openApkExternally(context, apkUrl));
            }
        });
    }

    private void startReleaseDownload(WebView view, String fileUrl) {
        Context context = view.getContext();
        downloadExecutor.execute(() -> {
            try {
                ReleaseDownloadHelper.enqueuePublicDownload(context, fileUrl);
                view.post(() -> ReleaseDownloadHelper.toastDownloadStarted(context, fileUrl));
            } catch (Exception exc) {
                Log.w(TAG, "release download failed: " + exc.getMessage());
                view.post(() -> openFileExternally(context, fileUrl));
            }
        });
    }

    private static void openFileExternally(Context context, String fileUrl) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(fileUrl));
            if (!(context instanceof Activity)) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            }
            context.startActivity(intent);
        } catch (Exception exc) {
            Log.w(TAG, "external file open failed: " + exc.getMessage());
        }
    }

    private static void openApkExternally(Context context, String apkUrl) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(apkUrl));
            if (!(context instanceof Activity)) {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            }
            context.startActivity(intent);
        } catch (Exception exc) {
            Log.w(TAG, "external apk open failed: " + exc.getMessage());
        }
    }

    private static boolean isApkDownloadUrl(Uri uri) {
        if (uri == null) {
            return false;
        }
        String path = uri.getPath();
        if (path == null) {
            return false;
        }
        String lower = path.toLowerCase(Locale.US);
        return lower.endsWith(".apk") || lower.contains(".apk/");
    }

    private void injectInstalledAppVersion(WebView view) {
        try {
            PackageInfo info = view
                .getContext()
                .getPackageManager()
                .getPackageInfo(view.getContext().getPackageName(), 0);
            String version = info.versionName != null ? info.versionName : "";
            if (version.isEmpty()) {
                return;
            }
            String safe = version.replace("\\", "\\\\").replace("'", "\\'");
            String js =
                "(function(){var b=document.body;if(!b)return;" +
                "b.dataset.nativeApkVersion='" +
                safe +
                "';" +
                "var text='Installed: APK v" +
                safe +
                "';" +
                "document.querySelectorAll('.android-app-version-line,#android-app-version-line')" +
                ".forEach(function(el){el.textContent=text;});})();";
            view.evaluateJavascript(js, null);
        } catch (Exception ignored) {
            // PackageManager unavailable — web layer falls back to nativePromise.
        }
    }

    private boolean shouldRetryRemoteLoad(WebView view, WebResourceRequest request, int status) {
        if (request == null || !request.isForMainFrame()) {
            return false;
        }
        Uri requestUri = request.getUrl();
        if (requestUri != null && ReleaseDownloadHelper.isReleaseDownloadUrl(requestUri)) {
            return false;
        }
        String currentUrl = view.getUrl();
        if (currentUrl != null) {
            Uri currentUri = Uri.parse(currentUrl);
            if (ReleaseDownloadHelper.isReleaseDownloadUrl(currentUri) || isDownloadsPage(currentUri)) {
                return false;
            }
        }
        if (currentUrl != null && !isRemoteMinerUrl(currentUrl)) {
            return false;
        }
        if (status > 0 && status < 500 && status != 408 && status != 429) {
            return false;
        }
        return retryCount < MAX_RETRIES;
    }

    private static boolean isDownloadsPage(Uri uri) {
        if (uri == null) {
            return false;
        }
        String path = uri.getPath();
        return path != null && path.contains("/downloads");
    }

    private void scheduleRetry(WebView view) {
        retryCount += 1;
        cancelPendingRetry();
        long delay = Math.min(RETRY_BASE_MS * retryCount, RETRY_MAX_MS);
        pendingRetry = () -> {
            pendingRetry = null;
            String appUrl = bridge.getAppUrl();
            if (appUrl != null && !appUrl.isEmpty()) {
                view.loadUrl(appUrl);
            }
        };
        handler.postDelayed(pendingRetry, delay);
    }

    private void cancelPendingRetry() {
        if (pendingRetry != null) {
            handler.removeCallbacks(pendingRetry);
            pendingRetry = null;
        }
    }

    /** Portal miner pages lack Capacitor JS — only localhost bundle has the native bridge. */
    private static boolean shouldRedirectToBundledMiner(String url) {
        if (url == null || url.isEmpty()) {
            return false;
        }
        Uri uri = Uri.parse(url);
        String path = uri.getPath();
        if (path == null) {
            return false;
        }
        if (path.contains("/downloads")) {
            return false;
        }
        if (!isRemoteMinerUrl(url)) {
            return false;
        }
        return path.startsWith("/mining/mine")
            || "/mining/mine".equals(path)
            || (path.startsWith("/mining/") && path.endsWith("/mine"));
    }

    private static boolean isRemoteMinerUrl(String url) {
        if (url == null || url.isEmpty()) {
            return false;
        }
        Uri uri = Uri.parse(url);
        String host = uri.getHost();
        if (host == null) {
            return false;
        }
        if ("localhost".equals(host) || host.endsWith(".localhost")) {
            return false;
        }
        if ("https".equalsIgnoreCase(uri.getScheme())) {
            return host.contains("bloodstonewallet")
                || host.contains("mytunnel.org")
                || host.contains("duckdns.org");
        }
        return false;
    }
}