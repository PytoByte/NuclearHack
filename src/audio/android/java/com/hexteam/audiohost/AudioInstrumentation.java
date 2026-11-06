package com.hexteam.audiohost;

import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Debug;
import android.os.SystemClock;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.json.JSONArray;
import org.json.JSONObject;

public final class AudioInstrumentation extends Instrumentation {
    private Bundle arguments;
    public void onCreate(Bundle args) { super.onCreate(args); arguments = args; start(); }
    private static void write(File path, String text) throws Exception {
        try (FileWriter output = new FileWriter(path)) { output.write(text); }
    }
    private static byte[] digest(File path) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path.toPath()));
    }
    public void onStart() {
        Bundle status = new Bundle();
        try {
            String runId = arguments.getString("run_id", "baseline");
            if (!runId.matches("[a-zA-Z0-9_-]+")) throw new IllegalArgumentException("Invalid run ID");
            File base = getTargetContext().getFilesDir();
            File run = new File(base, "results/" + runId);
            if (run.exists()) throw new IllegalStateException("Run ID already exists");
            if (!run.mkdirs()) throw new IllegalStateException("Cannot create output directory");
            int threads = Integer.parseInt(arguments.getString("threads", "4"));
            float threshold = Float.parseFloat(arguments.getString("threshold", "0.8"));
            int chunk = Integer.parseInt(arguments.getString("chunk_seconds", "20"));
            boolean summary = "1".equals(arguments.getString("summary", "1"));
            String[] cases = arguments.getString("cases", "dialogs-clean_2,dialogs-pauses_short_3,dialogs-noise_overlap_3").split(",");
            if (summary && Native.llmAvailable() != 1) throw new IllegalStateException("LLM runtime missing");
            JSONArray results = new JSONArray();
            for (String audioId : cases) {
                if (!audioId.matches("[a-zA-Z0-9_-]+")) throw new IllegalArgumentException("Invalid audio ID");
                File output = new File(run, audioId + ".json");
                File events = new File(run, audioId + ".events.jsonl");
                AtomicBoolean sampling = new AtomicBoolean(true);
                AtomicLong peakPss = new AtomicLong(0);
                Thread monitor = new Thread(() -> {
                    while (sampling.get()) {
                        peakPss.accumulateAndGet(Debug.getPss(), Math::max);
                        SystemClock.sleep(100);
                    }
                }, "audio-memory");
                long began = SystemClock.elapsedRealtime();
                AtomicLong previousEvent = new AtomicLong(began);
                Native.listener = (stage, done, total) -> {
                    try {
                        long now = SystemClock.elapsedRealtime();
                        long previous = previousEvent.getAndSet(now);
                        JSONObject event = new JSONObject().put("run_id", runId).put("audio_id", audioId)
                            .put("stage", stage).put("elapsed_ms", now - began)
                            .put("start_ms", previous - began).put("duration_ms", now - previous)
                            .put("memory_mb", peakPss.get() / 1024.0).put("memory_kind", "sampled_peak_pss")
                            .put("status", stage.endsWith("done") ? "done" : "processing")
                            .put("model", stage.startsWith("llm") ? "qwen3-0.6b-q8" :
                                stage.startsWith("diarization") ? "pyannote-eres2net-fp32" : "giga-v3-ctc")
                            .put("config_hash", arguments.getString("config_hash", "not-provided"))
                            .put("completed_frames", done).put("total_frames", total);
                        try (FileWriter log = new FileWriter(events, true)) { log.write(event.toString() + "\n"); }
                        Bundle progress = new Bundle(); progress.putString("stage", stage);
                        sendStatus(0, progress);
                        return false;
                    } catch (Exception e) { return true; }
                };
                monitor.start();
                int code;
                try {
                    code = Native.transcribe(new File(base, "audio/" + audioId + ".mp3").toString(),
                        output.toString(), new File(base, "models").toString(), run.toString(), threads, threshold, chunk);
                } finally { sampling.set(false); monitor.join(); }
                if (code != 0) throw new IllegalStateException("Native status " + code + ": " + Native.lastError());
                JSONObject result = new JSONObject().put("audio_id", audioId)
                    .put("wall_ms", SystemClock.elapsedRealtime() - began).put("sampled_peak_pss_kib", peakPss.get())
                    .put("pss_sample_period_ms", 100).put("process_lifetime_peak_rss_kib", Native.peakRssKib());
                if (summary) {
                    byte[] sourceHash = digest(output);
                    AtomicBoolean llmSampling = new AtomicBoolean(true);
                    AtomicLong llmPeakPss = new AtomicLong(0);
                    Thread llmMonitor = new Thread(() -> {
                        while (llmSampling.get()) {
                            llmPeakPss.accumulateAndGet(Debug.getPss(), Math::max);
                            SystemClock.sleep(100);
                        }
                    }, "llm-memory");
                    long llmStart = SystemClock.elapsedRealtime();
                    llmMonitor.start();
                    int llm;
                    try {
                        llm = Native.summarize(output.toString(), new File(base, "models/qwen3-0.6b-q8/Qwen3-0.6B-Q8_0.gguf").toString(),
                            new File(run, audioId + ".summary.txt").toString(), threads);
                    } finally { llmSampling.set(false); llmMonitor.join(); }
                    if (llm != 0) throw new IllegalStateException("Summary status " + llm + ": " + Native.lastError());
                    boolean unchanged = Arrays.equals(sourceHash, digest(output));
                    if (!unchanged) throw new IllegalStateException("Summary changed main transcript");
                    result.put("llm_wall_ms", SystemClock.elapsedRealtime() - llmStart)
                        .put("main_transcript_unchanged", unchanged)
                        .put("llm_sampled_peak_pss_kib", llmPeakPss.get())
                        .put("process_lifetime_peak_rss_after_llm_kib", Native.peakRssKib());
                }
                results.put(result);
                write(new File(run, "metrics.json"), new JSONObject().put("run_id", runId).put("cases", results)
                    .put("scope", "Android 4GB headless native SDK host").toString(2));
            }
            Native.listener = null;
            status.putString("result", "PASS"); status.putString("path", run.toString());
            finish(-1, status);
        } catch (Throwable error) {
            Native.listener = null;
            status.putString("result", "FAIL"); status.putString("error", error.toString());
            finish(0, status);
        }
    }
}
