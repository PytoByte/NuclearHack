#include "internal.hpp"
#include "pipeline.hpp"
#include "json.hpp"
#include "picosha2.h"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iterator>
#include <map>
#include <memory>
#include <stdexcept>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/file.h>
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
  std::unique_ptr<picosha2::hash256_one_by_one> pcm_hash;
};
int32_t spool_pcm(const float *samples, uint32_t frames, uint64_t, void *opaque) {
  auto &ctx = *static_cast<DecodeContext *>(opaque);
  if (ctx.frames + frames > ctx.limit) { ctx.failure = NH_INVALID_ARGUMENT; return 1; }
  if (fwrite(samples, sizeof(float), frames, ctx.file) != frames) { ctx.failure = NH_IO_ERROR; return 1; }
  if (ctx.pcm_hash) {
    const auto *bytes = reinterpret_cast<const unsigned char *>(samples);
    ctx.pcm_hash->process(bytes, bytes + static_cast<size_t>(frames) * sizeof(float));
  }
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
  return nh::append_ctc_words(result.value("text", ""),
      result.value("tokens", std::vector<std::string>{}), result.value("timestamps", std::vector<double>{}),
      offset_ms, chunk_end_ms, words);
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
std::string file_hash(const char *path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("Cannot read checkpoint identity input");
  const auto result = picosha2::hash256_hex_string(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
  if (input.bad()) throw std::runtime_error("Checkpoint identity input read failed");
  return result;
}
struct Checkpoint {
  int lock_fd = -1;
  std::string path;
  Json data;
  nh_status status = NH_OK;
  ~Checkpoint() { if (lock_fd >= 0) close(lock_fd); }
  void open(const char *directory, const std::string &pcm_hash, const nh_pipeline_config *config) {
    if (!directory || !*directory) return;
    Json identity{{"cache_format", 2}, {"decoded_pcm_sha256", pcm_hash},
        {"asr_sha256", file_hash(config->asr_model)}, {"tokens_sha256", file_hash(config->tokens)},
        {"chunk_seconds", config->chunk_seconds}, {"threads", config->threads},
        {"sherpa", nh_sherpa_version()}, {"decoder", "miniaudio-0.11.23/lpf8/mono16k/greedy/tail-min1s/pad-short1s"},
#if defined(__aarch64__)
        {"architecture", "arm64"},
#elif defined(__x86_64__)
        {"architecture", "x86_64"},
#else
        {"architecture", "other"},
#endif
#ifdef __ANDROID__
        {"platform", "android"}
#else
        {"platform", "host"}
#endif
    };
    path = std::string(directory) + "/asr-" + picosha2::hash256_hex_string(identity.dump()) + ".json";
    const auto lock_path = path + ".lock";
    lock_fd = ::open(lock_path.c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (lock_fd < 0) throw std::runtime_error("Cannot open checkpoint lock");
    if (flock(lock_fd, LOCK_EX | LOCK_NB)) { status = NH_BUSY; return; }
    struct stat existing{};
    if (stat(path.c_str(), &existing) == 0 && existing.st_size > 64 * 1024 * 1024)
      throw std::runtime_error("Checkpoint exceeds 64-MiB metadata budget");
    std::ifstream previous(path);
    if (previous) {
      previous >> data;
      if (data.value("identity", Json()) != identity || !data.contains("asr") || !data["asr"].is_array())
        throw std::runtime_error("Checkpoint identity/format invalid; preserved for inspection");
    } else data = {{"identity", identity}, {"asr", Json::array()}};
  }
  bool enabled() const { return !path.empty(); }
  size_t size() const { return enabled() ? data["asr"].size() : 0; }
  Json cached(size_t index, uint64_t offset, size_t frames) const {
    const auto &chunk = data["asr"].at(index);
    if (chunk.at("offset_frames") != offset || chunk.at("frames") != frames || !chunk.at("backend").is_object())
      throw std::runtime_error("Checkpoint chunk timeline invalid; preserved for inspection");
    return chunk.at("backend");
  }
  void append(const Json &chunk) {
    if (!enabled()) return;
    data["asr"].push_back(chunk); write_json(path.c_str(), data);
  }
};
}

extern "C" nh_status nh_transcribe_file(const char *input, const nh_pipeline_config *config,
                                       nh_progress_callback progress, void *user) {
  return nh_transcribe_file_with_options(input, config, nullptr, progress, user);
}
extern "C" nh_status nh_transcribe_file_with_options(const char *input, const nh_pipeline_config *config,
    const nh_pipeline_options *options, nh_progress_callback progress, void *user) {
  return nh_transcribe_file_with_refinement(input,config,options,nullptr,progress,user);
}
extern "C" nh_status nh_transcribe_file_with_refinement(const char *input,const nh_pipeline_config *config,
    const nh_pipeline_options *options,const nh_speaker_refinement_config *refinement,
    nh_progress_callback progress,void *user) {
  return nh::guard([&]() -> nh_status {
    if(refinement && (refinement->struct_size!=sizeof(*refinement) ||
        !std::isfinite(refinement->cluster_threshold) || refinement->cluster_threshold<=0 ||
        refinement->cluster_threshold>=2 || refinement->max_clusters>256))
      return nh::fail(NH_INVALID_ARGUMENT,"Invalid bounded speaker refinement configuration");
    if (options && (options->struct_size != sizeof(*options) || options->attribution_mode > 1 ||
        !std::isfinite(options->min_duration_on) || options->min_duration_on < 0 || options->min_duration_on > 10 ||
        !std::isfinite(options->min_duration_off) || options->min_duration_off < 0 || options->min_duration_off > 10 ||
        !std::isfinite(options->window_shift_ratio) || (options->window_shift_ratio != 0 &&
            (options->window_shift_ratio < 0.05f || options->window_shift_ratio > 1))))
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid file pipeline options");
    if (!input || !config || config->struct_size != sizeof(nh_pipeline_config) ||
        !config->asr_model || !config->tokens || !config->segmentation || !config->embedding ||
        !config->scratch_directory || !config->output_json || config->threads < 1 || config->threads > 16 ||
        !config->chunk_seconds || config->chunk_seconds > 25 || !config->max_audio_seconds || config->max_audio_seconds > 3600 ||
        !std::isfinite(config->cluster_threshold) || config->cluster_threshold <= 0 || config->cluster_threshold > 2)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid file pipeline configuration (duration budget <=3600s)");
    nh::BusyGuard job(nh::heavy_job_busy);
    if (!job.owns_lock()) return nh::fail(NH_BUSY, "Another file/summary job is using the model memory budget");
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
    // Resampling/container delay rounding can add a fraction of a millisecond.
    DecodeContext decoded{spool.file, 0, static_cast<uint64_t>(config->max_audio_seconds) * 16000 + 16, progress, user, NH_OK, {}};
    if (options && options->checkpoint_directory && *options->checkpoint_directory)
      decoded.pcm_hash = std::make_unique<picosha2::hash256_one_by_one>();
    auto code = nh_decode_file(input, 16000, 16000, spool_pcm, &decoded);
    if (decoded.failure != NH_OK) return nh::fail(decoded.failure, "Decode exceeded duration budget or scratch I/O failed");
    if (code != NH_OK) return code;
    if (fflush(spool.file)) return nh::fail(NH_IO_ERROR, "Cannot flush scratch PCM");
    std::vector<nh::Word> words;
    Json raw_asr = Json::array();
    if (decoded.frames) {
      Checkpoint checkpoint;
      if (options && options->checkpoint_directory && emit("checkpoint_identity", 0, decoded.frames))
        return nh::fail(NH_CANCELLED, "Cancelled before checkpoint identity");
      std::string pcm_hash;
      if (decoded.pcm_hash) { decoded.pcm_hash->finish(); pcm_hash = picosha2::get_hash_hex_string(*decoded.pcm_hash); }
      checkpoint.open(options ? options->checkpoint_directory : nullptr, pcm_hash, config);
      if (checkpoint.status != NH_OK) return nh::fail(checkpoint.status, "Checkpoint is in use by another job");
      nh_asr *ptr = nullptr;
      {
        std::unique_ptr<nh_asr, decltype(&nh_asr_destroy)> asr(ptr, nh_asr_destroy);
        rewind(spool.file);
        std::vector<float> samples(config->chunk_seconds * 16000);
        uint64_t offset = 0;
        while (offset < decoded.frames) {
          const uint64_t remaining=decoded.frames-offset;
          size_t requested=samples.size();
          if(remaining>requested && remaining-requested<16000 && requested>16000)
            requested=static_cast<size_t>(remaining-16000);
          const size_t count = fread(samples.data(), sizeof(float), requested, spool.file);
          if (!count || ferror(spool.file)) return nh::fail(NH_IO_ERROR, "Cannot read scratch PCM");
          AsrResult result;
          const bool cached = raw_asr.size() < checkpoint.size();
          if (cached) {
            result.value = checkpoint.cached(raw_asr.size(), offset, count);
            if (emit("asr_cached", offset, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled during checkpoint replay");
          } else {
            if (!asr) {
              if (emit("asr_load", offset, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled before ASR load");
              code = nh_asr_create_ctc(config->asr_model, config->tokens, config->threads, &ptr);
              if (code != NH_OK) return code;
              asr.reset(ptr);
            }
            if (emit("asr", offset, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled between ASR chunks");
            code = nh_asr_decode(asr.get(), samples.data(), static_cast<uint32_t>(count), receive_asr, &result);
          }
          if (result.failed) return nh::fail(NH_RUNTIME_ERROR, "Invalid ASR backend JSON");
          if (code != NH_OK) return code;
          const bool aligned = append_words(result.value, offset * 1000 / 16000, ((offset + count) * 1000 + 15999) / 16000, words);
          raw_asr.push_back({{"offset_frames", offset}, {"frames", count}, {"alignment", aligned ? "ctc_tokens" : "chunk_fallback"}, {"backend", std::move(result.value)}});
          if (!cached) checkpoint.append(raw_asr.back());
          offset += count;
        }
      } // ASR must be released before diarization model load.
    }
    DiarResult diar;
    if (decoded.frames) {
      if (emit("diarization_load", 0, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled before diarization");
      nh_diarizer *ptr = nullptr;
      nh_diarizer_config diar_config{sizeof(nh_diarizer_config), config->segmentation, config->embedding,
          config->threads, config->cluster_threshold, options ? options->min_duration_on : 0.3f,
          options ? options->min_duration_off : 0.5f, -1};
      code = nh_diarizer_create_with_window(&diar_config,
          options && options->window_shift_ratio ? options->window_shift_ratio : 0.1f, &ptr);
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
    std::vector<nh::Turn> initial_turns;
    nh::RefinementStats refinement_stats;
    if(refinement && decoded.frames) {
      initial_turns=diar.turns;
      Mapping pcm(spool.file,decoded.frames);
      code=nh::refine_speakers(static_cast<const float *>(pcm.data),static_cast<uint32_t>(decoded.frames),
          diar.turns,config->embedding,config->threads,*refinement,progress,user,refinement_stats);
      if(code!=NH_OK)return code;
    }
    if (emit("merge", decoded.frames, decoded.frames)) return nh::fail(NH_CANCELLED, "Cancelled before export");
    auto utterances = nh::attribute_words(words, diar.turns, options && options->attribution_mode == 1);
    Json output{{"transcript", Json::array()}};
    for (const auto &u : utterances)
      output["transcript"].push_back({{"speaker_id", u.speaker_id}, {"start_ms", u.start_ms}, {"end_ms", u.end_ms}, {"text", u.text}});
    if (config->trace_json && *config->trace_json) {
      Json trace{{"asr", std::move(raw_asr)}, {"words", Json::array()}, {"speaker_turns", Json::array()}};
      for (const auto &w : words) trace["words"].push_back({{"start_ms", w.start_ms}, {"end_ms", w.end_ms}, {"text", w.text}});
      for (const auto &t : diar.turns) trace["speaker_turns"].push_back({{"speaker", t.speaker}, {"start_ms", t.start_ms}, {"end_ms", t.end_ms}});
      if(refinement) {
        trace["initial_speaker_turns"]=Json::array();
        for(const auto &t:initial_turns)trace["initial_speaker_turns"].push_back({{"speaker",t.speaker},{"start_ms",t.start_ms},{"end_ms",t.end_ms}});
        trace["speaker_refinement"]={{"threshold",refinement->cluster_threshold},
            {"initial_clusters",refinement_stats.initial_clusters},{"final_clusters",refinement_stats.final_clusters},
            {"embedding_clusters",refinement_stats.embedding_clusters}};
      }
      write_json(config->trace_json, trace);
    }
    write_json(config->output_json, output);
    emit("done", decoded.frames, decoded.frames);
    return NH_OK;
  });
}
