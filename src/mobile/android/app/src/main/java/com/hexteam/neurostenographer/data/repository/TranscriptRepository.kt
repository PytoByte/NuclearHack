package com.hexteam.neurostenographer.data.repository

import android.content.Context
import android.net.Uri
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.data.model.Utterance
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class TranscriptRepository(private val context: Context) {
    fun samples() = listOf(
        Transcript(title = "Планирование спринта", createdAt = "Сегодня, 10:32", durationMs = 524_000, sourceName = "meeting.m4a", utterances = listOf(
            Utterance(speakerId = "speaker_1", startMs = 1250, endMs = 4380, text = "Добрый день! Давайте начнем с обзора результатов прошлого спринта."),
            Utterance(speakerId = "speaker_2", startMs = 5120, endMs = 9230, text = "Хорошо. Основная задача уже готова к проверке, осталось добавить обработку ошибок."),
            Utterance(speakerId = "speaker_1", startMs = 10100, endMs = 14800, text = "Отлично. Тогда перенесём финальное тестирование на четверг."),
            Utterance(speakerId = "speaker_2", startMs = 15320, endMs = 19100, text = "Согласен. Я подготовлю тестовые сценарии до среды."))
        ),
        Transcript(title = "Интервью с клиентом", createdAt = "Вчера, 18:05", durationMs = 1185_000, sourceName = "interview.mp3", utterances = listOf(
            Utterance(speakerId = "speaker_1", startMs = 0, endMs = 6200, text = "Расскажите, пожалуйста, о текущем процессе согласования документов."),
            Utterance(speakerId = "speaker_2", startMs = 7000, endMs = 15400, text = "Сейчас документы проходят три этапа проверки вручную.")))
    )

    fun nameFor(uri: Uri): String = context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
        val index = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
        if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else uri.lastPathSegment ?: "audio.mp3"
    } ?: "audio.mp3"

    fun createPlaceholder(sourceName: String) = Transcript(title = sourceName.substringBeforeLast('.'), createdAt = SimpleDateFormat("dd MMM, HH:mm", Locale.getDefault()).format(Date()), durationMs = 0, sourceName = sourceName, utterances = emptyList())

    fun toJson(transcript: Transcript): String = buildString {
        append("{\n  \"transcript\": [\n")
        transcript.utterances.forEachIndexed { index, u ->
            append("    {\n      \"speaker_id\": \"${u.speakerId}\",\n      \"start_ms\": ${u.startMs},\n      \"end_ms\": ${u.endMs},\n      \"text\": \"${u.text.replace("\\", "\\\\").replace("\"", "\\\"")}\"\n    }")
            if (index < transcript.utterances.lastIndex) append(',')
            append('\n')
        }
        append("  ]\n}")
    }
}
