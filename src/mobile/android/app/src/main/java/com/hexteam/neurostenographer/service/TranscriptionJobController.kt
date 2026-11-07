package com.hexteam.neurostenographer.service

import com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.util.concurrent.atomic.AtomicBoolean

data class TranscriptionJobSnapshot(
    val running: Boolean = false,
    val startedAt: Long = 0L,
    val processingStage: ProcessingStage = ProcessingStage.Idle,
    val progress: Int = 0,
    val stageLabel: String = "",
    val lastProgressAt: Long = 0L,
    val nativeStage: String = "",
    val nativeDone: Long = 0L,
    val nativeTotal: Long = 0L,
    val progressUpdateCount: Int = 0,
    val diagnosticLog: List<String> = emptyList(),
    val error: String? = null,
    val cancelled: Boolean = false,
    val displayName: String? = null,
    val resultId: String? = null,
    val completionHandled: Boolean = false,
)

object TranscriptionJobController {
    val cancelRequested = AtomicBoolean(false)

    private val mutableState = MutableStateFlow(TranscriptionJobSnapshot())
    val state: StateFlow<TranscriptionJobSnapshot> = mutableState.asStateFlow()

    fun resetForStart(
        displayName: String,
        startedAt: Long,
    ) {
        cancelRequested.set(false)
        mutableState.value =
            TranscriptionJobSnapshot(
                running = true,
                startedAt = startedAt,
                processingStage = ProcessingStage.Preparing,
                progress = 0,
                stageLabel = "Подготовка",
                lastProgressAt = startedAt,
                displayName = displayName,
            )
    }

    fun update(transform: (TranscriptionJobSnapshot) -> TranscriptionJobSnapshot) {
        mutableState.update(transform)
    }

    fun markCompletionHandled() {
        mutableState.update { it.copy(completionHandled = true) }
    }
}
