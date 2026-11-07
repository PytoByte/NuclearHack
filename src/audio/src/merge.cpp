#include "pipeline.hpp"

#include <algorithm>
#include <cmath>
#include <map>

namespace nh {
bool append_ctc_words(const std::string& text, const std::vector<std::string>& tokens, const std::vector<double>& times,
                      int64_t offset, int64_t chunk_end, std::vector<Word>& words) {
    if (text.empty())
        return true;
    const auto original = words.size();
    auto fallback = [&]() {
        words.resize(original);
        words.push_back({offset, chunk_end, text});
        return false;
    };
    if (tokens.empty() || tokens.size() != times.size() || chunk_end <= offset)
        return fallback();
    std::string word;
    int64_t start = offset, end = offset;
    auto flush = [&]() {
        if (!word.empty()) {
            words.push_back({start, std::min(chunk_end, std::max(start + 1, end)), word});
            word.clear();
        }
    };
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (!std::isfinite(times[i]) || (i && times[i] < times[i - 1]))
            return fallback();
        const auto stamp = std::min<int64_t>(
            chunk_end - 1, offset + std::llround(std::clamp(times[i], 0.0, (chunk_end - offset) / 1000.0) * 1000));
        // sherpa converts SentencePiece boundary markers to spaces. A BPE token can
        // contain both a leading space and letters, so split inside each token.
        for (char c : tokens[i]) {
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
                flush();
                continue;
            }
            if (word.empty())
                start = stamp;
            word += c;
            end = stamp + 40;
        }
    }
    flush();
    auto normalize = [](const std::string& value) {
        std::string out;
        bool space = false;
        for (char c : value) {
            if (c == ' ' || c == '\n' || c == '\t' || c == '\r') {
                space = !out.empty();
                continue;
            }
            if (space)
                out += ' ';
            out += c;
            space = false;
        }
        return out;
    };
    std::string reconstructed;
    for (size_t i = original; i < words.size(); ++i) {
        if (!reconstructed.empty())
            reconstructed += ' ';
        reconstructed += words[i].text;
    }
    return normalize(reconstructed) == normalize(text) ? true : fallback();
}
std::vector<Utterance> attribute_words(const std::vector<Word>& words, const std::vector<Turn>& turns, bool midpoint) {
    std::map<int32_t, std::string> ids;
    for (const auto& turn : turns)
        if (!ids.count(turn.speaker))
            ids[turn.speaker] = "speaker_" + std::to_string(ids.size() + 1);
    std::vector<Utterance> result;
    for (const auto& word : words) {
        int64_t best = 0;
        std::string speaker = "speaker_unknown";
        for (const auto& turn : turns) {
            int64_t overlap =
                std::max<int64_t>(0, std::min(word.end_ms, turn.end_ms) - std::max(word.start_ms, turn.start_ms));
            if (midpoint) {
                const int64_t middle = (word.start_ms + word.end_ms) / 2;
                overlap = turn.start_ms <= middle && middle < turn.end_ms ? 1 : 0;
            }
            if (overlap > best) {
                best = overlap;
                speaker = ids.at(turn.speaker);
            }
        }
        if (!result.empty() && result.back().speaker_id == speaker && word.start_ms - result.back().end_ms <= 1200) {
            result.back().end_ms = std::max(result.back().end_ms, word.end_ms);
            result.back().text += " " + word.text;
        } else {
            result.push_back({speaker, word.start_ms, word.end_ms, word.text});
        }
    }
    return result;
}
} // namespace nh
