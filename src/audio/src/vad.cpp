#include "internal.hpp"
#include "sherpa-onnx/c-api/c-api.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <memory>

struct nh_vad {
  const SherpaOnnxVoiceActivityDetector *native = nullptr;
  std::atomic_flag busy = ATOMIC_FLAG_INIT;
  uint64_t frames = 0;
  bool flushed = false;
  ~nh_vad() {
    if (native)
      SherpaOnnxDestroyVoiceActivityDetector(native);
  }
};
namespace {
nh_status deliver(nh_vad *handle, nh_speech_callback callback, void *user) {
  while (!SherpaOnnxVoiceActivityDetectorEmpty(handle->native)) {
    auto segment =
        std::unique_ptr<const SherpaOnnxSpeechSegment, decltype(&SherpaOnnxDestroySpeechSegment)>(
            SherpaOnnxVoiceActivityDetectorFront(handle->native), SherpaOnnxDestroySpeechSegment);
    if (!segment || segment->start < 0 || segment->n <= 0)
      return nh::fail(NH_RUNTIME_ERROR, "Invalid VAD segment");
    const uint64_t start = static_cast<uint64_t>(segment->start);
    const uint64_t end = std::min(handle->frames, start + static_cast<uint64_t>(segment->n));
    SherpaOnnxVoiceActivityDetectorPop(handle->native);
    if (start < end && callback(start, end, user))
      return nh::fail(NH_CANCELLED, "VAD delivery cancelled");
  }
  return NH_OK;
}
} // namespace
extern "C" nh_status nh_vad_create(const nh_vad_config *config, nh_vad **out) {
  return nh::guard([&]() -> nh_status {
    if (!out)
      return nh::fail(NH_INVALID_ARGUMENT, "Missing VAD output");
    *out = nullptr;
    if (!config || config->struct_size != sizeof(*config) || !config->threads ||
        config->threads > 16 || !std::isfinite(config->threshold) || config->threshold <= 0 ||
        config->threshold >= 1 || !std::isfinite(config->min_silence_seconds) ||
        config->min_silence_seconds < 0.05f || config->min_silence_seconds > 5 ||
        !std::isfinite(config->min_speech_seconds) || config->min_speech_seconds < 0.05f ||
        config->min_speech_seconds > 2 || !std::isfinite(config->max_speech_seconds) ||
        config->max_speech_seconds < 1 || config->max_speech_seconds > 25)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid VAD configuration");
    if (!config->model || !std::ifstream(config->model).good())
      return nh::fail(NH_IO_ERROR, "VAD model not readable");
    SherpaOnnxVadModelConfig options{};
    options.silero_vad.model = config->model;
    options.silero_vad.threshold = config->threshold;
    options.silero_vad.min_silence_duration = config->min_silence_seconds;
    options.silero_vad.min_speech_duration = config->min_speech_seconds;
    options.silero_vad.max_speech_duration = config->max_speech_seconds;
    options.silero_vad.window_size = 512;
    options.sample_rate = 16000;
    options.num_threads = config->threads;
    options.provider = "cpu";
    auto handle = std::make_unique<nh_vad>();
    handle->native = SherpaOnnxCreateVoiceActivityDetector(&options, 30.0f);
    if (!handle->native)
      return nh::fail(NH_RUNTIME_ERROR, "Cannot initialize Silero VAD");
    *out = handle.release();
    return NH_OK;
  });
}
extern "C" nh_status nh_vad_accept(nh_vad *handle, const float *samples, uint32_t frames,
                                   nh_speech_callback callback, void *user) {
  return nh::guard([&]() -> nh_status {
    if (!handle || !samples || !frames || frames > 400000 || !callback)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid VAD input");
    for (uint32_t i = 0; i < frames; ++i)
      if (!std::isfinite(samples[i]))
        return nh::fail(NH_INVALID_ARGUMENT, "VAD PCM must be finite");
    nh::BusyGuard lock(handle->busy);
    if (!lock.owns_lock())
      return nh::fail(NH_BUSY, "VAD handle busy");
    if (handle->flushed)
      return nh::fail(NH_INVALID_ARGUMENT, "VAD stream already flushed; create a new handle");
    for (uint32_t offset = 0; offset < frames; offset += 512) {
      const uint32_t n = std::min<uint32_t>(512, frames - offset);
      handle->frames += n;
      SherpaOnnxVoiceActivityDetectorAcceptWaveform(handle->native, samples + offset, n);
      const auto code = deliver(handle, callback, user);
      if (code != NH_OK)
        return code;
    }
    return NH_OK;
  });
}
extern "C" nh_status nh_vad_flush(nh_vad *handle, nh_speech_callback callback, void *user) {
  return nh::guard([&]() -> nh_status {
    if (!handle || !callback)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid VAD flush");
    nh::BusyGuard lock(handle->busy);
    if (!lock.owns_lock())
      return nh::fail(NH_BUSY, "VAD handle busy");
    if (!handle->flushed) {
      SherpaOnnxVoiceActivityDetectorFlush(handle->native);
      handle->flushed = true;
    }
    return deliver(handle, callback, user);
  });
}
extern "C" void nh_vad_destroy(nh_vad *handle) {
  delete handle;
}
