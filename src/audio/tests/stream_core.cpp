#include "mel.hpp"
#include "speaker_cache.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <cmath>
#include <stdexcept>
#include <vector>
#define CHECK(x) do { if (!(x)) { std::cerr << #x << '\n'; return 1; } } while (0)

int main() {
  nh::MelFrontend frontend;
  std::vector<float> silence(16000, 0.f), result;
  frontend.extract(silence, 0, silence.size(), 0, 100, result);
  CHECK(result.size() == 12800);
  for (float value : result) CHECK(value == std::log(0x1p-24f));

  std::vector<float> signal(64000);
  for (size_t i = 0; i < signal.size(); ++i) signal[i] = .2f*std::sin(static_cast<float>(i)*.3926990817f);
  std::vector<float> whole, retained;
  frontend.extract(signal, 0, signal.size(), 120, 10, whole);
  const uint64_t base = 120*160-201;
  std::vector<float> cropped(signal.begin()+base, signal.end());
  frontend.extract(cropped, base, signal.size(), 120, 10, retained);
  CHECK(whole == retained); // transport/ring history must not change any coefficient
  const auto peak = std::distance(whole.begin(), std::max_element(whole.begin(), whole.begin()+128));
  CHECK(peak >= 35 && peak <= 50); // 1-kHz tone, not a mirrored FFT implementation
  bool missing_history = false;
  try {
    std::vector<float> too_short(signal.begin()+120*160, signal.end());
    frontend.extract(too_short, 120*160, signal.size(), 120, 1, retained);
  } catch (const std::logic_error&) { missing_history = true; }
  CHECK(missing_history);

  nh::SpeakerCache cache(264, 222);
  std::vector<float> embeddings(13*512);
  for (size_t row = 0; row < 13; ++row)
    std::fill_n(embeddings.begin()+row*512, 512, static_cast<float>(row));
  std::array<float, 512> learned{};
  learned.fill(.123f);
  for (unsigned call = 0; call < 100; ++call) {
    const size_t frames = cache.cache_frames()+cache.fifo_frames()+13;
    std::vector<float> pooled(frames*8, .01f);
    for (size_t row = 0; row < frames; ++row) pooled[row*8] = .9f;
    cache.update(embeddings.data(), 13, pooled, 9, learned.data());
    CHECK(cache.cache_frames() <= 264 && cache.fifo_frames() <= 264);
    const auto input = cache.input();
    CHECK(input.size() == (cache.cache_frames()+cache.fifo_frames())*512);
    for (float value : input) CHECK(std::isfinite(value));
    if (!call) {
      CHECK(cache.cache_frames() == 0 && cache.fifo_frames() == 9);
      for (size_t row = 0; row < 9; ++row) CHECK(input[row*512] == row);
    }
  }
  CHECK(cache.cache_frames() == 264);
  cache.reset();
  CHECK(cache.input().empty() && !cache.cache_frames() && !cache.fifo_frames());
  bool rejected = false;
  try { cache.update(embeddings.data(), 13, std::vector<float>(1), 9, learned.data()); }
  catch (const std::logic_error&) { rejected = true; }
  CHECK(rejected);
}
