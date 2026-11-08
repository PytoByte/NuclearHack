@file:Suppress("FunctionNaming", "MagicNumber", "ModifierMissing", "TooManyFunctions", "Indentation")

package com.hexteam.neurostenographer.ui.components

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage
import com.hexteam.neurostenographer.ui.viewmodel.ProgressHealth

@Composable
fun TranscriptCard(
    transcript: Transcript,
    onClick: () -> Unit,
) {
    Card(onClick = onClick, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(46.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer),
                Alignment.Center,
            ) {
                Icon(Icons.Default.GraphicEq, null, tint = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(transcript.title, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    transcript.createdAt + "  •  " + transcript.utterances.size + " реплик",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Suppress("LongMethod", "LongParameterList")
@Composable
fun ProcessingCard(
    stage: ProcessingStage,
    progress: Int,
    label: String,
    elapsedMs: Long,
    health: ProgressHealth,
    nativeStage: String,
    nativeDone: Long,
    nativeTotal: Long,
    diagnostics: List<String>,
    onCancel: () -> Unit,
) {
    var showDiagnostics by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(false) }
    Card(
        Modifier
            .fillMaxWidth()
            .padding(top = 12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(label.ifBlank { "Обработка" }, fontWeight = FontWeight.Bold)
                Spacer(Modifier.weight(1f))
                Text(
                    progressStateLabel(health),
                    style = MaterialTheme.typography.bodySmall,
                    color = progressHealthColor(health),
                    modifier =
                        Modifier.semantics {
                            liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite
                            contentDescription =
                                "Состояние обработки: " + progressStateLabel(health)
                        },
                )
            }
            Spacer(Modifier.height(12.dp))
            LinearProgressIndicator(
                progress = { progress.coerceIn(0, 100) / 100f },
                modifier = Modifier.fillMaxWidth(),
                trackColor = MaterialTheme.colorScheme.surfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("$progress%", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.width(12.dp))
                Text("Прошло ${formatElapsed(elapsedMs)}", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { showDiagnostics = true }) { Text("Подробности") }
                if (stage != ProcessingStage.Complete) {
                    TextButton(onClick = onCancel) { Text("Отмена") }
                }
            }
            if (nativeStage.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "Этап SDK: $nativeStage ($nativeDone/$nativeTotal)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(2.dp))
            Text(
                "Состояние: " +
                    when (health) {
                        ProgressHealth.Progressing -> "активно"
                        ProgressHealth.Waiting -> "давно не было событий SDK"
                        ProgressHealth.Stalled -> "нет обновлений давно"
                        ProgressHealth.Idle -> "готово"
                    },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    if (showDiagnostics) {
        DiagnosticsDialog(
            text =
                buildDiagnosticsText(
                    progress,
                    label,
                    elapsedMs,
                    health,
                    nativeStage,
                    nativeDone,
                    nativeTotal,
                    diagnostics,
                ),
            onDismiss = { showDiagnostics = false },
        )
    }
}

@Composable
private fun progressHealthColor(health: ProgressHealth) =
    when (health) {
        ProgressHealth.Progressing -> MaterialTheme.colorScheme.primary
        ProgressHealth.Waiting -> MaterialTheme.colorScheme.tertiary
        ProgressHealth.Stalled -> MaterialTheme.colorScheme.error
        ProgressHealth.Idle -> MaterialTheme.colorScheme.onSurfaceVariant
    }

private fun progressStateLabel(health: ProgressHealth): String =
    when (health) {
        ProgressHealth.Progressing -> "Идёт"
        ProgressHealth.Waiting -> "Ожидание"
        ProgressHealth.Stalled -> "Нет ответа"
        ProgressHealth.Idle -> "Готово"
    }

@Suppress("LongParameterList")
private fun buildDiagnosticsText(
    progress: Int,
    label: String,
    elapsedMs: Long,
    health: ProgressHealth,
    nativeStage: String,
    nativeDone: Long,
    nativeTotal: Long,
    diagnostics: List<String>,
): String =
    buildString {
        appendLine("Текущий этап: $label")
        appendLine("Прогресс: $progress%")
        appendLine("Прошло: ${formatElapsed(elapsedMs)}")
        appendLine("Состояние: ${progressStateLabel(health)}")
        appendLine("Этап SDK: ${nativeStage.ifBlank { "-" }}")
        appendLine("Счётчики SDK: $nativeDone / $nativeTotal")
        appendLine("Записей диагностики: ${diagnostics.size}")
        appendLine()
        appendLine("Журнал:")
        if (diagnostics.isEmpty()) {
            appendLine("Нет записей.")
        } else {
            diagnostics.forEach { appendLine(it) }
        }
    }

@Composable
fun DiagnosticsDialog(
    text: String,
    onDismiss: () -> Unit,
) {
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { androidx.compose.material3.TextButton(onClick = onDismiss) { Text("Закрыть") } },
        title = { Text("Диагностика обработки") },
        text = {
            Box(
                Modifier
                    .heightIn(max = 420.dp)
                    .verticalScroll(rememberScrollState()),
            ) {
                Text(text, style = MaterialTheme.typography.bodySmall)
            }
        },
    )
}

@Composable
fun EmptyState(
    text: String,
    icon: ImageVector = Icons.Default.GraphicEq,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(icon, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun ErrorCard(
    message: String,
    onDismiss: (() -> Unit)? = null,
) {
    Card(
        Modifier
            .fillMaxWidth()
            .padding(top = 12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Warning, null, tint = MaterialTheme.colorScheme.onErrorContainer)
                Spacer(Modifier.width(8.dp))
                Text("Ошибка", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onErrorContainer)
            }
            Spacer(Modifier.height(8.dp))
            Text(message, color = MaterialTheme.colorScheme.onErrorContainer)
            if (onDismiss != null) {
                TextButton(onClick = onDismiss) { Text("Закрыть") }
            }
        }
    }
}

@Composable
fun SpeakerChip(speakerId: String) {
    AssistChip(onClick = {}, label = { Text(speakerLabel(speakerId)) })
}

@Composable
fun SummaryDialog(
    text: String,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Закрыть") } },
        title = { Text("Локальное резюме") },
        text = {
            Box(
                Modifier
                    .heightIn(max = 420.dp)
                    .verticalScroll(rememberScrollState()),
            ) {
                Text(text)
            }
        },
    )
}

fun speakerLabel(speakerId: String): String {
    val number = speakerId.takeLastWhile(Char::isDigit)
    return if (number.isNotEmpty()) "Спикер $number" else speakerId
}

fun formatTime(milliseconds: Long): String {
    val seconds = milliseconds / 1000
    return "%02d:%02d".format(seconds / 60, seconds % 60)
}

fun formatElapsed(milliseconds: Long): String {
    val totalSeconds = (milliseconds / 1000).coerceAtLeast(0L)
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, seconds) else "%02d:%02d".format(minutes, seconds)
}

fun displayName(
    context: Context,
    uri: Uri,
): String =
    context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
        val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
    } ?: uri.lastPathSegment ?: "audio"
