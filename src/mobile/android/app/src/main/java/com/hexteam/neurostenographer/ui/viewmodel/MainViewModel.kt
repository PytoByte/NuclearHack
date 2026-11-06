package com.hexteam.neurostenographer.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.hexteam.neurostenographer.data.model.AppSettings
import com.hexteam.neurostenographer.data.model.Transcript
import com.hexteam.neurostenographer.data.repository.TranscriptRepository
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface ProcessingStage { data object Idle: ProcessingStage; data object Decoding: ProcessingStage; data object Transcribing: ProcessingStage; data object Separating: ProcessingStage; data object Complete: ProcessingStage }
data class MainState(val transcripts: List<Transcript>, val selected: Transcript?, val processing: ProcessingStage = ProcessingStage.Idle, val progress: Int = 0, val settings: AppSettings = AppSettings())

class MainViewModel(app: Application): AndroidViewModel(app) {
    private val repository = TranscriptRepository(app)
    private val _state = MutableStateFlow(MainState(repository.samples(), null))
    val state = _state.asStateFlow()

    fun select(t: Transcript) { _state.value = _state.value.copy(selected = t) }
    fun clearSelection() { _state.value = _state.value.copy(selected = null) }
    fun updateSettings(settings: AppSettings) { _state.value = _state.value.copy(settings = settings) }
    fun addFile(name: String) { _state.value = _state.value.copy(selected = repository.createPlaceholder(name)) }
    fun json(t: Transcript = _state.value.selected ?: _state.value.transcripts.first()) = repository.toJson(t)

    fun process(sourceName: String = "Новая запись.mp3") = viewModelScope.launch {
        val stages = listOf(ProcessingStage.Decoding, ProcessingStage.Transcribing, ProcessingStage.Separating, ProcessingStage.Complete)
        stages.forEachIndexed { index, stage ->
            _state.value = _state.value.copy(processing = stage, progress = (index + 1) * 25)
            delay(650)
        }
        val sample = repository.samples().first().copy(title = sourceName.substringBeforeLast('.'), sourceName = sourceName)
        _state.value = _state.value.copy(transcripts = listOf(sample) + _state.value.transcripts, selected = sample, processing = ProcessingStage.Idle, progress = 0)
    }
}
