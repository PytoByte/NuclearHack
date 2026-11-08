# Nuclear Audio SDK

Самостоятельный офлайн C++17 модуль с C ABI1. Обрабатывает MP3/WAV целиком:
декодирование → GigaAM-v3 CTC с пунктуацией → Nemotron3 Q8 → реплики с
speaker ID и временем → строгий JSON. UI, Python, JVM и сеть для inference не нужны.

Рекомендуемый API — `nh_transcribe(input, &config, progress, user)`.
`nh_transcription_config` содержит локальные пути ASR/tokens/speaker model,
рабочего каталога и выходного JSON. Trace и ASR checkpoint необязательны.
Значения по умолчанию:4 CPU threads, лимит3600s (1 час); политика20s ASR chunks,
buffered speaker profile и first160ms word anchor фиксирована.
Полный C-клиент: [examples/transcribe_file.c](examples/transcribe_file.c).

Вызов блокирующий: клиент запускает его на рабочем потоке. Callback progress
может запросить кооперативную отмену. Ошибки — `nh_status` и `nh_last_error()`.
Один тяжёлый file/summary job на процесс; повторный вход возвращает `NH_BUSY`.
Другие ABI1 entry points сохраняются для существующих клиентов/расширенных сценариев.
Старый `nh_transcribe_file` использует прежний ERes backend; это не рекомендуемый preset.

```json
{"transcript":[{"speaker_id":"speaker_1","start_ms":120,"end_ms":920,"text":"Добрый день!"}]}
```

Текст — выход выбранного ASR без LLM-переписывания. ID стабильны только внутри
файла. Веса и runtime поставляются заранее; один `.so` без них недостаточен.
Пунктуация генерируется ASR, отдельный Python-пунктуатор не используется.

## Документация

Архитектура и ограничения: [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md).
Архитектура: [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md).

## Сборка и проверка

Из корня репозитория, Linux x86_64:

```sh
make audio-bootstrap                 # uv sync: pinned build tools и clang-format
.venv/bin/python scripts/bootstrap_models.py giga-v3-ctc-punct nemotron3-diarization-q8
make native-test native-sanitize
make mobile-bootstrap mobile-build   # NDK; ARM64 и x86_64, min API26
make check native-format-check research-test
make sdk-package
```

`make native-format` применяет `src/audio/.clang-format` (clang-format19.1.7).
Pre-commit проверяет точное staged-содержимое изменённых native файлов.
После bootstrap CMake ничего не скачивает. Версии/SHA закреплены в
`config/*lock.json` и `uv.lock`; модели/логи не хранятся в Git.

## Комплект SDK

`.build/nuclear-audio-sdk-ru-v1.tar` содержит:

- `include/nuclear_audio.h`, C-пример и `preset.json`;
- `lib/` и `bin/` для Linux x86_64, Android ARM64/x86_64;
- выбранные локальные модели, runtime, лицензии и SHA256 manifest;
- build provenance и описание ограничений.

Для Android-клиента нужно доставить соответствующие `.so` и модели локально,
вызвать C ABI через собственный JNI/native слой. APK в модуль не требуется.
В Linux распакованный комплект запускается без Python:

```sh
./nuclear-audio-sdk/run-linux.sh recording.mp3 transcript.json /tmp
# Необязательный четвёртый аргумент — private checkpoint directory.
```

Прямой CLI из рабочей сборки:

```sh
.build/audio/nh-audio transcribe-final recording.mp3 transcript.json \
  models/giga-v3-ctc-punct/model.int8.onnx models/giga-v3-ctc-punct/tokens.txt \
  models/nemotron3-diarization/model_quantized.onnx /tmp
```

Низкоуровневые decoder/ASR/diarizer/VAD API доступны отдельно. `nh_summarize_file`
остаётся отдельным действием, требует optional llama runtime и локальные Qwen
веса; Qwen не включён в минимальный transcription bundle. Сборки с llama требуют
его runtime-библиотеки и при транскрибации — упаковщик добавляет их автоматически.

## Ограничения

Это buffered file processing, не готовая real-time транскрибация микрофона.
Короткие третьи голоса/одновременная речь остаются сложными; стерео сводится в mono.
Timestamp MAE без ручных word GT неизвестен. ARM64 собран, но запуск на физическом
ARM не проверен.3600s long-dialogue soak и натворческая проверка качества не заменяют друг друга.
Выбранный ASR лучше восстанавливает пунктуацию, но на phone40 хуже plain CTC;
нет утверждения об универсальном качестве или независимом gold test.

Архитектура и ограничения — [ARCHITECTURE.md](../../docs/ARCHITECTURE.md).
Результаты экспериментов — `eval/results/`.
