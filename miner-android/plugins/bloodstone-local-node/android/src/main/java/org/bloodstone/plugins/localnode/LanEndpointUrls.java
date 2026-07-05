package org.bloodstone.plugins.localnode;

final class LanEndpointUrls {
    private static final String PUBLIC_HOST = "bloodstonewallet.mytunnel.org";
    private static final String RPC_SUFFIX = "/api/local-node/rpc";
    private static final String REGISTER_SUFFIX = "/api/local-node/lan-register";

    private LanEndpointUrls() {
    }

    static String normalizeUpstream(String upstreamUrl) {
        String url = (upstreamUrl == null || upstreamUrl.isEmpty())
            ? NodeSyncPreferences.DEFAULT_UPSTREAM
            : upstreamUrl.trim();
        if (url.contains(PUBLIC_HOST) && !url.contains("/mining/api/")) {
            url = url.replace(PUBLIC_HOST + "/api/", PUBLIC_HOST + "/mining/api/");
        }
        if (!url.contains(RPC_SUFFIX)) {
            if (url.endsWith("/mining")) {
                url = url + RPC_SUFFIX;
            } else if (url.endsWith("/")) {
                url = url + "mining" + RPC_SUFFIX;
            }
        }
        return url;
    }

    static String registerUrlFromUpstream(String upstreamUrl) {
        String rpc = normalizeUpstream(upstreamUrl);
        if (rpc.contains(RPC_SUFFIX)) {
            return rpc.replace(RPC_SUFFIX, REGISTER_SUFFIX);
        }
        if (rpc.endsWith("/mining")) {
            return rpc + REGISTER_SUFFIX;
        }
        if (rpc.endsWith("/")) {
            return rpc + "mining" + REGISTER_SUFFIX;
        }
        return rpc + "/mining" + REGISTER_SUFFIX;
    }
}