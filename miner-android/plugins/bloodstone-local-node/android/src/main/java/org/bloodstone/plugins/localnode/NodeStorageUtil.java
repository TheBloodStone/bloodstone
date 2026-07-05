package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.os.StatFs;

import java.io.File;

final class NodeStorageUtil {
    /** Bloodstone mainnet is still small (~tens of MiB); 2 GiB was blocking phones unnecessarily. */
    static final long FULL_NODE_MIN_FREE_BYTES = 400L * 1024L * 1024L;
    static final long FULL_NODE_ESTIMATE_BYTES = 550L * 1024L * 1024L;
    /** Below this we refuse to start any bloodstoned datadir. */
    static final long ABSOLUTE_MIN_FREE_BYTES = 96L * 1024L * 1024L;

    private NodeStorageUtil() {
    }

    static long freeBytes(Context context) {
        File root = context.getFilesDir();
        if (root == null) {
            return 0L;
        }
        try {
            StatFs stat = new StatFs(root.getAbsolutePath());
            return stat.getAvailableBlocksLong() * stat.getBlockSizeLong();
        } catch (Exception ignored) {
            return root.getFreeSpace();
        }
    }

    static long datadirBytes(Context context, String subdir) {
        File dir = new File(context.getFilesDir(), subdir);
        return dirSize(dir);
    }

    static boolean canRunFullNode(Context context) {
        return freeBytes(context) >= FULL_NODE_MIN_FREE_BYTES;
    }

    static boolean hasAbsoluteMinStorage(Context context) {
        return freeBytes(context) >= ABSOLUTE_MIN_FREE_BYTES;
    }

    static String recommendedMode(Context context) {
        if (canRunFullNode(context)) {
            return "full";
        }
        if (freeBytes(context) >= 200L * 1024L * 1024L) {
            return "mesh";
        }
        return "pruned";
    }

    private static long dirSize(File file) {
        if (file == null || !file.exists()) {
            return 0L;
        }
        if (file.isFile()) {
            return file.length();
        }
        long total = 0L;
        File[] children = file.listFiles();
        if (children == null) {
            return 0L;
        }
        for (File child : children) {
            total += dirSize(child);
        }
        return total;
    }
}