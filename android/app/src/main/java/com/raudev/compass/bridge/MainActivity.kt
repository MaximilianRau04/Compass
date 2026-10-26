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
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
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
    val resources = LocalResources.current
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
        Text(stringResource(R.string.app_name), style = MaterialTheme.typography.headlineMedium)

        Section(stringResource(R.string.server)) {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                label = { Text(stringResource(R.string.server_url)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text(stringResource(R.string.token)) },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
            )
            Button(onClick = {
                settings.serverUrl = url
                settings.token = token
                url = settings.serverUrl
                connection = resources.getString(R.string.testing)
                scope.launch {
                    connection = withContext(Dispatchers.IO) {
                        runCatching { Api(context, settings.serverUrl, settings.token).status() }.fold(
                            onSuccess = { last ->
                                resources.getString(R.string.connected, last ?: resources.getString(R.string.none_yet))
                            },
                            onFailure = { resources.getString(R.string.error, it.message ?: it.javaClass.simpleName) },
                        )
                    }
                    readDeviceState()
                }
            }) { Text(stringResource(R.string.save_and_test)) }
            connection?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        }

        Section("Health Connect") {
            when (device.sdkStatus) {
                HealthConnectClient.SDK_AVAILABLE -> {
                    Line(stringResource(R.string.hc_types), stringResource(R.string.n_of_m, device.grantedTypes, HealthTypes.ALL.size))
                    Line(
                        stringResource(R.string.hc_background),
                        when {
                            !device.backgroundFeature -> stringResource(R.string.not_supported)
                            device.background -> stringResource(R.string.allowed)
                            else -> stringResource(R.string.not_allowed)
                        },
                    )
                    Line(
                        stringResource(R.string.hc_history),
                        stringResource(if (device.history) R.string.allowed else R.string.only_30_days),
                    )
                    Button(onClick = { permissions.launch(HealthTypes.PERMISSIONS) }) {
                        Text(stringResource(R.string.grant))
                    }
                }
                HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED ->
                    Text(stringResource(R.string.hc_update))
                else -> Text(stringResource(R.string.hc_missing))
            }
        }

        Section(stringResource(R.string.battery)) {
            Line(
                stringResource(R.string.battery_optimization),
                stringResource(if (device.batteryUnrestricted) R.string.battery_off else R.string.battery_on),
            )
            if (!device.batteryUnrestricted) {
                OutlinedButton(onClick = {
                    context.startActivity(
                        Intent(
                            AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            "package:${context.packageName}".toUri(),
                        ),
                    )
                }) { Text(stringResource(R.string.battery_turn_off)) }
                Text(
                    stringResource(R.string.battery_samsung),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        Section(stringResource(R.string.sync)) {
            val (lastAt, lastResult, lastError) = status
            Line(
                stringResource(R.string.last_sync),
                if (lastAt == 0L) stringResource(R.string.none_yet)
                else DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(lastAt)),
            )
            if (lastResult.isNotEmpty()) Line(stringResource(R.string.result), lastResult)
            if (lastError.isNotEmpty()) {
                Text(stringResource(R.string.error, lastError), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            OutlinedTextField(
                value = days,
                onValueChange = { value ->
                    days = value.filter(Char::isDigit).take(4)
                    days.toIntOrNull()?.let { settings.initialDays = it }
                },
                label = { Text(stringResource(R.string.initial_days)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { SyncWorker.runNow(context) },
                    enabled = !running && settings.configured && device.grantedTypes > 0,
                ) { Text(stringResource(if (running) R.string.running else R.string.sync_now)) }
                TextButton(onClick = {
                    settings.resetSync()
                    refresh++
                }) { Text(stringResource(R.string.read_again)) }
            }
            Text(
                stringResource(R.string.sync_hint, stringResource(R.string.read_again)),
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
