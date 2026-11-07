#include "internal.hpp"
#include "pipeline_ports.hpp"
#include "pipeline_storage.hpp"
#include "posterior_merge.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <memory>
#include <vector>

namespace nh {
namespace {
struct DiarResult {
    std::vector<nh::Turn> turns;
    bool failed = false;
};
int32_t receive_turn(int32_t speaker, double start, double end, void* opaque) {
    auto& result = *static_cast<DiarResult*>(opaque);
    try {
        result.turns.push_back({speaker, std::llround(start * 1000), std::llround(end * 1000)});
        return 0;
    } catch (...) {
        result.failed = true;
        return 1;
    }
}
struct StreamMergeContext {
    nh::PosteriorMerge& merge;
    nh_progress_callback progress = nullptr;
    void* user = nullptr;
    uint64_t total = 0;
    std::string error;
    bool failed = false;
};
int32_t receive_frames(const float* p, uint32_t frames, uint32_t slots, uint64_t start, void* opaque) noexcept {
    auto& ctx = *static_cast<StreamMergeContext*>(opaque);
    try {
        ctx.merge.accept(p, frames, slots, start);
        return ctx.progress &&
               ctx.progress("speaker_stream", start + static_cast<uint64_t>(frames) * 160, ctx.total, ctx.user);
    } catch (const std::exception& e) {
        ctx.failed = true;
        try {
            ctx.error = e.what();
        } catch (...) { // NOLINT(bugprone-empty-catch)
        }
        return 1;
    } catch (...) {
        ctx.failed = true;
        try {
            ctx.error = "Cannot merge speaker probabilities";
        } catch (...) { // NOLINT(bugprone-empty-catch)
        }
        return 1;
    }
}

class NativeAudioDecoder final : public AudioDecoderPort {
  public:
    nh_status decode(const char* input, nh_pcm_callback callback, void* user) override {
        return nh_decode_file(input, 16000, 16000, callback, user);
    }
};
class NativeCtcAsr final : public AsrPort {
  public:
    nh_status load(const nh_pipeline_config& config) override {
        nh_asr* handle = nullptr;
        const auto status = nh_asr_create_ctc(config.asr_model, config.tokens, config.threads, &handle);
        if (status == NH_OK)
            handle_.reset(handle);
        return status;
    }
    nh_status decode(const float* samples, uint32_t frames, nh_asr_callback callback, void* user) override {
        return nh_asr_decode(handle_.get(), samples, frames, callback, user);
    }

  private:
    std::unique_ptr<nh_asr, decltype(&nh_asr_destroy)> handle_{nullptr, nh_asr_destroy};
};
class AtomicJsonSink final : public TranscriptSinkPort {
  public:
    void write(const char* path, const Json& value) override { storage::write_json(path, value); }
};

class PosteriorSpeakerBackend final : public SpeakerPort {
  public:
    nh_status process(const PipelineRequest& request, FILE* pcm, uint64_t frames, uint32_t budget,
                      const std::vector<Word>& words, SpeakerResult& result) override {

        const auto* config = request.config;
        const auto progress = request.progress;
        void* user = request.user;
        const Progress reporter(progress, user);
        const auto emit = [&](const char* stage, uint64_t done, uint64_t total) {
            return reporter.emit(stage, done, total);
        };
        nh_status code = NH_OK;
        DiarResult diar;
        const auto* speaker = request.speaker;
        auto& word_slots = result.word_slots;
        auto& stream_stats = result.stats;
        if (emit("speaker_stream_load", 0, frames))
            return nh::fail(NH_CANCELLED, "Cancelled before speaker model load");
        nh_streaming_diarizer_config cfg = *speaker;
        cfg.max_audio_seconds = budget;
        nh_streaming_diarizer* ptr = nullptr;
        code = nh_streaming_diarizer_create(&cfg, &ptr);
        if (code != NH_OK)
            return code;
        std::unique_ptr<nh_streaming_diarizer, decltype(&nh_streaming_diarizer_destroy)> handle(
            ptr, nh_streaming_diarizer_destroy);
        nh::PosteriorMerge merge(words, frames / 160, config->trace_json && *config->trace_json);
        StreamMergeContext ctx{merge, progress, user, frames, {}};
        if (std::fseek(pcm, 0, SEEK_SET) != 0) {
            return nh::fail(NH_IO_ERROR, "Cannot rewind PCM input");
        }
        std::vector<float> block(16000);
        uint64_t offset = 0;
        while (offset < frames) {
            if (emit("speaker_stream", merge.completed_samples(), frames))
                return nh::fail(NH_CANCELLED, "Cancelled before speaker inference");
            const auto count =
                fread(block.data(), sizeof(float), std::min<uint64_t>(block.size(), frames - offset), pcm);
            if (!count || ferror(pcm))
                return nh::fail(NH_IO_ERROR, "Cannot read speaker PCM block");
            code = nh_streaming_diarizer_accept(handle.get(), block.data(), static_cast<uint32_t>(count),
                                                receive_frames, &ctx);
            if (ctx.failed)
                return nh::fail(NH_RUNTIME_ERROR,
                                ctx.error.empty() ? "Cannot merge speaker probabilities" : ctx.error.c_str());
            if (code != NH_OK)
                return code;
            offset += count;
        }
        code = nh_streaming_diarizer_flush(handle.get(), receive_frames, &ctx);
        if (ctx.failed)
            return nh::fail(NH_RUNTIME_ERROR,
                            ctx.error.empty() ? "Cannot merge speaker probabilities" : ctx.error.c_str());
        if (code != NH_OK)
            return code;
        code = nh_streaming_diarizer_get_stats(handle.get(), &stream_stats);
        if (code != NH_OK)
            return code;
        merge.finish();
        word_slots = std::move(merge.slots);
        diar.turns = std::move(merge.turns);
        result.turns = std::move(diar.turns);
        return NH_OK;
    }
};

class LegacySpeakerBackend final : public SpeakerPort {
  public:
    nh_status process(const PipelineRequest& request, FILE* pcm, uint64_t frames, uint32_t, const std::vector<Word>&,
                      SpeakerResult& result) override {

        const auto* config = request.config;
        const auto progress = request.progress;
        void* user = request.user;
        const Progress reporter(progress, user);
        const auto emit = [&](const char* stage, uint64_t done, uint64_t total) {
            return reporter.emit(stage, done, total);
        };
        nh_status code = NH_OK;
        DiarResult diar;
        const auto* options = request.options;
        if (emit("diarization_load", 0, frames))
            return nh::fail(NH_CANCELLED, "Cancelled before diarization");
        nh_diarizer* ptr = nullptr;
        nh_diarizer_config diar_config{sizeof(nh_diarizer_config),
                                       config->segmentation,
                                       config->embedding,
                                       config->threads,
                                       config->cluster_threshold,
                                       options ? options->min_duration_on : 0.3f,
                                       options ? options->min_duration_off : 0.5f,
                                       -1};
        code = nh_diarizer_create_with_window(
            &diar_config, options && options->window_shift_ratio ? options->window_shift_ratio : 0.1f, &ptr);
        if (code != NH_OK)
            return code;
        {
            std::unique_ptr<nh_diarizer, decltype(&nh_diarizer_destroy)> handle(ptr, nh_diarizer_destroy);
            storage::PcmMapping mapping(pcm, frames);
            if (emit("diarization", 0, frames))
                return nh::fail(NH_CANCELLED, "Cancelled before diarization inference");
            code =
                nh_diarizer_process(handle.get(), mapping.data(), static_cast<uint32_t>(frames), receive_turn, &diar);
            if (diar.failed)
                return nh::fail(NH_RUNTIME_ERROR, "Cannot collect speaker turns");
            if (code != NH_OK)
                return code;
        }
        result.turns = std::move(diar.turns);
        return NH_OK;
    }
};

class NativePipelineFactory final : public PipelineFactory {
  public:
    std::unique_ptr<AudioDecoderPort> create_decoder() const override { return std::make_unique<NativeAudioDecoder>(); }
    std::unique_ptr<AsrPort> create_asr() const override { return std::make_unique<NativeCtcAsr>(); }
    std::unique_ptr<SpeakerPort> create_speaker(bool posterior_mode) const override {
        if (posterior_mode)
            return std::make_unique<PosteriorSpeakerBackend>();
        return std::make_unique<LegacySpeakerBackend>();
    }
    std::unique_ptr<TranscriptSinkPort> create_sink() const override { return std::make_unique<AtomicJsonSink>(); }
};
} // namespace
std::unique_ptr<PipelineFactory> make_native_pipeline_factory() { return std::make_unique<NativePipelineFactory>(); }
} // namespace nh
