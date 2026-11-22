package com.smartnet.walletcollector

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var backendUrlInput: EditText
    private lateinit var deviceTokenInput: EditText
    private lateinit var statusView: TextView
    private lateinit var permissionView: TextView
    private lateinit var queueView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 36, 36, 36)
        }
        val scroll = ScrollView(this).apply { addView(layout) }

        layout.addView(TextView(this).apply {
            text = "SmartNet — جامع إشعارات المحافظ"
            textSize = 22f
        })
        layout.addView(TextView(this).apply {
            text = "هذا الهاتف يرسل إشعارات المحافظ المعتمدة فقط. لا تدخل PIN أو كلمة مرور أو OTP."
            textSize = 14f
            setPadding(0, 14, 0, 24)
        })

        backendUrlInput = EditText(this).apply {
            hint = "عنوان SmartNet API مثل https://smartnet.example.com"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        deviceTokenInput = EditText(this).apply {
            hint = "رمز الهاتف الذي أنشأه مدير SmartNet"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        layout.addView(backendUrlInput, matchWidth())
        layout.addView(deviceTokenInput, matchWidth())

        layout.addView(Button(this).apply {
            text = "حفظ بيانات الاتصال المشفرة"
            setOnClickListener { saveConnection() }
        }, matchWidth())
        layout.addView(Button(this).apply {
            text = "فتح إعدادات صلاحية الإشعارات"
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            }
        }, matchWidth())
        layout.addView(Button(this).apply {
            text = "مزامنة إعدادات الهاتف الآن"
            setOnClickListener {
                WalletSyncJobService.scheduleNow(this@MainActivity)
                refreshStatus()
            }
        }, matchWidth())

        permissionView = TextView(this).apply { textSize = 15f; setPadding(0, 22, 0, 8) }
        queueView = TextView(this).apply { textSize = 15f; setPadding(0, 4, 0, 8) }
        statusView = TextView(this).apply { textSize = 14f; setPadding(0, 4, 0, 8) }
        layout.addView(permissionView)
        layout.addView(queueView)
        layout.addView(statusView)

        setContentView(scroll)
        refreshStatus()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    private fun saveConnection() {
        val baseUrl = backendUrlInput.text.toString().trim().trimEnd('/')
        val token = deviceTokenInput.text.toString().trim()
        if (!isAllowedBackendUrl(baseUrl)) {
            statusView.text = "عنوان الخادم غير صالح. استخدم HTTPS في بيئة الإنتاج."
            return
        }
        if (token.length < 32) {
            statusView.text = "رمز الهاتف غير صالح."
            return
        }
        try {
            SecureStorage.saveSecret(this, "base_url", baseUrl)
            SecureStorage.saveSecret(this, "device_token", token)
            deviceTokenInput.text?.clear()
            WalletSyncJobService.schedulePeriodic(this)
            WalletSyncJobService.scheduleNow(this)
            statusView.text = "تم حفظ بيانات الاتصال مشفرة. جارٍ جلب الحزم المسموح بها."
        } catch (_: Exception) {
            statusView.text = "تعذر حفظ بيانات الهاتف بأمان."
        }
        refreshStatus()
    }

    private fun isAllowedBackendUrl(value: String): Boolean {
        val uri = Uri.parse(value)
        val secure = uri.scheme.equals("https", true) && !uri.host.isNullOrBlank()
        val localDebug = BuildConfig.DEBUG &&
            uri.scheme.equals("http", true) &&
            uri.host in setOf("10.0.2.2", "127.0.0.1", "localhost")
        return secure || localDebug
    }

    private fun refreshStatus() {
        if (!::permissionView.isInitialized) return
        permissionView.text = if (NotificationAccess.isGranted(this)) {
            "صلاحية قراءة إشعارات التطبيقات المحددة: ممنوحة"
        } else {
            "صلاحية قراءة الإشعارات: غير ممنوحة"
        }
        val count = try { SecureStorage.queueCount(this) } catch (_: Exception) { -1 }
        queueView.text = when {
            count < 0 -> "تعذر فتح الطابور المشفر؛ لا تحذف بيانات التطبيق قبل مراجعة الدعم."
            SecureStorage.hasQueueOverflow(this) -> "تحذير: امتلأ الطابور المشفر؛ راجع اتصال الهاتف بالخادم."
            else -> "أحداث بانتظار الإرسال: $count"
        }
        statusView.text = SecureStorage.getSyncStatus(this)
    }

    private fun matchWidth() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT
    ).apply { bottomMargin = 12 }
}
