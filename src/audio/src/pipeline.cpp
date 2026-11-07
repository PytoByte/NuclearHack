#include "file_transcriber.hpp"
#include "internal.hpp"

extern "C" nh_status nh_transcribe(const char *input, const nh_transcription_config *options,
                                   nh_progress_callback progress, void *user) {
  return nh::guard([&]() -> nh_status {
    if (!options || options->struct_size != sizeof(*options) || options->threads > 16 ||
        options->max_audio_seconds > 600)
      return nh::fail(NH_INVALID_ARGUMENT, "Invalid final transcription configuration");
    nh_pipeline_config pipeline{};
    pipeline.struct_size = sizeof(pipeline);
    pipeline.asr_model = options->asr_model;
    pipeline.tokens = options->tokens;
    pipeline.scratch_directory = options->scratch_directory;
    pipeline.output_json = options->output_json;
    pipeline.trace_json = options->trace_json;
    pipeline.threads = options->threads ? options->threads : 4;
    pipeline.chunk_seconds = 20;
    pipeline.max_audio_seconds = options->max_audio_seconds ? options->max_audio_seconds : 600;
    nh_pipeline_options checkpoint{};
    checkpoint.struct_size = sizeof(checkpoint);
    checkpoint.checkpoint_directory = options->checkpoint_directory;
    nh_streaming_diarizer_config speaker{sizeof(speaker), options->speaker_model, pipeline.threads,
                                         1, 0};
    return nh_transcribe_file_with_streaming_diarizer(input, &pipeline, &checkpoint, &speaker,
                                                      progress, user);
  });
}

extern "C" nh_status nh_transcribe_file(const char *input, const nh_pipeline_config *config,
                                        nh_progress_callback progress, void *user) {
  return nh_transcribe_file_with_options(input, config, nullptr, progress, user);
}
extern "C" nh_status nh_transcribe_file_with_options(const char *input,
                                                     const nh_pipeline_config *config,
                                                     const nh_pipeline_options *options,
                                                     nh_progress_callback progress, void *user) {
  return nh_transcribe_file_with_refinement(input, config, options, nullptr, progress, user);
}
static nh_status transcribe_file(const char *input, const nh_pipeline_config *config,
                                 const nh_pipeline_options *options,
                                 const nh_speaker_refinement_config *refinement,
                                 const nh_streaming_diarizer_config *speaker,
                                 nh_progress_callback progress, void *user);
extern "C" nh_status nh_transcribe_file_with_refinement(
    const char *input, const nh_pipeline_config *config, const nh_pipeline_options *options,
    const nh_speaker_refinement_config *refinement, nh_progress_callback progress, void *user) {
  return transcribe_file(input, config, options, refinement, nullptr, progress, user);
}
extern "C" nh_status nh_transcribe_file_with_streaming_diarizer(
    const char *input, const nh_pipeline_config *config, const nh_pipeline_options *options,
    const nh_streaming_diarizer_config *speaker, nh_progress_callback progress, void *user) {
  return nh::guard([&]() -> nh_status {
    if (!speaker)
      return nh::fail(NH_INVALID_ARGUMENT, "Speaker streaming configuration is required");
    return transcribe_file(input, config, options, nullptr, speaker, progress, user);
  });
}
static nh_status transcribe_file(const char *input, const nh_pipeline_config *config,
                                 const nh_pipeline_options *options,
                                 const nh_speaker_refinement_config *refinement,
                                 const nh_streaming_diarizer_config *speaker,
                                 nh_progress_callback progress, void *user) {
  return nh::guard([&]() -> nh_status {
    nh::FileTranscriber transcriber({input, config, options, refinement, speaker, progress, user},
                                    nh::make_native_pipeline_factory());
    return transcriber.run();
  });
}
