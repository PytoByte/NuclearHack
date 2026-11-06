# Nuclear Audio SDK

Самостоятельная native-библиотека C++17 с C ABI. Не требует UI, Android SDK,
Gradle или JVM на dev-машине. Сборка под Android требует только NDK.

```sh
make audio-bootstrap       # uv должен быть установлен; Linux x86_64
make doctor
make native-test
make native-sanitize
make mobile-bootstrap     # дополнительно NDK r27d, ~664 MB download
make mobile-build         # arm64-v8a + x86_64, API 26
```

Публичный интерфейс: `include/nuclear_audio.h`.
Linux `.so`: `.build/audio/libnuclear_audio.so`.
Android `.so`: `.build/android-{arm64-v8a,x86_64}/libnuclear_audio.so`.
Для мобильной интеграции также нужны sherpa C API, ONNX Runtime из
`.tools/sherpa-android/<abi>/`. Текущая сборка использует статическую C++ runtime;
`libc++_shared.so` нужна только если интегратор переключит STL на shared.
Зависимости и лицензии перечислены в `docs/RESEARCH.md`.

Исследования через тот же C ABI:

```sh
make research-bootstrap research-test
.venv/bin/python eval/scripts/prepare_fleurs.py --split test
.venv/bin/python eval/scripts/prepare_ami.py --split validation
.venv/bin/python eval/scripts/prepare_ami.py --split test
# Use a fresh experiment ID; completed runs are never overwritten.
python3 scripts/audio_tools.py run -- .venv/bin/python eval/scripts/run_asr.py --experiment exp_1000 --model giga-v3-ctc --threads 4
```

`eval/scripts/run_diarization.py` проверяет native diarizer по разметке AMI;
`compare_asr.py` — paired bootstrap и разбор ошибок; `probe_memory.py` — lifecycle.
Краткие результаты/этапы/ADR: `docs/RESEARCH.md`. Только набор read-speech
FLEURS и English AMI не подтверждают качество на русских разговорах.

Пример C/C++ клиента:

```c
#include "nuclear_audio.h"
static int32_t consume(const float *pcm, uint32_t frames,
                       uint64_t start_frame, void *user) {
    /* Consume here; copy only if the data must outlive this callback.
       Timestamp in ms = start_frame * 1000 / sample_rate. */
    return 0;
}
int main(void) {
    return nh_decode_file("meeting.mp3", 16000, 16000, consume, 0);
}
```

Декодер отдаёт resampled PCM; ASR и diarizer принимают PCM независимо от файла.
Модели передаются локальными путями. Все handles нужно явно освобождать.
Пример — обработка PCM, не полная транскрибация.

```sh
.build/audio/nh-audio native-info
.build/audio/nh-audio probe meeting.mp3
python3 scripts/benchmark_decode.py meeting.mp3
python3 scripts/audio_tools.py models models/manifest.json
```

`probe`/benchmark измеряют только decoder на dev-машине. ASR adapters:
NeMo/GigaAM CTC, transducer RNNT, Whisper (ru/transcribe). Модельные веса,
сквозной orchestrator, VAD, экспорт transcript и LLM — следующие этапы;
искусственных расшифровок в native SDK нет.

Версии и SHA256: `config/audio-toolchain.lock.json`, Python wheels: `uv.lock`.
После bootstrap CMake не скачивает зависимости. CI выполняет host tests,
ASan/UBSan и Android cross-compilation; CI ещё не запускался в GitHub.
Подробное решение и ограничения: `docs/ARCHITECTURE.md`.
