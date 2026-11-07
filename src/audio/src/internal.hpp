#pragma once
#include "nuclear_audio.h"
#include <exception>
#include <atomic>
#include <string>
namespace nh {
extern thread_local std::string error;
extern std::atomic_flag heavy_job_busy;
class BusyGuard {
  std::atomic_flag &flag;
  bool acquired;
 public:
  explicit BusyGuard(std::atomic_flag &value) noexcept : flag(value), acquired(!flag.test_and_set(std::memory_order_acquire)) {}
  ~BusyGuard() { if (acquired) flag.clear(std::memory_order_release); }
  BusyGuard(const BusyGuard &)=delete;
  BusyGuard &operator=(const BusyGuard &)=delete;
  bool owns_lock() const noexcept { return acquired; }
};
inline nh_status fail(nh_status code, const char *message) {
  error = message;
  return code;
}
template <class F> nh_status guard(F &&operation) noexcept {
  try {
    error.clear();
    return operation();
  } catch (const std::exception &e) {
    return fail(NH_RUNTIME_ERROR, e.what());
  } catch (...) {
    return fail(NH_RUNTIME_ERROR, "Unknown native exception");
  }
}
}
