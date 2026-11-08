package com.hexteam.neurostenographer.audio

import android.content.Context
import java.io.File

/** Owns the local native transcription/summary session. Calls block, so use Dispatchers.IO. */
class AudioEngine(private val context: Context) {
    private val models = AudioModelStore(context)

    fun prepareInput(input: File): File {
        if (!M4aDecoder.needsConversion(input)) return input
        val converted = M4aDecoder.decodeToWav(input, directory("converted"))
        if (!converted.isFile || converted.length() == 0L) {
            converted.delete()
            throw TranscriptionException("Не удалось декодировать M4A/MP4 в PCM WAV")
        }
        return converted
    }

    fun isAvailable(): Boolean = runCatching { NativeAudio.llmAvailable() }.isSuccess

    fun summaryAvailable(): Boolean = runCatching { NativeAudio.llmAvailable() == 1 }.getOrDefault(false)

    fun transcribe(
        input: File,
        onProgress: (String, Long, Long) -> Boolean,
    ): File {
        val root = models.ensureInstalled()
        val output = File(resultsDirectory(), "transcript-${System.currentTimeMillis()}.json")
        val scratch = directory("scratch")
        val cache = directory("job-cache")
        val trace = File(output.path + ".trace.json")
        val threads = Runtime.getRuntime().availableProcessors().coerceIn(1, MAX_THREADS)
        val finalPreset = models.finalPreset(root)
        NativeAudio.listener = NativeAudio.Listener { stage, done, total -> onProgress(stage, done, total) }
        val status =
            try {
                if (finalPreset != null) {
                    NativeAudio.transcribeFinal(
                        input.path,
                        output.path,
                        finalPreset.asrModel.path,
                        finalPreset.tokens.path,
                        finalPreset.speakerModel.path,
                        scratch.path,
                        threads,
                        MAX_AUDIO_SECONDS,
                        cache.path,
                        trace.path,
                    )
                } else {
                    NativeAudio.transcribeJob(
                        input.path,
                        output.path,
                        root.path,
                        scratch.path,
                        legacyOptions(cache),
                    )
                }
            } finally {
                NativeAudio.listener = null
            }
        if (status != STATUS_OK) {
            throw TranscriptionException(statusMessage(status))
        }
        if (!output.isFile) {
            throw TranscriptionException("Движок не создал JSON-файл")
        }
        return output
    }

    fun summarize(
        transcriptJson: File,
        onProgress: (String, Long, Long) -> Boolean,
    ): String {
        val root = models.ensureInstalled()
        val model = models.summaryModel(root) ?: throw TranscriptionException("Модель Qwen не установлена")
        val output = File(directory("summaries"), "summary-${System.currentTimeMillis()}.txt")
        NativeAudio.listener = NativeAudio.Listener { stage, done, total -> onProgress(stage, done, total) }
        val status =
            try {
                NativeAudio.summarize(
                    transcriptJson.path,
                    model.path,
                    output.path,
                    Runtime.getRuntime().availableProcessors().coerceIn(1, MAX_THREADS),
                )
            } finally {
                NativeAudio.listener = null
            }
        if (status != STATUS_OK) {
            throw TranscriptionException(statusMessage(status))
        }
        return output.takeIf(File::isFile)?.readText().orEmpty()
    }

    private fun legacyOptions(cache: File): NativeAudio.JobOptions =
        NativeAudio.JobOptions().apply {
            threads = Runtime.getRuntime().availableProcessors().coerceIn(1, MAX_THREADS)
            chunkSeconds = CHUNK_SECONDS
            maxAudioSeconds = MAX_AUDIO_SECONDS
            checkpointDirectory = cache.path
        }

    private fun statusMessage(status: Int): String =
        when (status) {
            STATUS_CANCELLED -> "Обработка отменена"
            STATUS_BUSY -> "Другой файл уже обрабатывается"
            else -> NativeAudio.lastError().ifBlank { "Ошибка движка (код $status)" }
        }

    private fun directory(name: String): File = File(context.filesDir, name).apply { mkdirs() }

    private fun resultsDirectory(): File = directory("results")

    class TranscriptionException(message: String) : IllegalStateException(message)

    private companion object {
        const val STATUS_OK = 0
        const val STATUS_CANCELLED = 4
        const val STATUS_BUSY = 5
        const val MAX_THREADS = 4
        const val CHUNK_SECONDS = 20
        const val MAX_AUDIO_SECONDS = Int.MAX_VALUE
    }
}
