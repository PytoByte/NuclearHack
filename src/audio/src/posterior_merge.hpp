#pragma once
#include "pipeline.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <numeric>
#include <stdexcept>

namespace nh {
// Fixed policy from the validated prototype: mean probabilities over the first
// min(word duration,160ms), argmax, stable low-slot tie. No oracle/word edits.
class PosteriorMerge {
    struct Window {
        uint64_t begin = 0, end = 0;
        size_t word = 0;
        std::array<double, 8> sums{};
    };
    std::vector<Window> windows_;
    std::vector<size_t> active_;
    size_t next_ = 0;
    uint64_t emitted_ = 0, total_;
    bool trace_;
    struct Span {
        int64_t begin = -1, end = 0;
    };
    std::array<Span, 8> spans_{};
    void close(size_t slot) {
        auto& s = spans_[slot];
        if (s.begin >= 0 && s.end - s.begin >= 30) {
            if (turns.size() >= 65536)
                throw std::runtime_error("Speaker turn trace exceeds budget");
            turns.push_back({static_cast<int32_t>(slot), s.begin * 10, s.end * 10});
        }
        s.begin = -1;
    }

  public:
    std::vector<int32_t> slots;
    std::vector<Turn> turns;
    PosteriorMerge(const std::vector<Word>& words, uint64_t total_frames, bool trace)
        : total_(total_frames), trace_(trace), slots(words.size(), -1) {
        if (!total_)
            return;
        windows_.reserve(words.size());
        for (size_t i = 0; i < words.size(); ++i) {
            const auto start = static_cast<uint64_t>(std::max<int64_t>(0, words[i].start_ms) / 10);
            const auto end = static_cast<uint64_t>((std::max<int64_t>(0, words[i].end_ms) + 9) / 10);
            Window w;
            w.begin = std::min(start, total_ - 1);
            w.end = std::min(std::max(w.begin + 1, std::min(end, total_)), w.begin + 16);
            w.word = i;
            windows_.push_back(w);
        }
        std::stable_sort(windows_.begin(), windows_.end(),
                         [](const Window& a, const Window& b) { return a.begin < b.begin; });
    }
    void accept(const float* p, uint32_t frames, uint32_t speakers, uint64_t start_sample) {
        if (!p || speakers != 8 || start_sample != emitted_ * 160 || emitted_ + frames > total_)
            throw std::runtime_error("Invalid posterior merge timeline");
        for (uint32_t r = 0; r < frames; ++r) {
            const float* row = p + static_cast<size_t>(r) * 8;
            for (size_t s = 0; s < 8; ++s)
                if (!std::isfinite(row[s]) || row[s] < 0 || row[s] > 1)
                    throw std::runtime_error("Invalid speaker probabilities");
            while (next_ < windows_.size() && windows_[next_].begin <= emitted_)
                active_.push_back(next_++);
            for (const size_t i : active_) {
                auto& w = windows_[i];
                for (size_t s = 0; s < 8; ++s)
                    w.sums[s] += row[s];
                if (emitted_ + 1 == w.end) {
                    slots[w.word] =
                        static_cast<int32_t>(std::max_element(w.sums.begin(), w.sums.end()) - w.sums.begin());
                }
            }
            active_.erase(std::remove_if(active_.begin(), active_.end(),
                                         [&](size_t i) { return windows_[i].end == emitted_ + 1; }),
                          active_.end());
            if (trace_)
                for (size_t s = 0; s < 8; ++s) {
                    auto& span = spans_[s];
                    if (row[s] > .5f) {
                        if (span.begin < 0)
                            span.begin = static_cast<int64_t>(emitted_);
                        span.end = static_cast<int64_t>(emitted_ + 1);
                    } else if (span.begin >= 0 && static_cast<int64_t>(emitted_ + 1) - span.end >= 50)
                        close(s);
                }
            ++emitted_;
        }
    }
    uint64_t completed_samples() const { return emitted_ * 160; }
    void finish() {
        if (emitted_ != total_ || next_ != windows_.size() || !active_.empty())
            throw std::runtime_error("Incomplete speaker posterior coverage");
        if (trace_) {
            for (size_t s = 0; s < 8; ++s)
                close(s);
            std::sort(turns.begin(), turns.end(), [](const Turn& a, const Turn& b) {
                if (a.start_ms != b.start_ms)
                    return a.start_ms < b.start_ms;
                if (a.end_ms != b.end_ms)
                    return a.end_ms < b.end_ms;
                return a.speaker < b.speaker;
            });
        }
    }
};

inline std::vector<Utterance> attribute_word_slots(const std::vector<Word>& words, const std::vector<int32_t>& slots) {
    if (words.size() != slots.size())
        throw std::invalid_argument("Word/slot counts differ");
    std::vector<Utterance> result;
    std::array<std::string, 8> ids{};
    size_t speakers = 0;
    for (size_t i = 0; i < words.size(); ++i) {
        const auto& w = words[i];
        const auto slot = slots[i];
        std::string speaker = "speaker_unknown";
        if (slot >= 0) {
            if (slot >= 8)
                throw std::invalid_argument("Invalid speaker slot");
            if (ids[slot].empty())
                ids[slot] = "speaker_" + std::to_string(++speakers);
            speaker = ids[slot];
        }
        if (!result.empty() && result.back().speaker_id == speaker && w.start_ms - result.back().end_ms <= 1200) {
            result.back().text += " " + w.text;
            result.back().end_ms = std::max(result.back().end_ms, w.end_ms);
        } else
            result.push_back({speaker, w.start_ms, w.end_ms, w.text});
    }
    return result;
}
} // namespace nh
