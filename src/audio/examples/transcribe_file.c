/* Standalone C integration example, same complete pipeline as the SDK launcher.
 * Run off the UI thread. Models and runtime libraries must already be local. */
#include "nuclear_audio.h"

#include <stdio.h>

static int32_t progress(const char* stage, uint64_t done, uint64_t total, void* user) {
    (void)user;
    fprintf(stderr, "%s %llu/%llu\n", stage, (unsigned long long)done, (unsigned long long)total);
    return 0; /* Return nonzero for cooperative cancellation. */
}

int main(int argc, char** argv) {
    if (argc != 7) {
        fprintf(stderr, "Usage: client INPUT OUTPUT ASR TOKENS SPEAKER_MODEL SCRATCH\n");
        return NH_INVALID_ARGUMENT;
    }
    nh_transcription_config config = {0};
    config.struct_size = sizeof(config);
    config.asr_model = argv[3];
    config.tokens = argv[4];
    config.speaker_model = argv[5];
    config.scratch_directory = argv[6];
    config.output_json = argv[2];
    /* Zero threads and duration use the measured preset:4 threads,600s limit. */
    const nh_status status = nh_transcribe(argv[1], &config, progress, NULL);
    if (status != NH_OK)
        fprintf(stderr, "%s\n", nh_last_error());
    return (int)status;
}
