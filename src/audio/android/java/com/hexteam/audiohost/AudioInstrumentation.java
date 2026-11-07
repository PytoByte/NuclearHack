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
import java.util.concurrent.atomic.AtomicReference;
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
            Native.JobOptions job=new Native.JobOptions();
            job.threads=threads;job.threshold=threshold;job.chunkSeconds=chunk;
            job.maxAudioSeconds=Integer.parseInt(arguments.getString("max_seconds","600"));
            job.minOn=Float.parseFloat(arguments.getString("min_on","0.3"));
            job.minOff=Float.parseFloat(arguments.getString("min_off","0.5"));
            job.refinementThreshold=Float.parseFloat(arguments.getString("refinement_threshold","0"));
            job.windowShiftRatio=Float.parseFloat(arguments.getString("window_shift_ratio","0.1"));
            job.attributionMode=Integer.parseInt(arguments.getString("attribution_mode","0"));
            String model=arguments.getString("asr_model","giga-v3-ctc"), modelFile=arguments.getString("model_file","model.int8.onnx");
            String embedding=arguments.getString("embedding","embedding.onnx"), segmentation=arguments.getString("segmentation","segmentation-model.onnx");
            if(!model.matches("[a-zA-Z0-9_-]+") || !modelFile.matches("[a-zA-Z0-9_.-]+") ||
                !embedding.matches("[a-zA-Z0-9_.-]+") || !segmentation.matches("[a-zA-Z0-9_.-]+")) throw new IllegalArgumentException("Invalid model paths");
            job.asrModel=model+"/"+modelFile;job.tokens=model+"/tokens.txt";
            job.embedding="diarization/"+embedding;job.segmentation="diarization/"+segmentation;
            String cancelStage=arguments.getString("cancel_stage","");
            long cancelFrames=Long.parseLong(arguments.getString("cancel_after_frames","0"));
            boolean expectedCancel="1".equals(arguments.getString("expect_cancel","0"));
            boolean summary = "1".equals(arguments.getString("summary", "1"));
            String[] cases = arguments.getString("cases", "dialogs-clean_2,dialogs-pauses_short_3,dialogs-noise_overlap_3").split(",");
            if (summary && Native.llmAvailable() != 1) throw new IllegalStateException("LLM runtime missing");
            JSONArray results = new JSONArray();
            for (String audioId : cases) {
                if (!audioId.matches("[a-zA-Z0-9_-]+")) throw new IllegalArgumentException("Invalid audio ID");
                File output = new File(run, audioId + ".json");
                File events = new File(run, audioId + ".events.jsonl");
                if("1".equals(arguments.getString("checkpoint","0"))) {
                    File cache=new File(base,"job-cache/"+audioId);
                    if(!cache.exists() && !cache.mkdirs())throw new IllegalStateException("Cannot create checkpoint directory");
                    job.checkpointDirectory=cache.toString();
                }
                AtomicBoolean sampling = new AtomicBoolean(true);
                AtomicLong peakPss = new AtomicLong(0);
                AtomicLong currentPss = new AtomicLong(0);
                Thread monitor = new Thread(() -> {
                    while (sampling.get()) {
                        long pss = Debug.getPss(); currentPss.set(pss);
                        peakPss.accumulateAndGet(pss, Math::max);
                        SystemClock.sleep(100);
                    }
                }, "audio-memory");
                long began = SystemClock.elapsedRealtime();
                AtomicLong previousEvent = new AtomicLong(began);
                AtomicReference<String> previousStage=new AtomicReference<>("queued");
                Native.listener = (stage, done, total) -> {
                    try {
                        long now = SystemClock.elapsedRealtime();
                        long previous = previousEvent.getAndSet(now);
                        JSONObject event = new JSONObject().put("run_id", runId).put("audio_id", audioId)
                            .put("stage", stage).put("elapsed_ms", now - began)
                            .put("start_ms", previous - began).put("duration_ms", now - previous)
                            .put("previous_stage",previousStage.getAndSet(stage)).put("duration_scope","since_previous_callback")
                            .put("unit",stage.startsWith("llm")?"tokens":"frames")
                            .put("memory_mb", currentPss.get() / 1024.0).put("memory_kind", "latest_sampled_pss")
                            .put("status", stage.endsWith("done") ? "done" : "processing")
                            .put("model", stage.startsWith("llm") ? "qwen3-0.6b-q8" :
                                stage.startsWith("diarization") ? segmentation+"/"+embedding :
                                stage.startsWith("speaker_") ? embedding : model)
                            .put("config_hash", arguments.getString("config_hash", "not-provided"))
                            .put("completed_frames", done).put("total_frames", total);
                        try (FileWriter log = new FileWriter(events, true)) { log.write(event.toString() + "\n"); }
                        Bundle progress = new Bundle(); progress.putString("stage", stage);
                        sendStatus(0, progress);
                        return !cancelStage.isEmpty() && stage.equals(cancelStage) && done>=cancelFrames;
                    } catch (Exception e) { return true; }
                };
                monitor.start();
                int code;
                try {
                    code = Native.transcribeJob(new File(base, "audio/" + audioId + ".mp3").toString(),
                        output.toString(), new File(base, "models").toString(), run.toString(),job);
                } finally { sampling.set(false); monitor.join(); }
                if(expectedCancel && code==4) {
                    if(output.exists())throw new IllegalStateException("Cancelled job committed final export");
                    results.put(new JSONObject().put("audio_id",audioId).put("status",code)
                        .put("expected_cancel",true).put("wall_ms",SystemClock.elapsedRealtime()-began)
                        .put("sampled_peak_pss_kib",peakPss.get()));
                    write(new File(run,"metrics.json"),new JSONObject().put("run_id",runId).put("cases",results).toString(2));
                    continue;
                }
                if(expectedCancel)throw new IllegalStateException("Requested cancellation did not occur");
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
                            long pss = Debug.getPss(); currentPss.set(pss);
                            llmPeakPss.accumulateAndGet(pss, Math::max);
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
