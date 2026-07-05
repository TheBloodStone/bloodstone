package org.bloodstone.miner;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    protected void load() {
        super.load();
        Bridge activeBridge = getBridge();
        if (activeBridge != null) {
            activeBridge.setWebViewClient(new ResilientBridgeWebViewClient(activeBridge));
        }
    }
}