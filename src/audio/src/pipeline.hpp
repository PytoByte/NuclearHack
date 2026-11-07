#pragma once
#include "nuclear_audio.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace nh {
struct Word {
    int64_t start_ms = 0, end_ms = 0;
    std::string text;
};
struct Turn {
    int32_t speaker;
    int64_t start_ms, end_ms;
};
struct Utterance {
    std::string speaker_id;
    int64_t start_ms = 0, end_ms = 0;
    std::string text;
};
struct RefinementStats {
    size_t initial_clusters = 0, final_clusters = 0, embedding_clusters = 0;
};
nh_status refine_speakers(const float* pcm, uint32_t frames, std::vector<Turn>& turns, const char* model,
                          uint32_t threads, const nh_speaker_refinement_config& config, nh_progress_callback progress,
                          void* user, RefinementStats& stats);
bool append_ctc_words(const std::string& text, const std::vector<std::string>& tokens, const std::vector<double>& times,
                      int64_t offset_ms, int64_t chunk_end_ms, std::vector<Word>& words);
std::vector<Utterance> attribute_words(const std::vector<Word>& words, const std::vector<Turn>& turns,
                                       bool midpoint = false);
} // namespace nh
