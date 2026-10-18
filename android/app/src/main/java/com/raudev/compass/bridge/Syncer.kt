package com.raudev.compass.bridge

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.changes.DeletionChange
import androidx.health.connect.client.changes.UpsertionChange
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.request.ChangesTokenRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.time.Duration
import java.time.Instant
import kotlin.reflect.KClass

/**
 * One sync run: read what changed in Health Connect since the last run and post it to Compass.
 *
 * The first run (and every run after the record types changed or the changes token expired, which
 * happens after 30 days without a sync) creates a changes token first and then reads the last
 * [Settings.initialDays] days, so nothing written in between gets lost. Later runs only read the
 * changes. The token moves on only after the server accepted a batch, and the server import is
 * idempotent, so a run that breaks off halfway just sends some records again next time.
 */
class Syncer(private val context: Context, private val settings: Settings) {

    suspend fun run(): String = lock.withLock {
        check(settings.configured) { "Server-Adresse und Token fehlen" }
        check(HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE) {
            "Health Connect ist nicht verfügbar"
        }
        val client = HealthConnectClient.getOrCreate(context)
        val granted = client.permissionController.getGrantedPermissions()
        val types = HealthTypes.ALL.filter { it.permission in granted }
        check(types.isNotEmpty()) { "Keine Leseberechtigung für Health Connect" }

        val typesKey = types.joinToString(",") { it.name }
        val batch = Batch(Api(settings.serverUrl, settings.token))
        val token = settings.changesToken.takeIf { settings.changesTypes == typesKey }
        if (token == null || !readChanges(client, token, batch)) {
            readWindow(client, types, typesKey, batch)
        }
        batch.flush()
        "${batch.sent} Datensätze, ${batch.deletedSent} gelöscht"
    }

    /** Returns false when the token expired and a full read is needed instead. */
    private suspend fun readChanges(client: HealthConnectClient, start: String, batch: Batch): Boolean {
        var token = start
        while (true) {
            val response = client.getChanges(token)
            if (response.changesTokenExpired) {
                settings.resetSync()
                return false
            }
            for (change in response.changes) {
                when (change) {
                    is UpsertionChange -> HealthTypes.toJson(change.record)?.let { batch.add(it) }
                    is DeletionChange -> batch.delete(change.recordId)
                }
            }
            batch.flush()
            token = response.nextChangesToken
            settings.changesToken = token
            if (!response.hasMore) return true
        }
    }

    private suspend fun readWindow(
        client: HealthConnectClient,
        types: List<HealthType>,
        typesKey: String,
        batch: Batch,
    ) {
        val token = client.getChangesToken(ChangesTokenRequest(types.map { it.recordClass }.toSet()))
        val since = Instant.now().minus(Duration.ofDays(settings.initialDays.toLong()))
        for (type in types) {
            readAll(client, type.recordClass, since) { record ->
                HealthTypes.toJson(record)?.let { batch.add(it) }
            }
        }
        batch.flush()
        settings.changesToken = token
        settings.changesTypes = typesKey
    }

    private suspend fun <T : Record> readAll(
        client: HealthConnectClient,
        type: KClass<T>,
        since: Instant,
        each: suspend (Record) -> Unit,
    ) {
        var pageToken: String? = null
        do {
            val response = client.readRecords(
                ReadRecordsRequest(
                    recordType = type,
                    timeRangeFilter = TimeRangeFilter.after(since),
                    pageSize = 1000,
                    pageToken = pageToken,
                ),
            )
            response.records.forEach { each(it) }
            pageToken = response.pageToken
        } while (pageToken != null)
    }

    /** Collects records and posts them in chunks small enough for one request. */
    private class Batch(private val api: Api) {
        private val records = mutableListOf<JSONObject>()
        private val deleted = mutableListOf<String>()
        private var bytes = 0
        var sent = 0
            private set
        var deletedSent = 0
            private set

        fun add(record: JSONObject) {
            records += record
            bytes += record.toString().length
            if (records.size >= MAX_RECORDS || bytes >= MAX_BYTES) flush()
        }

        fun delete(id: String) {
            deleted += id
            if (deleted.size >= MAX_RECORDS) flush()
        }

        fun flush() {
            if (records.isEmpty() && deleted.isEmpty()) return
            api.upload(records, deleted)
            sent += records.size
            deletedSent += deleted.size
            records.clear()
            deleted.clear()
            bytes = 0
        }
    }

    companion object {
        private const val MAX_RECORDS = 500
        private const val MAX_BYTES = 4_000_000

        /** The periodic job and "sync now" must not read and move the token at the same time. */
        private val lock = Mutex()
    }
}
