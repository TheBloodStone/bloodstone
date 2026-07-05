package org.bloodstone.plugins.localnode;

import android.content.Context;

/** Application context holder for traffic counters (set by local node service). */
final class NodeTrafficStatsHolder {
    static volatile Context appContext;

    private NodeTrafficStatsHolder() {}
}