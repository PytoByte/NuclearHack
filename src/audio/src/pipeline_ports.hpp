#pragma once

#include "json.hpp"
#include "pipeline.hpp"

#include <cstdio>
#include <memory>

namespace nh {
using Json = nlohmann::json;

// Borrowed configuration is valid for the duration of the synchronous operation.
struct PipelineRequest {
    const char* input;
    const nh_pipeline_config* config;
    const nh_pipeline_options* options;
    const nh_speaker_refinement_config* refinement;
    const nh_streaming_diarizer_config* speaker;
    nh_progress_callback progress;
    void* user;
};

class Progress final {
  public:
    Progress(nh_progress_callback callback, void* user) noexcept : callback_(callback), user_(user) {}
    bool emit(const char* stage, uint64_t completed, uint64_t total) const {
        return callback_ && callback_(stage, completed, total, user_);
    }

  private:
    nh_progress_callback callback_;
    void* user_;
};

struct SpeakerResult {
    std::vector<Turn> turns;
    std::vector<int32_t> word_slots;
    nh_streaming_diarizer_stats stats{};
    SpeakerResult() { stats.struct_size = sizeof(stats); }
};

class AudioDecoderPort {
  public:
    virtual ~AudioDecoderPort() = default;
    virtual nh_status decode(const char* input, nh_pcm_callback callback, void* user) = 0;
};

class AsrPort {
  public:
    virtual ~AsrPort() = default;
    virtual nh_status load(const nh_pipeline_config& config) = 0;
    virtual nh_status decode(const float* samples, uint32_t frames, nh_asr_callback callback, void* user) = 0;
};

class SpeakerPort {
  public:
    virtual ~SpeakerPort() = default;
    virtual nh_status process(const PipelineRequest& request, FILE* pcm, uint64_t frames, uint32_t budget,
                              const std::vector<Word>& words, SpeakerResult& result) = 0;
};

class TranscriptSinkPort {
  public:
    virtual ~TranscriptSinkPort() = default;
    virtual void write(const char* path, const Json& value) = 0;
};

// Adapters are constructed per stage. In particular, the ASR adapter is destroyed
// before a speaker adapter is created, preserving the sequential model budget.
class PipelineFactory {
  public:
    virtual ~PipelineFactory() = default;
    virtual std::unique_ptr<AudioDecoderPort> create_decoder() const = 0;
    virtual std::unique_ptr<AsrPort> create_asr() const = 0;
    virtual std::unique_ptr<SpeakerPort> create_speaker(bool posterior_mode) const = 0;
    virtual std::unique_ptr<TranscriptSinkPort> create_sink() const = 0;
};

std::unique_ptr<PipelineFactory> make_native_pipeline_factory();
} // namespace nh
