#include "pipeline_storage.hpp"

#include "picosha2.h"

#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace nh::storage {
using Json = nlohmann::json;
PcmSpool::PcmSpool(const char* directory) {
    std::string pattern = std::string(directory) + "/nh-pcm-XXXXXX";
    std::vector<char> path(pattern.begin(), pattern.end());
    path.push_back(0);
    const int fd = mkstemp(path.data());
    if (fd < 0)
        throw std::runtime_error("Cannot create scratch PCM file");
    unlink(path.data());
    file_ = fdopen(fd, "w+b");
    if (!file_) {
        close(fd);
        throw std::runtime_error("Cannot open scratch PCM stream");
    }
}
PcmSpool::~PcmSpool() {
    if (file_)
        fclose(file_);
}
PcmMapping::PcmMapping(FILE* file, uint64_t frames) : size_(static_cast<size_t>(frames) * sizeof(float)) {
    data_ = mmap(nullptr, size_, PROT_READ, MAP_PRIVATE, fileno(file), 0);
    if (data_ == MAP_FAILED)
        throw std::runtime_error("Cannot map scratch PCM");
}
PcmMapping::~PcmMapping() {
    if (data_ != MAP_FAILED)
        munmap(data_, size_);
}
AsrCheckpoint::~AsrCheckpoint() {
    if (lock_fd_ >= 0)
        close(lock_fd_);
}
bool same_file(const char* a, const char* b) {
    if (!a || !b || !*a || !*b)
        return false;
    if (std::strcmp(a, b) == 0)
        return true;
    struct stat x{}, y{};
    return stat(a, &x) == 0 && stat(b, &y) == 0 && x.st_dev == y.st_dev && x.st_ino == y.st_ino;
}
void write_json(const char* path, const Json& value) {
    const std::string data = value.dump(2) + "\n";
    std::string pattern = std::string(path) + ".tmp-XXXXXX";
    std::vector<char> temporary(pattern.begin(), pattern.end());
    temporary.push_back(0);
    const int fd = mkstemp(temporary.data());
    if (fd < 0)
        throw std::runtime_error("Cannot create JSON output");
    FILE* out = fdopen(fd, "wb");
    if (!out) {
        close(fd);
        unlink(temporary.data());
        throw std::runtime_error("Cannot open JSON output");
    }
    const auto size = fwrite(data.data(), 1, data.size(), out);
    const bool flushed = fflush(out) == 0 && fsync(fd) == 0;
    const int status = fclose(out);
    if (size != data.size() || !flushed || status || rename(temporary.data(), path)) {
        unlink(temporary.data());
        throw std::runtime_error("Could not write complete JSON output");
    }
}
std::string file_hash(const char* path) {
    std::ifstream input(path, std::ios::binary);
    if (!input)
        throw std::runtime_error("Cannot read checkpoint identity input");
    const auto result =
        picosha2::hash256_hex_string(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
    if (input.bad())
        throw std::runtime_error("Checkpoint identity input read failed");
    return result;
}
void AsrCheckpoint::open(const char* directory, const std::string& pcm_hash, const nh_pipeline_config* config) {
    if (!directory || !*directory)
        return;
    Json identity{{"cache_format", 2},
                  {"decoded_pcm_sha256", pcm_hash},
                  {"asr_sha256", file_hash(config->asr_model)},
                  {"tokens_sha256", file_hash(config->tokens)},
                  {"chunk_seconds", config->chunk_seconds},
                  {"threads", config->threads},
                  {"sherpa", nh_sherpa_version()},
                  {"decoder", "miniaudio-0.11.23/lpf8/mono16k/greedy/tail-min1s/pad-short1s"},
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
    path_ = std::string(directory) + "/asr-" + picosha2::hash256_hex_string(identity.dump()) + ".json";
    const auto lock_path = path_ + ".lock";
    lock_fd_ = ::open(lock_path.c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (lock_fd_ < 0)
        throw std::runtime_error("Cannot open checkpoint lock");
    if (flock(lock_fd_, LOCK_EX | LOCK_NB)) {
        status_ = NH_BUSY;
        return;
    }
    struct stat existing{};
    if (stat(path_.c_str(), &existing) == 0 && existing.st_size > 64 * 1024 * 1024)
        throw std::runtime_error("Checkpoint exceeds 64-MiB metadata budget");
    std::ifstream previous(path_);
    if (previous) {
        previous >> data_;
        if (data_.value("identity", Json()) != identity || !data_.contains("asr") || !data_["asr"].is_array())
            throw std::runtime_error("Checkpoint identity/format invalid; preserved for inspection");
    } else
        data_ = {{"identity", identity}, {"asr", Json::array()}};
}
size_t AsrCheckpoint::size() const { return enabled() ? data_["asr"].size() : 0; }
Json AsrCheckpoint::cached(size_t index, uint64_t offset, size_t frames) const {
    const auto& chunk = data_["asr"].at(index);
    if (chunk.at("offset_frames") != offset || chunk.at("frames") != frames || !chunk.at("backend").is_object())
        throw std::runtime_error("Checkpoint chunk timeline invalid; preserved for inspection");
    return chunk.at("backend");
}
void AsrCheckpoint::append(const Json& chunk) {
    if (!enabled())
        return;
    data_["asr"].push_back(chunk);
    write_json(path_.c_str(), data_);
}
} // namespace nh::storage
