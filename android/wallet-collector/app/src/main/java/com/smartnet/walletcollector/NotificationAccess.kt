package com.smartnet.walletcollector

import android.content.ComponentName
import android.content.Context
import android.provider.Settings

object NotificationAccess {
    fun isGranted(context: Context): Boolean {
        val configured = Settings.Secure.getString(
            context.contentResolver,
            "enabled_notification_listeners"
        ) ?: return false
        val component = ComponentName(context, WalletNotificationListener::class.java).flattenToString()
        return configured.split(':').any { it.equals(component, ignoreCase = true) }
    }
}
