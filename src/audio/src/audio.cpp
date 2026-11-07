#include "internal.hpp"
#define MA_NO_DEVICE_IO
#define MA_NO_ENGINE
#define MA_NO_RESOURCE_MANAGER
#define MA_NO_NODE_GRAPH
#define MA_NO_GENERATION
#define MA_NO_ENCODING
#include "miniaudio.h"

#include <cstdio>
#include <cstring>
#include <memory>
#include <vector>

namespace nh {
thread_local std::string error;
std::atomic_flag heavy_job_busy = ATOMIC_FLAG_INIT;
} // namespace nh
extern "C" {
uint32_t nh_abi_version(void) { return 1; }
const char* nh_last_error(void) { return nh::error.c_str(); }
nh_status nh_decode_file(const char* path, uint32_t sample_rate, uint32_t block_frames, nh_pcm_callback callback,
                         void* user) {
    return nh::guard([&]() -> nh_status {
        if (!path || !*path || !callback || sample_rate < 8000 || sample_rate > 192000 || block_frames == 0 ||
            block_frames > 1920000)
            return nh::fail(NH_INVALID_ARGUMENT, "Invalid decoder path/rate/block/callback");
        auto decoder = std::make_unique<ma_decoder>();
        auto config = ma_decoder_config_init(ma_format_f32, 1, sample_rate);
        config.resampling.linear.lpfOrder = 8;
        // Filename hints can make the MP3 backend mistake PCM sync bytes for MPEG.
        // A strong WAVE container header takes precedence over any suffix.
        const auto close_file = [](FILE* file) { std::fclose(file); };
        std::unique_ptr<FILE, decltype(close_file)> header_file(std::fopen(path, "rb"), close_file);
        if (!header_file)
            return nh::fail(NH_IO_ERROR, "Cannot open local audio header");
        unsigned char header[12]{};
        const size_t header_size = std::fread(header, 1, sizeof(header), header_file.get());
        if (std::ferror(header_file.get()))
            return nh::fail(NH_IO_ERROR, "Cannot read local audio header");
        header_file.reset();
        if (header_size == sizeof(header) && std::memcmp(header + 8, "WAVE", 4) == 0 &&
            (std::memcmp(header, "RIFF", 4) == 0 || std::memcmp(header, "RF64", 4) == 0))
            config.encodingFormat = ma_encoding_format_wav;
        if (ma_decoder_init_file(path, &config, decoder.get()) != MA_SUCCESS)
            return nh::fail(NH_IO_ERROR, "Cannot open/decode local audio");
        struct Cleanup {
            ma_decoder* d;
            ~Cleanup() { ma_decoder_uninit(d); }
        } cleanup{decoder.get()};
        std::vector<float> samples(block_frames);
        uint64_t offset = 0;
        while (true) {
            ma_uint64 count = 0;
            const auto result = ma_decoder_read_pcm_frames(decoder.get(), samples.data(), block_frames, &count);
            if (result != MA_SUCCESS && result != MA_AT_END)
                return nh::fail(NH_IO_ERROR, "Audio decode failed mid-stream");
            if (count && callback(samples.data(), static_cast<uint32_t>(count), offset, user))
                return nh::fail(NH_CANCELLED, "Decoder cancelled by caller");
            offset += count;
            if (result == MA_AT_END || count == 0)
                break;
        }
        return NH_OK;
    });
}
}
