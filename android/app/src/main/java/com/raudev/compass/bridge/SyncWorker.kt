package com.raudev.compass.bridge

import android.content.Context
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.concurrent.TimeUnit

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val settings = Settings(applicationContext)
        return try {
            val summary = withContext(Dispatchers.IO) { Syncer(applicationContext, settings).run() }
            settings.lastSyncAt = System.currentTimeMillis()
            settings.lastResult = summary
            settings.lastError = ""
            Result.success()
        } catch (e: CancellationException) {
            // WorkManager stopped the job (constraints lost, rescheduled). Not a sync error.
            throw e
        } catch (e: IOException) {
            // Offline, VPN down or a server error: WorkManager tries again with backoff.
            fail(settings, "Netzwerk: ${e.message ?: e.javaClass.simpleName}", e)
            if (runAttemptCount < MAX_RETRIES) Result.retry() else Result.failure()
        } catch (e: SecurityException) {
            fail(settings, "Health Connect verweigert das Lesen (Hintergrund-Berechtigung?): ${e.message}", e)
            Result.failure()
        } catch (e: Exception) {
            fail(settings, e.message ?: e.javaClass.simpleName, e)
            Result.failure()
        }
    }

    private fun fail(settings: Settings, message: String, e: Exception) {
        Log.w(TAG, message, e)
        settings.lastError = message
    }

    companion object {
        private const val TAG = "CompassSync"
        private const val PERIODIC = "compass-sync"
        const val NOW = "compass-sync-now"
        private const val MAX_RETRIES = 5

        private val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        /** Hourly in the background. KEEP: replacing the schedule would cancel a running sync. */
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(1, TimeUnit.HOURS)
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 5, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request)
        }

        fun runNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, request)
        }
    }
}
