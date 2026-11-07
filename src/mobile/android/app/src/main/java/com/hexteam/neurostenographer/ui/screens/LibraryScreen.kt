@file:Suppress("FunctionNaming", "MagicNumber", "ModifierMissing")

package com.hexteam.neurostenographer.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.ui.components.EmptyState
import com.hexteam.neurostenographer.ui.components.TranscriptCard

@Composable
fun LibraryScreen(
    items: List<Transcript>,
    onOpen: (Transcript) -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = 20.dp),
    ) {
        Spacer(Modifier.height(24.dp))
        Text("Мои записи", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(18.dp))
        if (items.isEmpty()) {
            EmptyState("Расшифровок пока нет")
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(items, key = Transcript::id) { transcript ->
                    TranscriptCard(transcript) { onOpen(transcript) }
                }
            }
        }
    }
}
