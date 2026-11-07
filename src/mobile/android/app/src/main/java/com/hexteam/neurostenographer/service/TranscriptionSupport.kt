@file:Suppress("MagicNumber")

package com.hexteam.neurostenographer.service

import com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage

object TranscriptionStageMapper {
    fun toProcessingStage(stage: String): ProcessingStage? =
        when {
            stage == "queued" || stage == "checkpoint_identity" -> ProcessingStage.Preparing
            stage == "decode" -> ProcessingStage.Decoding
            stage.startsWith("asr") -> ProcessingStage.Transcribing
            stage.startsWith("diarization") || stage.startsWith("speaker") -> ProcessingStage.Separating
            stage == "merge" -> ProcessingStage.Exporting
            stage == "done" -> ProcessingStage.Complete
            else -> null
        }

    fun progressRange(stage: ProcessingStage): IntRange =
        when (stage) {
            ProcessingStage.Preparing -> 0..2
            ProcessingStage.Decoding -> 2..15
            ProcessingStage.Transcribing -> 15..65
            ProcessingStage.Separating -> 65..95
            ProcessingStage.Exporting -> 95..99
            ProcessingStage.Complete -> 100..100
            ProcessingStage.Idle -> 0..0
        }

    fun stageLabel(stage: ProcessingStage): String =
        when (stage) {
            ProcessingStage.Preparing -> "Подготовка моделей"
            ProcessingStage.Decoding -> "Анализ аудио"
            ProcessingStage.Transcribing -> "Распознавание речи"
            ProcessingStage.Separating -> "Определение говорящих"
            ProcessingStage.Exporting -> "Сохранение"
            ProcessingStage.Complete -> "Готово"
            ProcessingStage.Idle -> ""
        }
}

object TranscriptionDiagnostics {
    @Suppress("LongParameterList")
    fun formatProcessingLog(
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
}
