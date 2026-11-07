#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace nh {
struct Word { int64_t start_ms, end_ms; std::string text; };
struct Turn { int32_t speaker; int64_t start_ms, end_ms; };
struct Utterance { std::string speaker_id; int64_t start_ms, end_ms; std::string text; };
bool append_ctc_words(const std::string &text,const std::vector<std::string> &tokens,
    const std::vector<double> &times,int64_t offset_ms,int64_t chunk_end_ms,std::vector<Word> &words);
std::vector<Utterance> attribute_words(const std::vector<Word> &words,
                                     const std::vector<Turn> &turns, bool midpoint = false);
}
