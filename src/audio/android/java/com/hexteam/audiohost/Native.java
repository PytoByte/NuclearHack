package com.hexteam.audiohost;

public final class Native {
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
