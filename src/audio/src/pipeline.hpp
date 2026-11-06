#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace nh {
struct Word { int64_t start_ms, end_ms; std::string text; };
struct Turn { int32_t speaker; int64_t start_ms, end_ms; };
struct Utterance { std::string speaker_id; int64_t start_ms, end_ms; std::string text; };
std::vector<Utterance> attribute_words(const std::vector<Word> &words,
                                     const std::vector<Turn> &turns, bool midpoint = false);
}
