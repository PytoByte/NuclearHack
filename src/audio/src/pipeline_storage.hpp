#pragma once

#include "json.hpp"
#include "nuclear_audio.h"

#include <cstdint>
#include <cstdio>
#include <string>

namespace nh::storage {
class PcmSpool final {
  public:
    explicit PcmSpool(const char* directory);
    ~PcmSpool();
    PcmSpool(const PcmSpool&) = delete;
    PcmSpool& operator=(const PcmSpool&) = delete;
    FILE* file() const noexcept { return file_; }

  private:
    FILE* file_ = nullptr;
};

class PcmMapping final {
  public:
    PcmMapping(FILE* file, uint64_t frames);
    ~PcmMapping();
    PcmMapping(const PcmMapping&) = delete;
    PcmMapping& operator=(const PcmMapping&) = delete;
    const float* data() const noexcept { return static_cast<const float*>(data_); }

  private:
    void* data_;
    size_t size_;
};

bool same_file(const char* first, const char* second);
void write_json(const char* path, const nlohmann::json& value);

class AsrCheckpoint final {
  public:
    AsrCheckpoint() = default;
    ~AsrCheckpoint();
    AsrCheckpoint(const AsrCheckpoint&) = delete;
    AsrCheckpoint& operator=(const AsrCheckpoint&) = delete;
    void open(const char* directory, const std::string& pcm_hash, const nh_pipeline_config* config);
    nh_status status() const noexcept { return status_; }
    size_t size() const;
    nlohmann::json cached(size_t index, uint64_t offset, size_t frames) const;
    void append(const nlohmann::json& chunk);

  private:
    bool enabled() const noexcept { return !path_.empty(); }
    int lock_fd_ = -1;
    std::string path_;
    nlohmann::json data_;
    nh_status status_ = NH_OK;
};
} // namespace nh::storage
