# Нейростенографист / Nuclear Audio SDK

Локальный офлайн-конвейер для транскрибации аудиодиалогов с диаризацией.
Каталог `task/` read-only: это исходный brief хакатона и справочные материалы.

## Быстрый старт

```sh
make audio-bootstrap
uv run python scripts/bootstrap_models.py giga-v3-ctc-punct nemotron3-diarization-q8
make native-test native-sanitize
make mobile-build
make android-app
```

APK после сборки: `.build/android-app/neurostenographer-debug.apk`.

## Окружение

Все команды запускаются из корня репозитория, если явно не указано иное.
Python-зависимости поставляются только через `uv`; используйте
`uv run python ...` или `.venv/bin/python ...`, а не системный Python.

Системные требования для разработчика:
- Linux x86_64 для сборки/тестов native SDK и CMake/Ninja из `.venv/bin`;
- `uv` и Python, окружение создаётся через `uv sync --frozen`;
- для Android: NDK, JDK 17 и Android SDK under `.tools` или экспортированные
  `JAVA_HOME`/`ANDROID_HOME`;
- внешняя сеть доступна только developer tooling. Готовое приложение и SDK не
  имеют доступа в интернет.

Базовые команды установки и проверок:

```sh
make audio-bootstrap        # uv sync --frozen + pinned native dev dependencies
make mobile-bootstrap       # bootstrap + NDK для кросскомпиляции
make doctor                # показать отсутствующие локальные инструменты
make check                  # task/ protection, INTERNET permission, whitespace
make test                  # Python unit tests
```

Для Android из одной сессии shell:

```sh
export JAVA_HOME="$PWD/.tools/jdk" ANDROID_HOME="$PWD/.tools/android-sdk"
export PATH="$JAVA_HOME/bin:$PATH"
```

Важно: AGP/Gradle здесь не запускаются на системном JDK 25. Используйте
JDK 17 из `.tools/jdk`; если `JAVA_HOME` не задан, `gradlew` возьмёт системный.

## Модели

Модели скачивает разработчик. В Git они не хранятся, а приложение не имеет
доступа в интернет. SDK работает только с заранее поставленными весами.

Основной набор для рекомендуемого preset `ru-offline-v1`:

```sh
uv run python scripts/bootstrap_models.py giga-v3-ctc-punct nemotron3-diarization-q8
```

Это создаёт локальные директории `models/giga-v3-ctc-punct` и
`models/nemotron3-diarization`. После сборки assets они упаковываются в APK.

Проверка хешей и структуры локальных весов:

```sh
uv run python scripts/audio_tools.py models config/audio-models.lock.json
```

Опционально, если нужна функция локального резюме (Qwen; вне текущего
пользовательского scope transcription):

```sh
uv run python scripts/bootstrap_models.py qwen3-0.6b-q8
```

Qwen не входит в минимальный SDK/APK-сценарий. Если GGUF присутствует в
`models/qwen3-0.6b-q8`, `make android-app` упакует его как optional model.
Все модели должны соответствовать `config/audio-models.lock.json`.
Utility-модели и reference-модели исследований (`pyannote`, `sortformer`,
LLM/Qwen-варианты и др.) описаны в lock и ставятся явными ID из
`scripts/bootstrap_models.py --help`.

Gradle синхронизирует только:
- `giga-v3-ctc`
- `giga-v3-ctc-punct`
- `diarization`
- `nemotron3-diarization`
- `qwen3-0.6b-q8`

## Native SDK

Сборка и проверка core SDK:

```sh
make native-build                       # Release build in .build/audio
make native-test                        # build + CTest + Python C ABI tests
make native-sanitize                    # ASan/UBSan build + tests
make native-format-check                 # src/audio/.clang-format --check
make native-format                      # apply local clang-format
```

Прямые CLI-примеры из собранного SDK:

```sh
.build/audio/nh-audio transcribe-final recording.mp3 transcript.json \
  models/giga-v3-ctc-punct/model.int8.onnx models/giga-v3-ctc-punct/tokens.txt \
  models/nemotron3-diarization/model_quantized.onnx /tmp
```

Рекомендуемый API — `nh_transcribe` / `ru-offline-v1` из
`config/audio-sdk-preset.json`. По умолчанию 4 потока и лимит 3600 секунд;
20-секундные ASR chunks, buffered speaker profile и first 160 мс word anchor
фиксированы preset-ом. `nh_transcribe_file*` — legacy backend, его не смешивать
с финальным preset.

Публичный ABI и пример клиента: `src/audio/include/nuclear_audio.h`,
`src/audio/examples/transcribe_file.c`. Один вызов блокирует поток; progress
callback может запросить кооперативную отмену.

## Android-приложение

Сборка native-зависимостей и APK:

```sh
make mobile-build                      # cross-build arm64-v8a and x86_64
make android-app                        # debug APK + libs/assets checks
```

Результат: `.build/android-app/neurostenographer-debug.apk`.

Ручная сборка без `make android-app`:

```sh
cd src/mobile/android
sh gradlew :app:assembleDebug -PrequireNativeAudio=true
```

Качество Android client:

```sh
cd src/mobile/android
./gradlew ktlintCheck detekt
./gradlew :app:lintDebug
```

Release-сборка (unsigned APK, затем подпись):

```sh
cd src/mobile/android
./gradlew :app:assembleRelease
# результат: app/build/outputs/apk/release/app-release-unsigned.apk

export ANDROID_HOME="/path/to/android-sdk"  # например /home/user/NuclearHack/.tools/android-sdk
BUILD_TOOLS="$ANDROID_HOME/build-tools/35.0.0"
"$BUILD_TOOLS/zipalign" -f -p 4 app/build/outputs/apk/release/app-release-unsigned.apk /tmp/app-aligned.apk
"$BUILD_TOOLS/apksigner" sign --ks /path/to/release.jks --ks-key-alias <alias>   --ks-pass pass:<store-pass> --key-pass pass:<key-pass>   --out .build/android-app/neurostenographer-release-signed.apk /tmp/app-aligned.apk
"$BUILD_TOOLS/apksigner" verify --verbose .build/android-app/neurostenographer-release-signed.apk
```

Для обычной локальной проверки можно использовать debug-ключ, но для
публикации нужен собственный keystore; ключ из `/tmp` не использовать для релиза.

Оффлайн-инвариант: `INTERNET` должен отсутствовать в manifest. Модели
копируются из assets в app-private `filesDir/models`. Прогресс транскрибации
обрабатывается foreground-службой с уведомлением по этапам.

## Бенчмарки и проверки

### Host CPU/RSS
- `scripts/benchmark_decode.py <audio>` — измеряет wall time и peak RSS только
  native decoder, без ASR/diarization. Запускать на Linux. Результаты
  (metrics.json) сохраняются в `.audio-runs/decode-*`.
- `make leak-check` — cppcheck + clang-tidy + ASan/LSan ctest + Valgrind
  для `src/audio`; логи в `.audio-runs/leak-*`.
- `make native-sanitize` — санитайзеры native тестов.

### ASR/diarization качество
Качество сравнивается через scripts из `eval/scripts` и фиксирует run IDs:
- `run_asr.py`, `run_file_pipeline.py`, `run_diarization.py`,
  `run_fragment_asr.py` — запуск путей;
- `compare_asr.py`, `compare_punctuation.py`,
  `score_conversation_diarization.py` — сравнения и scoring;
- `probe_*`, `analyze_*` — воспроизводимые эксперименты, фrozen sources,
  budgets and baselines (см. `docs/AUDIO_RESEARCH_AGENT.md`).

Запускать гейты в точной последовательности и фиксировать run IDs:
`research-bootstrap` prepares pinned audio/model state and FLEURS validation40.
`research-pilot` runs native build + selected model prep and a frozen research queue.

```sh
make research-bootstrap                 # uv research group + native build + data/models
make research-test                     # eval/tests
```

Метрики сохраняются в `eval/results/exp_NNNN/` (configs, per-case metrics,
environment, aggregate). `.audio-runs/` и debug outputs не коммитятся.
Ни один из runtime numbers не считается Android-доказательством, пока не
измерен на AVD или физическом ARM.

### Android client
- `make android-check` — build + lint + unit tests APK permission check.

## Ограничения и provenance

- Обрабатывается готовый файл до 3600 секунд (1 час). Это лимит одного
  высокопроизводительного SDK-вызова, а не файлового формата. Более длинные
  записи лучше сегментировать.
- Это buffered file processing, не real-time microphone ASR. Приложение не
  записывает аудио; импорт только через SAF.
- ID спикеров стабильны только внутри одного файла.
- Запуск на физическом Android и ARM-метрики остаются `not measured`, пока не
  измерены.
- Qwen/summary — optional compatibility capability, outside current user scope.
  Existing optional summary API не меняет transcript JSON.

## Документация

- Архитектура: `docs/ARCHITECTURE.md`
- Цели, статусы и экспериментальная картина: `docs/GOALS.md`, `docs/RESEARCH.md`
- Research cycle: `docs/AUDIO_RESEARCH_AGENT.md`
- Правила репозитория: `AGENTS.md`
- SDK: `src/audio/README.md`
- Android client: `src/mobile/android/README.md`
- Scripts: `scripts/README.md`

Не изменяйте `task/`: он read-only. Не коммитьте `.build`, модели, аудио,
weights и raw logs.
