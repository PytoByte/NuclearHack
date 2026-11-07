#include "speaker_cache.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>

namespace nh {
std::vector<float> SpeakerCache::input() const {
  std::vector<float> result;
  result.reserve(cache_.size()+fifo_.size());
  result.insert(result.end(), cache_.begin(), cache_.end());
  result.insert(result.end(), fifo_.begin(), fifo_.end());
  return result;
}
void SpeakerCache::reset() { cache_.clear(); fifo_.clear(); cache_probs_.clear(); compressed_ = false; }

void SpeakerCache::update(const float* embeddings, size_t embedding_frames,
                          const std::vector<float>& pooled, size_t keep, const float* silence) {
  const size_t c = cache_frames(), f = fifo_frames();
  if (!embeddings || !silence || !keep || keep > 340 || keep > embedding_frames || embedding_frames > 380 ||
      pooled.size() != (c+f+embedding_frames)*8 || c > 264 || f > fifo_cap_)
    throw std::logic_error("Invalid speaker cache update");
  fifo_.insert(fifo_.end(), embeddings, embeddings+keep*512);
  if (f+keep <= fifo_cap_) return;
  const size_t pop = std::min(std::max(update_period_, f+keep-fifo_cap_), f+keep);
  std::vector<float> fifo_probs;
  fifo_probs.reserve((f+keep)*8);
  fifo_probs.insert(fifo_probs.end(), pooled.begin()+c*8, pooled.begin()+(c+f+keep)*8);
  if (!compressed_) cache_probs_.assign(pooled.begin(), pooled.begin()+c*8);
  cache_.insert(cache_.end(), fifo_.begin(), fifo_.begin()+pop*512);
  cache_probs_.insert(cache_probs_.end(), fifo_probs.begin(), fifo_probs.begin()+pop*8);
  fifo_.erase(fifo_.begin(), fifo_.begin()+pop*512);
  if (cache_frames() > 264) { compress(silence); compressed_ = true; }
  if (cache_frames() > 264 || fifo_frames() > fifo_cap_ || cache_probs_.size() != cache_frames()*8)
    throw std::logic_error("Speaker cache budget exceeded");
}

void SpeakerCache::compress(const float* silence) {
  const size_t n = cache_frames(), padded = n+1;
  constexpr size_t capacity = 264, per_speaker = capacity/8-1;
  const double log_half = std::log(.5), negative_inf = -std::numeric_limits<double>::infinity();
  std::vector<double> scores(padded*8, negative_inf);
  for (size_t t = 0; t < n; ++t) {
    float sum = 0;
    for (size_t s = 0; s < 8; ++s) sum += std::log(std::max(1.f-cache_probs_[t*8+s], .25f));
    for (size_t s = 0; s < 8; ++s) {
      const float p = cache_probs_[t*8+s];
      const float base = std::log(std::max(p, .25f))-std::log(std::max(1.f-p, .25f))+sum;
      scores[s*padded+t] = static_cast<double>(base)-log_half;
    }
  }
  for (size_t s = 0; s < 8; ++s) {
    size_t positive = 0;
    for (size_t t = 0; t < n; ++t)
      if (cache_probs_[t*8+s] > .5f && scores[s*padded+t] > 0) ++positive;
    for (size_t t = 0; t < n; ++t) {
      auto& score = scores[s*padded+t];
      if (cache_probs_[t*8+s] <= .5f || (score <= 0 && positive >= per_speaker/2)) score = negative_inf;
      if (t >= capacity) score += .05;
    }
    for (const auto& boost : {std::pair<size_t, double>{per_speaker*3/4, -2*log_half},
                               std::pair<size_t, double>{per_speaker*3/2, -log_half}}) {
      std::vector<size_t> order(n);
      std::iota(order.begin(), order.end(), 0);
      std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) { return scores[s*padded+a] > scores[s*padded+b]; });
      for (size_t i = 0; i < std::min(boost.first, n); ++i) scores[s*padded+order[i]] += boost.second;
    }
    scores[s*padded+n] = std::numeric_limits<double>::infinity();
  }
  std::vector<size_t> order(scores.size());
  std::iota(order.begin(), order.end(), 0);
  std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) { return scores[a] > scores[b]; });
  order.resize(capacity);
  const size_t sentinel = scores.size();
  for (auto& i : order) if (scores[i] == negative_inf) i = sentinel;
  std::sort(order.begin(), order.end());
  std::vector<float> embeddings(capacity*512), probabilities(capacity*8, 0.f);
  for (size_t target = 0; target < capacity; ++target) {
    const size_t frame = order[target] == sentinel ? n : order[target]%padded;
    const float* row = frame == n ? silence : cache_.data()+frame*512;
    std::copy_n(row, 512, embeddings.begin()+target*512);
    if (frame != n) std::copy_n(cache_probs_.begin()+frame*8, 8, probabilities.begin()+target*8);
  }
  cache_.swap(embeddings); cache_probs_.swap(probabilities);
}
}
