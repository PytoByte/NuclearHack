#include "internal.hpp"
#include "pipeline.hpp"
#include "json.hpp"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <map>
#include <memory>
#include <stdexcept>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

using Json = nlohmann::json;

namespace {
struct Spool {
  FILE *file = nullptr;
  explicit Spool(const char *directory) {
    std::string pattern = std::string(directory) + "/nh-pcm-XXXXXX";
    std::vector<char> path(pattern.begin(), pattern.end()); path.push_back(0);
    int fd = mkstemp(path.data());
    if (fd < 0) throw std::runtime_error("Cannot create scratch PCM file");
    unlink(path.data());
    file = fdopen(fd, "w+b");
    if (!file) { close(fd); throw std::runtime_error("Cannot open scratch PCM stream"); }
  }
  ~Spool() { if (file) fclose(file); }
};
struct Mapping {
  void *data = MAP_FAILED;
  size_t size = 0;
  Mapping(FILE *file, uint64_t frames) : size(static_cast<size_t>(frames) * sizeof(float)) {
    data = mmap(nullptr, size, PROT_READ, MAP_PRIVATE, fileno(file), 0);
    if (data == MAP_FAILED) throw std::runtime_error("Cannot map scratch PCM");
  }
  ~Mapping() { if (data != MAP_FAILED) munmap(data, size); }
};
struct DecodeContext {
  FILE *file;
  uint64_t frames = 0, limit;
  nh_progress_callback progress;
  void *user;
  nh_status failure = NH_OK;
};
int32_t spool_pcm(const float *samples, uint32_t frames, uint64_t, void *opaque) {
  auto &ctx = *static_cast<DecodeContext *>(opaque);
  if (ctx.frames + frames > ctx.limit) { ctx.failure = NH_INVALID_ARGUMENT; return 1; }
  if (fwrite(samples, sizeof(float), frames, ctx.file) != frames) { ctx.failure = NH_IO_ERROR; return 1; }
  ctx.frames += frames;
  return ctx.progress && ctx.progress("decode", ctx.frames, 0, ctx.user);
}
struct AsrResult { Json value; bool failed = false; };
int32_t receive_asr(const char *, const char *json, void *opaque) {
  auto &result = *static_cast<AsrResult *>(opaque);
  try { result.value = Json::parse(json); return 0; }
  catch (...) { result.failed = true; return 1; }
}
struct DiarResult { std::vector<nh::Turn> turns; bool failed = false; };
int32_t receive_turn(int32_t speaker, double start, double end, void *opaque) {
  auto &result = *static_cast<DiarResult *>(opaque);
  try { result.turns.push_back({speaker, std::llround(start * 1000), std::llround(end * 1000)}); return 0; }
  catch (...) { result.failed = true; return 1; }
}
bool append_words(const Json &result, int64_t offset_ms, int64_t chunk_end_ms, std::vector<nh::Word> &words) {
  const std::string text = result.value("text", "");
  if (text.empty()) return true;
  const size_t original_size = words.size();
  const auto &tokens = result.at("tokens");
  const auto &times = result.at("timestamps");
  if (!tokens.is_array() || tokens.size() != times.size() || tokens.empty()) {
    words.push_back({offset_ms, chunk_end_ms, text});
    return false;
  }
  std::string word;
  int64_t start = 0, end = 0;
  auto flush = [&]() {
    if (word.empty()) return;
    words.push_back({start, std::min(chunk_end_ms, std::max(start + 1, end)), word});
    word.clear();
  };
  for (size_t i = 0; i < tokens.size(); ++i) {
    const auto token = tokens.at(i).get<std::string>();
    const int64_t stamp = std::clamp<int64_t>(offset_ms + std::llround(times.at(i).get<double>() * 1000), offset_ms, chunk_end_ms - 1);
    if (token == " " || token == "\t" || token == "\n") { flush(); continue; }
    if (word.empty()) start = stamp;
    word += token;
    end = stamp + 40; // GigaAM CTC frame hop; not a forced-alignment guarantee.
  }
  flush();
  auto normalized = [](const std::string &value) {
    std::string out; bool space = false;
    for (char c : value) {
      if (c == ' ' || c == '\n' || c == '\t' || c == '\r') { space = !out.empty(); continue; }
      if (space) out += ' ';
      out += c; space = false;
    }
    return out;
  };
  std::string reconstructed;
  for (size_t i = original_size; i < words.size(); ++i) {
    if (!reconstructed.empty()) reconstructed += ' ';
    reconstructed += words[i].text;
  }
  if (normalized(reconstructed) != normalized(text)) {
    words.resize(original_size);
    words.push_back({offset_ms, chunk_end_ms, text});
    return false;
  }
  return true;
}
bool same_file(const char *a, const char *b) {
  if (!a || !b || !*a || !*b) return false;
  if (std::strcmp(a, b) == 0) return true;
  struct stat x{}, y{};
  return stat(a, &x) == 0 && stat(b, &y) == 0 && x.st_dev == y.st_dev && x.st_ino == y.st_ino;
}
void write_json(const char *path, const Json &value) {
  const std::string data = value.dump(2) + "\n";
  std::string pattern = std::string(path) + ".tmp-XXXXXX";
  std::vector<char> temporary(pattern.begin(), pattern.end()); temporary.push_back(0);
  const int fd = mkstemp(temporary.data());
  if (fd < 0) throw std::runtime_error("Cannot create JSON output");
  FILE *out = fdopen(fd, "wb");
  if (!out) { close(fd); unlink(temporary.data()); throw std::runtime_error("Cannot open JSON output"); }
  const auto size = fwrite(data.data(), 1, data.size(), out);
  const bool flushed = fflush(out) == 0 && fsync(fd) == 0;
  const int status = fclose(out);
  if (size != data.size() || !flushed || status || rename(temporary.data(), path)) {
    unlink(temporary.data()); throw std::runtime_error("Could not write complete JSON output");
  }
}
}

extern "C" nh_status nh_transcribe_file(const char *input, const nh_pipeline_config *config,
                                       nh_progress_callback progress, void *user) {
  return nh::guard([&]() -> nh_status {
    if (!input || !config || config->struct_size != sizeof(nh_pipeline_config) ||
        !config->asr_model || !config->tokens || !config->segmentation || !config->embedding ||
        !config->scratch_directory || !config->output_json || config->threads < 1 || config->threads > 16 ||
        !config->chunk_seconds || config->chunk_seconds > 25 || !config->max_audio_seconds || config->max_audio_seconds > 600)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid file pipeline configuration (max duration <=600s in baseline)");
    for (const char *source : {input, config->asr_model, config->tokens, config->segmentation, config->embedding})
      if (same_file(source, config->output_json) || same_file(source, config->trace_json))
        return nh::fail(NH_INVALID_ARGUMENT, "Output would overwrite an input/model file");
    if (same_file(config->output_json, config->trace_json))
      return nh::fail(NH_INVALID_ARGUMENT, "Transcript and trace paths must differ");
    auto emit = [&](const char *stage, uint64_t done, uint64_t total) {
      return progress && progress(stage, done, total, user);
    };
    if (emit("queued", 0, 0)) return nh::fail(NH_CANCELLED, "Cancelled before processing");
    Spool spool(config->scratch_directory);
    DecodeContext decoded{spool.file, 0, static_cast<uint64_t>(config->max_audio_seconds) * 16000, progress, user};
    auto code = nh_decode_file(input, 16000, 16000, spool_pcm, &decoded);
    if (decoded.failure != NH_OK) return nh::fail(decoded.failure, "Decode exceeded duration budget or scratch I/O failed");
    if (code != NH_OK) return code;
    if (fflush(spool.file)) return nh::fail(NH_IO_ERROR, "Cannot flush scratch PCM");
    std::vector<nh::Word> words;
    Json raw_asr = Json::array();
    if (decoded.frames) {
      if (emit("asr_load", 0, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled before ASR");
      nh_asr *ptr = nullptr;
      code = nh_asr_create_ctc(config->asr_model, config->tokens, config->threads, &ptr);
      if (code != NH_OK) return code;
      {
        std::unique_ptr<nh_asr, decltype(&nh_asr_destroy)> asr(ptr, nh_asr_destroy);
        rewind(spool.file);
        std::vector<float> samples(config->chunk_seconds * 16000);
        uint64_t offset = 0;
        while (offset < decoded.frames) {
          if (emit("asr", offset, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled between ASR chunks");
          const size_t count = fread(samples.data(), sizeof(float), samples.size(), spool.file);
          if (!count || ferror(spool.file)) return nh::fail(NH_IO_ERROR, "Cannot read scratch PCM");
          AsrResult result;
          code = nh_asr_decode(asr.get(), samples.data(), static_cast<uint32_t>(count), receive_asr, &result);
          if (result.failed) return nh::fail(NH_RUNTIME_ERROR, "Invalid ASR backend JSON");
          if (code != NH_OK) return code;
          const bool aligned = append_words(result.value, offset * 1000 / 16000, ((offset + count) * 1000 + 15999) / 16000, words);
          raw_asr.push_back({{"offset_frames", offset}, {"frames", count}, {"alignment", aligned ? "ctc_chars" : "chunk_fallback"}, {"backend", std::move(result.value)}});
          offset += count;
        }
      } // ASR must be released before diarization model load.
    }
    DiarResult diar;
    if (decoded.frames) {
      if (emit("diarization_load", 0, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled before diarization");
      nh_diarizer *ptr = nullptr;
      code = nh_diarizer_create(config->segmentation, config->embedding, config->threads, config->cluster_threshold, &ptr);
      if (code != NH_OK) return code;
      {
        std::unique_ptr<nh_diarizer, decltype(&nh_diarizer_destroy)> handle(ptr, nh_diarizer_destroy);
        Mapping pcm(spool.file, decoded.frames);
        if (emit("diarization", 0, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled before diarization inference");
        code = nh_diarizer_process(handle.get(), static_cast<const float *>(pcm.data), static_cast<uint32_t>(decoded.frames), receive_turn, &diar);
        if (diar.failed) return nh::fail(NH_RUNTIME_ERROR, "Cannot collect speaker turns");
        if (code != NH_OK) return code;
      }
    }
    if (emit("merge", decoded.frames, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled before export");
    auto utterances = nh::attribute_words(words, diar.turns);
    Json output{{"transcript", Json::array()}};
    for (const auto &u : utterances)
      output["transcript"].push_back({{"speaker_id", u.speaker_id}, {"start_ms", u.start_ms}, {"end_ms", u.end_ms}, {"text", u.text}});
    if (config->trace_json && *config->trace_json) {
      Json trace{{"asr", std::move(raw_asr)}, {"words", Json::array()}, {"speaker_turns", Json::array()}};
      for (const auto &w : words) trace["words"].push_back({{"start_ms", w.start_ms}, {"end_ms", w.end_ms}, {"text", w.text}});
      for (const auto &t : diar.turns) trace["speaker_turns"].push_back({{"speaker", t.speaker}, {"start_ms", t.start_ms}, {"end_ms", t.end_ms}});
      write_json(config->trace_json, trace);
    }
    write_json(config->output_json, output);
    emit("done", decoded.frames, decoded.frames);
    return NH_OK;
  });
}
