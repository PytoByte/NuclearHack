#include "mel.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <stdexcept>

namespace nh {
namespace {
constexpr double pi = 3.141592653589793238462643383279502884;
}

MelFrontend::MelFrontend() {
    for (unsigned i = 0; i != 400; ++i) {
        const float phase = static_cast<float>(i) * static_cast<float>(2 * pi / 399);
        window_[i + 56] = .5f - .5f * std::cos(phase);
    }
    for (unsigned i = 0; i != 256; ++i) {
        const double phase = -2 * pi * i / 512;
        twiddles_[i] = {static_cast<float>(std::cos(phase)), static_cast<float>(std::sin(phase))};
    }
    for (unsigned i = 0; i != 512; ++i) {
        unsigned source = i, target = 0;
        for (unsigned bit = 0; bit != 9; ++bit) {
            target = (target << 1) | (source & 1);
            source >>= 1;
        }
        reversed_[i] = static_cast<uint16_t>(target);
    }
    const double log_step = std::log(6.4) / 27;
    const double maximum = 15 + std::log(8.0) / log_step;
    std::array<double, 130> hz{};
    for (unsigned i = 0; i != hz.size(); ++i) {
        const double mel = i == 129 ? maximum : i * (maximum / 129);
        hz[i] = mel < 15 ? mel * (200.0 / 3) : 1000 * std::exp((mel - 15) * log_step);
    }
    for (unsigned mel = 0; mel != 128; ++mel) {
        const double scale = 2 / (hz[mel + 2] - hz[mel]);
        for (unsigned bin = 0; bin != 257; ++bin) {
            const double frequency = bin * (16000.0 / 512);
            const double lower = (frequency - hz[mel]) / (hz[mel + 1] - hz[mel]);
            const double upper = (hz[mel + 2] - frequency) / (hz[mel + 2] - hz[mel + 1]);
            // librosa stores the float32 triangle before applying Slaney normalization.
            const float triangle = static_cast<float>(std::max(0.0, std::min(lower, upper)));
            const float value = static_cast<float>(triangle * scale);
            if (value > 0)
                filters_[mel].push_back({static_cast<uint16_t>(bin), value});
        }
    }
}

void MelFrontend::extract(const std::vector<float>& pcm, uint64_t base_sample, uint64_t total_samples,
                          uint64_t first_mel_frame, uint32_t frames, std::vector<float>& output) const {
    if (frames > 3040 || total_samples < base_sample || pcm.size() != total_samples - base_sample ||
        first_mel_frame > 360000 || first_mel_frame + frames > 363040)
        throw std::invalid_argument("Invalid bounded frontend window");
    output.resize(static_cast<size_t>(frames) * 128);
    const auto raw = [&](int64_t sample) -> float {
        if (sample < 0 || static_cast<uint64_t>(sample) >= total_samples)
            return 0;
        if (static_cast<uint64_t>(sample) < base_sample)
            throw std::logic_error("Frontend history was discarded");
        return pcm[static_cast<uint64_t>(sample) - base_sample];
    };
    constexpr float guard = 0x1p-24f;
    for (uint32_t frame = 0; frame < frames; ++frame) {
        const int64_t center = static_cast<int64_t>(first_mel_frame + frame) * 160;
        std::array<std::complex<float>, 512> spectrum{};
        bool nonzero = false;
        for (unsigned i = 56; i != 456; ++i) {
            if (window_[i] == 0)
                continue;
            const int64_t index = center - 256 + i;
            // Preemphasis precedes STFT zero padding: no artificial impulse at EOF.
            float value = 0;
            if (index >= 0 && static_cast<uint64_t>(index) < total_samples) {
                value = raw(index);
                if (index > 0)
                    value -= .97f * raw(index - 1);
                value *= window_[i];
            }
            nonzero |= value != 0;
            spectrum[reversed_[i]] = {value, 0};
        }
        if (!nonzero) {
            std::fill_n(output.begin() + static_cast<size_t>(frame) * 128, 128, std::log(guard));
            continue;
        }
        for (unsigned length = 2; length <= 512; length <<= 1) {
            const unsigned half = length / 2, stride = 512 / length;
            for (unsigned start = 0; start != 512; start += length) {
                for (unsigned i = 0; i != half; ++i) {
                    const auto even = spectrum[start + i];
                    const auto odd = spectrum[start + i + half] * twiddles_[i * stride];
                    spectrum[start + i] = even + odd;
                    spectrum[start + i + half] = even - odd;
                }
            }
        }
        std::array<float, 257> power{};
        for (unsigned bin = 0; bin != power.size(); ++bin)
            power[bin] = std::norm(spectrum[bin]);
        for (unsigned mel = 0; mel != 128; ++mel) {
            float value =
                std::accumulate(filters_[mel].begin(), filters_[mel].end(), 0.0f,
                                [&](float acc, const auto& weight) { return acc + weight.value * power[weight.bin]; });
            value = std::log(value + guard);
            if (!std::isfinite(value))
                throw std::runtime_error("Non-finite log-mel feature");
            output[static_cast<size_t>(frame) * 128 + mel] = value;
        }
    }
}
} // namespace nh
