#include "nuclear_audio.h"
#include <jni.h>
#include <string>
#include <sys/resource.h>

namespace {
std::string utf8(JNIEnv *env, jstring value) {
  if (!value) return {};
  jclass cls = env->GetObjectClass(value);
  jmethodID get = env->GetMethodID(cls, "getBytes", "(Ljava/lang/String;)[B");
  jstring encoding = env->NewStringUTF("UTF-8");
  auto bytes = static_cast<jbyteArray>(env->CallObjectMethod(value, get, encoding));
  const jsize size = env->GetArrayLength(bytes);
  std::string result(size, 0);
  env->GetByteArrayRegion(bytes, 0, size, reinterpret_cast<jbyte *>(result.data()));
  env->DeleteLocalRef(bytes); env->DeleteLocalRef(encoding); env->DeleteLocalRef(cls);
  return result;
}
struct Callback { JNIEnv *env; jclass type; jmethodID method; };
int32_t progress(const char *stage, uint64_t done, uint64_t total, void *opaque) {
  auto &callback = *static_cast<Callback *>(opaque);
  jstring name = callback.env->NewStringUTF(stage);
  const jboolean cancel = callback.env->CallStaticBooleanMethod(callback.type, callback.method, name,
      static_cast<jlong>(done), static_cast<jlong>(total));
  callback.env->DeleteLocalRef(name);
  return cancel || callback.env->ExceptionCheck();
}
Callback make_callback(JNIEnv *env, jclass cls) {
  return {env, cls, env->GetStaticMethodID(cls, "onProgress", "(Ljava/lang/String;JJ)Z")};
}
}
extern "C" JNIEXPORT jint JNICALL Java_com_hexteam_audiohost_Native_transcribe(
    JNIEnv *env, jclass cls, jstring input, jstring output, jstring models, jstring scratch,
    jint threads, jfloat threshold, jint chunk) {
  const auto in = utf8(env, input), out = utf8(env, output), root = utf8(env, models), tmp = utf8(env, scratch);
  const auto asr = root + "/giga-v3-ctc/model.int8.onnx", tokens = root + "/giga-v3-ctc/tokens.txt";
  const auto segmentation = root + "/diarization/segmentation-model.onnx", embedding = root + "/diarization/embedding.onnx";
  const auto trace = out + ".trace.json";
  nh_pipeline_config config{};
  config.struct_size = sizeof(config); config.asr_model = asr.c_str(); config.tokens = tokens.c_str();
  config.segmentation = segmentation.c_str(); config.embedding = embedding.c_str();
  config.scratch_directory = tmp.c_str(); config.output_json = out.c_str(); config.trace_json = trace.c_str();
  config.threads = threads; config.cluster_threshold = threshold; config.chunk_seconds = chunk; config.max_audio_seconds = 600;
  auto callback = make_callback(env, cls);
  return nh_transcribe_file(in.c_str(), &config, progress, &callback);
}
extern "C" JNIEXPORT jint JNICALL Java_com_hexteam_audiohost_Native_summarize(
    JNIEnv *env, jclass cls, jstring input, jstring model, jstring output, jint threads) {
  const auto in = utf8(env, input), path = utf8(env, model), out = utf8(env, output);
  nh_llm_config config{};
  config.struct_size = sizeof(config); config.model = path.c_str(); config.output_text = out.c_str();
  config.threads = threads; config.context_tokens = 4096; config.max_output_tokens = 256;
  auto callback = make_callback(env, cls);
  return nh_summarize_file(in.c_str(), &config, progress, &callback);
}
extern "C" JNIEXPORT jstring JNICALL Java_com_hexteam_audiohost_Native_lastError(JNIEnv *env, jclass) {
  return env->NewStringUTF(nh_last_error());
}
extern "C" JNIEXPORT jint JNICALL Java_com_hexteam_audiohost_Native_llmAvailable(JNIEnv *, jclass) {
  return nh_llm_available();
}
extern "C" JNIEXPORT jlong JNICALL Java_com_hexteam_audiohost_Native_peakRssKib(JNIEnv *, jclass) {
  struct rusage usage{}; getrusage(RUSAGE_SELF, &usage); return usage.ru_maxrss;
}
