#include "clustering.hpp"
#include "internal.hpp"
#include "pipeline.hpp"
#include "sherpa-onnx/c-api/c-api.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <memory>
#include <set>
#include <vector>

namespace nh {
nh_status refine_speakers(const float* pcm, uint32_t frames, std::vector<Turn>& turns, const char* model,
                          uint32_t threads, const nh_speaker_refinement_config& config, nh_progress_callback progress,
                          void* user, RefinementStats& stats) {
    if (turns.size() > 65536)
        return fail(NH_INVALID_ARGUMENT, "Speaker refinement turn budget exceeded");
    std::map<int32_t, size_t> index;
    std::vector<std::vector<Turn>> groups;
    const size_t cap = config.max_clusters ? config.max_clusters : 128;
    for (const auto& t : turns) {
        // The upstream final segmentation frame may extend past EOF; PCM reads below are clipped.
        if (t.speaker < 0 || t.start_ms < 0 || t.end_ms <= t.start_ms)
            return fail(NH_INVALID_ARGUMENT, "Speaker refinement timeline is invalid");
        if (!index.count(t.speaker)) {
            if (groups.size() == cap)
                return fail(NH_INVALID_ARGUMENT, "Speaker refinement cluster budget exceeded; no silent fallback");
            index[t.speaker] = groups.size();
            groups.emplace_back();
        }
        groups[index.at(t.speaker)].push_back(t);
    }
    const size_t n = groups.size();
    stats.initial_clusters = n;
    stats.final_clusters = n;
    if (n < 2)
        return NH_OK;
    auto emit = [&](const char* stage, size_t done) {
        return progress && progress(stage, frames * static_cast<uint64_t>(done) / n, frames, user);
    };
    if (emit("speaker_refine_load", 0))
        return fail(NH_CANCELLED, "Cancelled before speaker refinement load");
    SherpaOnnxSpeakerEmbeddingExtractorConfig native{};
    native.model = model;
    native.num_threads = threads;
    native.provider = "cpu";
    using Extractor = std::unique_ptr<const SherpaOnnxSpeakerEmbeddingExtractor,
                                      decltype(&SherpaOnnxDestroySpeakerEmbeddingExtractor)>;
    Extractor extractor(SherpaOnnxCreateSpeakerEmbeddingExtractor(&native), SherpaOnnxDestroySpeakerEmbeddingExtractor);
    if (!extractor)
        return fail(NH_RUNTIME_ERROR, "Cannot load speaker refinement embedding");
    const int32_t dim = SherpaOnnxSpeakerEmbeddingExtractorDim(extractor.get());
    if (dim < 1 || dim > 4096)
        return fail(NH_RUNTIME_ERROR, "Unexpected speaker embedding dimension");
    std::vector<std::vector<float>> vectors(n);
    std::vector<float> samples;
    samples.reserve(320000);
    for (size_t i = 0; i < n; ++i) {
        if (emit("speaker_refine", i))
            return fail(NH_CANCELLED, "Cancelled between speaker refinement clusters");
        auto selected = groups[i];
        std::stable_sort(selected.begin(), selected.end(),
                         [](const Turn& a, const Turn& b) { return a.end_ms - a.start_ms > b.end_ms - b.start_ms; });
        samples.clear();
        size_t used = 0;
        for (const auto& t : selected) {
            if (used == 3 || samples.size() == 320000)
                break;
            if (t.end_ms - t.start_ms < 800)
                continue;
            const auto width = std::min<int64_t>(8000, t.end_ms - t.start_ms);
            const auto left = t.start_ms + (t.end_ms - t.start_ms - width) / 2;
            const auto begin = std::min<uint64_t>(frames, static_cast<uint64_t>(left) * 16);
            const auto end = std::min<uint64_t>(frames, static_cast<uint64_t>(left + width) * 16);
            const auto count = std::min<uint64_t>(end - begin, 320000 - samples.size());
            samples.insert(samples.end(), pcm + begin, pcm + begin + count);
            ++used;
        }
        if (samples.size() < 32000)
            continue; // Explicit minimum evidence; keep this cluster separate.
        using Stream = std::unique_ptr<const SherpaOnnxOnlineStream, decltype(&SherpaOnnxDestroyOnlineStream)>;
        Stream stream(SherpaOnnxSpeakerEmbeddingExtractorCreateStream(extractor.get()), SherpaOnnxDestroyOnlineStream);
        if (!stream)
            return fail(NH_RUNTIME_ERROR, "Cannot allocate speaker embedding stream");
        SherpaOnnxOnlineStreamAcceptWaveform(stream.get(), 16000, samples.data(), samples.size());
        SherpaOnnxOnlineStreamInputFinished(stream.get());
        if (!SherpaOnnxSpeakerEmbeddingExtractorIsReady(extractor.get(), stream.get()))
            continue;
        using Embedding = std::unique_ptr<const float, decltype(&SherpaOnnxSpeakerEmbeddingExtractorDestroyEmbedding)>;
        Embedding value(SherpaOnnxSpeakerEmbeddingExtractorComputeEmbedding(extractor.get(), stream.get()),
                        SherpaOnnxSpeakerEmbeddingExtractorDestroyEmbedding);
        if (!value)
            return fail(NH_RUNTIME_ERROR, "Cannot compute speaker refinement embedding");
        float norm = 0;
        for (int32_t j = 0; j < dim; ++j) {
            if (!std::isfinite(value.get()[j]))
                return fail(NH_RUNTIME_ERROR, "Nonfinite speaker embedding");
            norm += value.get()[j] * value.get()[j];
        }
        norm = std::sqrt(norm);
        if (norm < 1e-8f)
            continue;
        vectors[i].assign(static_cast<const float*>(value.get()), static_cast<const float*>(value.get()) + dim);
        std::transform(vectors[i].begin(), vectors[i].end(), vectors[i].begin(), [norm](float v) { return v / norm; });
        ++stats.embedding_clusters;
    }
    extractor.reset(); // Release model before clustering and export.
    if (emit("speaker_cluster", n))
        return fail(NH_CANCELLED, "Cancelled before speaker clustering");
    std::vector<std::vector<Turn>> intervals = groups;
    for (auto& spans : intervals) {
        std::stable_sort(spans.begin(), spans.end(),
                         [](const Turn& a, const Turn& b) { return a.start_ms < b.start_ms; });
        std::vector<Turn> merged;
        for (const auto& t : spans) {
            if (!merged.empty() && t.start_ms <= merged.back().end_ms)
                merged.back().end_ms = std::max(merged.back().end_ms, t.end_ms);
            else
                merged.push_back(t);
        }
        spans = std::move(merged);
    }
    std::vector<float> distances(n * n, 2);
    for (size_t i = 0; i < n; ++i) {
        distances[i * n + i] = 0;
        for (size_t j = 0; j < i; ++j) {
            size_t a = 0, b = 0;
            bool simultaneous = false;
            while (a < intervals[i].size() && b < intervals[j].size()) {
                const auto &x = intervals[i][a], &y = intervals[j][b];
                if (std::min(x.end_ms, y.end_ms) > std::max(x.start_ms, y.start_ms)) {
                    simultaneous = true;
                    break;
                }
                if (x.end_ms <= y.end_ms)
                    ++a;
                else
                    ++b;
            }
            if (simultaneous || vectors[i].empty() || vectors[j].empty())
                continue;
            float cosine = 0;
            for (int32_t k = 0; k < dim; ++k)
                cosine += vectors[i][k] * vectors[j][k];
            distances[i * n + j] = distances[j * n + i] = std::clamp(1 - cosine, 0.0f, 2.0f);
        }
    }
    const auto labels = complete_link(std::move(distances), n, config.cluster_threshold);
    std::set<size_t> unique(labels.begin(), labels.end());
    stats.final_clusters = unique.size();
    for (auto& t : turns)
        t.speaker = static_cast<int32_t>(labels[index.at(t.speaker)]);
    return NH_OK;
}
} // namespace nh
