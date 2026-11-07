#include "nuclear_audio.h"

#include <cstdint>
#include <jni.h>
#include <string>
#include <sys/resource.h>
#include <vector>

namespace {
std::string utf8(JNIEnv* env, jstring value) {
    if (!value)
        return {};
    jclass cls = env->GetObjectClass(value);
    jmethodID get = env->GetMethodID(cls, "getBytes", "(Ljava/lang/String;)[B");
    jstring encoding = env->NewStringUTF("UTF-8");
    auto bytes = static_cast<jbyteArray>(env->CallObjectMethod(value, get, encoding));
    const jsize size = env->GetArrayLength(bytes);
    std::string result(size, 0);
    env->GetByteArrayRegion(bytes, 0, size, reinterpret_cast<jbyte*>(result.data()));
    env->DeleteLocalRef(bytes);
    env->DeleteLocalRef(encoding);
    env->DeleteLocalRef(cls);
    return result;
}
struct Callback {
    JNIEnv* env;
    jclass type;
    jmethodID method;
};
int32_t progress(const char* stage, uint64_t done, uint64_t total, void* opaque) {
    auto& callback = *static_cast<Callback*>(opaque);
    jstring name = callback.env->NewStringUTF(stage);
    const jboolean cancel = callback.env->CallStaticBooleanMethod(callback.type, callback.method, name,
                                                                  static_cast<jlong>(done), static_cast<jlong>(total));
    callback.env->DeleteLocalRef(name);
    return cancel || callback.env->ExceptionCheck();
}
Callback make_callback(JNIEnv* env, jclass cls) {
    return {env, cls, env->GetStaticMethodID(cls, "onProgress", "(Ljava/lang/String;JJ)Z")};
}
struct Pcm {
    std::vector<float> samples;
    bool exceeded = false;
};
int32_t collect_pcm(const float* samples, uint32_t frames, uint64_t, void* opaque) {
    auto& pcm = *static_cast<Pcm*>(opaque);
    if (pcm.samples.size() + frames > 400000) {
        pcm.exceeded = true;
        return 1;
    }
    try {
        pcm.samples.insert(pcm.samples.end(), samples, samples + frames);
        return 0;
    } catch (...) {
        return 1;
    }
}
int32_t collect_json(const char*, const char* value, void* opaque) {
    try {
        *static_cast<std::string*>(opaque) = value;
        return 0;
    } catch (...) {
        return 1;
    }
}
jstring java_utf8(JNIEnv* env, const std::string& text) {
    jbyteArray bytes = env->NewByteArray(text.size());
    env->SetByteArrayRegion(bytes, 0, text.size(), reinterpret_cast<const jbyte*>(text.data()));
    jclass type = env->FindClass("java/lang/String");
    jmethodID constructor = env->GetMethodID(type, "<init>", "([BLjava/lang/String;)V");
    jstring encoding = env->NewStringUTF("UTF-8");
    auto result = static_cast<jstring>(env->NewObject(type, constructor, bytes, encoding));
    env->DeleteLocalRef(bytes);
    env->DeleteLocalRef(type);
    env->DeleteLocalRef(encoding);
    return result;
}
} // namespace
extern "C" JNIEXPORT jlong JNICALL Java_com_hexteam_audiohost_Native_asrCreate(JNIEnv* env, jclass, jstring directory,
                                                                               jstring kind, jstring model_file,
                                                                               jint threads, jstring method,
                                                                               jstring language, jstring hotwords) {
    const auto root = utf8(env, directory), family = utf8(env, kind), decoding = utf8(env, method),
               lang = utf8(env, language), hints = utf8(env, hotwords);
    const auto model = root + "/" + utf8(env, model_file);
    const auto decoder = root + (family == "whisper" ? "/base-decoder.int8.onnx" : "/decoder.onnx");
    const auto joiner = root + "/joiner.onnx",
               tokens = root + (family == "whisper" ? "/base-tokens.txt" : "/tokens.txt");
    nh_asr_config config{sizeof(nh_asr_config),
                         family.c_str(),
                         model.c_str(),
                         decoder.c_str(),
                         joiner.c_str(),
                         tokens.c_str(),
                         lang.c_str(),
                         decoding.c_str(),
                         hints.empty() ? nullptr : hints.c_str(),
                         static_cast<uint32_t>(threads),
                         4,
                         1.5f};
    nh_asr* handle = nullptr;
    if (nh_asr_create(&config, &handle) != NH_OK)
        return 0;
    return reinterpret_cast<intptr_t>(handle);
}
extern "C" JNIEXPORT jstring JNICALL Java_com_hexteam_audiohost_Native_asrDecode(JNIEnv* env, jclass, jlong pointer,
                                                                                 jstring input) {
    Pcm pcm;
    const auto path = utf8(env, input);
    if (nh_decode_file(path.c_str(), 16000, 16000, collect_pcm, &pcm) != NH_OK || pcm.exceeded)
        return nullptr;
    std::string result;
    if (nh_asr_decode(reinterpret_cast<nh_asr*>(static_cast<intptr_t>(pointer)), pcm.samples.data(), pcm.samples.size(),
                      collect_json, &result) != NH_OK)
        return nullptr;
    return java_utf8(env, result);
}
extern "C" JNIEXPORT void JNICALL Java_com_hexteam_audiohost_Native_asrDestroy(JNIEnv*, jclass, jlong pointer) {
    nh_asr_destroy(reinterpret_cast<nh_asr*>(static_cast<intptr_t>(pointer)));
}
extern "C" JNIEXPORT jint JNICALL Java_com_hexteam_audiohost_Native_transcribe(JNIEnv* env, jclass cls, jstring input,
                                                                               jstring output, jstring models,
                                                                               jstring scratch, jint threads,
                                                                               jfloat threshold, jint chunk) {
    const auto in = utf8(env, input), out = utf8(env, output), root = utf8(env, models), tmp = utf8(env, scratch);
    const auto asr = root + "/giga-v3-ctc/model.int8.onnx", tokens = root + "/giga-v3-ctc/tokens.txt";
    const auto segmentation = root + "/diarization/segmentation-model.onnx",
               embedding = root + "/diarization/embedding.onnx";
    const auto trace = out + ".trace.json";
    nh_pipeline_config config{};
    config.struct_size = sizeof(config);
    config.asr_model = asr.c_str();
    config.tokens = tokens.c_str();
    config.segmentation = segmentation.c_str();
    config.embedding = embedding.c_str();
    config.scratch_directory = tmp.c_str();
    config.output_json = out.c_str();
    config.trace_json = trace.c_str();
    config.threads = threads;
    config.cluster_threshold = threshold;
    config.chunk_seconds = chunk;
    config.max_audio_seconds = 600;
    auto callback = make_callback(env, cls);
    return nh_transcribe_file(in.c_str(), &config, progress, &callback);
}
extern "C" JNIEXPORT jint JNICALL Java_com_hexteam_audiohost_Native_transcribeJob(JNIEnv* env, jclass cls,
                                                                                  jstring input, jstring output,
                                                                                  jstring models, jstring scratch,
                                                                                  jobject options) {
    if (!options)
        return NH_INVALID_ARGUMENT;
    jclass type = env->GetObjectClass(options);
    auto integer = [&](const char* name) { return env->GetIntField(options, env->GetFieldID(type, name, "I")); };
    auto real = [&](const char* name) { return env->GetFloatField(options, env->GetFieldID(type, name, "F")); };
    auto string = [&](const char* name) {
        auto value =
            static_cast<jstring>(env->GetObjectField(options, env->GetFieldID(type, name, "Ljava/lang/String;")));
        auto result = utf8(env, value);
        if (value)
            env->DeleteLocalRef(value);
        return result;
    };
    const auto in = utf8(env, input), out = utf8(env, output), root = utf8(env, models), tmp = utf8(env, scratch);
    const auto asr = root + "/" + string("asrModel"), tokens = root + "/" + string("tokens"),
               seg = root + "/" + string("segmentation"), embedding = root + "/" + string("embedding"),
               checkpoint = string("checkpointDirectory"), trace = out + ".trace.json";
    nh_pipeline_config config{};
    config.struct_size = sizeof(config);
    config.asr_model = asr.c_str();
    config.tokens = tokens.c_str();
    config.segmentation = seg.c_str();
    config.embedding = embedding.c_str();
    config.scratch_directory = tmp.c_str();
    config.output_json = out.c_str();
    config.trace_json = trace.c_str();
    config.threads = integer("threads");
    config.chunk_seconds = integer("chunkSeconds");
    config.max_audio_seconds = integer("maxAudioSeconds");
    config.cluster_threshold = real("threshold");
    nh_pipeline_options tuning{sizeof(nh_pipeline_options),
                               real("minOn"),
                               real("minOff"),
                               static_cast<uint32_t>(integer("attributionMode")),
                               checkpoint.empty() ? nullptr : checkpoint.c_str(),
                               real("windowShiftRatio")};
    nh_speaker_refinement_config refinement{sizeof(nh_speaker_refinement_config), real("refinementThreshold"), 128};
    env->DeleteLocalRef(type);
    auto callback = make_callback(env, cls);
    return refinement.cluster_threshold != 0
               ? nh_transcribe_file_with_refinement(in.c_str(), &config, &tuning, &refinement, progress, &callback)
               : nh_transcribe_file_with_options(in.c_str(), &config, &tuning, progress, &callback);
}
extern "C" JNIEXPORT jint JNICALL Java_com_hexteam_audiohost_Native_summarize(JNIEnv* env, jclass cls, jstring input,
                                                                              jstring model, jstring output,
                                                                              jint threads) {
    const auto in = utf8(env, input), path = utf8(env, model), out = utf8(env, output);
    nh_llm_config config{};
    config.struct_size = sizeof(config);
    config.model = path.c_str();
    config.output_text = out.c_str();
    config.threads = threads;
    config.context_tokens = 4096;
    config.max_output_tokens = 256;
    auto callback = make_callback(env, cls);
    return nh_summarize_file(in.c_str(), &config, progress, &callback);
}
extern "C" JNIEXPORT jstring JNICALL Java_com_hexteam_audiohost_Native_lastError(JNIEnv* env, jclass) {
    return env->NewStringUTF(nh_last_error());
}
extern "C" JNIEXPORT jint JNICALL Java_com_hexteam_audiohost_Native_llmAvailable(JNIEnv*, jclass) {
    return nh_llm_available();
}
extern "C" JNIEXPORT jlong JNICALL Java_com_hexteam_audiohost_Native_peakRssKib(JNIEnv*, jclass) {
    struct rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    return usage.ru_maxrss;
}
