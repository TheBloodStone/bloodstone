package org.bloodstone.plugins.localnode;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.work.ForegroundInfo;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

public class NodeSyncWorker extends Worker {
    private static final String TAG = "BloodstoneNodeSyncWorker";
    public static final String UNIQUE_WORK = "bloodstone_node_periodic_sync";
    static final String CHANNEL_ID = "bloodstone_node_sync";
    static final int NOTIFICATION_ID = 73423;

    public NodeSyncWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        createChannel();
        try {
            NodeSyncEngine.Result result = NodeSyncEngine.runPeriodicCheck(
                getApplicationContext(),
                (localHeight, networkHeight) -> enterSyncForeground(
                    "Local " + localHeight + " · network " + networkHeight
                )
            );
            Log.i(
                TAG,
                "periodic check outcome=" + result.outcome
                    + " local=" + result.localHeight
                    + " network=" + result.networkHeight
                    + " msg=" + result.message
            );

            if (result.outcome == NodeSyncEngine.Outcome.SYNC_FAILED
                || result.outcome == NodeSyncEngine.Outcome.CHECK_FAILED) {
                return Result.retry();
            }
            return Result.success();
        } catch (Exception exc) {
            Log.w(TAG, "worker failed: " + exc.getMessage());
            return Result.retry();
        } finally {
            clearForegroundNotification();
        }
    }

    static void createChannel(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Bloodstone node sync",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Brief chain sync when your node falls behind the network");
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.createNotificationChannel(channel);
        }
    }

    private void createChannel() {
        createChannel(getApplicationContext());
    }

    static Notification buildSyncNotification(Context context, String body) {
        return new NotificationCompat.Builder(context, CHANNEL_ID)
            .setContentTitle("Bloodstone — catching up blocks")
            .setContentText(body)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
    }

    ForegroundInfo buildForegroundInfo(String body) {
        Notification notification = buildSyncNotification(getApplicationContext(), body);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            return new ForegroundInfo(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            );
        }
        return new ForegroundInfo(NOTIFICATION_ID, notification);
    }

    void enterSyncForeground(String body) {
        try {
            setForegroundAsync(buildForegroundInfo(body));
        } catch (Exception exc) {
            Log.w(TAG, "foreground promotion failed: " + exc.getMessage());
        }
    }

    private void clearForegroundNotification() {
        NotificationManager manager =
            getApplicationContext().getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.cancel(NOTIFICATION_ID);
        }
    }
}