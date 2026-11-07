package com.hexteam.neurostenographer.data.repository

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.data.model.Utterance
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/** Persists transcripts and imported audio inside app-private storage. */
class TranscriptRepository(private val context: Context) {
    private val transcriptDirectory = File(context.filesDir, TRANSCRIPT_DIRECTORY).apply { mkdirs() }
    private val importDirectory = File(context.filesDir, IMPORT_DIRECTORY).apply { mkdirs() }

    fun load(): List<Transcript> =
        transcriptDirectory
            .listFiles { file -> file.isFile && file.extension == "json" }
            .orEmpty()
            .sortedByDescending(File::lastModified)
            .mapNotNull(::parse)

    fun nameFor(uri: Uri): String =
        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else uri.lastPathSegment ?: "audio"
        } ?: uri.lastPathSegment ?: "audio"

    fun importAudio(
        uri: Uri,
        displayName: String,
    ): File {
        val target =
            File(
                importDirectory,
                "${System.currentTimeMillis()}-${FileNames.safeName(
                    displayName,
                    context.contentResolver.getType(uri),
                )}",
            )
        val input =
            context.contentResolver.openInputStream(uri)
                ?: error("Не удалось открыть выбранный файл")
        input.use { source ->
            FileOutputStream(target).buffered(BUFFER_BYTES).use { output -> source.copyTo(output) }
        }
        if (target.length() == 0L) {
            target.delete()
            error("Выбранный файл пуст")
        }
        return target
    }

    fun create(
        sourceName: String,
        nativeJson: String,
    ): Transcript {
        val root = JSONObject(nativeJson)
        val turns = root.getJSONArray("transcript")
        val utterances = ArrayList<Utterance>(turns.length())
        for (index in 0 until turns.length()) {
            val turn = turns.getJSONObject(index)
            utterances +=
                Utterance(
                    speakerId = turn.getString("speaker_id"),
                    startMs = turn.getLong("start_ms"),
                    endMs = turn.getLong("end_ms"),
                    text = turn.getString("text"),
                )
        }
        val transcript =
            Transcript(
                title = sourceName.substringBeforeLast('.', sourceName),
                createdAt = SimpleDateFormat(DATE_FORMAT, Locale.getDefault()).format(Date()),
                durationMs = utterances.maxOfOrNull(Utterance::endMs) ?: 0,
                sourceName = sourceName,
                utterances = utterances,
            )
        save(transcript)
        return transcript
    }

    fun save(transcript: Transcript) {
        val target = File(transcriptDirectory, "${transcript.id}.json")
        val temporary = File.createTempFile("transcript-", ".tmp", transcriptDirectory)
        temporary.writeText(encode(transcript))
        target.delete()
        if (!temporary.renameTo(target)) {
            temporary.copyTo(target, overwrite = true)
            temporary.delete()
        }
    }

    fun toJson(transcript: Transcript): String {
        val turns = JSONArray()
        for (utterance in transcript.utterances) {
            turns.put(
                JSONObject()
                    .put("speaker_id", utterance.speakerId)
                    .put("start_ms", utterance.startMs)
                    .put("end_ms", utterance.endMs)
                    .put("text", utterance.text),
            )
        }
        return JSONObject().put("transcript", turns).toString(JSON_INDENT)
    }

    fun summaryInput(transcript: Transcript): File {
        val target = File(context.cacheDir, "summary-input-${transcript.id}.json")
        target.writeText(toJson(transcript))
        return target
    }

    private fun encode(transcript: Transcript): String {
        val turns = JSONArray()
        for (utterance in transcript.utterances) {
            turns.put(
                JSONObject()
                    .put("speaker_id", utterance.speakerId)
                    .put("start_ms", utterance.startMs)
                    .put("end_ms", utterance.endMs)
                    .put("text", utterance.text),
            )
        }
        return JSONObject()
            .put("id", transcript.id)
            .put("title", transcript.title)
            .put("createdAt", transcript.createdAt)
            .put("durationMs", transcript.durationMs)
            .put("sourceName", transcript.sourceName)
            .put("utterances", turns)
            .toString(JSON_INDENT)
    }

    private fun parse(file: File): Transcript? =
        runCatching {
            val root = JSONObject(file.readText())
            val turns = root.getJSONArray("utterances")
            val utterances = ArrayList<Utterance>(turns.length())
            for (index in 0 until turns.length()) {
                val turn = turns.getJSONObject(index)
                utterances +=
                    Utterance(
                        id = turn.optString("id", UUID.randomUUID().toString()),
                        speakerId = turn.getString("speaker_id"),
                        startMs = turn.getLong("start_ms"),
                        endMs = turn.getLong("end_ms"),
                        text = turn.getString("text"),
                    )
            }
            Transcript(
                id = root.getString("id"),
                title = root.getString("title"),
                createdAt = root.getString("createdAt"),
                durationMs = root.optLong("durationMs", 0),
                sourceName = root.optString("sourceName", root.getString("title")),
                utterances = utterances,
            )
        }.getOrNull()

    private companion object {
        const val TRANSCRIPT_DIRECTORY = "transcripts"
        const val IMPORT_DIRECTORY = "imports"
        const val DATE_FORMAT = "dd MMM, HH:mm"
        const val BUFFER_BYTES = 64 * 1024
        const val JSON_INDENT = 2
    }
}

private object FileNames {
    fun safeName(
        displayName: String,
        mimeType: String?,
    ): String {
        val extension = extensionFor(displayName, mimeType)
        val stem =
            displayName.substringBeforeLast('.', displayName)
                .replace(UNSAFE_NAME, "_")
                .take(MAX_NAME_LENGTH)
                .ifBlank { "audio" }
        return stem + extension
    }

    private fun extensionFor(
        displayName: String,
        mimeType: String?,
    ): String {
        val extension = displayName.substringAfterLast('.', "")
        if (extension.isNotEmpty() && extension.length <= MAX_EXTENSION_LENGTH) {
            return "." + extension.lowercase(Locale.ROOT)
        }
        return when (mimeType) {
            "audio/mpeg", "audio/mp3" -> ".mp3"
            "audio/wav", "audio/x-wav", "audio/wave" -> ".wav"
            "audio/mp4", "audio/m4a", "audio/x-m4a" -> ".m4a"
            "audio/ogg", "audio/opus" -> ".ogg"
            "audio/flac", "audio/x-flac" -> ".flac"
            else -> ".bin"
        }
    }

    const val MAX_NAME_LENGTH = 80
    const val MAX_EXTENSION_LENGTH = 5
    val UNSAFE_NAME = Regex("[^A-Za-z0-9._-]")
}
