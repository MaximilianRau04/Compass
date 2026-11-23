package com.raudev.compass.bridge

import android.content.Context
import androidx.core.content.edit

/** App settings and sync state in private SharedPreferences (not backed up, see the manifest). */
class Settings(context: Context) {
    private val prefs = context.getSharedPreferences("compass-bridge", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", "") ?: ""
        set(value) = prefs.edit { putString("server_url", value.trim().trimEnd('/')) }

    var token: String
        get() {
            val raw = prefs.getString("token", "") ?: ""
            if (raw.isEmpty()) return ""
            if (TokenCipher.isEncrypted(raw)) return SecretStore.decrypt(raw) ?: ""
            // Migrate plaintext tokens written by older app versions on first read.
            runCatching { prefs.edit { putString("token", SecretStore.encrypt(raw)) } }
            return raw
        }
        set(value) {
            val clean = value.trim()
            val stored = if (clean.isEmpty()) "" else SecretStore.encrypt(clean)
            prefs.edit { putString("token", stored) }
        }

    /** How far back the first sync (and a reset) reads. Without the history permission Health
     * Connect only returns the last 30 days anyway. */
    var initialDays: Int
        get() = prefs.getInt("initial_days", 30)
        set(value) = prefs.edit { putInt("initial_days", value.coerceIn(1, 3650)) }

    /** Health Connect changes token and the record types it was created for. */
    var changesToken: String?
        get() = prefs.getString("changes_token", null)
        set(value) = prefs.edit { putString("changes_token", value) }

    var changesTypes: String?
        get() = prefs.getString("changes_types", null)
        set(value) = prefs.edit { putString("changes_types", value) }

    var lastSyncAt: Long
        get() = prefs.getLong("last_sync_at", 0)
        set(value) = prefs.edit { putLong("last_sync_at", value) }

    var lastResult: String
        get() = prefs.getString("last_result", "") ?: ""
        set(value) = prefs.edit { putString("last_result", value) }

    var lastError: String
        get() = prefs.getString("last_error", "") ?: ""
        set(value) = prefs.edit { putString("last_error", value) }

    val configured: Boolean get() = serverUrl.isNotEmpty() && token.isNotEmpty()

    fun resetSync() = prefs.edit {
        remove("changes_token")
        remove("changes_types")
    }
}
