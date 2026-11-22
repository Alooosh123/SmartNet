package com.smartnet.walletcollector

import android.content.Context
import android.net.Uri
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

data class ApiResponse(val statusCode: Int, val body: String) {
    val isSuccessful: Boolean get() = statusCode in 200..299
}

/** HTTPS API client using platform TLS certificate and hostname verification. */
object WalletApi {
    fun request(
        context: Context,
        path: String,
        method: String,
        payload: JSONObject? = null
    ): ApiResponse {
        val baseUrl = SecureStorage.readSecret(context, "base_url")
            ?: throw IllegalStateException("Backend URL is not configured.")
        val deviceToken = SecureStorage.readSecret(context, "device_token")
            ?: throw IllegalStateException("Device token is not configured.")
        val base = baseUrl.trimEnd('/')
        val uri = Uri.parse(base)
        val isHttps = uri.scheme.equals("https", true) && !uri.host.isNullOrBlank()
        val isLocalDebug = BuildConfig.DEBUG &&
            uri.scheme.equals("http", true) &&
            uri.host in setOf("10.0.2.2", "127.0.0.1", "localhost")
        require(isHttps || isLocalDebug) { "Production collector requires HTTPS." }

        val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10_000
            readTimeout = 15_000
            useCaches = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer $deviceToken")
            if (payload != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (payload != null) {
                val bytes = payload.toString().toByteArray(StandardCharsets.UTF_8)
                connection.outputStream.use { it.write(bytes) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..399) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() } ?: ""
            return ApiResponse(status, body)
        } finally {
            connection.disconnect()
        }
    }

    fun heartbeat(context: Context, notificationAccessGranted: Boolean): ApiResponse =
        request(
            context,
            "/api/v1/wallet-monitor/device/heartbeat",
            "POST",
            JSONObject()
                .put("app_version", BuildConfig.VERSION_NAME)
                .put("notification_access_granted", notificationAccessGranted)
        )

    fun configuration(context: Context): ApiResponse =
        request(context, "/api/v1/wallet-monitor/device/config", "GET")

    fun sendEvent(context: Context, event: JSONObject): ApiResponse =
        request(context, "/api/v1/wallet-monitor/device/events", "POST", event)
}
