package com.raudev.compass.bridge

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.work.WorkInfo
import androidx.work.WorkManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.DateFormat
import java.util.Date

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BridgeTheme {
                Surface(Modifier.fillMaxSize()) { BridgeScreen() }
            }
        }
    }
}

/** What Health Connect and the system currently allow, read again on every resume. */
private data class DeviceState(
    val sdkStatus: Int = HealthConnectClient.SDK_UNAVAILABLE,
    val grantedTypes: Int = 0,
    val background: Boolean = false,
    val history: Boolean = false,
    val backgroundFeature: Boolean = false,
    val batteryUnrestricted: Boolean = false,
)

@SuppressLint("BatteryLife") // Self-installed app; the hourly sync needs to survive Samsung's battery saver.
@Composable
private fun BridgeScreen() {
    val context = LocalContext.current
    val settings = remember { Settings(context) }
    val scope = rememberCoroutineScope()

    var url by rememberSaveable { mutableStateOf(settings.serverUrl) }
    var token by rememberSaveable { mutableStateOf(settings.token) }
    var days by rememberSaveable { mutableStateOf(settings.initialDays.toString()) }
    var connection by remember { mutableStateOf<String?>(null) }
    var device by remember { mutableStateOf(DeviceState()) }
    var refresh by remember { mutableIntStateOf(0) }

    suspend fun readDeviceState() {
        val status = HealthConnectClient.getSdkStatus(context)
        val power = context.getSystemService(PowerManager::class.java)
        val battery = power.isIgnoringBatteryOptimizations(context.packageName)
        if (status != HealthConnectClient.SDK_AVAILABLE) {
            device = DeviceState(sdkStatus = status, batteryUnrestricted = battery)
            return
        }
        val client = HealthConnectClient.getOrCreate(context)
        val granted = client.permissionController.getGrantedPermissions()
        device = DeviceState(
            sdkStatus = status,
            grantedTypes = HealthTypes.ALL.count { it.permission in granted },
            background = HealthTypes.BACKGROUND in granted,
            history = HealthTypes.HISTORY in granted,
            backgroundFeature = client.features.getFeatureStatus(
                HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND,
            ) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE,
            batteryUnrestricted = battery,
        )
        if (settings.configured && device.grantedTypes > 0) {
            SyncWorker.schedule(context)
            // Opening the app brings Compass up to date, e.g. right after Zepp synced the night.
            SyncWorker.runNow(context)
        }
    }

    LifecycleResumeEffect(Unit) {
        scope.launch { readDeviceState() }
        onPauseOrDispose {}
    }

    val permissions = rememberLauncherForActivityResult(
        PermissionController.createRequestPermissionResultContract(),
    ) { scope.launch { readDeviceState() } }

    val work by WorkManager.getInstance(context)
        .getWorkInfosForUniqueWorkFlow(SyncWorker.NOW)
        .collectAsStateWithLifecycle(emptyList())
    val running = work.any { it.state == WorkInfo.State.RUNNING || it.state == WorkInfo.State.ENQUEUED }
    // Settings are plain preferences; read them again whenever the job state changes.
    val status = remember(work, refresh) {
        Triple(settings.lastSyncAt, settings.lastResult, settings.lastError)
    }

    Column(
        Modifier
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Compass Bridge", style = MaterialTheme.typography.headlineMedium)

        Section("Server") {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text("Adresse, z. B. https://compass.example.com") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("Token (HEALTHCONNECT_TOKEN)") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
            )
            Button(onClick = {
                settings.serverUrl = url
                settings.token = token
                url = settings.serverUrl
                connection = "Teste …"
                scope.launch {
                    connection = withContext(Dispatchers.IO) {
                        runCatching { Api(settings.serverUrl, settings.token).status() }.fold(
                            onSuccess = { last -> "Verbunden. Letzter Sync laut Server: ${last ?: "noch keiner"}" },
                            onFailure = { "Fehler: ${it.message ?: it.javaClass.simpleName}" },
                        )
                    }
                    readDeviceState()
                }
            }) { Text("Speichern und testen") }
            connection?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        }

        Section("Health Connect") {
            when (device.sdkStatus) {
                HealthConnectClient.SDK_AVAILABLE -> {
                    Line("Datentypen freigegeben", "${device.grantedTypes} von ${HealthTypes.ALL.size}")
                    Line(
                        "Lesen im Hintergrund",
                        when {
                            !device.backgroundFeature -> "vom Gerät nicht unterstützt"
                            device.background -> "erlaubt"
                            else -> "nicht erlaubt"
                        },
                    )
                    Line("Ältere Daten (Verlauf)", if (device.history) "erlaubt" else "nur 30 Tage")
                    Button(onClick = { permissions.launch(HealthTypes.PERMISSIONS) }) {
                        Text("Berechtigungen erteilen")
                    }
                }
                HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED ->
                    Text("Health Connect muss aktualisiert werden.")
                else -> Text("Health Connect ist auf diesem Gerät nicht verfügbar.")
            }
        }

        Section("Akku") {
            Line(
                "Akku-Optimierung",
                if (device.batteryUnrestricted) "aus (gut)" else "an, Sync kann ausfallen",
            )
            if (!device.batteryUnrestricted) {
                OutlinedButton(onClick = {
                    context.startActivity(
                        Intent(
                            AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            "package:${context.packageName}".toUri(),
                        ),
                    )
                }) { Text("Akku-Optimierung ausschalten") }
                Text(
                    "Bei Samsung zusätzlich: App nicht unter \"Schlafende Apps\" oder \"Apps im Tiefschlaf\".",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        Section("Sync") {
            val (lastAt, lastResult, lastError) = status
            Line(
                "Letzter Sync",
                if (lastAt == 0L) "noch keiner"
                else DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(lastAt)),
            )
            if (lastResult.isNotEmpty()) Line("Ergebnis", lastResult)
            if (lastError.isNotEmpty()) {
                Text("Fehler: $lastError", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            OutlinedTextField(
                value = days,
                onValueChange = { value ->
                    days = value.filter(Char::isDigit).take(4)
                    days.toIntOrNull()?.let { settings.initialDays = it }
                },
                label = { Text("Erster Sync: so viele Tage zurück") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { SyncWorker.runNow(context) },
                    enabled = !running && settings.configured && device.grantedTypes > 0,
                ) { Text(if (running) "Läuft …" else "Jetzt synchronisieren") }
                TextButton(onClick = {
                    settings.resetSync()
                    refresh++
                }) { Text("Neu einlesen") }
            }
            Text(
                "Läuft stündlich im Hintergrund. \"Neu einlesen\" schickt beim nächsten Sync " +
                    "alles aus dem eingestellten Zeitraum noch einmal, Compass legt dabei nichts doppelt an.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            HorizontalDivider()
            content()
        }
    }
}

@Composable
private fun Line(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value)
    }
}
