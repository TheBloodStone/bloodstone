package org.bloodstone.plugins.localnode;

import android.content.Context;

import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;

import java.util.concurrent.TimeUnit;

final class NodeSyncScheduler {
    static final long INTERVAL_MINUTES = 15L;

    private NodeSyncScheduler() {
    }

    static void schedule(Context context) {
        NodeSyncWorker.createChannel(context);
        Constraints constraints = new Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build();
        PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(
            NodeSyncWorker.class,
            INTERVAL_MINUTES,
            TimeUnit.MINUTES
        )
            .setConstraints(constraints)
            .addTag(NodeSyncWorker.UNIQUE_WORK)
            .build();
        WorkManager.getInstance(context.getApplicationContext())
            .enqueueUniquePeriodicWork(
                NodeSyncWorker.UNIQUE_WORK,
                ExistingPeriodicWorkPolicy.UPDATE,
                request
            );
    }

    static void cancel(Context context) {
        WorkManager.getInstance(context.getApplicationContext())
            .cancelUniqueWork(NodeSyncWorker.UNIQUE_WORK);
    }
}