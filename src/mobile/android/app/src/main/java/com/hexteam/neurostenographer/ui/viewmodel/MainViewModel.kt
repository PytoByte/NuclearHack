@file:Suppress("MagicNumber")

package com.hexteam.neurostenographer.ui.viewmodel

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.hexteam.neurostenographer.audio.AudioEngine
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.data.repository.TranscriptRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

enum class ProgressHealth {
    Idle,
    Progressing,
    Waiting,
    Stalled,
}

sealed interface ProcessingStage {
    data object Idle : ProcessingStage

    data object Preparing : ProcessingStage

    data object Decoding : ProcessingStage

    data object Transcribing : ProcessingStage

    data object Separating : ProcessingStage

    data object Exporting : ProcessingStage

    data object Complete : ProcessingStage
}

data class MainState(
    val transcripts: List<Transcript> = emptyList(),
    val selected: Transcript? = null,
    val processing: ProcessingStage = ProcessingStage.Idle,
    val progress: Int = 0,
    val stageLabel: String = "",
    val processingStartedAt: Long = 0L,
    val elapsedMs: Long = 0L,
    val lastProgressAt: Long = 0L,
    val progressHealth: ProgressHealth = ProgressHealth.Idle,
    val nativeStage: String = "",
    val nativeDone: Long = 0L,
    val nativeTotal: Long = 0L,
    val progressUpdateCount: Int = 0,
    val diagnosticLog: List<String> = emptyList(),
    val error: String? = null,
    val nativeAvailable: Boolean = false,
    val summaryAvailable: Boolean = false,
    val summarizing: Boolean = false,
    val summary: String? = null,
)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val repository = TranscriptRepository(app)
    private val engine = AudioEngine(app)
    private val _state =
        MutableStateFlow(
            MainState(
                transcripts = repository.load(),
                nativeAvailable = engine.isAvailable(),
                summaryAvailable = false,
            ),
        )
    val state = _state.asStateFlow()

    @Volatile private var cancelRequested = false
    private var progressFloor = 0
    private var processingTimer: Job? = null

    fun select(transcript: Transcript) {
        _state.update { it.copy(selected = transcript) }
    }

    fun clearSelection() {
        _state.update { it.copy(selected = null) }
    }

    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    fun json(transcript: Transcript = _state.value.selected ?: _state.value.transcripts.first()): String =
        repository.toJson(transcript)

    @Suppress("LongMethod")
    fun process(
        uri: Uri,
        displayName: String,
    ) {
        if (_state.value.processing != ProcessingStage.Idle) return
        cancelRequested = false
        progressFloor = 0
        processingTimer?.cancel()
        val startedAt = System.currentTimeMillis()
        _state.update {
            it.copy(
                processing = ProcessingStage.Preparing,
                progress = 0,
                stageLabel = "Подготовка",
                error = null,
                summary = null,
                processingStartedAt = startedAt,
                elapsedMs = 0L,
                lastProgressAt = startedAt,
                progressHealth = ProgressHealth.Progressing,
                nativeStage = "",
                nativeDone = 0L,
                nativeTotal = 0L,
                progressUpdateCount = 0,
                diagnosticLog = listOf(formatProcessingLog(startedAt, startedAt, "start", 0L, 0L, 0)),
            )
        }
        val timer =
            viewModelScope.launch {
                while (isActive) {
                    delay(1_000L)
                    val now = System.currentTimeMillis()
                    _state.update { current ->
                        if (current.processing == ProcessingStage.Idle) {
                            current
                        } else {
                            val health =
                                processingHealth(current.processing, now - current.lastProgressAt)
                            val baseTime =
                                if (current.processingStartedAt > 0L) {
                                    current.processingStartedAt
                                } else {
                                    startedAt
                                }
                            current.copy(
                                elapsedMs = now - baseTime,
                                progressHealth = health,
                            )
                        }
                    }
                }
            }
        processingTimer = timer

        viewModelScope.launch {
            val result =
                withContext(Dispatchers.IO) {
                    runCatching {
                        requireNative()
                        val input = repository.importAudio(uri, displayName)
                        val prepared = engine.prepareInput(input)
                        val output =
                            try {
                                engine.transcribe(prepared) { stage, done, total ->
                                    onNativeProgress(stage, done, total)
                                }
                            } finally {
                                if (prepared != input) prepared.delete()
                            }
                        val now = System.currentTimeMillis()
                        val startedAt = _state.value.processingStartedAt
                        val entry =
                            formatProcessingLog(
                                now,
                                startedAt,
                                "export",
                                output.length(),
                                output.length(),
                                99,
                            )
                        _state.update {
                            it.copy(
                                processing = ProcessingStage.Exporting,
                                progress = 99,
                                stageLabel = "Сохранение",
                                lastProgressAt = now,
                                progressHealth = ProgressHealth.Progressing,
                                diagnosticLog = (it.diagnosticLog + entry).takeLast(120),
                            )
                        }
                        repository.create(displayName, output.readText())
                    }
                }
            processingTimer?.cancel()
            processingTimer = null
            result.fold(
                onSuccess = { transcript ->
                    _state.update { current ->
                        val updated =
                            listOf(transcript) +
                                current.transcripts.filterNot { item -> item.id == transcript.id }
                        current.copy(
                            transcripts = updated,
                            selected = transcript,
                            processing = ProcessingStage.Idle,
                            progress = 0,
                            stageLabel = "",
                            error = null,
                            processingStartedAt = 0L,
                            elapsedMs = 0L,
                            lastProgressAt = 0L,
                            progressHealth = ProgressHealth.Idle,
                            nativeStage = "",
                            nativeDone = 0L,
                            nativeTotal = 0L,
                            progressUpdateCount = 0,
                            diagnosticLog = emptyList(),
                        )
                    }
                },
                onFailure = { error ->
                    _state.update {
                        it.copy(
                            processing = ProcessingStage.Idle,
                            progress = 0,
                            stageLabel = "",
                            error = if (cancelRequested) null else error.message ?: "Не удалось обработать файл",
                            processingStartedAt = 0L,
                            elapsedMs = 0L,
                            lastProgressAt = 0L,
                            progressHealth = ProgressHealth.Idle,
                            nativeStage = "",
                            nativeDone = 0L,
                            nativeTotal = 0L,
                            progressUpdateCount = 0,
                            diagnosticLog = emptyList(),
                        )
                    }
                },
            )
        }
    }

    fun cancel() {
        if (_state.value.processing == ProcessingStage.Idle) return
        cancelRequested = true
        val startedAt = _state.value.processingStartedAt
        val cancelEntry =
            formatProcessingLog(
                System.currentTimeMillis(),
                startedAt,
                "cancel_requested",
                _state.value.nativeDone,
                _state.value.nativeTotal,
                _state.value.progressUpdateCount,
            )
        _state.update {
            it.copy(
                stageLabel = "Отмена…",
                diagnosticLog = it.diagnosticLog + cancelEntry,
            )
        }
    }

    fun summarize(transcript: Transcript) {
        if (_state.value.summarizing || _state.value.processing != ProcessingStage.Idle) return
        _state.update { it.copy(summarizing = true, error = null, summary = null) }
        viewModelScope.launch {
            val result =
                withContext(Dispatchers.IO) {
                    runCatching {
                        requireNative()
                        engine.summarize(repository.summaryInput(transcript)) { stage, done, total ->
                            _state.update {
                                it.copy(
                                    stageLabel = StageProgress.summaryLabel(stage),
                                    progress = StageProgress.summaryProgress(done, total),
                                )
                            }
                            false
                        }
                    }
                }
            result.fold(
                onSuccess = { text ->
                    _state.update { it.copy(summarizing = false, summary = text, stageLabel = "", progress = 0) }
                },
                onFailure = { error ->
                    _state.update {
                        it.copy(
                            summarizing = false,
                            stageLabel = "",
                            progress = 0,
                            error = error.message ?: "Не удалось построить резюме",
                        )
                    }
                },
            )
        }
    }

    fun dismissSummary() {
        _state.update { it.copy(summary = null) }
    }

    private fun requireNative() {
        check(_state.value.nativeAvailable) {
            "Нативный модуль не загружен. Соберите APK через make android-app."
        }
    }

    private fun onNativeProgress(
        stage: String,
        done: Long,
        total: Long,
    ): Boolean {
        val mapped =
            when {
                stage == "queued" || stage == "checkpoint_identity" -> ProcessingStage.Preparing
                stage == "decode" -> ProcessingStage.Decoding
                stage.startsWith("asr") -> ProcessingStage.Transcribing
                stage.startsWith("diarization") || stage.startsWith("speaker") -> ProcessingStage.Separating
                stage == "merge" -> ProcessingStage.Exporting
                stage == "done" -> ProcessingStage.Complete
                else -> null
            } ?: return cancelRequested
        val range = StageProgress.range(mapped)
        val fraction = if (total > 0) (done.toDouble() / total).coerceIn(0.0, 1.0) else 0.0
        val percent = range.first + ((range.last - range.first) * fraction).toInt()
        progressFloor = maxOf(progressFloor, percent)
        val now = System.currentTimeMillis()
        val startedAt = _state.value.processingStartedAt
        val entry = formatProcessingLog(now, startedAt, stage, done, total, percent)
        _state.update {
            it.copy(
                processing = mapped,
                progress = if (mapped == ProcessingStage.Complete) 100 else progressFloor,
                stageLabel = StageProgress.label(mapped),
                nativeStage = stage,
                nativeDone = done,
                nativeTotal = total,
                progressUpdateCount = it.progressUpdateCount + 1,
                lastProgressAt = now,
                progressHealth = ProgressHealth.Progressing,
                diagnosticLog = (it.diagnosticLog + entry).takeLast(120),
            )
        }
        return cancelRequested
    }
}

private fun processingHealth(
    stage: ProcessingStage,
    ageMs: Long,
): ProgressHealth =
    when {
        stage == ProcessingStage.Complete -> ProgressHealth.Progressing
        ageMs <= 5_000L -> ProgressHealth.Progressing
        ageMs <= 20_000L -> ProgressHealth.Waiting
        else -> ProgressHealth.Stalled
    }

@Suppress("LongParameterList")
private fun formatProcessingLog(
    now: Long,
    startedAt: Long,
    stage: String,
    done: Long,
    total: Long,
    percent: Int,
): String {
    val elapsed = ((now - startedAt).coerceAtLeast(0L) / 100.0).let { (it * 10).toLong() / 10.0 }
    return "${elapsed}s: $stage ($done/$total) ${percent.coerceIn(0, 100)}%"
}

private object StageProgress {
    fun range(stage: ProcessingStage): IntRange =
        when (stage) {
            ProcessingStage.Preparing -> 0..2
            ProcessingStage.Decoding -> 2..15
            ProcessingStage.Transcribing -> 15..65
            ProcessingStage.Separating -> 65..95
            ProcessingStage.Exporting -> 95..99
            ProcessingStage.Complete -> 100..100
            ProcessingStage.Idle -> 0..0
        }

    fun label(stage: ProcessingStage): String =
        when (stage) {
            ProcessingStage.Preparing -> "Подготовка моделей"
            ProcessingStage.Decoding -> "Анализ аудио"
            ProcessingStage.Transcribing -> "Распознавание речи"
            ProcessingStage.Separating -> "Определение говорящих"
            ProcessingStage.Exporting -> "Сохранение"
            ProcessingStage.Complete -> "Готово"
            ProcessingStage.Idle -> ""
        }

    fun summaryLabel(stage: String): String =
        when (stage) {
            "llm_load" -> "Загрузка локальной LLM"
            "llm_prefill" -> "Чтение расшифровки"
            "llm_generate" -> "Формирование резюме"
            else -> "Локальное резюме"
        }

    fun summaryProgress(
        done: Long,
        total: Long,
    ): Int = if (total > 0) ((done.toDouble() / total) * 100).toInt().coerceIn(0, 100) else 0
}
