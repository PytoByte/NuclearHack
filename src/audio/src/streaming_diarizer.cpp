#include "internal.hpp"
#include "mel.hpp"
#include "speaker_cache.hpp"
#include "onnxruntime_cxx_api.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <vector>

namespace {
Ort::Env& environment() { static Ort::Env value(ORT_LOGGING_LEVEL_WARNING, "nuclear_audio"); return value; }
constexpr size_t slots = 8, dimension = 512;
constexpr uint64_t history = 201;

void validate_model(Ort::Session& session) {
  if (session.GetInputCount() != 3 || session.GetOutputCount() != 3)
    throw std::invalid_argument("Expected Nemotron3 three-input/three-output graph");
  Ort::AllocatorWithDefaultOptions allocator;
  const char* inputs[] = {"input_features", "cached_embeds", "attention_mask"};
  const char* outputs[] = {"logits", "chunk_embeds", "silence_embeds"};
  for (size_t i = 0; i != 3; ++i) {
    auto name = session.GetInputNameAllocated(i, allocator);
    if (std::string(name.get()) != inputs[i]) throw std::invalid_argument("Unexpected streaming input name");
    auto type = session.GetInputTypeInfo(i);
    auto info = type.GetTensorTypeAndShapeInfo();
    const auto shape = info.GetShape();
    if (info.GetElementType() != (i == 2 ? ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64 : ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) ||
        shape.size() != (i == 2 ? 2 : 3) || (shape[0] != -1 && shape[0] != 1) ||
        (i < 2 && shape[2] != (i == 0 ? 128 : 512)))
      throw std::invalid_argument("Unexpected streaming input type/shape");
    auto output_name = session.GetOutputNameAllocated(i, allocator);
    if (std::string(output_name.get()) != outputs[i]) throw std::invalid_argument("Unexpected streaming output name");
    auto output_type = session.GetOutputTypeInfo(i);
    auto output_info = output_type.GetTensorTypeAndShapeInfo();
    const auto output_shape = output_info.GetShape();
    if (output_info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT ||
        output_shape.size() != (i == 2 ? 1 : 3) ||
        (i == 0 && output_shape.back() != 8) ||
        (i == 1 && output_shape.back() != 512) ||
        (i == 2 && output_shape[0] != 512))
      throw std::invalid_argument("Unexpected streaming output type/shape");
  }
}
float sigmoid(float value) {
  if (value >= 0) return 1.f/(1.f+std::exp(-value));
  const float exponential = std::exp(value);
  return exponential/(1.f+exponential);
}
}

struct nh_streaming_diarizer {
  std::atomic_flag busy = ATOMIC_FLAG_INIT;
  Ort::Session session{nullptr};
  nh::MelFrontend frontend;
  nh::SpeakerCache cache;
  uint32_t chunk, right;
  uint64_t max_samples, received = 0, first_mel = 0, base_sample = 0;
  uint64_t calls = 0, emitted = 0, peak_pcm = 0;
  uint32_t max_features = 0;
  double inference_seconds = 0;
  bool flushed = false, failed = false, has_silence = false;
  std::array<float, dimension> silence{};
  std::vector<float> pcm, features;

  explicit nh_streaming_diarizer(const nh_streaming_diarizer_config& config)
      : cache(config.profile == 0 ? 264 : 40, config.profile == 0 ? 222 : 300),
        chunk(config.profile == 0 ? 9 : 340), right(config.profile == 0 ? 4 : 40),
        max_samples(static_cast<uint64_t>(config.max_audio_seconds ? config.max_audio_seconds : 600)*16000) {
    Ort::SessionOptions options;
    options.SetIntraOpNumThreads(static_cast<int>(config.threads)); options.SetInterOpNumThreads(1);
    options.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
    options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    session = Ort::Session(environment(), config.model, options);
    validate_model(session);
    pcm.reserve(static_cast<size_t>(chunk+right)*8*160+history+200);
    features.reserve(static_cast<size_t>(chunk+right)*8*128);
  }

  void discard_history() {
    const uint64_t center = first_mel*160;
    const uint64_t keep_from = center > history ? center-history : 0;
    const uint64_t drop_to = std::min(keep_from, received);
    if (drop_to < base_sample || drop_to-base_sample > pcm.size()) throw std::logic_error("Invalid PCM ring position");
    pcm.erase(pcm.begin(), pcm.begin()+static_cast<size_t>(drop_to-base_sample));
    base_sample = drop_to;
  }

  nh_status step(uint32_t mel_frames, uint32_t keep_mel, nh_speaker_frames_callback callback, void* user) {
    if (!mel_frames || mel_frames > (chunk+right)*8 || !keep_mel || keep_mel > chunk*8 || keep_mel > mel_frames)
      throw std::logic_error("Invalid streaming step budget");
    // Any exception after inference/state mutation poisons this stream until reset.
    failed = true;
    frontend.extract(pcm, base_sample, received, first_mel, mel_frames, features);
    max_features = std::max(max_features, mel_frames);
    const size_t old_cache = cache.cache_frames(), old_fifo = cache.fifo_frames();
    const size_t new_frames = (mel_frames+7)/8, keep = (keep_mel+7)/8;
    auto cached = cache.input();
    float empty = 0;
    std::vector<int64_t> mask(old_cache+old_fifo+new_frames, 1);
    const std::array<int64_t, 3> feature_shape{1, mel_frames, 128};
    const std::array<int64_t, 3> cached_shape{1, static_cast<int64_t>(old_cache+old_fifo), 512};
    const std::array<int64_t, 2> mask_shape{1, static_cast<int64_t>(mask.size())};
    auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    std::array<Ort::Value, 3> inputs{
      Ort::Value::CreateTensor<float>(memory, features.data(), features.size(), feature_shape.data(), feature_shape.size()),
      Ort::Value::CreateTensor<float>(memory, cached.empty() ? &empty : cached.data(), cached.size(), cached_shape.data(), cached_shape.size()),
      Ort::Value::CreateTensor<int64_t>(memory, mask.data(), mask.size(), mask_shape.data(), mask_shape.size())};
    const char* input_names[] = {"input_features", "cached_embeds", "attention_mask"};
    const char* output_names[] = {"logits", "chunk_embeds", "silence_embeds"};
    const auto started = std::chrono::steady_clock::now();
    auto outputs = session.Run(Ort::RunOptions{nullptr}, input_names, inputs.data(), inputs.size(), output_names, 3);
    inference_seconds += std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
    ++calls;
    const size_t total = old_cache+old_fifo+new_frames;
    const std::vector<int64_t> expected[] = {{1, static_cast<int64_t>(total*8), 8},
      {1, static_cast<int64_t>(new_frames), 512}, {512}};
    for (size_t i = 0; i != 3; ++i) {
      const auto info = outputs[i].GetTensorTypeAndShapeInfo();
      if (info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || info.GetShape() != expected[i])
        throw std::runtime_error("Unexpected streaming output grid");
      const float* data = outputs[i].GetTensorData<float>();
      for (size_t j = 0; j < info.GetElementCount(); ++j)
        if (!std::isfinite(data[j])) throw std::runtime_error("Non-finite streaming model output");
    }
    const float* learned = outputs[2].GetTensorData<float>();
    if (has_silence && !std::equal(silence.begin(), silence.end(), learned))
      throw std::runtime_error("Learned silence embedding changed");
    std::copy_n(learned, dimension, silence.begin()); has_silence = true;
    float* probabilities = outputs[0].GetTensorMutableData<float>();
    for (size_t i = 0; i != total*8*slots; ++i) probabilities[i] = sigmoid(probabilities[i]);
    std::vector<float> pooled(total*slots, 0.f);
    for (size_t frame = 0; frame != total; ++frame)
      for (size_t row = 0; row != 8; ++row)
        for (size_t speaker = 0; speaker != slots; ++speaker)
          pooled[frame*slots+speaker] += probabilities[(frame*8+row)*slots+speaker]/8.f;
    cache.update(outputs[1].GetTensorData<float>(), new_frames, pooled, keep, silence.data());
    const uint64_t start_sample = first_mel*160;
    first_mel += keep_mel; emitted += keep_mel;
    const float* current = probabilities+(old_cache+old_fifo)*8*slots;
    const bool cancelled = callback(current, keep_mel, static_cast<uint32_t>(slots), start_sample, user) != 0;
    discard_history();
    if (cancelled) return nh::fail(NH_CANCELLED, "Streaming diarization cancelled");
    failed = false;
    return NH_OK;
  }
};

extern "C" const char* nh_onnxruntime_version(void) { return OrtGetApiBase()->GetVersionString(); }

extern "C" nh_status nh_streaming_diarizer_create(const nh_streaming_diarizer_config* config, nh_streaming_diarizer** out) {
  return nh::guard([&]() -> nh_status {
    if (!out) return nh::fail(NH_INVALID_ARGUMENT, "Missing streaming diarizer output");
    *out = nullptr;
    if (!config || config->struct_size != sizeof(*config) || !config->threads || config->threads > 16 ||
        config->profile > 1 || config->max_audio_seconds > 3600)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid streaming diarizer configuration");
    if (!config->model || !*config->model || !std::ifstream(config->model).good())
      return nh::fail(NH_IO_ERROR, "Streaming diarization model not readable");
    auto handle = std::make_unique<nh_streaming_diarizer>(*config);
    *out = handle.release();
    return NH_OK;
  });
}

extern "C" nh_status nh_streaming_diarizer_accept(nh_streaming_diarizer* handle, const float* samples,
    uint32_t frames, nh_speaker_frames_callback callback, void* user) {
  return nh::guard([&]() -> nh_status {
    if (!handle || !samples || !frames || frames > 400000 || !callback)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid streaming PCM input");
    nh::BusyGuard lock(handle->busy);
    if (!lock.owns_lock()) return nh::fail(NH_BUSY, "Streaming diarizer busy");
    if (handle->flushed || handle->failed) return nh::fail(NH_INVALID_ARGUMENT, "Reset terminated streaming diarizer before reuse");
    if (frames > handle->max_samples-handle->received) return nh::fail(NH_INVALID_ARGUMENT, "Streaming duration budget exceeded");
    for (uint32_t i = 0; i != frames; ++i)
      if (!std::isfinite(samples[i])) return nh::fail(NH_INVALID_ARGUMENT, "Streaming PCM must be finite");
    uint32_t offset = 0;
    while (offset < frames) {
      const uint64_t required = (handle->first_mel+static_cast<uint64_t>(handle->chunk+handle->right)*8-1)*160+200;
      if (handle->received >= required) throw std::logic_error("Unprocessed streaming window");
      const auto take = static_cast<uint32_t>(std::min<uint64_t>(frames-offset, required-handle->received));
      handle->pcm.insert(handle->pcm.end(), samples+offset, samples+offset+take);
      handle->received += take; offset += take;
      handle->peak_pcm = std::max<uint64_t>(handle->peak_pcm, handle->pcm.size());
      if (handle->received == required) {
        const auto status = handle->step((handle->chunk+handle->right)*8, handle->chunk*8, callback, user);
        if (status != NH_OK) return status;
      }
    }
    return NH_OK;
  });
}

extern "C" nh_status nh_streaming_diarizer_flush(nh_streaming_diarizer* handle,
    nh_speaker_frames_callback callback, void* user) {
  return nh::guard([&]() -> nh_status {
    if (!handle || !callback) return nh::fail(NH_INVALID_ARGUMENT, "Invalid streaming flush");
    nh::BusyGuard lock(handle->busy);
    if (!lock.owns_lock()) return nh::fail(NH_BUSY, "Streaming diarizer busy");
    if (handle->failed) return nh::fail(NH_INVALID_ARGUMENT, "Reset failed streaming diarizer before reuse");
    if (handle->flushed) return NH_OK;
    const uint64_t end_mel = handle->received/160;
    while (handle->first_mel < end_mel) {
      const uint32_t keep = static_cast<uint32_t>(std::min<uint64_t>(handle->chunk*8, end_mel-handle->first_mel));
      const uint32_t right = static_cast<uint32_t>(std::min<uint64_t>(handle->right*8, end_mel-handle->first_mel-keep));
      const auto status = handle->step(keep+right, keep, callback, user);
      if (status != NH_OK) return status;
    }
    handle->flushed = true;
    handle->pcm.clear(); handle->base_sample = handle->received;
    return NH_OK;
  });
}

extern "C" nh_status nh_streaming_diarizer_reset(nh_streaming_diarizer* handle) {
  return nh::guard([&]() -> nh_status {
    if (!handle) return nh::fail(NH_INVALID_ARGUMENT, "Missing streaming diarizer");
    nh::BusyGuard lock(handle->busy);
    if (!lock.owns_lock()) return nh::fail(NH_BUSY, "Streaming diarizer busy");
    handle->cache.reset(); handle->pcm.clear(); handle->features.clear();
    handle->received = handle->first_mel = handle->base_sample = 0;
    handle->calls = handle->emitted = handle->peak_pcm = 0; handle->max_features = 0;
    handle->inference_seconds = 0; handle->flushed = handle->failed = handle->has_silence = false;
    return NH_OK;
  });
}

extern "C" nh_status nh_streaming_diarizer_get_stats(nh_streaming_diarizer* handle, nh_streaming_diarizer_stats* out) {
  return nh::guard([&]() -> nh_status {
    if (!handle || !out || out->struct_size != sizeof(*out)) return nh::fail(NH_INVALID_ARGUMENT, "Invalid streaming stats output");
    nh::BusyGuard lock(handle->busy);
    if (!lock.owns_lock()) return nh::fail(NH_BUSY, "Streaming diarizer busy");
    *out = {sizeof(*out), static_cast<uint32_t>(slots), handle->received, handle->emitted, handle->calls,
      handle->pcm.size(), handle->peak_pcm, static_cast<uint32_t>(handle->cache.cache_frames()),
      static_cast<uint32_t>(handle->cache.fifo_frames()), handle->max_features, handle->inference_seconds};
    return NH_OK;
  });
}
extern "C" void nh_streaming_diarizer_destroy(nh_streaming_diarizer* handle) { delete handle; }
