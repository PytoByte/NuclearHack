package com.hexteam.neurostenographer.audio

import android.content.Context
import java.io.File

/** Copies the pinned model bundle from APK assets into app-private storage once. */
class AudioModelStore(private val context: Context) {
    fun ensureInstalled(): File {
        val root = File(context.filesDir, MODELS_DIRECTORY)
        val marker = File(root, MARKER_FILE)
        if (marker.isFile && marker.readText() == ASSET_VERSION && requiredFiles(root).all(File::isFile)) {
            return root
        }
        if (context.assets.list(MODELS_DIRECTORY).isNullOrEmpty()) {
            error("В APK нет моделей. Соберите приложение через make android-app.")
        }
        root.mkdirs()
        copyDirectory(MODELS_DIRECTORY, root)
        marker.writeText(ASSET_VERSION)
        val missing = requiredFiles(root).filterNot(File::isFile)
        if (missing.isNotEmpty()) {
            error("Неполный комплект моделей: " + missing.joinToString { it.name })
        }
        return root
    }

    fun finalPreset(root: File): FinalPreset? {
        val asr = File(root, FINAL_ASR)
        val tokens = File(root, FINAL_TOKENS)
        val speaker = File(root, FINAL_SPEAKER)
        return if (asr.isFile && tokens.isFile && speaker.isFile) {
            FinalPreset(asr, tokens, speaker)
        } else {
            null
        }
    }

    fun summaryModel(root: File): File? = File(root, SUMMARY_MODEL).takeIf(File::isFile)

    private fun requiredFiles(root: File): List<File> =
        listOf(
            File(root, LEGACY_ASR),
            File(root, LEGACY_TOKENS),
            File(root, LEGACY_SEGMENTATION),
            File(root, LEGACY_EMBEDDING),
        )

    private fun copyDirectory(
        assetPath: String,
        target: File,
    ) {
        val children = context.assets.list(assetPath)
        if (children.isNullOrEmpty()) {
            target.parentFile?.mkdirs()
            context.assets.open(assetPath).use { input ->
                target.outputStream().buffered(BUFFER_BYTES).use { output -> input.copyTo(output) }
            }
            return
        }
        target.mkdirs()
        for (child in children) {
            copyDirectory("$assetPath/$child", File(target, child))
        }
    }

    data class FinalPreset(val asrModel: File, val tokens: File, val speakerModel: File)

    private companion object {
        const val MODELS_DIRECTORY = "models"
        const val MARKER_FILE = ".asset-version"
        const val ASSET_VERSION = "1"
        const val BUFFER_BYTES = 64 * 1024
        const val LEGACY_ASR = "giga-v3-ctc/model.int8.onnx"
        const val LEGACY_TOKENS = "giga-v3-ctc/tokens.txt"
        const val LEGACY_SEGMENTATION = "diarization/segmentation-model.onnx"
        const val LEGACY_EMBEDDING = "diarization/embedding.onnx"
        const val FINAL_ASR = "giga-v3-ctc-punct/model.int8.onnx"
        const val FINAL_TOKENS = "giga-v3-ctc-punct/tokens.txt"
        const val FINAL_SPEAKER = "nemotron3-diarization/model_quantized.onnx"
        const val SUMMARY_MODEL = "qwen3-0.6b-q8/Qwen3-0.6B-Q8_0.gguf"
    }
}
