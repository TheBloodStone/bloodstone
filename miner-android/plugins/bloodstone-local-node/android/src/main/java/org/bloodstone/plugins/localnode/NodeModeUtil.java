package org.bloodstone.plugins.localnode;

import android.content.Context;

import java.io.File;

final class NodeModeUtil {
    static final String CONSENSUS = "consensus";
    static final String CONSENSUS_WITNESS = "consensus-witness";

    private NodeModeUtil() {
    }

    static String normalize(String mode) {
        if (mode == null) {
            return "pruned";
        }
        String m = mode.trim().toLowerCase();
        if ("lan-client".equals(m) || "lan_client".equals(m)) {
            return "lan-client";
        }
        if ("consensus_witness".equals(m)) {
            return CONSENSUS_WITNESS;
        }
        if ("full".equals(m)
            || "mesh".equals(m)
            || "pruned".equals(m)
            || CONSENSUS.equals(m)
            || CONSENSUS_WITNESS.equals(m)) {
            return m;
        }
        return "pruned";
    }

    static boolean isConsensusMode(String mode) {
        String m = normalize(mode);
        return CONSENSUS.equals(m) || CONSENSUS_WITNESS.equals(m);
    }

    static boolean hostsStratum(String mode) {
        String m = normalize(mode);
        return !isConsensusMode(m) && !"lan-client".equals(m);
    }

    static boolean runsBloodstoned(String mode) {
        String m = normalize(mode);
        return !"lan-client".equals(m);
    }

    /** Pruned, full, and mesh nodes may host wallet.dat on-device; consensus modes stay wallet-less. */
    static boolean supportsOnDeviceWallet(String mode) {
        String m = normalize(mode);
        return "pruned".equals(m) || "full".equals(m) || "mesh".equals(m);
    }

    static File datadir(Context context, String mode) {
        String m = normalize(mode);
        String subdir;
        if ("full".equals(m)) {
            subdir = "bloodstone-full";
        } else if (CONSENSUS.equals(m)) {
            subdir = "bloodstone-consensus";
        } else if (CONSENSUS_WITNESS.equals(m)) {
            subdir = "bloodstone-consensus-witness";
        } else {
            subdir = "bloodstone-pruned";
        }
        return new File(context.getFilesDir(), subdir);
    }

    static int nodePriority(String mode) {
        String m = normalize(mode);
        if ("full".equals(m)) {
            return 100;
        }
        if ("mesh".equals(m)) {
            return 60;
        }
        if (CONSENSUS.equals(m)) {
            return 50;
        }
        if ("pruned".equals(m)) {
            return 40;
        }
        if (CONSENSUS_WITNESS.equals(m)) {
            return 30;
        }
        return 10;
    }
}