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
int main(void) {
  CHECK(nh_abi_version() == 1);
  CHECK(strlen(nh_sherpa_version()) > 0);
  CHECK(nh_decode_file(NULL, 16000, 16000, NULL, NULL) == NH_INVALID_ARGUMENT);
  CHECK(strlen(nh_last_error()) > 0);
  nh_asr *asr = NULL;
  CHECK(nh_asr_create_ctc("missing.onnx", "missing.txt", 2, &asr) == NH_IO_ERROR);
  CHECK(asr == NULL);
  CHECK(nh_asr_create_ctc("missing", "missing", 0, &asr) == NH_INVALID_ARGUMENT);
  CHECK(nh_asr_decode(NULL, NULL, 0, NULL, NULL) == NH_INVALID_ARGUMENT);
  nh_asr_destroy(NULL);
  nh_diarizer *diarizer = NULL;
  CHECK(nh_diarizer_create("missing", "missing", 2, 0.5f, &diarizer) == NH_IO_ERROR);
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
  CHECK(remove("c-abi-fixture.wav") == 0);
  return 0;
}
