package com.raudev.compass.bridge

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Compass palette: paper, ink, brass.
private val Light = lightColorScheme(
    primary = Color(0xFFB07D2B),
    onPrimary = Color.White,
    background = Color(0xFFEEF2F0),
    surface = Color(0xFFEEF2F0),
    surfaceContainer = Color(0xFFF8FAF9),
    onBackground = Color(0xFF14202B),
    onSurface = Color(0xFF14202B),
    onSurfaceVariant = Color(0xFF5E6B74),
    error = Color(0xFFD1343B),
)

private val Dark = darkColorScheme(
    primary = Color(0xFFD3A04E),
    onPrimary = Color(0xFF14202B),
    background = Color(0xFF0F1A24),
    surface = Color(0xFF0F1A24),
    surfaceContainer = Color(0xFF15232F),
    onBackground = Color(0xFFE4EBE8),
    onSurface = Color(0xFFE4EBE8),
    onSurfaceVariant = Color(0xFF8D9AA3),
    error = Color(0xFFF06A6F),
)

@Composable
fun BridgeTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}
