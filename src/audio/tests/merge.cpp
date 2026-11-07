#include "clustering.hpp"
#include "pipeline.hpp"

#include <iostream>
#include <limits>
using namespace nh;
#define CHECK(x)                                                                                                       \
    do {                                                                                                               \
        if (!(x)) {                                                                                                    \
            std::cerr << #x << '\n';                                                                                   \
            return 1;                                                                                                  \
        }                                                                                                              \
    } while (0)
int main() {
    std::vector<Word> bpe;
    CHECK(append_ctc_words("Ну ээ да да", {" Ну", " ээ", " да", " да"}, {0.1, 0.4, 0.6, 0.9}, 1000, 2500, bpe));
    CHECK(bpe.size() == 4 && bpe[0].text == "Ну" && bpe[0].start_ms == 1100);
    CHECK(bpe[2].text == "да" && bpe[3].text == "да" && bpe[3].start_ms == 1900);
    CHECK(!append_ctc_words("Не менять текст", {"другой"}, {0.0}, 0, 1000, bpe));
    CHECK(bpe.back().text == "Не менять текст");
    CHECK(!append_ctc_words("угу", {"угу"}, {std::numeric_limits<double>::quiet_NaN()}, 0, 1000, bpe));
    CHECK(!append_ctc_words("да да", {" да", " да"}, {0.8, 0.2}, 0, 1000, bpe));
    std::vector<Word> words{{100, 200, "ээ"}, {210, 300, "да"}, {310, 400, "да"}, {500, 600, "ещё"}};
    std::vector<Turn> turns{{9, 90, 320}, {4, 300, 650}};
    auto result = attribute_words(words, turns);
    CHECK(result.size() == 2);
    CHECK(result[0].speaker_id == "speaker_1");
    CHECK(result[0].text == "ээ да");
    CHECK(result[1].speaker_id == "speaker_2");
    CHECK(result[1].text == "да ещё");
    CHECK(result[0].start_ms == 100 && result[1].end_ms == 600);
    CHECK(attribute_words({Word{900, 1000, "угу"}}, turns)[0].speaker_id == "speaker_unknown");
    CHECK(attribute_words({}, turns).empty());
    CHECK(attribute_words(words, turns, true).size() == 2);
    const auto labels = complete_link({0, .1f, 2, .1f, 0, .1f, 2, .1f, 0}, 3, .4f);
    CHECK(labels[0] == labels[1] && labels[0] != labels[2]); // cannot-link survives a tempting transitive bridge
    CHECK(complete_link({}, 0, .4f).empty());
    CHECK(complete_link({0, 2, 2, 0}, 2, .4f)[0] != complete_link({0, 2, 2, 0}, 2, .4f)[1]);
    return 0;
}
