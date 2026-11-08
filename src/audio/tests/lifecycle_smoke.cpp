/* Success-path lifecycle test: create -> process -> destroy for every handle
 * kind, under ASan/LSan. Sections are skipped when the pinned model is not
 * bootstrapped locally, so the default ctest run stays green without weights.
 * The VAD section additionally churns the same handle kind over many cycles:
 * a per-cycle leak is invisible to a single create/destroy pair. */
#include "nuclear_audio.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

/* Churn budget: cycles and the tolerated RSS growth across them (kB). The first
 * cycles are warm-up: the first ORT session load reserves arena pages that the
 * allocator never returns to the OS, so the leak signal is the growth *after*
 * warm-up, not the warm-up itself. */
/* Measured noise band on the host (2..80 cycles): -3.6 MB .. +2.7 MB around a
 * ~35 MB plateau, so the limit has to sit above that band while still catching a
 * per-cycle leak (>= ~300 kB/cycle at 30 cycles). */
static const int kDefaultCycles = 20;
static const int kWarmupCycles = 2;
static const long kRssLimitKb = 8192;

/* GCC defines __SANITIZE_ADDRESS__; clang exposes the sanitizer through
 * __has_feature. The two cannot be tested in one #if: GCC preprocesses
 * __has_feature(...) even when defined(__has_feature) is false. */
#if defined(__SANITIZE_ADDRESS__)
static const bool rss_under_sanitizer = true;
#elif defined(__has_feature)
#if __has_feature(address_sanitizer)
static const bool rss_under_sanitizer = true;
#else
static const bool rss_under_sanitizer = false;
#endif
#else
static const bool rss_under_sanitizer = false;
#endif

static long vm_rss_kb() {
#ifdef __linux__
    FILE* status = fopen("/proc/self/status", "rb");
    if (!status)
        return -1;
    char line[256];
    long rss = -1;
    while (fgets(line, sizeof(line), status)) {
        if (strncmp(line, "VmRSS:", 6) == 0)
            rss = strtol(line + 6, nullptr, 10);
    }
    fclose(status);
    return rss;
#else
    return -1;
#endif
}

static const char* env_or(const char* name) {
    const char* value = getenv(name);
    return value && *value ? value : nullptr;
}

/* Signal length per cycle. Under Valgrind the inference is ~10x slower, so the
 * leak stage uses a short signal: create/destroy accounting does not need
 * seconds of audio. */
static uint32_t signal_seconds() {
    const char* value = getenv("NH_LIFECYCLE_SECONDS");
    int seconds = value ? atoi(value) : 3;
    return seconds > 0 ? static_cast<uint32_t>(seconds) : 3u;
}

/* Deterministic synthetic dialogue-like tone: no recordings, no network. */
static std::vector<float> make_signal(uint32_t seconds) {
    std::vector<float> samples(static_cast<size_t>(seconds) * 16000u);
    for (size_t i = 0; i < samples.size(); ++i) {
        double t = static_cast<double>(i) / 16000.0;
        double envelope = 0.5 + 0.5 * std::sin(2.0 * 3.141592653589793 * 0.3 * t);
        samples[i] = static_cast<float>(0.2 * envelope * std::sin(2.0 * 3.141592653589793 * 440.0 * t));
    }
    return samples;
}

static int32_t accept_text(const char* text, const char* backend_json, void* user) {
    (void)text;
    (void)backend_json;
    (void)user;
    return 0;
}
static int32_t accept_turn(int32_t speaker, double start, double end, void* user) {
    (void)speaker;
    (void)start;
    (void)end;
    (void)user;
    return 0;
}
static int32_t accept_frames(const float* probabilities, uint32_t frames, uint32_t slots, uint64_t start_sample,
                             void* user) {
    (void)probabilities;
    (void)frames;
    (void)slots;
    (void)start_sample;
    (void)user;
    return 0;
}
static int32_t accept_span(uint64_t start_frame, uint64_t end_frame, void* user) {
    (void)start_frame;
    (void)end_frame;
    (void)user;
    return 0;
}

static int failures = 0;
static void report(const char* what, nh_status status) {
    if (status != NH_OK) {
        std::fprintf(stderr, "lifecycle-smoke: %s failed: %s\n", what, nh_last_error());
        ++failures;
    }
}

int main() {
    const std::vector<float> audio = make_signal(signal_seconds());

    if (const char* model = env_or("NH_VAD_MODEL")) {
        const char* cycles_text = env_or("NH_LIFECYCLE_CYCLES");
        const int cycles = cycles_text ? atoi(cycles_text) : kDefaultCycles;
        long rss_warm = -1;
        for (int cycle = 0; cycle < cycles + kWarmupCycles; ++cycle) {
            nh_vad* vad = nullptr;
            nh_vad_config config = {sizeof(config), model, 2, 0.5f, 0.3f, 0.1f, 20.0f};
            report("vad create", nh_vad_create(&config, &vad));
            if (vad) {
                const uint32_t first = static_cast<uint32_t>(audio.size() / 2);
                report("vad accept", nh_vad_accept(vad, audio.data(), first, accept_span, nullptr));
                report("vad accept", nh_vad_accept(vad, audio.data() + first,
                                                   static_cast<uint32_t>(audio.size() - first), accept_span, nullptr));
                report("vad flush", nh_vad_flush(vad, accept_span, nullptr));
                nh_vad_destroy(vad);
            }
            /* The first cycles load the ORT session and grow its arena; that is warm-up,
             * not a leak. Sample right after warm-up so the delta covers only steady state. */
            if (cycle == kWarmupCycles - 1)
                rss_warm = vm_rss_kb();
        }
        const long rss_after = vm_rss_kb();
        std::printf("lifecycle-smoke: vad churn %d cycles (+%d warm-up), VmRSS %ld -> %ld kB (delta %ld, limit %ld)\n",
                    cycles, kWarmupCycles, rss_warm, rss_after, rss_after - rss_warm, kRssLimitKb);
        /* AddressSanitizer keeps freed pages in its own arenas, so RSS under ASan is
         * dominated by the tool, not by the SDK: churn/RSS is measured in the plain build. */
        if (!rss_under_sanitizer && rss_warm >= 0 && rss_after >= 0 && rss_after - rss_warm > kRssLimitKb) {
            std::fprintf(stderr, "lifecycle-smoke: rss growth above limit after vad churn\n");
            ++failures;
        }
    }

    if (const char* segmentation = env_or("NH_SEGMENTATION_MODEL"); segmentation) {
        const char* embedding = env_or("NH_EMBEDDING_MODEL");
        if (embedding) {
            nh_diarizer* diarizer = nullptr;
            nh_diarizer_config config = {sizeof(config), segmentation, embedding, 2, 0.8f, 0.3f, 0.5f, -1};
            report("diarizer create", nh_diarizer_create_config(&config, &diarizer));
            if (diarizer) {
                report("diarizer process",
                       nh_diarizer_process(diarizer, audio.data(), static_cast<uint32_t>(audio.size()), accept_turn,
                                           nullptr));
                nh_diarizer_destroy(diarizer);
            }
            nh_diarizer* windowed = nullptr;
            report("diarizer create (window)", nh_diarizer_create_with_window(&config, 0.1f, &windowed));
            if (windowed) {
                report("diarizer process",
                       nh_diarizer_process(windowed, audio.data(), static_cast<uint32_t>(audio.size()), accept_turn,
                                           nullptr));
                nh_diarizer_destroy(windowed);
            }
        }
    }

    if (const char* model = env_or("NH_NEMOTRON_MODEL")) {
        nh_streaming_diarizer* streaming = nullptr;
        nh_streaming_diarizer_config config = {sizeof(config), model, 2, 0, 60};
        report("streaming create", nh_streaming_diarizer_create(&config, &streaming));
        if (streaming) {
            for (size_t offset = 0; offset < audio.size(); offset += 4000) {
                report("streaming accept",
                       nh_streaming_diarizer_accept(streaming, audio.data() + offset, 4000, accept_frames, nullptr));
            }
            report("streaming flush", nh_streaming_diarizer_flush(streaming, accept_frames, nullptr));
            report("streaming reset", nh_streaming_diarizer_reset(streaming));
            report("streaming accept after reset",
                   nh_streaming_diarizer_accept(streaming, audio.data(), 4000, accept_frames, nullptr));
            nh_streaming_diarizer_stats stats = {sizeof(nh_streaming_diarizer_stats)};
            report("streaming stats", nh_streaming_diarizer_get_stats(streaming, &stats));
            nh_streaming_diarizer_destroy(streaming);
        }
    }

    if (const char* encoder = env_or("NH_ASR_ENCODER"); encoder) {
        const char* decoder = env_or("NH_ASR_DECODER");
        const char* tokens = env_or("NH_ASR_TOKENS");
        if (decoder && tokens) {
            nh_asr* asr = nullptr;
            report("asr whisper create", nh_asr_create_whisper(encoder, decoder, tokens, 2, &asr));
            if (asr) {
                report("asr decode",
                       nh_asr_decode(asr, audio.data(), static_cast<uint32_t>(audio.size()), accept_text, nullptr));
                nh_asr_destroy(asr);
            }
        }
    }

    if (!env_or("NH_VAD_MODEL") && !env_or("NH_SEGMENTATION_MODEL") && !env_or("NH_NEMOTRON_MODEL") &&
        !env_or("NH_ASR_ENCODER")) {
        std::printf("lifecycle-smoke: no pinned models present, nothing exercised\n");
    }
    return failures ? 1 : 0;
}
