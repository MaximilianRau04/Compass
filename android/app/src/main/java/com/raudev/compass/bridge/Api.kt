package com.raudev.compass.bridge

import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** The server answered with an error that a retry will not fix (wrong token, bad data). */
class PermanentApiError(message: String) : Exception(message)

/** Client for /api/ingest/healthconnect. Plain HttpURLConnection, no extra dependencies. */
class Api(private val baseUrl: String, private val token: String) {
    private val endpoint get() = URL("$baseUrl/api/ingest/healthconnect")

    /** Checks URL and token; returns the server's last successful sync (ISO) or null. */
    fun status(): String? {
        val body = request("GET", null)
        return JSONObject(body).optString("last_success_at").takeIf { it.isNotEmpty() && it != "null" }
    }

    fun upload(records: List<JSONObject>, deleted: List<String>): JSONObject {
        val payload = JSONObject()
            .put("device", Build.MODEL)
            .put("app_version", BuildConfig.VERSION_NAME)
            .put("records", JSONArray(records))
            .put("deleted", JSONArray(deleted))
        return JSONObject(request("POST", payload.toString()))
    }

    private fun request(method: String, body: String?): String {
        val conn = endpoint.openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = 60_000
            conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Accept", "application/json")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body.toByteArray()) }
            }
            val code = conn.responseCode
            val text = (if (code < 400) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use { it.readText() } ?: ""
            return when {
                code in 200..299 -> text
                code == 401 -> throw PermanentApiError("Token abgelehnt (401)")
                code == 503 -> throw PermanentApiError("Ingest auf dem Server nicht aktiv (HEALTHCONNECT_TOKEN fehlt)")
                code in 400..499 -> throw PermanentApiError("Server lehnt ab ($code): ${text.take(300)}")
                else -> throw IOException("Serverfehler $code")
            }
        } finally {
            conn.disconnect()
        }
    }
}
