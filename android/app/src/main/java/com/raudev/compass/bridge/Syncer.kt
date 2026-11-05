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
import org.json.JSONArray
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
        check(settings.configured) { context.getString(R.string.error_not_configured) }
        check(HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE) {
            context.getString(R.string.error_hc_unavailable)
        }
        val client = HealthConnectClient.getOrCreate(context)
        val granted = client.permissionController.getGrantedPermissions()
        val types = HealthTypes.ALL.filter { it.permission in granted }
        check(types.isNotEmpty()) { context.getString(R.string.error_no_permission) }

        val typesKey = types.joinToString(",") { it.name }
        val batch = Batch(Api(context, settings.serverUrl, settings.token))
        val token = settings.changesToken.takeIf { settings.changesTypes == typesKey }
        if (token == null || !readChanges(client, token, batch)) {
            readWindow(client, types, typesKey, batch)
        }
        batch.flush()
        snapshot(client, types, batch)
        context.getString(R.string.sync_result, batch.sent, batch.deletedSent)
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

    /**
     * Everything Health Connect has of the small types for the last days ([SNAPSHOT_DAYS]), one
     * request per type. The server stores what is listed and drops what is missing, so a rewrite
     * that the change feed did not deliver (Zepp rewrites a night several times) still arrives.
     */
    private suspend fun snapshot(client: HealthConnectClient, types: List<HealthType>, batch: Batch) {
        for (type in types) {
            val days = SNAPSHOT_DAYS[type.name] ?: continue
            val since = Instant.now().minus(Duration.ofDays(days))
            val records = mutableListOf<JSONObject>()
            readAll(client, type.recordClass, since) { record ->
                HealthTypes.toJson(record)?.let { records += it }
            }
            if (records.size > MAX_RECORDS) {
                // Too many for one request; send them as normal records, without the snapshot.
                records.forEach { batch.add(it) }
                batch.flush()
                continue
            }
            val ids = records.map { it.getString("id") }
            batch.snapshot(records, type.name, since, ids)
        }
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

    /**
     * Collects records and posts them in chunks small enough for one request. Per id only the last
     * change counts: Zepp deletes and rewrites a night under the same id, and the server cannot
     * tell the order of a record and a deletion within one request.
     */
    private class Batch(private val api: Api) {
        private val records = LinkedHashMap<String, JSONObject>()
        private val deleted = LinkedHashSet<String>()
        private var bytes = 0
        var sent = 0
            private set
        var deletedSent = 0
            private set

        fun add(record: JSONObject) {
            val id = record.getString("id")
            deleted -= id
            records[id] = record
            bytes += record.toString().length
            if (records.size >= MAX_RECORDS || bytes >= MAX_BYTES) flush()
        }

        fun delete(id: String) {
            records -= id
            deleted += id
            if (deleted.size >= MAX_RECORDS) flush()
        }

        fun snapshot(records: List<JSONObject>, type: String, since: Instant, ids: List<String>) {
            flush()
            val snapshot = JSONObject()
                .put("type", type)
                .put("since", since.toString())
                .put("ids", JSONArray(ids))
            api.upload(records, emptyList(), snapshot)
            sent += records.size
        }

        fun flush() {
            if (records.isEmpty() && deleted.isEmpty()) return
            api.upload(records.values.toList(), deleted.toList())
            sent += records.size
            deletedSent += deleted.size
            records.clear()
            deleted.clear()
            bytes = 0
        }
    }

    companion object {
        private const val MAX_RECORDS = 500
        /**
         * How far back each small type is compared. Nutrition and weight reach further: MFP
         * rewrites older days under new ids (25.10.2026 again on 28.10), and with three days the
         * old ids were out of range and stayed, so the day counted twice. MFP writes about four
         * records a day, far below [MAX_RECORDS].
         */
        private val SNAPSHOT_DAYS = mapOf(
            "sleep" to 3L,
            "exercise" to 3L,
            "nutrition" to 14L,
            "weight" to 14L,
        )
        private const val MAX_BYTES = 4_000_000

        /** The periodic job and "sync now" must not read and move the token at the same time. */
        private val lock = Mutex()
    }
}
