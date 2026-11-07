@file:Suppress("FunctionNaming", "MagicNumber", "ModifierMissing")

package com.hexteam.neurostenographer.ui.screens

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.data.model.Utterance
import com.hexteam.neurostenographer.ui.components.EmptyState
import com.hexteam.neurostenographer.ui.components.ErrorCard
import com.hexteam.neurostenographer.ui.components.SpeakerChip
import com.hexteam.neurostenographer.ui.components.SummaryDialog
import com.hexteam.neurostenographer.ui.components.formatTime
import com.hexteam.neurostenographer.ui.viewmodel.MainState

@Composable
fun TranscriptScreen(
    state: MainState,
    transcript: Transcript,
    actions: TranscriptActions,
    jsonFor: (Transcript) -> String,
) {
    val context = LocalContext.current
    val export =
        rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
            uri?.let {
                context.contentResolver.openOutputStream(it)?.use { output ->
                    output.write(jsonFor(transcript).toByteArray())
                }
                Toast.makeText(context, "JSON сохранён", Toast.LENGTH_SHORT).show()
            }
        }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = actions.onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, null) }
            Text(
                transcript.title,
                Modifier.weight(1f),
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (state.summaryAvailable) {
                IconButton(onClick = { actions.onSummarize(transcript) }) {
                    Icon(Icons.Default.AutoAwesome, null)
                }
            }
            IconButton(onClick = { export.launch(transcript.title + ".json") }) {
                Icon(Icons.Default.FileDownload, null)
            }
        }
        if (state.summarizing) {
            LinearProgressIndicator(
                progress = { state.progress / 100f },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
            )
            Text(
                state.stageLabel.ifBlank { "Локальное резюме" },
                Modifier.padding(horizontal = 20.dp, vertical = 6.dp),
                style = MaterialTheme.typography.bodySmall,
            )
        }
        state.error?.let {
            ErrorCard(it, onDismiss = null)
        }
        if (transcript.utterances.isEmpty()) {
            EmptyState("В этой записи не найдено речи")
        } else {
            LazyColumn(
                Modifier.padding(horizontal = 20.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(transcript.utterances, key = Utterance::id) { utterance ->
                    UtteranceCard(utterance)
                }
            }
        }
    }
    state.summary?.let { SummaryDialog(it, actions.onDismissSummary) }
}

@Composable
private fun UtteranceCard(utterance: Utterance) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                SpeakerChip(utterance.speakerId)
                Spacer(Modifier.weight(1f))
                Text(
                    formatTime(utterance.startMs) + " – " + formatTime(utterance.endMs),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(utterance.text)
        }
    }
}
