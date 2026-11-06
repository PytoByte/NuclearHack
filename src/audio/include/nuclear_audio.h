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
 * 1..400000 frames (25s). Backend JSON is a
 * diagnostic ASR result, NOT the competition transcript export.
 * Cancellation granularity is one synchronous inference call. */
NH_API nh_status nh_asr_decode(nh_asr *handle, const float *samples, uint32_t frames,
                               nh_asr_callback callback, void *user);
NH_API void nh_asr_destroy(nh_asr *handle);

/* Whole-window diarization: IDs are scoped to this call. Cross-window matching
 * belongs to the future file orchestrator. 16-kHz mono, <=600s per call.
 * Runtime owns segmentation + embedding + clustering; speaker count is auto.
 * cluster_threshold is cosine dissimilarity in (0,2], not a probability. */
typedef struct nh_diarizer nh_diarizer;
typedef int32_t (*nh_turn_callback)(int32_t speaker, double start_seconds,
                                   double end_seconds, void *user);
NH_API nh_status nh_diarizer_create(const char *segmentation, const char *embedding,
                                    uint32_t threads, float cluster_threshold,
                                    nh_diarizer **out);
NH_API nh_status nh_diarizer_process(nh_diarizer *handle, const float *samples,
                                     uint32_t frames, nh_turn_callback callback,
                                     void *user);
NH_API void nh_diarizer_destroy(nh_diarizer *handle);
#ifdef __cplusplus
}
#endif
#endif
