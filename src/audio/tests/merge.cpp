#include "pipeline.hpp"
#include <iostream>
using namespace nh;
#define CHECK(x) do { if (!(x)) { std::cerr << #x << '\n'; return 1; } } while (0)
int main() {
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
  return 0;
}
