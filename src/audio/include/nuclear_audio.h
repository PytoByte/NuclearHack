#ifndef NUCLEAR_AUDIO_H
#define NUCLEAR_AUDIO_H
#include <stdint.h>
#if defined(_WIN32)
#define NH_API __declspec(dllexport)
#else
#define NH_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif

/* v1 ABI. All paths/text are UTF-8. Calls block; invoke on a worker thread.
 * Buffers/text passed to callbacks are borrowed until that callback returns.
 * Callbacks must not throw exceptions across this boundary.
 * Separate handles may run concurrently; a handle permits one operation at a
 * time. Destroy only after all calls on that handle have finished. */
typedef enum nh_status {
  NH_OK = 0, NH_INVALID_ARGUMENT = 1, NH_IO_ERROR = 2,
  NH_RUNTIME_ERROR = 3, NH_CANCELLED = 4, NH_BUSY = 5
} nh_status;
NH_API uint32_t nh_abi_version(void);
/* Thread-local, valid until the next SDK operation on the same thread. */
NH_API const char *nh_last_error(void);
NH_API const char *nh_sherpa_version(void);

/* Frame offsets refer to the resampled source timeline, never wall time.
 * Mono mixes channels; preserve independent stereo speakers outside this API.
 * 0 continues, nonzero cancels. No PCM accumulation; one reused block. */
typedef int32_t (*nh_pcm_callback)(const float *samples, uint32_t frames,
                                  uint64_t start_frame, void *user);
NH_API nh_status nh_decode_file(const char *path, uint32_t sample_rate,
                                uint32_t block_frames, nh_pcm_callback callback,
                                void *user);

/* NeMo/GigaAM CTC adapter. Models/tokens must already be local.
 * No model downloads, network providers, LLM rewriting or UI dependencies. */
typedef struct nh_asr nh_asr;
/* Explicit research/integration configuration. family: ctc/transducer/whisper.
 * CTC and Whisper support greedy_search only. Empty Whisper language = auto.
 * Hotwords require transducer + modified_beam_search, character vocabulary,
 * one known lowercase word per line. Invalid hints fail, never silently skip. */
typedef struct nh_asr_config {
  uint32_t struct_size;
  const char *family;
  const char *model; /* CTC model or transducer/Whisper encoder */
  const char *decoder;
  const char *joiner;
  const char *tokens;
  const char *language;
  const char *decoding_method;
  const char *hotwords_file;
  uint32_t threads;
  uint32_t max_active_paths;
  float hotwords_score;
} nh_asr_config;
NH_API nh_status nh_asr_create(const nh_asr_config *config, nh_asr **out);
NH_API nh_status nh_asr_create_ctc(const char *model, const char *tokens,
                                  uint32_t threads, nh_asr **out);
NH_API nh_status nh_asr_create_transducer(const char *encoder, const char *decoder,
                                         const char *joiner, const char *tokens,
                                         uint32_t threads, nh_asr **out);
/* Multilingual Whisper, fixed Russian/transcribe mode for this SDK revision. */
NH_API nh_status nh_asr_create_whisper(const char *encoder, const char *decoder,
                                      const char *tokens, uint32_t threads, nh_asr **out);
typedef int32_t (*nh_asr_callback)(const char *text, const char *backend_json, void *user);
/* Mono 16-kHz PCM, nominally [-1,1] (finite decoder headroom is accepted),
 * 1..400000 frames (25s). Inputs shorter than 1s are zero-padded for the model;
 * caller clips diagnostic timestamps to the unpadded duration. Backend JSON is a
 * diagnostic ASR result, NOT the competition transcript export.
 * Cancellation granularity is one synchronous inference call. */
NH_API nh_status nh_asr_decode(nh_asr *handle, const float *samples, uint32_t frames,
                               nh_asr_callback callback, void *user);
NH_API void nh_asr_destroy(nh_asr *handle);

/* Whole-window diarization: IDs are scoped to this call. Cross-window matching
 * belongs to the file orchestrator. 16-kHz mono, <=3600s (+1ms codec rounding) per call.
 * Runtime owns segmentation + embedding + clustering; speaker count is auto.
 * cluster_threshold is cosine dissimilarity in (0,2], not a probability. */
typedef struct nh_diarizer nh_diarizer;
typedef struct nh_diarizer_config {
  uint32_t struct_size;
  const char *segmentation;
  const char *embedding;
  uint32_t threads;
  float cluster_threshold;
  float min_duration_on;
  float min_duration_off;
  int32_t oracle_speakers; /* -1 = automatic; positive = diagnostic only */
} nh_diarizer_config;
NH_API nh_status nh_diarizer_create_config(const nh_diarizer_config *config, nh_diarizer **out);
NH_API nh_status nh_diarizer_create_with_window(const nh_diarizer_config *config,
    float window_shift_ratio, nh_diarizer **out);
typedef int32_t (*nh_turn_callback)(int32_t speaker, double start_seconds,
                                   double end_seconds, void *user);
NH_API nh_status nh_diarizer_create(const char *segmentation, const char *embedding,
                                    uint32_t threads, float cluster_threshold,
                                    nh_diarizer **out);
NH_API nh_status nh_diarizer_process(nh_diarizer *handle, const float *samples,
                                     uint32_t frames, nh_turn_callback callback,
                                     void *user);
NH_API void nh_diarizer_destroy(nh_diarizer *handle);

/* Experimental stateful Nemotron3 ONNX diarization. This is independent of the
 * existing file pipeline/default preset. Local graph and external weights must
 * already be present. CPU only; eight model slots, automatic activity, no
 * reference speaker count or cross-stream identity. Input is mono 16-kHz f32.
 * Profile 0: 1.04s nominal input buffer; profile 1: 30.4s. Centered STFT adds
 * 2.5ms at the first full window; computation time is additional.
 * No transcript text or word timestamps are generated/changed by this API. */
typedef struct nh_streaming_diarizer nh_streaming_diarizer;
typedef struct nh_streaming_diarizer_config {
  uint32_t struct_size;
  const char *model;
  uint32_t threads; /* 1..16 */
  uint32_t profile; /* 0 = low latency, 1 = buffered file-mode */
  uint32_t max_audio_seconds; /* 0 = 600, maximum 3600 per stream/reset */
} nh_streaming_diarizer_config;
/* Row-major probabilities[frames][speaker_slots], borrowed during callback.
 * Each posterior row covers 160 original PCM samples (10ms); start_sample is
 * an absolute source PCM offset. The final <160 samples have no complete row.
 * Slots are stable within a stream. Rows are emitted once and never revised.
 * Nonzero cancels after this inference step; reset before another stream. */
typedef int32_t (*nh_speaker_frames_callback)(const float *probabilities,
    uint32_t frames, uint32_t speaker_slots, uint64_t start_sample, void *user);
typedef struct nh_streaming_diarizer_stats {
  uint32_t struct_size;
  uint32_t speaker_slots;
  uint64_t received_samples;
  uint64_t emitted_frames;
  uint64_t model_calls;
  uint64_t buffered_samples;
  uint64_t peak_buffered_samples;
  uint32_t cache_frames;
  uint32_t fifo_frames;
  uint32_t max_feature_frames;
  double inference_seconds; /* synchronous model calls only */
} nh_streaming_diarizer_stats;
NH_API const char *nh_onnxruntime_version(void);
NH_API nh_status nh_streaming_diarizer_create(const nh_streaming_diarizer_config *config,
                                              nh_streaming_diarizer **out);
/* 1..400000 finite PCM samples per call; transport block sizes do not reset
 * model/frontend state. Cancellation is cooperative between inference calls.
 * Runtime failure or cancellation terminates the stream until reset. */
NH_API nh_status nh_streaming_diarizer_accept(nh_streaming_diarizer *handle,
    const float *samples, uint32_t frames, nh_speaker_frames_callback callback, void *user);
NH_API nh_status nh_streaming_diarizer_flush(nh_streaming_diarizer *handle,
    nh_speaker_frames_callback callback, void *user);
/* Reset source timeline/cache, retaining the model session for reuse. */
NH_API nh_status nh_streaming_diarizer_reset(nh_streaming_diarizer *handle);
NH_API nh_status nh_streaming_diarizer_get_stats(nh_streaming_diarizer *handle,
                                                nh_streaming_diarizer_stats *out);
NH_API void nh_streaming_diarizer_destroy(nh_streaming_diarizer *handle);

/* Incremental Silero VAD. Emits unpadded source-frame ranges at 16 kHz;
 * caller applies padding and joins overlaps without changing source offsets. */
typedef struct nh_vad nh_vad;
typedef struct nh_vad_config {
  uint32_t struct_size;
  const char *model;
  uint32_t threads;
  float threshold;
  float min_silence_seconds;
  float min_speech_seconds;
  float max_speech_seconds;
} nh_vad_config;
typedef int32_t (*nh_speech_callback)(uint64_t start_frame, uint64_t end_frame, void *user);
NH_API nh_status nh_vad_create(const nh_vad_config *config, nh_vad **out);
NH_API nh_status nh_vad_accept(nh_vad *handle, const float *samples, uint32_t frames,
                               nh_speech_callback callback, void *user);
NH_API nh_status nh_vad_flush(nh_vad *handle, nh_speech_callback callback, void *user);
NH_API void nh_vad_destroy(nh_vad *handle);

/* File pipeline. The SDK writes only output_json and optional trace_json.
 * Scratch PCM is spooled to disk, then unlinked; models run sequentially.
 * Cancellation is cooperative at decoder blocks/ASR chunks/stage boundaries. */
typedef struct nh_pipeline_config {
  uint32_t struct_size;
  const char *asr_model;
  const char *tokens;
  const char *segmentation;
  const char *embedding;
  const char *scratch_directory;
  const char *output_json;
  const char *trace_json;
  uint32_t threads;
  uint32_t chunk_seconds;
  uint32_t max_audio_seconds;
  float cluster_threshold;
} nh_pipeline_config;
typedef int32_t (*nh_progress_callback)(const char *stage, uint64_t completed_frames,
                                        uint64_t total_frames, void *user);
NH_API nh_status nh_transcribe_file(const char *input_path, const nh_pipeline_config *config,
                                    nh_progress_callback progress, void *user);
typedef struct nh_pipeline_options {
  uint32_t struct_size;
  float min_duration_on;
  float min_duration_off;
  uint32_t attribution_mode; /* 0 maximum overlap, 1 midpoint */
  const char *checkpoint_directory; /* Optional private directory, atomic ASR cache; no text in shared logs */
  float window_shift_ratio; /* 0 uses baseline .1; explicit range [.05,1] */
} nh_pipeline_options;
NH_API nh_status nh_transcribe_file_with_options(const char *input_path, const nh_pipeline_config *config,
    const nh_pipeline_options *options, nh_progress_callback progress, void *user);
/* Optional global speaker refinement; existing ABI structs/defaults stay unchanged.
 * Uses config->embedding after releasing the diarizer. Up to three predicted
 * spans, 2..20s total per cluster; complete linkage forbids merging simultaneous
 * predicted speakers. No oracle speaker count. Experimental, caller opt-in. */
typedef struct nh_speaker_refinement_config {
  uint32_t struct_size;
  float cluster_threshold; /* cosine dissimilarity in (0,2); dev candidate .4 */
  uint32_t max_clusters; /* 0 = 128, maximum 256; excess fails explicitly */
} nh_speaker_refinement_config;
NH_API nh_status nh_transcribe_file_with_refinement(const char *input_path, const nh_pipeline_config *config,
    const nh_pipeline_options *options, const nh_speaker_refinement_config *refinement,
    nh_progress_callback progress, void *user);
typedef struct nh_llm_config {
  uint32_t struct_size;
  const char *model;
  const char *output_text;
  uint32_t threads;
  uint32_t context_tokens;
  uint32_t max_output_tokens;
} nh_llm_config;
NH_API int32_t nh_llm_available(void);
/* Separate Qwen3 summary; never modifies the source transcript JSON. */
NH_API nh_status nh_summarize_file(const char *transcript_json, const nh_llm_config *config,
                                  nh_progress_callback progress, void *user);
#ifdef __cplusplus
}
#endif
#endif
