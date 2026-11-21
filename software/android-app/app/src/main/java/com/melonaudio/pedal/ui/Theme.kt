package com.melonaudio.pedal.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Same tokens as the pedal's LCD (docs/lcd-gui-design.md §3). */
object Melon {
    val ground = Color(0xFF0D1610)
    val surface = Color(0xFF172A1F)
    val surfaceHigh = Color(0xFF203629)
    val line = Color(0xFF2E4A39)
    val rind = Color(0xFF1E3A2B)
    val cream = Color(0xFFF3ECD6)
    val sage = Color(0xFF93AC9A)
    val dim = Color(0xFF7A9582)
    val lime = Color(0xFFA6E07A)
    val amber = Color(0xFFFFB547)
    val bypass = Color(0xFFC8262B)
    val flesh = Color(0xFFFF7B8A)
}

@Composable
fun MelonTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Melon.lime,
            onPrimary = Melon.ground,
            primaryContainer = Melon.rind,
            onPrimaryContainer = Melon.cream,
            secondary = Melon.amber,
            onSecondary = Melon.ground,
            secondaryContainer = Melon.rind,
            onSecondaryContainer = Melon.cream,
            background = Melon.ground,
            onBackground = Melon.cream,
            surface = Melon.ground,
            onSurface = Melon.cream,
            surfaceVariant = Melon.surface,
            onSurfaceVariant = Melon.sage,
            surfaceContainerLowest = Melon.ground,
            surfaceContainerLow = Melon.surface,
            surfaceContainer = Melon.surface,
            surfaceContainerHigh = Melon.surfaceHigh,
            surfaceContainerHighest = Melon.surfaceHigh,
            outline = Melon.line,
            outlineVariant = Melon.line,
            error = Melon.bypass,
            onError = Color.White,
        ),
        content = content,
    )
}
