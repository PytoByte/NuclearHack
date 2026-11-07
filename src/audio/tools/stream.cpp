#include "nuclear_audio.h"
#include "picosha2.h"
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>
#include <sys/resource.h>
#include <unistd.h>
#include <vector>

namespace {
struct Context {
  nh_streaming_diarizer *handle = nullptr;
  int descriptor = -1;
  uint64_t source_samples = 0, emitted_frames = 0;
  nh_status status = NH_OK;
  std::string error;
  picosha2::hash256_one_by_one pcm_hash;
  std::chrono::steady_clock::time_point previous_posterior;
  std::vector<double> callback_intervals;
};
int32_t posterior(const float *values, uint32_t frames, uint32_t slots, uint64_t start,
                  void *user) noexcept try {
  auto &context = *static_cast<Context *>(user);
  if (!values || slots != 8 || !frames || start != context.emitted_frames * 160) {
    context.status = NH_RUNTIME_ERROR;
    context.error = "Invalid posterior source timeline";
    return 1;
  }
  const auto now = std::chrono::steady_clock::now();
  context.callback_intervals.push_back(
      std::chrono::duration<double>(now - context.previous_posterior).count());
  context.previous_posterior = now;
  const auto *bytes = reinterpret_cast<const unsigned char *>(values);
  size_t remaining = static_cast<size_t>(frames) * slots * sizeof(float);
  while (remaining) {
    const auto written = write(context.descriptor, bytes, remaining);
    if (written < 0 && errno == EINTR)
      continue;
    if (written <= 0) {
      context.status = NH_IO_ERROR;
      context.error = "Cannot write posterior data";
      return 1;
    }
    bytes += written;
    remaining -= static_cast<size_t>(written);
  }
  context.emitted_frames += frames;
  return 0;
} catch (...) {
  auto &context = *static_cast<Context *>(user);
  context.status = NH_RUNTIME_ERROR;
  context.error.clear();
  return 1;
}
int32_t decoded(const float *samples, uint32_t frames, uint64_t start, void *user) noexcept try {
  auto &context = *static_cast<Context *>(user);
  if (start != context.source_samples) {
    context.status = NH_RUNTIME_ERROR;
    context.error = "Noncontiguous decoded PCM";
    return 1;
  }
  const auto *bytes = reinterpret_cast<const unsigned char *>(samples);
  context.pcm_hash.process(bytes, bytes + static_cast<size_t>(frames) * sizeof(float));
  const auto status =
      nh_streaming_diarizer_accept(context.handle, samples, frames, posterior, user);
  if (status != NH_OK) {
    if (context.status == NH_OK) {
      context.status = status;
      context.error = nh_last_error();
    }
    return 1;
  }
  context.source_samples += frames;
  return 0;
} catch (...) {
  auto &context = *static_cast<Context *>(user);
  context.status = NH_RUNTIME_ERROR;
  context.error.clear();
  return 1;
}
} // namespace

int main(int argc, char **argv) {
  if (argc < 4 || argc > 7) {
    std::cerr << "Usage: nh-audio-stream INPUT MODEL OUTPUT_F32LE [THREADS PROFILE MAX_SECONDS]\n";
    return NH_INVALID_ARGUMENT;
  }
  int descriptor = -1;
  try {
    const uint16_t endian = 1;
    if (*reinterpret_cast<const unsigned char *>(&endian) != 1)
      throw std::runtime_error("Expected little-endian target");
    auto parse = [&](int index, uint32_t fallback) -> uint32_t {
      if (argc <= index)
        return fallback;
      size_t consumed = 0;
      const auto value = std::stoull(argv[index], &consumed);
      if (consumed != std::strlen(argv[index]) || value > UINT32_MAX)
        throw std::invalid_argument("Invalid integer argument");
      return static_cast<uint32_t>(value);
    };
    nh_streaming_diarizer_config config{sizeof(config), argv[2], parse(4, 4), parse(5, 1),
                                        parse(6, 600)};
    const auto started = std::chrono::steady_clock::now();
    std::cerr << "{\"stage\":\"speaker_load\"}\n";
    nh_streaming_diarizer *raw = nullptr;
    auto status = nh_streaming_diarizer_create(&config, &raw);
    if (status != NH_OK) {
      std::cerr << nh_last_error() << '\n';
      return status;
    }
    std::unique_ptr<nh_streaming_diarizer, decltype(&nh_streaming_diarizer_destroy)> handle(
        raw, nh_streaming_diarizer_destroy);
    const double load_seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    // Exclusive creation protects input/model files, hard links and existing results.
    descriptor = open(argv[3], O_CREAT | O_EXCL | O_WRONLY, 0600);
    if (descriptor < 0) {
      std::cerr << "Cannot create new posterior output: " << std::strerror(errno) << '\n';
      return NH_IO_ERROR;
    }
    Context context;
    context.handle = handle.get();
    context.descriptor = descriptor;
    const auto processing_started = std::chrono::steady_clock::now();
    context.previous_posterior = processing_started;
    context.callback_intervals.reserve(
        (config.max_audio_seconds ? config.max_audio_seconds : 600) * 100 / 72 + 1);
    std::cerr << "{\"stage\":\"speaker_stream\"}\n";
    status = nh_decode_file(argv[1], 16000, 16000, decoded, &context);
    if (context.status != NH_OK) {
      status = context.status;
    } else if (status != NH_OK) {
      context.error = nh_last_error();
    }
    if (status == NH_OK) {
      status = nh_streaming_diarizer_flush(handle.get(), posterior, &context);
      if (context.status != NH_OK)
        status = context.status;
      else if (status != NH_OK)
        context.error = nh_last_error();
    }
    if (status == NH_OK && fsync(descriptor) != 0) {
      status = NH_IO_ERROR;
      context.error = "Posterior fsync failed";
    }
    close(descriptor);
    descriptor = -1;
    if (status != NH_OK) {
      std::cerr << context.error << '\n';
      return status;
    }
    nh_streaming_diarizer_stats stats{};
    stats.struct_size = sizeof(stats);
    status = nh_streaming_diarizer_get_stats(handle.get(), &stats);
    if (status != NH_OK) {
      std::cerr << nh_last_error() << '\n';
      return status;
    }
    if (stats.received_samples != context.source_samples ||
        stats.emitted_frames != context.emitted_frames ||
        stats.emitted_frames != context.source_samples / 160)
      throw std::runtime_error("Posterior/source size mismatch");
    const auto completed = std::chrono::steady_clock::now();
    const double processing_seconds =
        std::chrono::duration<double>(completed - processing_started).count();
    const double total_seconds = std::chrono::duration<double>(completed - started).count();
    const double audio_seconds = context.source_samples / 16000.0;
    context.pcm_hash.finish();
    const auto pcm_sha = picosha2::get_hash_hex_string(context.pcm_hash);
    const double first_posterior =
        context.callback_intervals.empty() ? 0 : context.callback_intervals.front();
    std::sort(context.callback_intervals.begin(), context.callback_intervals.end());
    const size_t intervals = context.callback_intervals.size();
    const double max_interval = intervals ? context.callback_intervals.back() : 0;
    const double p95_interval =
        intervals ? context.callback_intervals[(intervals - 1) * 95 / 100] : 0;
    struct rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) != 0)
      throw std::runtime_error("Cannot query peak process RSS");
    std::cout << std::setprecision(12)
              << "{\"scope\":\"standalone native speaker stream; no "
                 "ASR\",\"format\":\"float32le\",\"ort_version\":\""
              << nh_onnxruntime_version() << "\",\"profile\":" << config.profile
              << ",\"threads\":" << config.threads
              << ",\"source_samples\":" << context.source_samples
              << ",\"posterior_frames\":" << context.emitted_frames
              << ",\"speaker_slots\":8,\"frame_step_samples\":160,\"audio_seconds\":"
              << audio_seconds << ",\"decoded_pcm_sha256\":\"" << pcm_sha << "\""
              << ",\"posterior_callbacks\":" << intervals
              << ",\"unpaced_first_posterior_seconds\":" << first_posterior
              << ",\"unpaced_max_callback_interval_seconds\":" << max_interval
              << ",\"unpaced_p95_callback_interval_seconds\":" << p95_interval
              << ",\"load_seconds\":" << load_seconds
              << ",\"processing_seconds\":" << processing_seconds
              << ",\"total_seconds\":" << total_seconds
              << ",\"inference_seconds\":" << stats.inference_seconds
              << ",\"inference_rtf\":" << (audio_seconds ? processing_seconds / audio_seconds : 0)
              << ",\"full_rtf\":" << (audio_seconds ? total_seconds / audio_seconds : 0)
              << ",\"process_peak_rss_kib\":" << usage.ru_maxrss
              << ",\"model_calls\":" << stats.model_calls
              << ",\"peak_buffered_samples\":" << stats.peak_buffered_samples
              << ",\"cache_frames\":" << stats.cache_frames
              << ",\"fifo_frames\":" << stats.fifo_frames
              << ",\"max_feature_frames\":" << stats.max_feature_frames << "}\n";
    return NH_OK;
  } catch (const std::exception &error) {
    if (descriptor >= 0)
      close(descriptor);
    std::cerr << error.what() << '\n';
    return NH_RUNTIME_ERROR;
  }
}
