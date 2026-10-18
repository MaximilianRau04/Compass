package com.raudev.compass.bridge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Required by Health Connect: explains what the app does with the data. */
class RationaleActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            BridgeTheme {
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.safeDrawingPadding().padding(24.dp)) {
                        Text("Compass Bridge", style = MaterialTheme.typography.headlineSmall)
                        Text(
                            "Die App liest Schlaf, Schritte, Herzfrequenz, Ruhepuls, Trainings, " +
                                "Ernährung, Gewicht und verbrannte Kalorien aus Health Connect und " +
                                "schickt sie an deinen eigenen Compass-Server, den du in der App " +
                                "einträgst. Sie schreibt nichts in Health Connect und gibt keine " +
                                "Daten an Dritte weiter.",
                            Modifier.padding(top = 12.dp),
                        )
                    }
                }
            }
        }
    }
}
