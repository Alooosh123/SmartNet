package com.smartnet.walletcollector

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import org.json.JSONObject
import java.time.Instant
import java.util.UUID
import java.util.concurrent.Executors

class WalletNotificationListener : NotificationListenerService() {
    private val captureExecutor = Executors.newSingleThreadExecutor()

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val packageName = sbn.packageName ?: return
        if (packageName !in SecureStorage.getAllowedPackages(this)) return

        val extras = sbn.notification.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.take(500).orEmpty()
        val body = (
            extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString()
                ?: extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()
                ?: ""
            ).take(4000)
        if (title.isBlank() && body.isBlank()) return
        if (containsOtpOrCredentialPrompt("$title\n$body")) return

        val event = JSONObject()
            .put("event_uuid", UUID.randomUUID().toString())
            .put("package_name", packageName)
            .put("title", title)
            .put("body", body)
            .put("notification_posted_at", Instant.ofEpochMilli(sbn.postTime).toString())
            .put("sent_at", Instant.now().toString())

        captureExecutor.execute {
            try {
                SecureStorage.appendEvent(this, event)
                WalletSyncJobService.scheduleNow(this)
            } catch (_: Exception) {
                // Never log notification text or sensitive values.
                Log.w("SmartNetWallet", "Could not securely queue a wallet notification.")
            }
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        WalletSyncJobService.scheduleNow(this)
    }

    override fun onDestroy() {
        captureExecutor.shutdown()
        super.onDestroy()
    }

    private fun containsOtpOrCredentialPrompt(text: String): Boolean {
        val pattern = Regex(
            "(?i)(\\bOTP\\b|one[- ]time password|verification code|security code|" +
                "رمز التحقق|رمز الدخول|كلمة المرور المؤقتة|الرقم السري)"
        )
        return pattern.containsMatchIn(text)
    }
}
