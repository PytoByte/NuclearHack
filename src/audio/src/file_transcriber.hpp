#pragma once

#include "pipeline_ports.hpp"

#include <memory>
#include <string>

namespace nh {
class FileTranscriber final {
  public:
    FileTranscriber(PipelineRequest request, std::unique_ptr<PipelineFactory> factory);
    nh_status run();

  private:
    nh_status validate() const;
    nh_status validate_paths() const;
    nh_status recognize(FILE* pcm, uint64_t frames, const std::string& pcm_hash, std::vector<Word>& words,
                        Json& raw_asr);
    void publish(const std::string& source_pcm_sha, const std::vector<Word>& words, Json raw_asr,
                 const SpeakerResult& speakers, const std::vector<Turn>& initial_turns,
                 const RefinementStats& refinement_stats);
    bool emit(const char* stage, uint64_t done, uint64_t total) const;

    const char* input;
    const nh_pipeline_config* config;
    const nh_pipeline_options* options;
    const nh_speaker_refinement_config* refinement;
    const nh_streaming_diarizer_config* speaker;
    nh_progress_callback progress;
    void* user;
    std::unique_ptr<PipelineFactory> factory_;
};
} // namespace nh
