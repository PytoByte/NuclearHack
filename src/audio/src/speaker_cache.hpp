#pragma once
#include <cstddef>
#include <vector>

namespace nh {
// Eight-slot arrival-order cache. Encoder frames are 80 ms; the model produces
// eight posterior rows per encoder frame. No reference speaker count is used.
class SpeakerCache {
  size_t fifo_cap_, update_period_;
  bool compressed_ = false;
  std::vector<float> cache_, fifo_, cache_probs_;
  void compress(const float* silence);
 public:
  SpeakerCache(size_t fifo_cap, size_t update_period) : fifo_cap_(fifo_cap), update_period_(update_period) {}
  size_t cache_frames() const { return cache_.size()/512; }
  size_t fifo_frames() const { return fifo_.size()/512; }
  std::vector<float> input() const;
  void update(const float* embeddings, size_t embedding_frames,
              const std::vector<float>& pooled_probs, size_t keep,
              const float* silence);
  void reset();
};
}
