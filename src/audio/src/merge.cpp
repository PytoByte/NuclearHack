#include "pipeline.hpp"
#include <algorithm>
#include <map>

namespace nh {
std::vector<Utterance> attribute_words(const std::vector<Word> &words,
                                     const std::vector<Turn> &turns, bool midpoint) {
  std::map<int32_t, std::string> ids;
  for (const auto &turn : turns)
    if (!ids.count(turn.speaker)) ids[turn.speaker] = "speaker_" + std::to_string(ids.size() + 1);
  std::vector<Utterance> result;
  for (const auto &word : words) {
    int64_t best = 0;
    std::string speaker = "speaker_unknown";
    for (const auto &turn : turns) {
      int64_t overlap = std::max<int64_t>(0, std::min(word.end_ms, turn.end_ms) - std::max(word.start_ms, turn.start_ms));
      if (midpoint) {
        const int64_t middle = (word.start_ms + word.end_ms) / 2;
        overlap = turn.start_ms <= middle && middle < turn.end_ms ? 1 : 0;
      }
      if (overlap > best) { best = overlap; speaker = ids.at(turn.speaker); }
    }
    if (!result.empty() && result.back().speaker_id == speaker &&
        word.start_ms - result.back().end_ms <= 1200) {
      result.back().end_ms = std::max(result.back().end_ms, word.end_ms);
      result.back().text += " " + word.text;
    } else {
      result.push_back({speaker, word.start_ms, word.end_ms, word.text});
    }
  }
  return result;
}
}
