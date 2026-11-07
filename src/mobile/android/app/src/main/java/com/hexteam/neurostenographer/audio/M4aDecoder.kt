package com.hexteam.neurostenographer.audio

import android.media.MediaCodec
import android.media.MediaCodecList
import android.media.MediaExtractor
import android.media.MediaFormat
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Converts AAC-in-MP4/M4A containers to a PCM WAV accepted by the native decoder. */
object M4aDecoder {
    private const val INPUT_TIMEOUT_US = 10_000L
    private const val WAV_HEADER_SIZE = 44
    private const val WAV_HEADER_BYTES_BEFORE_DATA = 36L
    private const val WAV_FORMAT_PCM = 1
    private const val WAV_FORMAT_CHUNK_SIZE = 16
    private const val WAV_BITS_PER_SAMPLE = 16
    private const val BYTES_PER_SAMPLE = 2
    private const val WAV_CHANNEL_COUNT = 1
    private const val MIN_CHANNEL_COUNT = 1
    private const val BUFFER_OFFSET = 0
    private const val END_OF_INPUT = -1
    private const val EOS_PRESENTATION_TIME_US = 0L
    private const val NO_BUFFER_FLAGS = 0

    private data class DecodeState(
        var sampleRate: Int,
        var channelCount: Int,
        var inputDone: Boolean = false,
        var outputDone: Boolean = false,
        var pcmBytes: Long = 0,
    )

    fun needsConversion(file: File): Boolean = file.extension.lowercase() in setOf("m4a", "mp4", "aac")

    fun decodeToWav(input: File, outputDirectory: File): File {
        require(input.isFile && input.length() > 0L) { "Выбранный файл пуст или недоступен" }

        val extractor = MediaExtractor()
        extractor.setDataSource(input.absolutePath)
        val track = selectAudioTrack(extractor)
            ?: throw IllegalArgumentException("В файле ${input.name} не найден аудиотрек AAC/M4A")
        extractor.selectTrack(track)
        val format = extractor.getTrackFormat(track)
        val mime = format.getString(MediaFormat.KEY_MIME)
            ?: throw IllegalArgumentException("Не удалось определить формат аудио")
        require(MediaCodecList(MediaCodecList.ALL_CODECS).findDecoderForFormat(format) != null) {
            "На устройстве нет декодера для $mime"
        }

        val output = File(outputDirectory, "${input.nameWithoutExtension}-${System.nanoTime()}.wav")
        val codec = MediaCodec.createDecoderByType(mime)
        try {
            codec.configure(format, null, null, 0)
            codec.start()
            writePcmWav(extractor, codec, output, format)
        } finally {
            runCatching { codec.stop() }
            codec.release()
            extractor.release()
        }
        return output
    }

    private fun selectAudioTrack(extractor: MediaExtractor): Int? {
        for (index in 0 until extractor.trackCount) {
            val mime = extractor.getTrackFormat(index).getString(MediaFormat.KEY_MIME) ?: continue
            if (mime.startsWith("audio/")) return index
        }
        return null
    }

    private fun writePcmWav(
        extractor: MediaExtractor,
        codec: MediaCodec,
        output: File,
        sourceFormat: MediaFormat,
    ) {
        val state =
            DecodeState(
                sourceFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE),
                sourceFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT).coerceAtLeast(MIN_CHANNEL_COUNT),
            )
        val info = MediaCodec.BufferInfo()
        output.outputStream().buffered().use { stream ->
            stream.write(ByteArray(WAV_HEADER_SIZE))
            while (!state.outputDone) {
                if (!state.inputDone) state.inputDone = queueInput(extractor, codec)
                state.outputDone = drainOutput(codec, info, stream, state)
            }
        }
        writeWavHeader(output, state.sampleRate, state.pcmBytes)
    }

    private fun queueInput(extractor: MediaExtractor, codec: MediaCodec): Boolean {
        val inputIndex = codec.dequeueInputBuffer(INPUT_TIMEOUT_US)
        return if (inputIndex < 0) {
            false
        } else {
            val inputBuffer =
                requireNotNull(codec.getInputBuffer(inputIndex)) { "Декодер не предоставил входной буфер" }
            val size = extractor.readSampleData(inputBuffer, BUFFER_OFFSET)
            if (size == END_OF_INPUT) {
                codec.queueInputBuffer(
                    inputIndex,
                    BUFFER_OFFSET,
                    BUFFER_OFFSET,
                    EOS_PRESENTATION_TIME_US,
                    MediaCodec.BUFFER_FLAG_END_OF_STREAM,
                )
                true
            } else {
                codec.queueInputBuffer(inputIndex, BUFFER_OFFSET, size, extractor.sampleTime, NO_BUFFER_FLAGS)
                extractor.advance()
                false
            }
        }
    }

    private fun drainOutput(
        codec: MediaCodec,
        info: MediaCodec.BufferInfo,
        stream: java.io.BufferedOutputStream,
        state: DecodeState,
    ): Boolean {
        val outputIndex = codec.dequeueOutputBuffer(info, INPUT_TIMEOUT_US)
        if (outputIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
            val changed = codec.outputFormat
            state.sampleRate = changed.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            state.channelCount = changed.getInteger(MediaFormat.KEY_CHANNEL_COUNT).coerceAtLeast(MIN_CHANNEL_COUNT)
        } else if (outputIndex >= BUFFER_OFFSET) {
            if (info.size > 0) state.pcmBytes += writeDecodedPcm(codec, outputIndex, info, stream, state.channelCount)
            codec.releaseOutputBuffer(outputIndex, false)
        } else {
            check(
                outputIndex == MediaCodec.INFO_TRY_AGAIN_LATER ||
                    outputIndex == MediaCodec.INFO_OUTPUT_BUFFERS_CHANGED,
            ) { "Декодер вернул неизвестный статус $outputIndex" }
        }
        return outputIndex >= BUFFER_OFFSET && (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0
    }

    private fun writeDecodedPcm(
        codec: MediaCodec,
        outputIndex: Int,
        info: MediaCodec.BufferInfo,
        stream: java.io.BufferedOutputStream,
        channels: Int,
    ): Long {
        val bytes = ByteArray(info.size)
        val buffer = requireNotNull(codec.getOutputBuffer(outputIndex)) { "Декодер не предоставил выходной буфер" }
        buffer.position(info.offset)
        buffer.limit(info.offset + info.size)
        buffer.get(bytes)
        val mono = toMono16Bit(bytes, channels)
        if (mono.isEmpty()) return 0
        stream.write(mono)
        return mono.size.toLong()
    }

    private fun toMono16Bit(pcm: ByteArray, channels: Int): ByteArray {
        if (channels <= 1) return pcm
        val input = ByteBuffer.wrap(pcm).order(ByteOrder.nativeOrder())
        val bytesPerFrame = channels * BYTES_PER_SAMPLE
        val frames = pcm.size / bytesPerFrame
        val output = ByteArray(frames * BYTES_PER_SAMPLE)
        val result = ByteBuffer.wrap(output).order(ByteOrder.LITTLE_ENDIAN)
        for (frame in 0 until frames) {
            var sum = 0
            for (channel in 0 until channels) {
                val sampleOffset = frame * bytesPerFrame + channel * BYTES_PER_SAMPLE
                sum += input.getShort(sampleOffset).toInt()
            }
            result.putShort((sum / channels).toShort())
        }
        return output
    }

    private fun writeWavHeader(output: File, sampleRate: Int, pcmBytes: Long) {
        require(pcmBytes <= Int.MAX_VALUE.toLong()) { "Расшифровываемое PCM-аудио слишком велико для WAV" }
        val byteRate = sampleRate * BYTES_PER_SAMPLE
        val header = ByteArray(WAV_HEADER_SIZE)
        val buffer = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put("RIFF".toByteArray(Charsets.US_ASCII))
        buffer.putInt((WAV_HEADER_BYTES_BEFORE_DATA + pcmBytes).toInt())
        buffer.put("WAVE".toByteArray(Charsets.US_ASCII))
        buffer.put("fmt ".toByteArray(Charsets.US_ASCII))
        buffer.putInt(WAV_FORMAT_CHUNK_SIZE)
        buffer.putShort(WAV_FORMAT_PCM.toShort())
        buffer.putShort(WAV_CHANNEL_COUNT.toShort())
        buffer.putInt(sampleRate)
        buffer.putInt(byteRate.toInt())
        buffer.putShort((WAV_CHANNEL_COUNT * BYTES_PER_SAMPLE).toShort())
        buffer.putShort(WAV_BITS_PER_SAMPLE.toShort())
        buffer.put("data".toByteArray(Charsets.US_ASCII))
        buffer.putInt(pcmBytes.toInt())
        RandomAccessFile(output, "rw").use { wav -> wav.write(header, 0, header.size) }
    }
}
