#include "mel.hpp"
#include "posterior_merge.hpp"
#include "speaker_cache.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <cmath>
#include <stdexcept>
#include <vector>
#define CHECK(x) do { if (!(x)) { std::cerr << #x << '\n'; return 1; } } while (0)

int main() {
  std::vector<nh::Word> words{{0,400,"длинное"},{10,20,"да"},{400,410,"ещё"}};
  std::vector<float> probabilities(40*8,0);
  for(size_t r=0;r<40;++r)probabilities[r*8+(r<16?1:2)]=.9f;
  nh::PosteriorMerge posterior_whole(words,40,true), posterior_split(words,40,true);
  posterior_whole.accept(probabilities.data(),40,8,0);posterior_whole.finish();
  posterior_split.accept(probabilities.data(),7,8,0);
  CHECK(posterior_split.completed_samples()==7*160);
  posterior_split.accept(probabilities.data()+7*8,33,8,7*160);posterior_split.finish();
  CHECK(posterior_whole.slots==posterior_split.slots);
  CHECK((posterior_whole.slots==std::vector<int32_t>{1,1,2})); // 160ms anchor, source-tail clamp
  auto attributed=nh::attribute_word_slots(words,posterior_whole.slots);
  CHECK(attributed.size()==2 && attributed[0].text=="длинное да" && attributed[1].text=="ещё");
  CHECK(attributed[0].start_ms==0 && attributed[0].end_ms==400);
  bool incomplete=false;
  try {nh::PosteriorMerge missing(words,40,false);missing.finish();}catch(const std::runtime_error&){incomplete=true;}
  CHECK(incomplete);
  std::vector<float> bridge(80*8,0);
  for(size_t r=0;r<20;++r)bridge[r*8]=.9f;
  for(size_t r=60;r<80;++r)bridge[r*8]=.9f;
  nh::PosteriorMerge short_spans({},80,true);short_spans.accept(bridge.data(),80,8,0);short_spans.finish();
  CHECK(short_spans.turns.size()==1 && short_spans.turns[0].start_ms==0 && short_spans.turns[0].end_ms==800);
  // A gap of exactly500ms must not bridge two individually too-short spans.
  std::fill(bridge.begin(),bridge.end(),0);
  for(size_t r=0;r<20;++r)bridge[r*8]=.9f;
  for(size_t r=70;r<80;++r)bridge[r*8]=.9f;
  nh::PosteriorMerge gap({},80,true);gap.accept(bridge.data(),80,8,0);gap.finish();CHECK(gap.turns.empty());
  nh::PosteriorMerge empty({{0,1,"угу"}},0,false);empty.finish();CHECK(empty.slots[0]==-1);
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
