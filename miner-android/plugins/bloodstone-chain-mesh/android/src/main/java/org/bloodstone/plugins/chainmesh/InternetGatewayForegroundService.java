package org.bloodstone.plugins.chainmesh;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

import androidx.core.app.NotificationCompat;

/**
 * Keeps the mesh chunk server alive while this phone shares internet with LAN miners.
 * Works with or without mining / full node.
 */
public class InternetGatewayForegroundService extends Service {
    public static final String CHANNEL_ID = "bloodstone_internet_gateway";
    public static final int NOTIFICATION_ID = 73423;
    public static final String ACTION_STOP = "org.bloodstone.miner.STOP_INTERNET_GATEWAY";

    private static volatile boolean running = false;

    static boolean isRunning() {
        return running;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        running = true;
        ChainMeshPlugin.setGatewaySharingEnabled(true);
        createChannel();
        startForeground(NOTIFICATION_ID, buildNotification());
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        ChainMeshPlugin.setGatewaySharingEnabled(false);
        super.onDestroy();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "LAN internet sharing",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Shares this phone's internet with other Bloodstone miners on Wi‑Fi");
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification() {
        String lan = NetworkUtil.lanIpv4(this);
        String body = lan != null && !lan.isEmpty()
            ? "LAN miners on Wi‑Fi can use your connection · " + lan + ":18341"
            : "LAN miners on Wi‑Fi can use your internet";
        Intent launch = new Intent(Intent.ACTION_MAIN);
        launch.addCategory(Intent.CATEGORY_LAUNCHER);
        launch.setClassName(getPackageName(), "org.bloodstone.miner.MainActivity");
        launch.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pending = PendingIntent.getActivity(
            this,
            0,
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        Intent stop = new Intent(this, InternetGatewayForegroundService.class);
        stop.setAction(ACTION_STOP);
        PendingIntent stopPending = PendingIntent.getService(
            this,
            1,
            stop,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Sharing internet with LAN miners")
            .setContentText(body)
            .setSmallIcon(android.R.drawable.ic_menu_share)
            .setContentIntent(pending)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPending)
            .setOngoing(true)
            .build();
    }
}