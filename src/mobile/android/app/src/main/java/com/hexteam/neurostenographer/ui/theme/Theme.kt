package com.hexteam.neurostenographer.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private val DarkColors = darkColorScheme(
    primary = Color(0xFFB7A8FF), onPrimary = Color(0xFF211A4A), primaryContainer = Color(0xFF3A3172),
    background = Color(0xFF101117), onBackground = Color(0xFFF3F3F7), surface = Color(0xFF191A22),
    onSurface = Color(0xFFF3F3F7), surfaceVariant = Color(0xFF292A35), outline = Color(0xFF474955),
    secondary = Color(0xFF65DDBB)
)
val AppShapes = Shapes(extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(16.dp), large = RoundedCornerShape(24.dp))

@Composable fun NeuroTheme(content: @Composable () -> Unit) = MaterialTheme(colorScheme = DarkColors, typography = Typography(), shapes = AppShapes, content = content)
