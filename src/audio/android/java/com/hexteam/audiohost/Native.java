package com.hexteam.audiohost;

public final class Native {
    public static final class JobOptions {
        public int threads=4, chunkSeconds=20, maxAudioSeconds=600, attributionMode=0;
        public float threshold=0.8f, minOn=0.3f, minOff=0.5f, windowShiftRatio=0.1f;
        public String asrModel="giga-v3-ctc/model.int8.onnx", tokens="giga-v3-ctc/tokens.txt";
        public String segmentation="diarization/segmentation-model.onnx", embedding="diarization/embedding.onnx";
        public String checkpointDirectory=null;
    }
    public static native int transcribeJob(String input,String output,String models,String scratch,JobOptions options);
    public static native long asrCreate(String root, String family, String modelFile, int threads, String method, String language, String hotwords);
    public static native String asrDecode(long handle, String input);
    public static native void asrDestroy(long handle);
    static { System.loadLibrary("nuclear_audio_jni"); }
    public interface Listener { boolean progress(String stage, long done, long total); }
    public static volatile Listener listener;
    public static boolean onProgress(String stage, long done, long total) {
        Listener current = listener;
        return current != null && current.progress(stage, done, total);
    }
    public static native int transcribe(String input, String output, String models, String scratch,
        int threads, float threshold, int chunkSeconds);
    public static native int summarize(String transcript, String model, String output, int threads);
    public static native String lastError();
    public static native int llmAvailable();
    public static native long peakRssKib();
}
