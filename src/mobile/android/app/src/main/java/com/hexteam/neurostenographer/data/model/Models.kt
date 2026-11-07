package com.hexteam.neurostenographer.data.model

import java.io.Serializable
import java.util.UUID

data class Utterance(
    val id: String = UUID.randomUUID().toString(),
    val speakerId: String,
    val startMs: Long,
    val endMs: Long,
    var text: String,
) : Serializable

data class Transcript(
    val id: String = UUID.randomUUID().toString(),
    val title: String,
    val createdAt: String,
    val durationMs: Long,
    val sourceName: String,
    val utterances: List<Utterance>,
)

data class AppSettings(
    val language: String = "Русский",
    val speakerDetection: Boolean = true,
    val preserveFillers: Boolean = true,
    val realtimeMode: Boolean = false,
)
