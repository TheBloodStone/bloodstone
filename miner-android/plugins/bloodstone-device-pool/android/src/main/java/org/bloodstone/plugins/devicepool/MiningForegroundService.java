package org.bloodstone.plugins.devicepool;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import androidx.core.app.NotificationCompat;

public class MiningForegroundService extends Service {
    public static final String CHANNEL_ID = "bloodstone_fleet_mining";
    public static final int NOTIFICATION_ID = 73421;
    public static final String ACTION_STOP = "org.bloodstone.miner.STOP_FLEET_MINING";

    private static volatile boolean running = false;
    private PowerManager.WakeLock partialWakeLock;

    public static boolean isRunning() {
        return running;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            releaseWakeLock();
            stopForeground(true);
            running = false;
            stopSelf();
            return START_NOT_STICKY;
        }

        String address = intent != null ? intent.getStringExtra("address") : null;
        String algo = intent != null ? intent.getStringExtra("algo") : null;
        String detail = "";
        if (algo != null && !algo.isEmpty()) {
            detail = " · " + algo;
        }
        if (address != null && address.length() > 8) {
            detail += " · " + address.substring(0, 4) + "…" + address.substring(address.length() - 4);
        }

        Notification notification = buildNotification(
            "Decentralized pool node active",
            "Your phone shares VPS load via direct stratum TCP" + detail
        );
        startForeground(NOTIFICATION_ID, notification);
        acquireWakeLock();
        running = true;
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        releaseWakeLock();
        running = false;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private Notification buildNotification(String title, String body) {
        Intent launch = buildResumeMainIntent();
        PendingIntent contentIntent = PendingIntent.getActivity(
            this,
            0,
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent stopIntent = new Intent(this, MiningForegroundService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPending = PendingIntent.getService(
            this,
            1,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(body)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setOngoing(true)
            .setContentIntent(contentIntent)
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                "Stop",
                stopPending
            )
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
    }

    private Intent buildResumeMainIntent() {
        Intent launch = new Intent(Intent.ACTION_MAIN);
        launch.addCategory(Intent.CATEGORY_LAUNCHER);
        launch.setClassName(getPackageName(), "org.bloodstone.miner.MainActivity");
        launch.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return launch;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Bloodstone fleet mining",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription(
            "Shows when this device is mining as a decentralized VPS pool node"
        );
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.createNotificationChannel(channel);
        }
    }

    public static void stop(Context context) {
        Intent intent = new Intent(context, MiningForegroundService.class);
        intent.setAction(ACTION_STOP);
        context.startService(intent);
    }

    private void acquireWakeLock() {
        if (partialWakeLock != null && partialWakeLock.isHeld()) {
            return;
        }
        PowerManager powerManager = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (powerManager == null) {
            return;
        }
        partialWakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "BloodstoneMiner::FleetMining"
        );
        partialWakeLock.setReferenceCounted(false);
        partialWakeLock.acquire();
    }

    private void releaseWakeLock() {
        if (partialWakeLock != null && partialWakeLock.isHeld()) {
            partialWakeLock.release();
        }
        partialWakeLock = null;
    }
}