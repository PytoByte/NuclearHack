@file:Suppress("FunctionNaming", "MagicNumber", "ModifierMissing")

package com.hexteam.neurostenographer.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.FileUpload
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.ui.components.EmptyState
import com.hexteam.neurostenographer.ui.components.ErrorCard
import com.hexteam.neurostenographer.ui.components.ProcessingCard
import com.hexteam.neurostenographer.ui.components.TranscriptCard
import com.hexteam.neurostenographer.ui.components.displayName
import com.hexteam.neurostenographer.ui.viewmodel.MainState
import com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage

@Composable
fun HomeScreen(
    state: MainState,
    onImport: (Uri, String) -> Unit,
    onOpen: (Transcript) -> Unit,
    onCancel: () -> Unit,
    onDismissError: () -> Unit,
) {
    val context = LocalContext.current
    val picker =
        rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            if (uri != null) onImport(uri, displayName(context, uri))
        }
    val idle = state.processing == ProcessingStage.Idle
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp),
    ) {
        Spacer(Modifier.height(24.dp))
        Header()
        Spacer(Modifier.height(28.dp))
        Text("Новый материал", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(18.dp))
        ImportCard(enabled = idle) { picker.launch(arrayOf("audio/*")) }
        if (!state.nativeAvailable) {
            ErrorCard(
                "Нативный аудиомодуль не упакован в APK. Соберите приложение командой make android-app.",
            )
        }
        state.error?.let { ErrorCard(it, onDismissError) }
        Spacer(Modifier.height(28.dp))
        Text("Недавняя расшифровка", fontWeight = FontWeight.Bold)
        when {
            state.processing != ProcessingStage.Idle ->
                ProcessingCard(
                    stage = state.processing,
                    progress = state.progress,
                    label = state.stageLabel,
                    elapsedMs = state.elapsedMs,
                    health = state.progressHealth,
                    nativeStage = state.nativeStage,
                    nativeDone = state.nativeDone,
                    nativeTotal = state.nativeTotal,
                    diagnostics = state.diagnosticLog,
                    onCancel = onCancel,
                )

            state.transcripts.isNotEmpty() -> {
                val latest = state.transcripts.first()
                Spacer(Modifier.height(12.dp))
                TranscriptCard(latest) { onOpen(latest) }
            }

            else -> EmptyState("Импортируйте аудиофайл, чтобы начать")
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun Header() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Default.AutoAwesome, null, tint = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.width(10.dp))
        Text("Neurostenographer", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun ImportCard(
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Card(
        onClick = onClick,
        enabled = enabled,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(22.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(54.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.primary),
                Alignment.Center,
            ) {
                Icon(Icons.Default.FileUpload, null, tint = MaterialTheme.colorScheme.onPrimary)
            }
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text("Импорт аудио", fontWeight = FontWeight.Bold)
                Text("MP3, M4A, WAV — обработка на устройстве", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.Default.ChevronRight, null)
        }
    }
}
