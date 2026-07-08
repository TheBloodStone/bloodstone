package org.bloodstone.miner;

import android.content.Intent;
import android.os.Bundle;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.webkit.WebView;

import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private boolean webClientConfigured;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        setIntent(intent);
        super.onNewIntent(intent);
    }

    @Override
    protected void load() {
        super.load();
        if (webClientConfigured) {
            return;
        }
        Bridge activeBridge = getBridge();
        if (activeBridge == null) {
            return;
        }
        WebView webView = activeBridge.getWebView();
        ResilientBridgeWebViewClient client = new ResilientBridgeWebViewClient(activeBridge);
        activeBridge.setWebViewClient(client);
        attachPullToRefresh(webView, client);
        webClientConfigured = true;
    }

    private void attachPullToRefresh(WebView webView, ResilientBridgeWebViewClient client) {
        ViewParent parent = webView.getParent();
        if (parent instanceof SwipeRefreshLayout) {
            client.setSwipeRefreshLayout((SwipeRefreshLayout) parent);
            return;
        }
        if (!(parent instanceof ViewGroup)) {
            return;
        }
        ViewGroup parentGroup = (ViewGroup) parent;
        int index = parentGroup.indexOfChild(webView);
        ViewGroup.LayoutParams params = webView.getLayoutParams();
        parentGroup.removeView(webView);

        SwipeRefreshLayout swipeRefreshLayout = new SwipeRefreshLayout(this);
        swipeRefreshLayout.setLayoutParams(params);
        swipeRefreshLayout.addView(
            webView,
            new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        );
        parentGroup.addView(swipeRefreshLayout, index);

        swipeRefreshLayout.setColorSchemeColors(0xFF6EB5FF, 0xFFD4A017);
        swipeRefreshLayout.setProgressBackgroundColorSchemeColor(0xFF1E2A3D);
        swipeRefreshLayout.setDistanceToTriggerSync(220);
        swipeRefreshLayout.setOnChildScrollUpCallback(
            (parentLayout, child) -> webView.getScrollY() > 0
        );
        swipeRefreshLayout.setOnRefreshListener(() -> {
            String url = webView.getUrl();
            if (url != null && !url.isEmpty()) {
                webView.reload();
                return;
            }
            Bridge bridge = getBridge();
            if (bridge != null) {
                String appUrl = bridge.getAppUrl();
                if (appUrl != null && !appUrl.isEmpty()) {
                    webView.loadUrl(appUrl);
                    return;
                }
            }
            webView.reload();
        });

        client.setSwipeRefreshLayout(swipeRefreshLayout);
    }
}