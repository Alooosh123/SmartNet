package com.smartnet.walletcollector

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Credentials and queued notification text are encrypted using a key held in Android Keystore. */
object SecureStorage {
    private const val PREFS = "smartnet_wallet_collector"
    private const val KEY_ALIAS = "smartnet_wallet_collector_aes_v1"
    private const val QUEUE_FILE = "wallet-events.queue.enc"
    private const val MAX_QUEUED_EVENTS = 2000
    private val lock = Any()

    private fun preferences(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun encryptionKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore")
        keyStore.load(null)
        val existing = keyStore.getKey(KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setRandomizedEncryptionRequired(true)
            .build()
        generator.init(spec)
        return generator.generateKey()
    }

    private fun encrypt(plain: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, encryptionKey())
        val iv = cipher.iv
        return byteArrayOf(iv.size.toByte()) + iv + cipher.doFinal(plain)
    }

    private fun decrypt(packed: ByteArray): ByteArray {
        require(packed.isNotEmpty()) { "Encrypted content is empty." }
        val ivLength = packed[0].toInt() and 0xff
        require(ivLength in 12..16 && packed.size > 1 + ivLength) {
            "Encrypted content header is invalid."
        }
        val iv = packed.copyOfRange(1, 1 + ivLength)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            encryptionKey(),
            GCMParameterSpec(128, iv)
        )
        return cipher.doFinal(packed.copyOfRange(1 + ivLength, packed.size))
    }

    fun saveSecret(context: Context, name: String, value: String) {
        require(name.matches(Regex("[a-z_]{2,40}")))
        val encrypted = encrypt(value.toByteArray(StandardCharsets.UTF_8))
        preferences(context).edit()
            .putString("secret_$name", Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .apply()
    }

    fun readSecret(context: Context, name: String): String? {
        val encoded = preferences(context).getString("secret_$name", null) ?: return null
        val encrypted = Base64.decode(encoded, Base64.NO_WRAP)
        return String(decrypt(encrypted), StandardCharsets.UTF_8)
    }

    fun isConfigured(context: Context): Boolean =
        !readSecret(context, "base_url").isNullOrBlank() &&
            !readSecret(context, "device_token").isNullOrBlank()

    fun setAllowedPackages(context: Context, packages: Collection<String>) {
        val pattern = Regex("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+")
        val clean = packages.map { it.trim() }.filter { pattern.matches(it) }.distinct().sorted()
        preferences(context).edit().putString("allowed_packages", JSONArray(clean).toString()).apply()
    }

    fun getAllowedPackages(context: Context): Set<String> {
        val array = JSONArray(preferences(context).getString("allowed_packages", "[]") ?: "[]")
        return (0 until array.length()).mapNotNull { array.optString(it, null) }.toSet()
    }

    fun setSyncStatus(context: Context, value: String) {
        preferences(context).edit().putString("sync_status", value.take(160)).apply()
    }

    fun getSyncStatus(context: Context): String =
        preferences(context).getString("sync_status", "لم تبدأ المزامنة") ?: "لم تبدأ المزامنة"

    fun setQueueOverflow(context: Context, value: Boolean) {
        preferences(context).edit().putBoolean("queue_overflow", value).apply()
    }

    fun hasQueueOverflow(context: Context): Boolean =
        preferences(context).getBoolean("queue_overflow", false)

    private fun atomicQueue(context: Context) =
        AtomicFile(File(context.filesDir, QUEUE_FILE))

    private fun readQueue(context: Context): JSONArray {
        val input = try {
            atomicQueue(context).openRead()
        } catch (_: java.io.FileNotFoundException) {
            return JSONArray()
        }
        input.use {
            return JSONArray(String(decrypt(it.readBytes()), StandardCharsets.UTF_8))
        }
    }

    private fun writeQueue(context: Context, queue: JSONArray) {
        val atomic = atomicQueue(context)
        var output: FileOutputStream? = null
        try {
            output = atomic.startWrite()
            output.write(encrypt(queue.toString().toByteArray(StandardCharsets.UTF_8)))
            output.fd.sync()
            atomic.finishWrite(output)
        } catch (error: Exception) {
            if (output != null) atomic.failWrite(output)
            throw error
        }
    }

    fun appendEvent(context: Context, event: JSONObject) = synchronized(lock) {
        val queue = readQueue(context)
        if (queue.length() >= MAX_QUEUED_EVENTS) {
            setQueueOverflow(context, true)
            throw IllegalStateException("Encrypted event queue is full.")
        }
        queue.put(JSONObject(event.toString()))
        writeQueue(context, queue)
    }

    fun nextEvent(context: Context): JSONObject? = synchronized(lock) {
        val queue = readQueue(context)
        if (queue.length() == 0) null else JSONObject(queue.getJSONObject(0).toString())
    }

    fun removeEvent(context: Context, eventUuid: String) = synchronized(lock) {
        val queue = readQueue(context)
        val remaining = JSONArray()
        for (index in 0 until queue.length()) {
            val event = queue.getJSONObject(index)
            if (event.optString("event_uuid") != eventUuid) remaining.put(event)
        }
        writeQueue(context, remaining)
        if (remaining.length() < MAX_QUEUED_EVENTS) setQueueOverflow(context, false)
    }

    fun queueCount(context: Context): Int = synchronized(lock) { readQueue(context).length() }
}
