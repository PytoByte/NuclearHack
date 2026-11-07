#include "nuclear_audio.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "Failed: %s\n", #x); return 1; } } while (0)
static void u32(FILE *f, uint32_t x) {
  unsigned char b[4] = {x & 255, (x >> 8) & 255, (x >> 16) & 255, (x >> 24) & 255};
  fwrite(b, 1, 4, f);
}
static int32_t collect(const float *samples, uint32_t frames, uint64_t offset, void *user) {
  uint64_t *total = (uint64_t *)user;
  if (!samples || frames > 128 || offset != *total) return 1;
  *total += frames;
  return 0;
}
static int32_t cancel(const float *samples, uint32_t frames, uint64_t offset, void *user) {
  (void)samples; (void)frames; (void)offset; (void)user;
  return 1;
}
static int32_t cancel_stage(const char *stage, uint64_t done, uint64_t total, void *user) {
  (void)done; (void)total; (void)user;
  return strcmp(stage, "queued") == 0;
}
struct reentry { const nh_pipeline_config *config; nh_status status; };
static int32_t nested_file(const char *stage, uint64_t done, uint64_t total, void *user) {
  (void)stage; (void)done; (void)total;
  struct reentry *state = (struct reentry *)user;
  state->status = nh_transcribe_file("c-abi-fixture.wav", state->config, NULL, NULL);
  return 1;
}
int main(void) {
  CHECK(nh_abi_version() == 1);
  CHECK(strlen(nh_sherpa_version()) > 0);
  CHECK(nh_decode_file(NULL, 16000, 16000, NULL, NULL) == NH_INVALID_ARGUMENT);
  CHECK(strlen(nh_last_error()) > 0);
  nh_asr *asr = NULL;
  nh_asr_config options = {0};
  CHECK(nh_asr_create(&options, &asr) == NH_INVALID_ARGUMENT);
  options.struct_size = sizeof(options); options.family = "ctc";
  options.threads = 2; options.decoding_method = "modified_beam_search"; options.max_active_paths = 4;
  CHECK(nh_asr_create(&options, &asr) == NH_INVALID_ARGUMENT);
  options.family = "transducer";
  CHECK(nh_asr_create(&options, &asr) == NH_IO_ERROR);
  CHECK(nh_asr_create_ctc("missing.onnx", "missing.txt", 2, &asr) == NH_IO_ERROR);
  CHECK(asr == NULL);
  CHECK(nh_asr_create_ctc("missing", "missing", 0, &asr) == NH_INVALID_ARGUMENT);
  CHECK(nh_asr_create_transducer("missing", "missing", "missing", "missing", 2, &asr) == NH_IO_ERROR);
  CHECK(nh_asr_create_whisper("missing", "missing", "missing", 2, &asr) == NH_IO_ERROR);
  CHECK(nh_asr_decode(NULL, NULL, 0, NULL, NULL) == NH_INVALID_ARGUMENT);
  nh_asr_destroy(NULL);
  nh_diarizer *diarizer = NULL;
  nh_diarizer_config diar_options = {sizeof(nh_diarizer_config), "missing", "missing", 2, 0.8f, 0.3f, 0.5f, 0};
  CHECK(nh_diarizer_create_config(&diar_options, &diarizer) == NH_INVALID_ARGUMENT);
  diar_options.oracle_speakers = -1;
  CHECK(nh_diarizer_create_config(&diar_options, &diarizer) == NH_IO_ERROR);
  CHECK(nh_diarizer_create_with_window(&diar_options, 0.01f, &diarizer) == NH_INVALID_ARGUMENT);
  CHECK(nh_diarizer_create("missing", "missing", 2, 0.5f, &diarizer) == NH_IO_ERROR);
  CHECK(nh_diarizer_create("missing", "missing", 2, 1.2f, &diarizer) == NH_IO_ERROR);
  CHECK(nh_diarizer_create("missing", "missing", 2, 2.1f, &diarizer) == NH_INVALID_ARGUMENT);
  CHECK(diarizer == NULL);
  CHECK(nh_diarizer_process(NULL, NULL, 0, NULL, NULL) == NH_INVALID_ARGUMENT);
  nh_diarizer_destroy(NULL);
  FILE *fixture = fopen("c-abi-fixture.wav", "wb");
  CHECK(fixture != NULL);
  fwrite("RIFF", 1, 4, fixture); u32(fixture, 96036);
  fwrite("WAVEfmt ", 1, 8, fixture); u32(fixture, 16);
  fwrite("\1\0\1\0", 1, 4, fixture); u32(fixture, 48000); u32(fixture, 96000);
  fwrite("\2\0\20\0data", 1, 8, fixture); u32(fixture, 96000);
  for (int i = 0; i < 96000; ++i) fputc(0, fixture);
  fclose(fixture);
  uint64_t total = 0;
  CHECK(nh_decode_file("c-abi-fixture.wav", 16000, 128, collect, &total) == NH_OK);
  CHECK(total >= 15998 && total <= 16002);
  CHECK(nh_decode_file("c-abi-fixture.wav", 16000, 128, cancel, NULL) == NH_CANCELLED);
  nh_pipeline_config pipeline = {0};
  CHECK(nh_transcribe_file("c-abi-fixture.wav", &pipeline, NULL, NULL) == NH_INVALID_ARGUMENT);
  pipeline.struct_size = sizeof(pipeline);
  pipeline.asr_model = pipeline.tokens = pipeline.segmentation = pipeline.embedding = "missing";
  pipeline.scratch_directory = "."; pipeline.output_json = "c-abi-result.json";
  pipeline.threads = 1; pipeline.chunk_seconds = 20; pipeline.max_audio_seconds = 600;
  pipeline.cluster_threshold = 0.8f;
  CHECK(nh_transcribe_file("c-abi-fixture.wav", &pipeline, cancel_stage, NULL) == NH_CANCELLED);
  struct reentry reentry = {&pipeline, NH_OK};
  CHECK(nh_transcribe_file("c-abi-fixture.wav", &pipeline, nested_file, &reentry) == NH_CANCELLED);
  CHECK(reentry.status == NH_BUSY);
  CHECK(fopen("c-abi-result.json", "rb") == NULL);
  pipeline.output_json = "c-abi-fixture.wav";
  CHECK(nh_transcribe_file("c-abi-fixture.wav", &pipeline, NULL, NULL) == NH_INVALID_ARGUMENT);
  nh_llm_config llm = {0};
  CHECK(nh_summarize_file("c-abi-fixture.wav", &llm, NULL, NULL) == NH_INVALID_ARGUMENT);
  nh_pipeline_options tuning = {sizeof(nh_pipeline_options), 0.1f, 0.2f, 2};
  CHECK(nh_transcribe_file_with_options("c-abi-fixture.wav", &pipeline, &tuning, NULL, NULL) == NH_INVALID_ARGUMENT);
  pipeline.output_json = "c-abi-result.json";
  nh_speaker_refinement_config refinement = {sizeof(nh_speaker_refinement_config),2.0f,128};
  CHECK(nh_transcribe_file_with_refinement("c-abi-fixture.wav",&pipeline,NULL,&refinement,NULL,NULL)==NH_INVALID_ARGUMENT);
  refinement.cluster_threshold=.4f;refinement.max_clusters=257;
  CHECK(nh_transcribe_file_with_refinement("c-abi-fixture.wav",&pipeline,NULL,&refinement,NULL,NULL)==NH_INVALID_ARGUMENT);
  nh_vad *vad = NULL;
  nh_vad_config vad_config = {sizeof(nh_vad_config), "missing", 1, 0.5f, 0.3f, 0.1f, 20};
  CHECK(nh_vad_create(&vad_config, &vad) == NH_IO_ERROR && vad == NULL);
  vad_config.threshold = 1.0f;
  CHECK(nh_vad_create(&vad_config, &vad) == NH_INVALID_ARGUMENT && vad == NULL);
  CHECK(nh_vad_accept(NULL, NULL, 0, NULL, NULL) == NH_INVALID_ARGUMENT);
  CHECK(nh_vad_flush(NULL, NULL, NULL) == NH_INVALID_ARGUMENT);
  nh_vad_destroy(NULL);
  CHECK(nh_onnxruntime_version() != NULL && strlen(nh_onnxruntime_version()) > 0);
  nh_streaming_diarizer *streaming = NULL;
  nh_streaming_diarizer_config streaming_config = {sizeof(nh_streaming_diarizer_config), "missing", 1, 0, 600};
  CHECK(nh_streaming_diarizer_create(&streaming_config, &streaming) == NH_IO_ERROR && streaming == NULL);
  streaming_config.profile = 2;
  CHECK(nh_streaming_diarizer_create(&streaming_config, &streaming) == NH_INVALID_ARGUMENT && streaming == NULL);
  streaming_config.profile = 0; streaming_config.max_audio_seconds = 3601;
  CHECK(nh_streaming_diarizer_create(&streaming_config, &streaming) == NH_INVALID_ARGUMENT && streaming == NULL);
  CHECK(nh_streaming_diarizer_accept(NULL, NULL, 0, NULL, NULL) == NH_INVALID_ARGUMENT);
  CHECK(nh_streaming_diarizer_flush(NULL, NULL, NULL) == NH_INVALID_ARGUMENT);
  CHECK(nh_streaming_diarizer_reset(NULL) == NH_INVALID_ARGUMENT);
  nh_streaming_diarizer_stats streaming_stats = {0};
  CHECK(nh_streaming_diarizer_get_stats(NULL, &streaming_stats) == NH_INVALID_ARGUMENT);
  nh_streaming_diarizer_destroy(NULL);
  llm.struct_size = sizeof(llm); llm.model = "missing"; llm.output_text = "c-abi-fixture.wav";
  llm.threads = 1; llm.context_tokens = 4096; llm.max_output_tokens = 256;
  CHECK(nh_summarize_file("c-abi-fixture.wav", &llm, NULL, NULL) == NH_INVALID_ARGUMENT);
  CHECK(remove("c-abi-fixture.wav") == 0);
  return 0;
}
