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
        var sampleRate = sourceFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        var channelCount = sourceFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT).coerceAtLeast(1)
        var inputDone = false
        var outputDone = false
        val info = MediaCodec.BufferInfo()
        output.outputStream().buffered().use { stream ->
            stream.write(ByteArray(44))
            var pcmBytes = 0L
            while (!outputDone) {
                if (!inputDone) {
                    val inputIndex = codec.dequeueInputBuffer(10_000L)
                    if (inputIndex >= 0) {
                        val size = extractor.readSampleData(codec.getInputBuffer(inputIndex)!!, 0)
                        if (size < 0) {
                            codec.queueInputBuffer(inputIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                            inputDone = true
                        } else {
                            codec.queueInputBuffer(inputIndex, 0, size, extractor.sampleTime, 0)
                            extractor.advance()
                        }
                    }
                }

                val outputIndex = codec.dequeueOutputBuffer(info, 10_000L)
                if (outputIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    val changed = codec.outputFormat
                    sampleRate = changed.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                    channelCount = changed.getInteger(MediaFormat.KEY_CHANNEL_COUNT).coerceAtLeast(1)
                } else if (outputIndex >= 0) {
                    if (info.size > 0) {
                        val bytes = ByteArray(info.size)
                        codec.getOutputBuffer(outputIndex)?.let { buffer ->
                            buffer.position(info.offset)
                            buffer.limit(info.offset + info.size)
                            buffer.get(bytes)
                        }
                        val mono = toMono16Bit(bytes, channelCount)
                        if (mono.isNotEmpty()) {
                            stream.write(mono)
                            pcmBytes += mono.size
                        }
                    }
                    codec.releaseOutputBuffer(outputIndex, false)
                    if ((info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) outputDone = true
                }
            }
        }
        writeWavHeader(output, sampleRate, pcmBytes)
    }

    private fun toMono16Bit(pcm: ByteArray, channels: Int): ByteArray {
        if (channels <= 1) return pcm
        val input = ByteBuffer.wrap(pcm).order(ByteOrder.nativeOrder())
        val frames = pcm.size / (channels * 2)
        val output = ByteArray(frames * 2)
        val result = ByteBuffer.wrap(output).order(ByteOrder.LITTLE_ENDIAN)
        for (frame in 0 until frames) {
            var sum = 0
            for (channel in 0 until channels) sum += input.getShort(frame * channels * 2 + channel * 2).toInt()
            result.putShort((sum / channels).toShort())
        }
        return output
    }

    private fun writeWavHeader(output: File, sampleRate: Int, pcmBytes: Long) {
        require(pcmBytes <= Int.MAX_VALUE.toLong()) { "Расшифровываемое PCM-аудио слишком велико для WAV" }
        val byteRate = sampleRate * 2L
        val header = ByteArray(44)
        val buffer = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put("RIFF".toByteArray(Charsets.US_ASCII))
        buffer.putInt((36L + pcmBytes).toInt())
        buffer.put("WAVE".toByteArray(Charsets.US_ASCII))
        buffer.put("fmt ".toByteArray(Charsets.US_ASCII))
        buffer.putInt(16)
        buffer.putShort(1)
        buffer.putShort(1)
        buffer.putInt(sampleRate)
        buffer.putInt(byteRate.toInt())
        buffer.putShort(2)
        buffer.putShort(16)
        buffer.put("data".toByteArray(Charsets.US_ASCII))
        buffer.putInt(pcmBytes.toInt())
        RandomAccessFile(output, "rw").use { wav -> wav.write(header, 0, header.size) }
    }
}
