package com.smartnet.walletcollector

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.locks.ReentrantLock

class WalletSyncJobService : JobService() {
    private val workers = ConcurrentHashMap<Int, Thread>()
    private val completionFlags = ConcurrentHashMap<Int, AtomicBoolean>()
    private val syncLock = ReentrantLock()

    override fun onStartJob(params: JobParameters): Boolean {
        val completed = AtomicBoolean(false)
        completionFlags[params.jobId] = completed
        val worker = Thread({
            val retry = try {
                syncLock.lockInterruptibly()
                try {
                    synchronize()
                } finally {
                    syncLock.unlock()
                }
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
                true
            } catch (_: Exception) {
                SecureStorage.setSyncStatus(this, "تعذر الاتصال بالخادم؛ ستتم إعادة المحاولة.")
                true
            }

            workers.remove(params.jobId)
            completionFlags.remove(params.jobId)
            if (completed.compareAndSet(false, true)) {
                jobFinished(params, retry)
            }
        }, "SmartNetWalletSync-${params.jobId}")
        workers[params.jobId] = worker
        worker.start()
        return true
    }

    override fun onStopJob(params: JobParameters): Boolean {
        completionFlags.remove(params.jobId)?.set(true)
        workers.remove(params.jobId)?.interrupt()
        return true
    }

    private fun synchronize(): Boolean {
        if (!SecureStorage.isConfigured(this)) {
            SecureStorage.setSyncStatus(this, "أدخل عنوان الخادم ورمز الهاتف أولاً.")
            return false
        }

        val heartbeat = WalletApi.heartbeat(this, NotificationAccess.isGranted(this))
        if (!heartbeat.isSuccessful) return handleFailure(heartbeat.statusCode)

        val configResponse = WalletApi.configuration(this)
        if (!configResponse.isSuccessful) return handleFailure(configResponse.statusCode)
        val config = JSONObject(configResponse.body)
        val packageArray = config.optJSONArray("allowed_packages") ?: JSONArray()
        val packages = (0 until packageArray.length())
            .mapNotNull { index -> packageArray.optString(index, null) }
        SecureStorage.setAllowedPackages(this, packages)

        var sent = 0
        while (!Thread.currentThread().isInterrupted) {
            val event = SecureStorage.nextEvent(this) ?: break
            val response = WalletApi.sendEvent(this, event)
            if (!response.isSuccessful) return handleFailure(response.statusCode)
            SecureStorage.removeEvent(this, event.optString("event_uuid"))
            sent += 1
        }

        val remaining = SecureStorage.queueCount(this)
        SecureStorage.setSyncStatus(
            this,
            "متصل. الحزم المسموحة: ${packages.size}. المرسل: $sent. المتبقي: $remaining."
        )
        return remaining > 0
    }

    private fun handleFailure(statusCode: Int): Boolean {
        SecureStorage.setSyncStatus(this, "توقفت المزامنة برمز HTTP $statusCode.")
        if (statusCode == 401 || statusCode == 403 || statusCode == 400 || statusCode == 404) return false
        return statusCode == 429 || statusCode >= 500 || statusCode == 0
    }

    companion object {
        private const val IMMEDIATE_JOB_ID = 41801
        private const val PERIODIC_JOB_ID = 41802
        private const val PERIODIC_INTERVAL_MS = 15L * 60L * 1000L

        private fun scheduler(context: Context) =
            context.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler

        fun scheduleNow(context: Context) {
            val job = JobInfo.Builder(
                IMMEDIATE_JOB_ID,
                ComponentName(context, WalletSyncJobService::class.java)
            )
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setOverrideDeadline(5_000)
                .build()
            scheduler(context).schedule(job)
        }

        fun schedulePeriodic(context: Context) {
            val job = JobInfo.Builder(
                PERIODIC_JOB_ID,
                ComponentName(context, WalletSyncJobService::class.java)
            )
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .setPeriodic(PERIODIC_INTERVAL_MS)
                .build()
            scheduler(context).schedule(job)
        }
    }
}
