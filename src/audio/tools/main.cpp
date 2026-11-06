#include "nuclear_audio.h"
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
struct Stats { uint64_t frames = 0; uint32_t max_block = 0; };
static int32_t consume(const float *, uint32_t frames, uint64_t, void *user) {
  auto &stats = *static_cast<Stats *>(user);
  stats.frames += frames;
  if (frames > stats.max_block) stats.max_block = frames;
  return 0;
}
int main(int argc, char **argv) {
  if (argc == 1 || (argc == 2 && std::string(argv[1]) == "native-info")) {
    std::cout << "{\"abi\":" << nh_abi_version() << ",\"sherpa\":\"" << nh_sherpa_version() << "\"}\n";
    return 0;
  }
  if (argc != 3 || std::string(argv[1]) != "probe") {
    std::cerr << "Usage: nh-audio [native-info | probe LOCAL_AUDIO]\n";
    return 2;
  }
  Stats stats;
  const auto begin = std::chrono::steady_clock::now();
  const auto status = nh_decode_file(argv[2], 16000, 16000, consume, &stats);
  const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
  if (status != NH_OK) {
    std::cerr << nh_last_error() << '\n';
    return static_cast<int>(status);
  }
  const double duration = stats.frames / 16000.0;
  std::cout << "{\"scope\":\"host_decode_only\",\"audio_seconds\":" << duration
            << ",\"wall_seconds\":" << seconds << ",\"max_pcm_block_bytes\":" << stats.max_block * sizeof(float)
            << ",\"decode_rtf\":" << (duration > 0 ? seconds / duration : 0) << "}\n";
}
