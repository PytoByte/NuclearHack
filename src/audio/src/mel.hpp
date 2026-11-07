#pragma once
#include <array>
#include <complex>
#include <cstdint>
#include <vector>

namespace nh {
// Stateless frames on the original 16-kHz timeline. Caller retains at least
// 201 preceding samples and 200 samples of lookahead around each frame center.
class MelFrontend {
  struct Weight { uint16_t bin; float value; };
  std::array<float, 512> window_{};
  std::array<std::complex<float>, 256> twiddles_{};
  std::array<uint16_t, 512> reversed_{};
  std::array<std::vector<Weight>, 128> filters_;
 public:
  MelFrontend();
  void extract(const std::vector<float>& pcm, uint64_t base_sample,
               uint64_t total_samples, uint64_t first_mel_frame,
               uint32_t frames, std::vector<float>& output) const;
};
}
