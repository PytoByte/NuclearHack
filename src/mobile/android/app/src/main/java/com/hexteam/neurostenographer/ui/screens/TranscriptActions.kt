package com.hexteam.neurostenographer.ui.screens

import com.hexteam.neurostenographer.data.model.Transcript

data class TranscriptActions(
    val onBack: () -> Unit,
    val onSummarize: (Transcript) -> Unit,
    val onDismissSummary: () -> Unit,
)
