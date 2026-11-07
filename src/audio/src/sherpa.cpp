#include "internal.hpp"
#include "sherpa-onnx/c-api/c-api.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <memory>
#include <set>
#include <string>
#include <vector>

struct nh_asr {
    const SherpaOnnxOfflineRecognizer* native = nullptr;
    std::atomic_flag busy = ATOMIC_FLAG_INIT;
    ~nh_asr() {
        if (native)
            SherpaOnnxDestroyOfflineRecognizer(native);
    }
};
struct nh_diarizer {
    const SherpaOnnxOfflineSpeakerDiarization* native = nullptr;
    std::atomic_flag busy = ATOMIC_FLAG_INIT;
    ~nh_diarizer() {
        if (native)
            SherpaOnnxDestroyOfflineSpeakerDiarization(native);
    }
};
namespace {
bool readable(const char* path) { return path && *path && std::ifstream(path).good(); }
bool valid_character_hotwords(const char* tokens, const char* path) {
    std::set<std::string> alphabet;
    std::ifstream vocabulary(tokens);
    std::string line;
    while (std::getline(vocabulary, line)) {
        const auto separator = line.rfind(' ');
        if (separator == std::string::npos)
            return false;
        const auto token = line.substr(0, separator);
        if (token == "<blk>" || token == "<blank>" || token == "<eps>")
            continue;
        size_t chars = std::count_if(token.begin(), token.end(), [](unsigned char c) { return (c & 0xc0) != 0x80; });
        if (chars != 1)
            return false;
        alphabet.insert(token);
    }
    std::ifstream words(path);
    bool found = false;
    while (std::getline(words, line)) {
        if (line.empty())
            continue;
        found = true;
        for (size_t i = 0; i < line.size();) {
            const unsigned char c = line[i];
            const size_t n = c < 0x80             ? 1
                             : (c & 0xe0) == 0xc0 ? 2
                             : (c & 0xf0) == 0xe0 ? 3
                             : (c & 0xf8) == 0xf0 ? 4
                                                  : 0;
            if (!n || i + n > line.size() || line[i] == ' ' || !alphabet.count(line.substr(i, n)))
                return false;
            i += n;
        }
    }
    return found;
}
bool valid_pcm(const float* samples, uint32_t n, uint32_t max) {
    if (!samples || !n || n > max)
        return false;
    for (uint32_t i = 0; i < n; ++i)
        if (!std::isfinite(samples[i]))
            return false;
    return true;
}
nh_status create_recognizer(SherpaOnnxOfflineRecognizerConfig& config, uint32_t threads, nh_asr** out) {
    config.feat_config.sample_rate = 16000;
    config.feat_config.feature_dim = 80;
    config.model_config.num_threads = static_cast<int32_t>(threads);
    config.model_config.provider = "cpu";
    if (!config.decoding_method)
        config.decoding_method = "greedy_search";
    auto handle = std::make_unique<nh_asr>();
    handle->native = SherpaOnnxCreateOfflineRecognizer(&config);
    if (!handle->native)
        return nh::fail(NH_RUNTIME_ERROR, "Could not initialize ASR model");
    *out = handle.release();
    return NH_OK;
}
} // namespace
extern "C" {
const char* nh_sherpa_version(void) { return SherpaOnnxGetVersionStr(); }
nh_status nh_asr_create(const nh_asr_config* options, nh_asr** out) {
    return nh::guard([&]() -> nh_status {
        if (!out)
            return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
        *out = nullptr;
        if (!options || options->struct_size != sizeof(*options) || !options->family || !options->threads ||
            options->threads > 16)
            return nh::fail(NH_INVALID_ARGUMENT, "Invalid ASR configuration");
        const std::string family = options->family;
        const std::string method = options->decoding_method ? options->decoding_method : "greedy_search";
        const bool beam = method == "modified_beam_search";
        if ((method != "greedy_search" && !beam) || (beam && family != "transducer") ||
            (beam && (!options->max_active_paths || options->max_active_paths > 64)) ||
            (options->hotwords_file && *options->hotwords_file && (!beam || !std::isfinite(options->hotwords_score))))
            return nh::fail(NH_INVALID_ARGUMENT, "Unsupported decoder/hotword configuration");
        if (family != "ctc" && family != "transducer" && family != "whisper")
            return nh::fail(NH_INVALID_ARGUMENT, "Unknown ASR family");
        if (!readable(options->model) || !readable(options->tokens) ||
            (family != "ctc" && !readable(options->decoder)) ||
            (family == "transducer" && !readable(options->joiner)) ||
            (options->hotwords_file && *options->hotwords_file && !readable(options->hotwords_file)))
            return nh::fail(NH_IO_ERROR, "ASR model/tokenizer/hotwords not readable");
        if (options->hotwords_file && *options->hotwords_file &&
            !valid_character_hotwords(options->tokens, options->hotwords_file))
            return nh::fail(NH_INVALID_ARGUMENT,
                            "Hotwords require character tokens and one known lowercase word per line");
        SherpaOnnxOfflineRecognizerConfig config{};
        config.model_config.tokens = options->tokens;
        config.decoding_method = method.c_str();
        config.max_active_paths = static_cast<int32_t>(options->max_active_paths);
        config.hotwords_file = options->hotwords_file;
        config.hotwords_score = options->hotwords_score;
        if (options->hotwords_file && *options->hotwords_file)
            config.model_config.modeling_unit = "cjkchar";
        if (family == "ctc")
            config.model_config.nemo_ctc.model = options->model;
        else if (family == "transducer") {
            config.model_config.transducer.encoder = options->model;
            config.model_config.transducer.decoder = options->decoder;
            config.model_config.transducer.joiner = options->joiner;
        } else {
            config.model_config.whisper.encoder = options->model;
            config.model_config.whisper.decoder = options->decoder;
            config.model_config.whisper.language = options->language ? options->language : "ru";
            config.model_config.whisper.task = "transcribe";
            config.model_config.whisper.tail_paddings = -1;
        }
        return create_recognizer(config, options->threads, out);
    });
}
nh_status nh_asr_create_ctc(const char* model, const char* tokens, uint32_t threads, nh_asr** out) {
    return nh::guard([&]() -> nh_status {
        if (!out)
            return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
        *out = nullptr;
        if (threads == 0 || threads > 16)
            return nh::fail(NH_INVALID_ARGUMENT, "threads must be 1..16");
        if (!readable(model) || !readable(tokens))
            return nh::fail(NH_IO_ERROR, "Model/tokens not readable");
        SherpaOnnxOfflineRecognizerConfig config{};
        config.feat_config.sample_rate = 16000;
        config.feat_config.feature_dim = 80;
        config.model_config.nemo_ctc.model = model;
        config.model_config.tokens = tokens;
        config.model_config.num_threads = static_cast<int32_t>(threads);
        config.model_config.provider = "cpu";
        config.decoding_method = "greedy_search";
        auto handle = std::make_unique<nh_asr>();
        handle->native = SherpaOnnxCreateOfflineRecognizer(&config);
        if (!handle->native)
            return nh::fail(NH_RUNTIME_ERROR, "Could not initialize CTC model");
        *out = handle.release();
        return NH_OK;
    });
}
nh_status nh_asr_decode(nh_asr* handle, const float* samples, uint32_t frames, nh_asr_callback callback, void* user) {
    return nh::guard([&]() -> nh_status {
        if (!handle || !callback || !valid_pcm(samples, frames, 400000))
            return nh::fail(NH_INVALID_ARGUMENT, "Expected handle, callback, finite 16kHz PCM <=25s");
        nh::BusyGuard lock(handle->busy);
        if (!lock.owns_lock())
            return nh::fail(NH_BUSY, "ASR handle busy");
        auto stream = std::unique_ptr<const SherpaOnnxOfflineStream, decltype(&SherpaOnnxDestroyOfflineStream)>(
            SherpaOnnxCreateOfflineStream(handle->native), SherpaOnnxDestroyOfflineStream);
        if (!stream)
            return nh::fail(NH_RUNTIME_ERROR, "Could not create ASR stream");
        std::vector<float> padded;
        const float* input = samples;
        uint32_t accepted = frames;
        if (frames < 16000) {
            padded.assign(16000, 0.0f);
            std::copy(samples, samples + frames, padded.begin());
            input = padded.data();
            accepted = 16000;
        }
        SherpaOnnxAcceptWaveformOffline(stream.get(), 16000, input, static_cast<int32_t>(accepted));
        SherpaOnnxDecodeOfflineStream(handle->native, stream.get());
        auto result = std::unique_ptr<const SherpaOnnxOfflineRecognizerResult,
                                      decltype(&SherpaOnnxDestroyOfflineRecognizerResult)>(
            SherpaOnnxGetOfflineStreamResult(stream.get()), SherpaOnnxDestroyOfflineRecognizerResult);
        if (!result)
            return nh::fail(NH_RUNTIME_ERROR, "No ASR result");
        if (callback(result->text, result->json, user))
            return nh::fail(NH_CANCELLED, "Result delivery cancelled");
        return NH_OK;
    });
}
nh_status nh_asr_create_transducer(const char* encoder, const char* decoder, const char* joiner, const char* tokens,
                                   uint32_t threads, nh_asr** out) {
    return nh::guard([&]() -> nh_status {
        if (!out)
            return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
        *out = nullptr;
        if (!threads || threads > 16)
            return nh::fail(NH_INVALID_ARGUMENT, "threads must be 1..16");
        if (!readable(encoder) || !readable(decoder) || !readable(joiner) || !readable(tokens))
            return nh::fail(NH_IO_ERROR, "Transducer model/tokens not readable");
        SherpaOnnxOfflineRecognizerConfig config{};
        config.model_config.transducer.encoder = encoder;
        config.model_config.transducer.decoder = decoder;
        config.model_config.transducer.joiner = joiner;
        config.model_config.tokens = tokens;
        return create_recognizer(config, threads, out);
    });
}
nh_status nh_asr_create_whisper(const char* encoder, const char* decoder, const char* tokens, uint32_t threads,
                                nh_asr** out) {
    return nh::guard([&]() -> nh_status {
        if (!out)
            return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
        *out = nullptr;
        if (!threads || threads > 16)
            return nh::fail(NH_INVALID_ARGUMENT, "threads must be 1..16");
        if (!readable(encoder) || !readable(decoder) || !readable(tokens))
            return nh::fail(NH_IO_ERROR, "Whisper model/tokens not readable");
        SherpaOnnxOfflineRecognizerConfig config{};
        config.model_config.whisper.encoder = encoder;
        config.model_config.whisper.decoder = decoder;
        config.model_config.whisper.language = "ru";
        config.model_config.whisper.task = "transcribe";
        config.model_config.whisper.tail_paddings = -1;
        config.model_config.tokens = tokens;
        return create_recognizer(config, threads, out);
    });
}
void nh_asr_destroy(nh_asr* handle) { delete handle; }
nh_status nh_diarizer_create(const char* segmentation, const char* embedding, uint32_t threads, float threshold,
                             nh_diarizer** out) {
    nh_diarizer_config options{sizeof(nh_diarizer_config), segmentation, embedding, threads, threshold, 0.3f, 0.5f, -1};
    return nh_diarizer_create_config(&options, out);
}
nh_status nh_diarizer_create_config(const nh_diarizer_config* options, nh_diarizer** out) {
    return nh_diarizer_create_with_window(options, 0.1f, out);
}
nh_status nh_diarizer_create_with_window(const nh_diarizer_config* options, float ratio, nh_diarizer** out) {
    return nh::guard([&]() -> nh_status {
        if (!out)
            return nh::fail(NH_INVALID_ARGUMENT, "Missing output handle");
        *out = nullptr;
        if (!options || options->struct_size != sizeof(*options) || !options->threads || options->threads > 16 ||
            !std::isfinite(ratio) || ratio < 0.05f || ratio > 1 || !std::isfinite(options->cluster_threshold) ||
            options->cluster_threshold <= 0 || options->cluster_threshold > 2 ||
            !std::isfinite(options->min_duration_on) || options->min_duration_on < 0 || options->min_duration_on > 10 ||
            !std::isfinite(options->min_duration_off) || options->min_duration_off < 0 ||
            options->min_duration_off > 10 ||
            (options->oracle_speakers != -1 && (options->oracle_speakers < 1 || options->oracle_speakers > 64)))
            return nh::fail(NH_INVALID_ARGUMENT, "Invalid diarization configuration");
        if (!readable(options->segmentation) || !readable(options->embedding))
            return nh::fail(NH_IO_ERROR, "Diarization models not readable");
        SherpaOnnxOfflineSpeakerDiarizationConfig config{};
        config.segmentation.pyannote.model = options->segmentation;
        config.segmentation.pyannote.window_shift_ratio = ratio;
        config.segmentation.num_threads = static_cast<int32_t>(options->threads);
        config.segmentation.provider = "cpu";
        config.embedding.model = options->embedding;
        config.embedding.num_threads = static_cast<int32_t>(options->threads);
        config.embedding.provider = "cpu";
        config.clustering.num_clusters = options->oracle_speakers;
        config.clustering.threshold = options->cluster_threshold;
        config.min_duration_on = options->min_duration_on;
        config.min_duration_off = options->min_duration_off;
        auto handle = std::make_unique<nh_diarizer>();
        handle->native = SherpaOnnxCreateOfflineSpeakerDiarization(&config);
        if (!handle->native)
            return nh::fail(NH_RUNTIME_ERROR, "Could not initialize diarizer");
        *out = handle.release();
        return NH_OK;
    });
}
nh_status nh_diarizer_process(nh_diarizer* handle, const float* samples, uint32_t frames, nh_turn_callback callback,
                              void* user) {
    return nh::guard([&]() -> nh_status {
        if (!handle || !callback || !valid_pcm(samples, frames, std::numeric_limits<uint32_t>::max()))
            return nh::fail(NH_INVALID_ARGUMENT, "Expected handle, callback, finite 16kHz PCM");
        nh::BusyGuard lock(handle->busy);
        if (!lock.owns_lock())
            return nh::fail(NH_BUSY, "Diarizer handle busy");
        auto result = std::unique_ptr<const SherpaOnnxOfflineSpeakerDiarizationResult,
                                      decltype(&SherpaOnnxOfflineSpeakerDiarizationDestroyResult)>(
            SherpaOnnxOfflineSpeakerDiarizationProcess(handle->native, samples, static_cast<int32_t>(frames)),
            SherpaOnnxOfflineSpeakerDiarizationDestroyResult);
        if (!result)
            return nh::fail(NH_RUNTIME_ERROR, "No diarization result");
        const int32_t count = SherpaOnnxOfflineSpeakerDiarizationResultGetNumSegments(result.get());
        auto turns = std::unique_ptr<const SherpaOnnxOfflineSpeakerDiarizationSegment,
                                     decltype(&SherpaOnnxOfflineSpeakerDiarizationDestroySegment)>(
            SherpaOnnxOfflineSpeakerDiarizationResultSortByStartTime(result.get()),
            SherpaOnnxOfflineSpeakerDiarizationDestroySegment);
        if (count > 0 && !turns)
            return nh::fail(NH_RUNTIME_ERROR, "No diarization segments");
        for (int32_t i = 0; i < count; ++i) {
            const auto& turn = turns.get()[i];
            if (callback(turn.speaker, turn.start, turn.end, user))
                return nh::fail(NH_CANCELLED, "Turn delivery cancelled");
        }
        return NH_OK;
    });
}
void nh_diarizer_destroy(nh_diarizer* handle) { delete handle; }
}
