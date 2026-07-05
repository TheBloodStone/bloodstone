package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Build;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.InetAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;

final class LanDiscovery {
    private static final String TAG = "BloodstoneLanDiscovery";
    static final String SERVICE_TYPE = "_bloodstone-rpc._tcp.";

    static final class DiscoveredPeer {
        final String serviceName;
        final String host;
        final int rpcPort;
        final int stratumPortNeoscrypt;
        final int stratumPortYespower;
        final String mode;

        DiscoveredPeer(
            String serviceName,
            String host,
            int rpcPort,
            int stratumPortNeoscrypt,
            int stratumPortYespower,
            String mode
        ) {
            this.serviceName = serviceName;
            this.host = host;
            this.rpcPort = rpcPort;
            this.stratumPortNeoscrypt = stratumPortNeoscrypt;
            this.stratumPortYespower = stratumPortYespower;
            this.mode = mode;
        }
    }

    private final NsdManager nsdManager;
    private final CopyOnWriteArrayList<DiscoveredPeer> discoveredPeers = new CopyOnWriteArrayList<>();
    private final String ownLanIp;

    private NsdManager.RegistrationListener registrationListener;
    private NsdManager.DiscoveryListener discoveryListener;
    private boolean registered;
    private boolean browsing;

    LanDiscovery(Context context) {
        nsdManager = (NsdManager) context.getSystemService(Context.NSD_SERVICE);
        ownLanIp = NetworkUtil.lanIpv4(context);
    }

    void register(String serviceName, int rpcPort, String mode, int stratumNeo, int stratumYp) {
        unregister();
        if (nsdManager == null) {
            return;
        }
        NsdServiceInfo serviceInfo = new NsdServiceInfo();
        serviceInfo.setServiceName(serviceName);
        serviceInfo.setServiceType(SERVICE_TYPE);
        serviceInfo.setPort(rpcPort);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            serviceInfo.setAttribute("mode", mode != null ? mode : "pruned");
            serviceInfo.setAttribute("stratum_neo", String.valueOf(stratumNeo));
            serviceInfo.setAttribute("stratum_yp", String.valueOf(stratumYp));
        }
        registrationListener = new NsdManager.RegistrationListener() {
            @Override
            public void onRegistrationFailed(NsdServiceInfo serviceInfo, int errorCode) {
                Log.w(TAG, "registration failed: " + errorCode);
                registered = false;
            }

            @Override
            public void onUnregistrationFailed(NsdServiceInfo serviceInfo, int errorCode) {
                Log.w(TAG, "unregistration failed: " + errorCode);
            }

            @Override
            public void onServiceRegistered(NsdServiceInfo serviceInfo) {
                registered = true;
                Log.i(TAG, "mDNS registered " + serviceInfo.getServiceName());
            }

            @Override
            public void onServiceUnregistered(NsdServiceInfo serviceInfo) {
                registered = false;
            }
        };
        try {
            nsdManager.registerService(serviceInfo, NsdManager.PROTOCOL_DNS_SD, registrationListener);
        } catch (Exception exc) {
            Log.w(TAG, "registerService failed: " + exc.getMessage());
        }
    }

    void startBrowse() {
        if (nsdManager == null || browsing) {
            return;
        }
        discoveryListener = new NsdManager.DiscoveryListener() {
            @Override
            public void onDiscoveryStarted(String serviceType) {
                browsing = true;
                Log.i(TAG, "mDNS browse started");
            }

            @Override
            public void onServiceFound(NsdServiceInfo serviceInfo) {
                if (serviceInfo == null || serviceInfo.getServiceName() == null) {
                    return;
                }
                if (serviceInfo.getServiceName().contains("Bloodstone")) {
                    return;
                }
                nsdManager.resolveService(
                    serviceInfo,
                    new NsdManager.ResolveListener() {
                        @Override
                        public void onResolveFailed(NsdServiceInfo info, int errorCode) {
                            Log.w(TAG, "resolve failed " + info.getServiceName() + ": " + errorCode);
                        }

                        @Override
                        public void onServiceResolved(NsdServiceInfo info) {
                            addResolvedPeer(info);
                        }
                    }
                );
            }

            @Override
            public void onServiceLost(NsdServiceInfo serviceInfo) {
                if (serviceInfo == null) {
                    return;
                }
                removePeer(serviceInfo.getServiceName());
            }

            @Override
            public void onDiscoveryStopped(String serviceType) {
                browsing = false;
            }

            @Override
            public void onStartDiscoveryFailed(String serviceType, int errorCode) {
                browsing = false;
                Log.w(TAG, "browse start failed: " + errorCode);
            }

            @Override
            public void onStopDiscoveryFailed(String serviceType, int errorCode) {
                Log.w(TAG, "browse stop failed: " + errorCode);
            }
        };
        try {
            nsdManager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, discoveryListener);
        } catch (Exception exc) {
            Log.w(TAG, "discoverServices failed: " + exc.getMessage());
        }
    }

    void unregister() {
        stopBrowse();
        if (nsdManager != null && registrationListener != null) {
            try {
                nsdManager.unregisterService(registrationListener);
            } catch (Exception ignored) {
            }
        }
        registrationListener = null;
        registered = false;
        discoveredPeers.clear();
    }

    void stopBrowse() {
        if (nsdManager != null && discoveryListener != null) {
            try {
                nsdManager.stopServiceDiscovery(discoveryListener);
            } catch (Exception ignored) {
            }
        }
        discoveryListener = null;
        browsing = false;
    }

    boolean isRegistered() {
        return registered;
    }

    List<DiscoveredPeer> getDiscoveredPeers() {
        return new ArrayList<>(discoveredPeers);
    }

    JSONArray peersJson() {
        JSONArray out = new JSONArray();
        for (DiscoveredPeer peer : discoveredPeers) {
            JSONObject row = new JSONObject();
            try {
                row.put("serviceName", peer.serviceName);
                row.put("lan_ip", peer.host);
                row.put("host", peer.host);
                row.put("rpc_port", peer.rpcPort);
                row.put("stratum_port", peer.stratumPortNeoscrypt);
                row.put("stratum_port_yespower", peer.stratumPortYespower);
                row.put("mode", peer.mode);
                row.put("source", "mdns");
            } catch (Exception ignored) {
            }
            out.put(row);
        }
        return out;
    }

    private void addResolvedPeer(NsdServiceInfo info) {
        InetAddress host = info.getHost();
        if (host == null) {
            return;
        }
        String ip = host.getHostAddress();
        if (ip == null || ip.isEmpty()) {
            return;
        }
        if (ownLanIp != null && ownLanIp.equals(ip)) {
            return;
        }
        int rpcPort = info.getPort();
        String mode = "pruned";
        int stratumNeo = LocalNodeForegroundService.STRATUM_PORT_NEOSCRYPT;
        int stratumYp = LocalNodeForegroundService.STRATUM_PORT_YESPOWER;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            if (info.getAttributes().containsKey("mode")) {
                mode = new String(info.getAttributes().get("mode"), java.nio.charset.StandardCharsets.UTF_8);
            }
            if (info.getAttributes().containsKey("stratum_neo")) {
                stratumNeo = parsePort(
                    new String(info.getAttributes().get("stratum_neo"), java.nio.charset.StandardCharsets.UTF_8),
                    stratumNeo
                );
            }
            if (info.getAttributes().containsKey("stratum_yp")) {
                stratumYp = parsePort(
                    new String(info.getAttributes().get("stratum_yp"), java.nio.charset.StandardCharsets.UTF_8),
                    stratumYp
                );
            }
        }
        DiscoveredPeer peer = new DiscoveredPeer(
            info.getServiceName(),
            ip,
            rpcPort,
            stratumNeo,
            stratumYp,
            mode
        );
        removePeer(info.getServiceName());
        discoveredPeers.add(peer);
        Log.i(TAG, "mDNS peer " + ip + " rpc:" + rpcPort + " neo:" + stratumNeo);
    }

    private void removePeer(String serviceName) {
        if (serviceName == null) {
            return;
        }
        discoveredPeers.removeIf(peer -> serviceName.equals(peer.serviceName));
    }

    private static int parsePort(String raw, int fallback) {
        try {
            return Integer.parseInt(raw.trim());
        } catch (Exception exc) {
            return fallback;
        }
    }

    static int nodePriority(String mode) {
        return NodeModeUtil.nodePriority(mode);
    }

    static DiscoveredPeer bestPeerForAlgo(List<DiscoveredPeer> peers, String poolKey) {
        if (peers == null || peers.isEmpty()) {
            return null;
        }
        List<DiscoveredPeer> sorted = new ArrayList<>(peers);
        sorted.sort((a, b) -> Integer.compare(nodePriority(b.mode), nodePriority(a.mode)));
        return sorted.get(0);
    }
}