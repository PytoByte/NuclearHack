package com.hexteam.neurostenographer.audio;

/** JNI bridge to the local nuclear_audio SDK. All calls block; use a worker thread. */
public final class NativeAudio {
    private NativeAudio() {}

    public static final class JobOptions {
        public int threads = 4;
        public int chunkSeconds = 20;
        public int maxAudioSeconds = 600;
        public int attributionMode = 0;
        public float threshold = 0.8f;
        public float minOn = 0.3f;
        public float minOff = 0.5f;
        public float windowShiftRatio = 0.1f;
        public float refinementThreshold = 0;
        public String asrModel = "giga-v3-ctc/model.int8.onnx";
        public String tokens = "giga-v3-ctc/tokens.txt";
        public String segmentation = "diarization/segmentation-model.onnx";
        public String embedding = "diarization/embedding.onnx";
        public String checkpointDirectory = null;
    }

    public interface Listener {
        boolean progress(String stage, long done, long total);
    }

    /** Progress is delivered on the native worker thread. */
    public static volatile Listener listener;

    public static boolean onProgress(String stage, long done, long total) {
        Listener current = listener;
        return current != null && current.progress(stage, done, total);
    }

    public static native int transcribeJob(
            String input, String output, String models, String scratch, JobOptions options);

    public static native int transcribeFinal(
            String input,
            String output,
            String asrModel,
            String tokens,
            String speakerModel,
            String scratch,
            int threads,
            int maxAudioSeconds,
            String checkpointDirectory,
            String traceJson);

    public static native int summarize(String transcript, String model, String output, int threads);

    public static native String lastError();

    public static native int llmAvailable();

    public static native long peakRssKib();

    static {
        System.loadLibrary("nuclear_audio_jni");
    }
}
