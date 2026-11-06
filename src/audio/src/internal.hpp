#pragma once
#include "nuclear_audio.h"
#include <exception>
#include <string>
namespace nh {
extern thread_local std::string error;
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
