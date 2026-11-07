#include "file_transcriber.hpp"

#include "internal.hpp"
#include "picosha2.h"
#include "pipeline_storage.hpp"
#include "posterior_merge.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <memory>
#include <utility>

namespace nh {
namespace {
struct DecodeContext {
    FILE* file = nullptr;
    uint64_t frames = 0, limit = 0;
    nh_progress_callback progress = nullptr;
    void* user = nullptr;
    nh_status failure = NH_OK;
    bool duration_exceeded = false;
    bool scratch_write_failed = false;
    std::unique_ptr<picosha2::hash256_one_by_one> pcm_hash;
};
auto spool_pcm(const float* samples, uint32_t frames, uint64_t /*unused*/, void* opaque) -> int32_t {
    auto& ctx = *static_cast<DecodeContext*>(opaque);
    if (ctx.frames + frames > ctx.limit) {
        ctx.failure = NH_INVALID_ARGUMENT;
        ctx.duration_exceeded = true;
        return 1;
    }
    if (fwrite(samples, sizeof(float), frames, ctx.file) != frames) {
        ctx.failure = NH_IO_ERROR;
        ctx.scratch_write_failed = true;
        return 1;
    }
    if (ctx.pcm_hash) {
        const auto* bytes = reinterpret_cast<const unsigned char*>(samples);
        ctx.pcm_hash->process(bytes, bytes + (static_cast<size_t>(frames) * sizeof(float)));
    }
    ctx.frames += frames;
    return static_cast<int32_t>((ctx.progress != nullptr) && (ctx.progress("decode", ctx.frames, 0, ctx.user)) != 0);
}
struct AsrResult {
    Json value;
    bool failed = false;
};
auto receive_asr(const char* /*unused*/, const char* json, void* opaque) -> int32_t {
    auto& result = *static_cast<AsrResult*>(opaque);
    try {
        result.value = Json::parse(json);
        return 0;
    } catch (...) {
        result.failed = true;
        return 1;
    }
}
auto append_words(const Json& result, int64_t offset_ms, int64_t chunk_end_ms, std::vector<nh::Word>& words) -> bool {
    return nh::append_ctc_words(result.value("text", ""), result.value("tokens", std::vector<std::string>{}),
                                result.value("timestamps", std::vector<double>{}), offset_ms, chunk_end_ms, words);
}

} // namespace
FileTranscriber::FileTranscriber(PipelineRequest request, std::unique_ptr<PipelineFactory> factory)
    : input(request.input), config(request.config), options(request.options), refinement(request.refinement),
      speaker(request.speaker), progress(request.progress), user(request.user), factory_(std::move(factory)) {}

auto FileTranscriber::emit(const char* stage, uint64_t done, uint64_t total) const -> bool {
    return Progress(progress, user).emit(stage, done, total);
}
auto FileTranscriber::validate() const -> nh_status {
    if ((speaker != nullptr) &&
        (speaker->struct_size != sizeof(*speaker) || (speaker->model == nullptr) || ((*speaker->model) == 0) ||
         speaker->threads < 1 || speaker->threads > 16 || speaker->profile > 1 || speaker->max_audio_seconds > 3600)) {
        return nh::fail(NH_INVALID_ARGUMENT, "Invalid file speaker streaming configuration");
    }
    if ((refinement != nullptr) &&
        (refinement->struct_size != sizeof(*refinement) || !std::isfinite(refinement->cluster_threshold) ||
         refinement->cluster_threshold <= 0 || refinement->cluster_threshold >= 2 || refinement->max_clusters > 256)) {
        return nh::fail(NH_INVALID_ARGUMENT, "Invalid bounded speaker refinement configuration");
    }
    if ((options != nullptr) &&
        (options->struct_size != sizeof(*options) || options->attribution_mode > 1 ||
         !std::isfinite(options->min_duration_on) || options->min_duration_on < 0 || options->min_duration_on > 10 ||
         !std::isfinite(options->min_duration_off) || options->min_duration_off < 0 || options->min_duration_off > 10 ||
         !std::isfinite(options->window_shift_ratio) ||
         (options->window_shift_ratio != 0 &&
          (options->window_shift_ratio < 0.05F || options->window_shift_ratio > 1)))) {
        return nh::fail(NH_INVALID_ARGUMENT, "Invalid file pipeline options");
    }
    if ((speaker != nullptr) && (options != nullptr) &&
        (options->min_duration_on != 0 || options->min_duration_off != 0 || options->attribution_mode != 0 ||
         options->window_shift_ratio != 0)) {
        return nh::fail(NH_INVALID_ARGUMENT, "Posterior file mode accepts only checkpoint options");
    }
    if ((input == nullptr) || (config == nullptr) || config->struct_size != sizeof(nh_pipeline_config) ||
        (config->asr_model == nullptr) || (config->tokens == nullptr) ||
        ((speaker == nullptr) && ((config->segmentation == nullptr) || (config->embedding == nullptr))) ||
        (config->scratch_directory == nullptr) || (config->output_json == nullptr) || config->threads < 1 ||
        config->threads > 16 || (config->chunk_seconds == 0u) || config->chunk_seconds > 25 ||
        (config->max_audio_seconds == 0u) || config->max_audio_seconds > 3600 ||
        ((speaker == nullptr) && (!std::isfinite(config->cluster_threshold) || config->cluster_threshold <= 0 ||
                                  config->cluster_threshold > 2))) {
        return nh::fail(NH_INVALID_ARGUMENT, "Invalid file pipeline configuration (duration budget <=3600s)");
    }
    return NH_OK;
}
auto FileTranscriber::validate_paths() const -> nh_status {
    for (const char* source : {input, config->asr_model, config->tokens, config->segmentation, config->embedding}) {
        if (storage::same_file(source, config->output_json) || storage::same_file(source, config->trace_json)) {
            return nh::fail(NH_INVALID_ARGUMENT, "Output would overwrite an input/model file");
        }
    }
    if (speaker != nullptr) {
        const std::string external = std::string(speaker->model) + "_data";
        for (const char* path : {speaker->model, external.c_str()}) {
            if (storage::same_file(path, config->output_json) || storage::same_file(path, config->trace_json)) {
                return nh::fail(NH_INVALID_ARGUMENT, "Output would overwrite speaker model/weights");
            }
        }
    }
    if (storage::same_file(config->output_json, config->trace_json)) {
        return nh::fail(NH_INVALID_ARGUMENT, "Transcript and trace paths must differ");
    }
    return NH_OK;
}
auto FileTranscriber::recognize(FILE* pcm, uint64_t frames, const std::string& pcm_hash, std::vector<Word>& words,
                                Json& raw_asr) -> nh_status {
    storage::AsrCheckpoint checkpoint;
    if ((options != nullptr) && (options->checkpoint_directory != nullptr) && emit("checkpoint_identity", 0, frames)) {
        return nh::fail(NH_CANCELLED, "Cancelled before checkpoint identity");
    }
    checkpoint.open((options != nullptr) ? options->checkpoint_directory : nullptr, pcm_hash, config);
    if (checkpoint.status() != NH_OK) {
        return nh::fail(checkpoint.status(), "Checkpoint is in use by another job");
    }
    {
        nh_status code = NH_OK;
        std::unique_ptr<AsrPort> asr;
        if (std::fseek(pcm, 0, SEEK_SET) != 0) {
            return nh::fail(NH_IO_ERROR, "Cannot rewind PCM input");
        }
        std::vector<float> samples(config->chunk_seconds * 16000);
        uint64_t offset = 0;
        while (offset < frames) {
            const uint64_t remaining = frames - offset;
            size_t requested = samples.size();
            if (remaining > requested && remaining - requested < 16000 && requested > 16000) {
                requested = static_cast<size_t>(remaining - 16000);
            }
            const size_t count = fread(samples.data(), sizeof(float), requested, pcm);
            if ((count == 0u) || (ferror(pcm) != 0)) {
                return nh::fail(NH_IO_ERROR, "Cannot read scratch PCM");
            }
            AsrResult result;
            const bool cached = raw_asr.size() < checkpoint.size();
            if (cached) {
                result.value = checkpoint.cached(raw_asr.size(), offset, count);
                if (emit("asr_cached", offset, frames)) {
                    return nh::fail(NH_CANCELLED, "Cancelled during checkpoint replay");
                }
            } else {
                if (!asr) {
                    if (emit("asr_load", offset, frames)) {
                        return nh::fail(NH_CANCELLED, "Cancelled before ASR load");
                    }
                    asr = factory_->create_asr();
                    code = asr->load(*config);
                    if (code != NH_OK) {
                        return code;
                    }
                }
                if (emit("asr", offset, frames)) {
                    return nh::fail(NH_CANCELLED, "Cancelled between ASR chunks");
                }
                code = asr->decode(samples.data(), static_cast<uint32_t>(count), receive_asr, &result);
            }
            if (result.failed) {
                return nh::fail(NH_RUNTIME_ERROR, "Invalid ASR backend JSON");
            }
            if (code != NH_OK) {
                return code;
            }
            const bool aligned =
                append_words(result.value, offset * 1000 / 16000, (((offset + count) * 1000) + 15999) / 16000, words);
            raw_asr.push_back({
                {"offset_frames", offset},
                {"frames", count},
                {"alignment", aligned ? "ctc_tokens" : "chunk_fallback"},
                {"backend", std::move(result.value)},
            });
            if (!cached) {
                checkpoint.append(raw_asr.back());
            }
            offset += count;
        }
    } // ASR must be released before diarization model load.
    return NH_OK;
}
void FileTranscriber::publish(const std::string& source_pcm_sha, const std::vector<Word>& words, Json raw_asr,
                              const SpeakerResult& speakers, const std::vector<Turn>& initial_turns,
                              const RefinementStats& refinement_stats) {
    auto sink = factory_->create_sink();
    auto utterances =
        (speaker != nullptr)
            ? nh::attribute_word_slots(words, speakers.word_slots)
            : nh::attribute_words(words, speakers.turns, (options != nullptr) && options->attribution_mode == 1);
    Json output{{"transcript", Json::array()}};
    for (const auto& u : utterances) {
        output["transcript"].push_back(
            {{"speaker_id", u.speaker_id}, {"start_ms", u.start_ms}, {"end_ms", u.end_ms}, {"text", u.text}});
    }
    if ((config->trace_json != nullptr) && ((*config->trace_json) != 0)) {
        Json trace{{"asr", std::move(raw_asr)}, {"words", Json::array()}, {"speaker_turns", Json::array()}};
        for (const auto& w : words) {
            trace["words"].push_back({{"start_ms", w.start_ms}, {"end_ms", w.end_ms}, {"text", w.text}});
        }
        for (const auto& t : speakers.turns) {
            trace["speaker_turns"].push_back({{"speaker", t.speaker}, {"start_ms", t.start_ms}, {"end_ms", t.end_ms}});
        }
        if (speaker != nullptr) {
            trace["word_speaker_slots"] = speakers.word_slots;
            trace["decoded_pcm_sha256"] = source_pcm_sha;
            trace["speaker_stream"] = {
                {"profile", speaker->profile},
                {"threads", speaker->threads},
                {"word_anchor_ms", 160},
                {"assignment", "posterior_mean_start_anchor"},
                {"ort", nh_onnxruntime_version()},
                {"model_calls", speakers.stats.model_calls},
                {"emitted_frames", speakers.stats.emitted_frames},
                {"peak_buffered_samples", speakers.stats.peak_buffered_samples},
                {"inference_seconds", speakers.stats.inference_seconds},
            };
        }
        if (refinement != nullptr) {
            trace["initial_speaker_turns"] = Json::array();
            for (const auto& t : initial_turns) {
                trace["initial_speaker_turns"].push_back(
                    {{"speaker", t.speaker}, {"start_ms", t.start_ms}, {"end_ms", t.end_ms}});
            }
            trace["speaker_refinement"] = {
                {"threshold", refinement->cluster_threshold},
                {"initial_clusters", refinement_stats.initial_clusters},
                {"final_clusters", refinement_stats.final_clusters},
                {"embedding_clusters", refinement_stats.embedding_clusters},
            };
        }
        sink->write(config->trace_json, trace);
    }
    sink->write(config->output_json, output);
}

auto FileTranscriber::run() -> nh_status {
    return guard([&]() -> nh_status {
        auto code = validate();
        if (code != NH_OK) {
            return code;
        }
        BusyGuard job(heavy_job_busy);
        if (!job.owns_lock()) {
            return fail(NH_BUSY, "Another file/summary job is using the model memory budget");
        }
        code = validate_paths();
        if (code != NH_OK) {
            return code;
        }
        if (emit("queued", 0, 0)) {
            return fail(NH_CANCELLED, "Cancelled before processing");
        }
        storage::PcmSpool spool(config->scratch_directory);
        const uint32_t budget = speaker && speaker->max_audio_seconds
                                    ? std::min(config->max_audio_seconds, speaker->max_audio_seconds)
                                    : config->max_audio_seconds;
        DecodeContext decoded{
            spool.file(), 0,     (static_cast<uint64_t>(budget) * 16000) + (speaker ? 0 : 16),
            progress,     user,  NH_OK,
            false,        false, {},
        };
        if (speaker || (options && options->checkpoint_directory && *options->checkpoint_directory)) {
            decoded.pcm_hash = std::make_unique<picosha2::hash256_one_by_one>();
        }
        {
            auto decoder = factory_->create_decoder();
            code = decoder->decode(input, spool_pcm, &decoded);
        }
        if (decoded.duration_exceeded) {
            return fail(decoded.failure,
                        ("Decode exceeded duration budget of " + std::to_string(budget) + " seconds").c_str());
        }
        if (decoded.scratch_write_failed) {
            return fail(decoded.failure,
                        ("Scratch PCM write failed in " + std::string(config->scratch_directory)).c_str());
        }
        if (code != NH_OK) {
            return code;
        }
        if (fflush(spool.file())) {
            return fail(NH_IO_ERROR, "Cannot flush scratch PCM");
        }
        std::vector<Word> words;
        Json raw_asr = Json::array();
        std::string source_pcm_sha;
        if (decoded.frames) {
            if (decoded.pcm_hash) {
                decoded.pcm_hash->finish();
                source_pcm_sha = picosha2::get_hash_hex_string(*decoded.pcm_hash);
            }
            code = recognize(spool.file(), decoded.frames, source_pcm_sha, words, raw_asr);
            if (code != NH_OK) {
                return code;
            }
        }
        SpeakerResult speakers;
        if (decoded.frames) {
            auto backend = factory_->create_speaker(speaker != nullptr);
            const PipelineRequest request{input, config, options, refinement, speaker, progress, user};
            code = backend->process(request, spool.file(), decoded.frames, budget, words, speakers);
            if (code != NH_OK) {
                return code;
            }
        }
        std::vector<Turn> initial_turns;
        RefinementStats refinement_stats;
        if (refinement && decoded.frames) {
            initial_turns = speakers.turns;
            storage::PcmMapping pcm(spool.file(), decoded.frames);
            code = refine_speakers(pcm.data(), static_cast<uint32_t>(decoded.frames), speakers.turns, config->embedding,
                                   config->threads, *refinement, progress, user, refinement_stats);
            if (code != NH_OK) {
                return code;
            }
        }
        if (emit("merge", decoded.frames, decoded.frames)) {
            return fail(NH_CANCELLED, "Cancelled before export");
        }
        publish(source_pcm_sha, words, std::move(raw_asr), speakers, initial_turns, refinement_stats);
        emit("done", decoded.frames, decoded.frames);
        return NH_OK;
    });
}
} // namespace nh
