#include "llama.h"
#include <filesystem>
#include <iostream>
#include <string>
int main(int argc, char **argv) {
  if (argc != 4) {
    std::cerr << "Usage: nh-audio-quantize SOURCE_GGUF NEW_Q4_K_M_GGUF THREADS\n";
    return 2;
  }
  try {
    const int threads = std::stoi(argv[3]);
    if (threads < 1 || threads > 16 || !std::filesystem::is_regular_file(argv[1]) ||
        std::filesystem::exists(argv[2]))
      return 2;
    auto params = llama_model_quantize_default_params();
    params.nthread = threads;
    params.ftype = LLAMA_FTYPE_MOSTLY_Q4_K_M;
    params.allow_requantize = true;
    llama_backend_init();
    const int result = llama_model_quantize(argv[1], argv[2], &params);
    llama_backend_free();
    return result;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}
