#include "internal.hpp"
#include "sherpa-onnx/c-api/c-api.h"
#include <cmath>
#include <fstream>
#include <memory>
#include <mutex>

struct nh_asr {
  const SherpaOnnxOfflineRecognizer *native = nullptr;
  std::mutex mutex;
  ~nh_asr() { if (native) SherpaOnnxDestroyOfflineRecognizer(native); }
};
struct nh_diarizer {
  const SherpaOnnxOfflineSpeakerDiarization *native = nullptr;
  std::mutex mutex;
  ~nh_diarizer() { if (native) SherpaOnnxDestroyOfflineSpeakerDiarization(native); }
};
namespace {
bool readable(const char *path) { return path && *path && std::ifstream(path).good(); }
bool valid_pcm(const float *samples, uint32_t n, uint32_t max) {
  if (!samples || !n || n > max) return false;
  for (uint32_t i = 0; i < n; ++i)
    if (!std::isfinite(samples[i])) return false;
  return true;
}
nh_status create_recognizer(SherpaOnnxOfflineRecognizerConfig &config, uint32_t threads, nh_asr **out) {
  config.feat_config.sample_rate = 16000;
  config.feat_config.feature_dim = 80;
  config.model_config.num_threads = static_cast<int32_t>(threads);
  config.model_config.provider = "cpu";
  config.decoding_method = "greedy_search";
  auto handle = std::make_unique<nh_asr>();
  handle->native = SherpaOnnxCreateOfflineRecognizer(&config);
  if (!handle->native) return nh::fail(NH_RUNTIME_ERROR, "Could not initialize ASR model");
  *out = handle.release();
  return NH_OK;
}
}
extern "C" {
const char *nh_sherpa_version(void) { return SherpaOnnxGetVersionStr(); }
nh_status nh_asr_create_ctc(const char *model, const char *tokens, uint32_t threads, nh_asr **out) {
  return nh::guard([&]() -> nh_status {
    if (!out) return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
    *out = nullptr;
    if (threads == 0 || threads > 16) return nh::fail(NH_INVALID_ARGUMENT, "threads must be 1..16");
    if (!readable(model) || !readable(tokens)) return nh::fail(NH_IO_ERROR, "Model/tokens not readable");
    SherpaOnnxOfflineRecognizerConfig config{};
    config.feat_config.sample_rate = 16000;
    config.feat_config.feature_dim = 80;
    config.model_config.nemo_ctc.model = model;
    config.model_config.tokens = tokens;
    config.model_config.num_threads = static_cast<int32_t>(threads);
    config.model_config.provider = "cpu";
    config.decoding_method = "greedy_search";
    auto handle = std::make_unique<nh_asr>();
    handle->native = SherpaOnnxCreateOfflineRecognizer(&config);
    if (!handle->native) return nh::fail(NH_RUNTIME_ERROR, "Could not initialize CTC model");
    *out = handle.release();
    return NH_OK;
  });
}
nh_status nh_asr_decode(nh_asr *handle, const float *samples, uint32_t frames,
                       nh_asr_callback callback, void *user) {
  return nh::guard([&]() -> nh_status {
    if (!handle || !callback || !valid_pcm(samples, frames, 400000))
      return nh::fail(NH_INVALID_ARGUMENT, "Expected handle, callback, finite 16kHz PCM <=25s");
    std::unique_lock<std::mutex> lock(handle->mutex, std::try_to_lock);
    if (!lock.owns_lock()) return nh::fail(NH_BUSY, "ASR handle busy");
    auto stream = std::unique_ptr<const SherpaOnnxOfflineStream, decltype(&SherpaOnnxDestroyOfflineStream)>(
        SherpaOnnxCreateOfflineStream(handle->native), SherpaOnnxDestroyOfflineStream);
    if (!stream) return nh::fail(NH_RUNTIME_ERROR, "Could not create ASR stream");
    SherpaOnnxAcceptWaveformOffline(stream.get(), 16000, samples, static_cast<int32_t>(frames));
    SherpaOnnxDecodeOfflineStream(handle->native, stream.get());
    auto result = std::unique_ptr<const SherpaOnnxOfflineRecognizerResult, decltype(&SherpaOnnxDestroyOfflineRecognizerResult)>(
        SherpaOnnxGetOfflineStreamResult(stream.get()), SherpaOnnxDestroyOfflineRecognizerResult);
    if (!result) return nh::fail(NH_RUNTIME_ERROR, "No ASR result");
    if (callback(result->text, result->json, user)) return nh::fail(NH_CANCELLED, "Result delivery cancelled");
    return NH_OK;
  });
}
nh_status nh_asr_create_transducer(const char *encoder, const char *decoder, const char *joiner,
                                  const char *tokens, uint32_t threads, nh_asr **out) {
  return nh::guard([&]() -> nh_status {
    if (!out) return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
    *out = nullptr;
    if (!threads || threads > 16) return nh::fail(NH_INVALID_ARGUMENT, "threads must be 1..16");
    if (!readable(encoder) || !readable(decoder) || !readable(joiner) || !readable(tokens))
      return nh::fail(NH_IO_ERROR, "Transducer model/tokens not readable");
    SherpaOnnxOfflineRecognizerConfig config{};
    config.model_config.transducer.encoder = encoder;
    config.model_config.transducer.decoder = decoder;
    config.model_config.transducer.joiner = joiner;
    config.model_config.tokens = tokens;
    return create_recognizer(config, threads, out);
  });
}
nh_status nh_asr_create_whisper(const char *encoder, const char *decoder, const char *tokens,
                               uint32_t threads, nh_asr **out) {
  return nh::guard([&]() -> nh_status {
    if (!out) return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
    *out = nullptr;
    if (!threads || threads > 16) return nh::fail(NH_INVALID_ARGUMENT, "threads must be 1..16");
    if (!readable(encoder) || !readable(decoder) || !readable(tokens))
      return nh::fail(NH_IO_ERROR, "Whisper model/tokens not readable");
    SherpaOnnxOfflineRecognizerConfig config{};
    config.model_config.whisper.encoder = encoder;
    config.model_config.whisper.decoder = decoder;
    config.model_config.whisper.language = "ru";
    config.model_config.whisper.task = "transcribe";
    config.model_config.whisper.tail_paddings = -1;
    config.model_config.tokens = tokens;
    return create_recognizer(config, threads, out);
  });
}
void nh_asr_destroy(nh_asr *handle) { delete handle; }
nh_status nh_diarizer_create(const char *segmentation, const char *embedding,
                            uint32_t threads, float threshold, nh_diarizer **out) {
  return nh::guard([&]() -> nh_status {
    if (!out) return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
    *out = nullptr;
    // sherpa clusters by cosine dissimilarity (1 - cosine), whose range is [0,2].
    if (!threads || threads > 16 || !std::isfinite(threshold) || threshold <= 0 || threshold > 2)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid diarization threads/threshold");
    if (!readable(segmentation) || !readable(embedding)) return nh::fail(NH_IO_ERROR, "Diarization models not readable");
    SherpaOnnxOfflineSpeakerDiarizationConfig config{};
    config.segmentation.pyannote.model = segmentation;
    config.segmentation.num_threads = static_cast<int32_t>(threads);
    config.segmentation.provider = "cpu";
    config.embedding.model = embedding;
    config.embedding.num_threads = static_cast<int32_t>(threads);
    config.embedding.provider = "cpu";
    config.clustering.num_clusters = -1;
    config.clustering.threshold = threshold;
    config.min_duration_on = 0.3f;
    config.min_duration_off = 0.5f;
    auto handle = std::make_unique<nh_diarizer>();
    handle->native = SherpaOnnxCreateOfflineSpeakerDiarization(&config);
    if (!handle->native) return nh::fail(NH_RUNTIME_ERROR, "Could not initialize diarizer");
    *out = handle.release();
    return NH_OK;
  });
}
nh_status nh_diarizer_process(nh_diarizer *handle, const float *samples, uint32_t frames,
                             nh_turn_callback callback, void *user) {
  return nh::guard([&]() -> nh_status {
    if (!handle || !callback || !valid_pcm(samples, frames, 16000 * 600))
      return nh::fail(NH_INVALID_ARGUMENT, "Expected handle, callback, finite 16kHz PCM <=600s");
    std::unique_lock<std::mutex> lock(handle->mutex, std::try_to_lock);
    if (!lock.owns_lock()) return nh::fail(NH_BUSY, "Diarizer handle busy");
    auto result = std::unique_ptr<const SherpaOnnxOfflineSpeakerDiarizationResult, decltype(&SherpaOnnxOfflineSpeakerDiarizationDestroyResult)>(
        SherpaOnnxOfflineSpeakerDiarizationProcess(handle->native, samples, static_cast<int32_t>(frames)),
        SherpaOnnxOfflineSpeakerDiarizationDestroyResult);
    if (!result) return nh::fail(NH_RUNTIME_ERROR, "No diarization result");
    const int32_t count = SherpaOnnxOfflineSpeakerDiarizationResultGetNumSegments(result.get());
    auto turns = std::unique_ptr<const SherpaOnnxOfflineSpeakerDiarizationSegment, decltype(&SherpaOnnxOfflineSpeakerDiarizationDestroySegment)>(
        SherpaOnnxOfflineSpeakerDiarizationResultSortByStartTime(result.get()),
        SherpaOnnxOfflineSpeakerDiarizationDestroySegment);
    if (count > 0 && !turns) return nh::fail(NH_RUNTIME_ERROR, "No diarization segments");
    for (int32_t i = 0; i < count; ++i) {
      const auto &turn = turns.get()[i];
      if (callback(turn.speaker, turn.start, turn.end, user))
        return nh::fail(NH_CANCELLED, "Turn delivery cancelled");
    }
    return NH_OK;
  });
}
void nh_diarizer_destroy(nh_diarizer *handle) { delete handle; }
}
