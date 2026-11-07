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
static int32_t progress(const char *stage, uint64_t done, uint64_t total, void *) {
  std::cerr << "{\"stage\":\"" << stage << "\",\"completed_frames\":" << done << ",\"total_frames\":" << total << "}\n";
  return 0;
}
int main(int argc, char **argv) {
  if (argc == 1 || (argc == 2 && std::string(argv[1]) == "native-info")) {
    std::cout << "{\"abi\":" << nh_abi_version() << ",\"sherpa\":\"" << nh_sherpa_version() << "\",\"llm\":" << nh_llm_available() << "}\n";
    return 0;
  }
  if (argc >= 5 && std::string(argv[1]) == "summarize") {
    try {
      nh_llm_config config{};
      config.struct_size = sizeof(config); config.model = argv[3]; config.output_text = argv[4];
      config.threads = argc > 5 ? std::stoul(argv[5]) : 4;
      config.context_tokens = 4096; config.max_output_tokens = 256;
      const auto code = nh_summarize_file(argv[2], &config, progress, nullptr);
      if (code != NH_OK) std::cerr << nh_last_error() << '\n';
      return code;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 2; }
  }
  if (argc >= 9 && std::string(argv[1]) == "transcribe") {
    try {
      const std::string trace = std::string(argv[3]) + ".trace.json";
      nh_pipeline_config config{};
      config.struct_size = sizeof(config);
      config.asr_model = argv[4]; config.tokens = argv[5]; config.segmentation = argv[6];
      config.embedding = argv[7]; config.scratch_directory = argv[8];
      config.output_json = argv[3]; config.trace_json = trace.c_str();
      config.threads = argc > 9 ? std::stoul(argv[9]) : 2;
      config.cluster_threshold = argc > 10 ? std::stof(argv[10]) : 0.8f;
      config.chunk_seconds = argc > 11 ? std::stoul(argv[11]) : 20;
      config.max_audio_seconds = argc > 15 ? std::stoul(argv[15]) : 600;
      nh_pipeline_options options{sizeof(nh_pipeline_options), argc > 12 ? std::stof(argv[12]) : 0.3f,
          argc > 13 ? std::stof(argv[13]) : 0.5f, argc > 14 ? static_cast<uint32_t>(std::stoul(argv[14])) : 0,
          argc > 16 && std::string(argv[16]) != "-" ? argv[16] : nullptr,
          argc > 17 ? std::stof(argv[17]) : 0.1f};
      nh_speaker_refinement_config refinement{sizeof(nh_speaker_refinement_config),argc>18?std::stof(argv[18]):0.0f,argc>19?static_cast<uint32_t>(std::stoul(argv[19])):128};
      const auto code = refinement.cluster_threshold!=0 ? nh_transcribe_file_with_refinement(argv[2],&config,&options,&refinement,progress,nullptr)
          : nh_transcribe_file_with_options(argv[2], &config, &options, progress, nullptr);
      if (code != NH_OK) std::cerr << nh_last_error() << '\n';
      return code;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 2; }
  }
  if (argc != 3 || std::string(argv[1]) != "probe") {
    std::cerr << "Usage: nh-audio [native-info | probe LOCAL_AUDIO | transcribe INPUT OUTPUT MODEL TOKENS SEGMENTATION EMBEDDING SCRATCH [THREADS THRESHOLD CHUNK_SECONDS]]\n";
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
