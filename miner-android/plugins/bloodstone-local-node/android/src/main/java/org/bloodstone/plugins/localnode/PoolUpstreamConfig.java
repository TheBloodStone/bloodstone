package org.bloodstone.plugins.localnode;

final class PoolUpstreamConfig {
    private static final String DEFAULT_POOL_HOST = "64.188.22.190";

    private PoolUpstreamConfig() {
    }

    static String poolHostFromUpstreamUrl(String upstreamUrl) {
        // Stratum relay uses plain TCP — always target the VPS stratum IP, not the HTTPS API host.
        return DEFAULT_POOL_HOST;
    }
}