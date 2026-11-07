@file:Suppress("MagicNumber", "TooManyFunctions", "LongMethod")

package com.hexteam.neurostenographer.service

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import android.net.Uri
import android.os.Build
import android.os.IBinder
import com.hexteam.neurostenographer.R
import com.hexteam.neurostenographer.audio.AudioEngine
import com.hexteam.neurostenographer.data.repository.TranscriptRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class TranscriptionService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var runningJob: Job? = null
    private var progressFloor = 0

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    @Suppress("ReturnCount")
    override fun onStartCommand(
        intent: Intent?,
        flags: Int,
        startId: Int,
    ): Int {
        return when (intent?.action) {
            ACTION_CANCEL -> {
                TranscriptionJobController.cancelRequested.set(true)
                TranscriptionJobController.update { snapshot ->
                    snapshot.copy(cancelled = true, stageLabel = "Отмена…")
                }
                START_STICKY
            }

            ACTION_START -> {
                val uriValue = intent.getStringExtra(EXTRA_URI)
                val displayName = intent.getStringExtra(EXTRA_NAME)
                if (uriValue.isNullOrBlank() || displayName.isNullOrBlank()) {
                    stopSelf(startId)
                    return START_NOT_STICKY
                }
                if (runningJob?.isActive == true) {
                    return START_STICKY
                }
                val initialNotification = buildNotification("Подготовка", 0)
                startForegroundSafely(initialNotification)
                runningJob =
                    scope.launch {
                        runJob(Uri.parse(uriValue), displayName, startId)
                    }
                START_STICKY
            }

            else -> START_NOT_STICKY
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    @Suppress("TooGenericExceptionCaught")
    private suspend fun runJob(
        uri: Uri,
        displayName: String,
        startId: Int,
    ) {
        val startedAt = System.currentTimeMillis()
        TranscriptionJobController.resetForStart(displayName, startedAt)
        val startEntry =
            TranscriptionDiagnostics.formatProcessingLog(startedAt, startedAt, "start", 0L, 0L, 0)
        TranscriptionJobController.update { it.copy(diagnosticLog = listOf(startEntry)) }
        progressFloor = 0
        val repository = TranscriptRepository(this@TranscriptionService)
        val engine = AudioEngine(this@TranscriptionService)

        try {
            val input = repository.importAudio(uri, displayName)
            val prepared = engine.prepareInput(input)
            val output =
                try {
                    engine.transcribe(prepared) { stage, done, total ->
                        onNativeProgress(stage, done, total)
                    }
                } finally {
                    if (prepared != input) {
                        prepared.delete()
                    }
                }

            val exportTime = System.currentTimeMillis()
            val exportEntry =
                TranscriptionDiagnostics.formatProcessingLog(
                    exportTime,
                    startedAt,
                    "export",
                    output.length(),
                    output.length(),
                    99,
                )
            updateNotification("Сохранение", 99)
            TranscriptionJobController.update { snapshot ->
                snapshot.copy(
                    running = true,
                    processingStage = com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage.Exporting,
                    progress = 99,
                    stageLabel = "Сохранение",
                    lastProgressAt = exportTime,
                    diagnosticLog = (snapshot.diagnosticLog + exportEntry).takeLast(120),
                )
            }

            val transcript = repository.create(displayName, output.readText())
            TranscriptionJobController.update { snapshot ->
                snapshot.copy(
                    running = false,
                    processingStage = com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage.Complete,
                    progress = 100,
                    stageLabel = "Готово",
                    error = null,
                    cancelled = false,
                    resultId = transcript.id,
                    diagnosticLog = snapshot.diagnosticLog,
                )
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Throwable) {
            val cancelled = TranscriptionJobController.cancelRequested.get()
            val message =
                if (cancelled) {
                    null
                } else {
                    error.message ?: "Не удалось обработать файл"
                }
            TranscriptionJobController.update { snapshot ->
                snapshot.copy(
                    running = false,
                    error = message,
                    cancelled = cancelled,
                )
            }
        } finally {
            stopForegroundSafely()
            stopSelf(startId)
        }
    }

    private fun onNativeProgress(
        stage: String,
        done: Long,
        total: Long,
    ): Boolean {
        val mapped =
            TranscriptionStageMapper.toProcessingStage(stage)
                ?: return TranscriptionJobController.cancelRequested.get()
        val range = TranscriptionStageMapper.progressRange(mapped)
        val fraction = if (total > 0L) (done.toDouble() / total).coerceIn(0.0, 1.0) else 0.0
        val percent = range.first + ((range.last - range.first) * fraction).toInt()
        progressFloor = maxOf(progressFloor, percent)
        val now = System.currentTimeMillis()
        val startedAt = TranscriptionJobController.state.value.startedAt
        val entry =
            TranscriptionDiagnostics.formatProcessingLog(now, startedAt, stage, done, total, progressFloor)
        val label = TranscriptionStageMapper.stageLabel(mapped)
        val displayProgress =
            if (mapped == com.hexteam.neurostenographer.ui.viewmodel.ProcessingStage.Complete) {
                100
            } else {
                progressFloor
            }
        updateNotification(label, displayProgress)
        TranscriptionJobController.update { snapshot ->
            snapshot.copy(
                running = true,
                processingStage = mapped,
                progress = displayProgress,
                stageLabel = label,
                nativeStage = stage,
                nativeDone = done,
                nativeTotal = total,
                progressUpdateCount = snapshot.progressUpdateCount + 1,
                lastProgressAt = now,
                diagnosticLog = (snapshot.diagnosticLog + entry).takeLast(120),
            )
        }
        return TranscriptionJobController.cancelRequested.get()
    }

    private fun updateNotification(
        label: String,
        progress: Int,
    ) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, buildNotification(label, progress))
    }

    private fun buildNotification(
        label: String,
        progress: Int,
    ): Notification {
        val cancelIntent =
            Intent(this, TranscriptionService::class.java).apply {
                action = ACTION_CANCEL
            }
        val cancelPendingIntent =
            PendingIntent.getService(
                this,
                1,
                cancelIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        val cancelAction =
            Notification.Action.Builder(
                Icon.createWithResource(this, android.R.drawable.ic_delete),
                "Отмена",
                cancelPendingIntent,
            ).build()

        val builder =
            Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_popup_sync)
                .setContentTitle("Транскрибация")
                .setContentText(label)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setProgress(100, progress.coerceIn(0, 100), progress <= 0)
                .addAction(cancelAction)

        return builder.build()
    }

    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel =
            NotificationChannel(
                CHANNEL_ID,
                "Транскрибация",
                NotificationManager.IMPORTANCE_LOW,
            )
        manager.createNotificationChannel(channel)
    }

    @SuppressLint("InlinedApi")
    private fun startForegroundSafely(notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun stopForegroundSafely() {
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    companion object {
        const val ACTION_START = "com.hexteam.neurostenographer.service.action.START"
        const val ACTION_CANCEL = "com.hexteam.neurostenographer.service.action.CANCEL"
        const val EXTRA_URI = "extra_uri"
        const val EXTRA_NAME = "extra_name"
        const val CHANNEL_ID = "transcription"
        const val NOTIFICATION_ID = 1001
    }
}
