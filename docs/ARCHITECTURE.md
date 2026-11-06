# Аудиомодуль: текущая архитектура

Обновлено: 07.11.2026. Реализованный код и принятые ограничения; этапы,
эксперименты и ADR — в [RESEARCH.md](RESEARCH.md).

## Границы и стек

Самостоятельный C++17 SDK с C ABI: `src/audio/include/nuclear_audio.h`.
CMake/Ninja, Linux x86_64 для разработки, NDK r27d/API 26 для Android
ARM64/x86_64. Android Java/JNI host — тонкий тестовый клиент, не ядро SDK.
Без Gradle/Kotlin/Compose в новом модуле; существующий UI не изменяется.

```text
клиент → libnuclear_audio.so / C ABI
  nh_decode_file → miniaudio → mono 16-kHz f32 blocks
  nh_transcribe_file:
    decode → temporary disk PCM → CTC chunks → release ASR
      → mmap PCM → segmentation + embeddings + auto clustering → release diarizer
      → CTC word spans + maximum speaker overlap → strict transcript JSON
  nh_summarize_file (отдельное действие):
    transcript JSON → local llama.cpp / Qwen3 → отдельный summary.txt
```

Низкоуровневые ASR/diarizer API доступны независимо от файлового orchestrator.
Runtime — sherpa-onnx 2.0.1 / ONNX Runtime 1.28.2 CPU и pinned llama.cpp.
Модели передаются локальными путями. Скачивания и сетевого inference в SDK нет.

## Файловый пайплайн

miniaudio 0.11.23 потоково декодирует MP3/WAV с настоящим ресемплированием
(linear + low-pass 8-го порядка). Один PCM-блок переиспользуется. Временный
PCM создаётся через mkstemp в scratch клиента, сразу unlink, удаляется при
закрытии. Размер на диске 64 KB/s; ASR читает ограниченные чанки 1–25 s.
После ASR PCM mmap используется whole-file diarizer. Это ограничивает heap
декодера, но не доказывает постоянную память всего inference.

Текущий файловый baseline ограничен **600 s** явным параметром. VAD,
silence-aware chunks, overlap/dedup, checkpoint/resume ещё не реализованы.
Стереоканалы сводятся в mono; channel-aware диаризации пока нет.

ASR файлового API: GigaAM-v3 CTC INT8, 4 CPU threads — host preset;
другие CTC, RNNT и Whisper доступны через низкоуровневые constructors.
ASR текст не редактируется. CTC char timestamps собираются в word spans,
последний символ +40 ms; это не forced alignment. При несовпадении
реконструированных слов с исходным текстом сохраняется whole-chunk span,
с явным `chunk_fallback` в trace, без подмены текста.

Diarization: pyannote segmentation FP32 → ERes2Net embeddings → автоматическая
agglomerative clustering. Число участников не задаётся. Порог — cosine
**dissimilarity** в (0,2], provisional .8 по AMI validation. minDurationOn/Off
пока .3/.5 s. ID канонизируются по первому появлению и стабильны внутри файла.
Межфайловая идентификация отсутствует. Короткие реплики остаются слабым местом.

Word→speaker — максимальное пересечение интервалов; без пересечения
`speaker_unknown`. Соседние слова одного speaker объединяются при gap≤1200 ms.
Экспорт содержит только `transcript` и обязательные поля
`speaker_id/start_ms/end_ms/text`; временные метки целые ms исходной timeline.
MP3 encoder delay и точность границ ещё требуют отдельного измерения.
Backend ASR, word spans и raw speaker turns хранятся в отдельном trace JSON.
Вывод атомарный (temp/fsync/rename); перезапись входа/модели/trace запрещена.

## Локальная LLM и ресурсы

Отдельный `nh_summarize_file`: Qwen3-0.6B Q8_0 GGUF, CPU mmap, context 4096,
output cap 256, greedy, ChatML no-thinking. Текст транскрипта токенизируется
без интерпретации control tokens. Переполнение context возвращает явную ошибку,
молчаливого усечения нет. Резюме сохраняется отдельно; основной JSON не меняется.
ASR и diarizer уже освобождены до вызова LLM; RAII освобождает model/context/sampler.
Отсутствующий optional llama runtime явно сообщает unavailable.

Handles освобождаются явно; один handle обслуживает одну операцию, повторный
вход — NH_BUSY. Разные handles независимы; общий бюджет контролирует клиент.
Буферы callbacks заимствованы до возврата, исключения через C ABI запрещены.
Progress: queued/decode/asr_load/asr/diarization_load/diarization/merge/done;
LLM имеет отдельные load/prefill/generate/done stages. Отмена кооперативная
между PCM-блоками, ASR-чанками, LLM batches/tokens и стадиями. Whole-file
вызов diarization пока непрерываемый; частичного экспорта/resume нет.

## Android host и offline-доставка

`src/audio/android/`: минимальный Java host, JNI → тот же C ABI. SAF импорт MP3,
просмотр реплик, экспорт JSON, отдельная кнопка резюме и отмена. Модели
предварительно устанавливаются в private files; Android-код их не скачивает.
APK собирается javac/d8/aapt2/zipalign/apksigner без Gradle. API 35, min26,
ARM64/x86_64; в проверенном manifest **нет INTERNET**.

Изолированный AVD NuclearAudio4G: API35 Google APIs/x86_64, 4096 MiB, 4 cores,
headless, adb5039/emulator-5558, airplane mode. `AudioInstrumentation` проводит
три MP3 через ASR/diar/JSON/optional LLM, пишет stage events, wall time,
per-case sampled PSS и **process-lifetime** peak RSS. Доставка весов — локальный
bundle с лицензиями/manifest, SHA256 проверяются перед упаковкой и на устройстве.

## Проверка и воспроизводимость

`make check native-test native-sanitize mobile-build research-test`.
ASan/UBSan инструментируют наш код, не готовые sherpa/ONNX binaries.
Release без fast-math; переносимый CPU baseline. Проверяются ABI и 16-KiB
LOAD alignment. Cross-build ARM64 не является доказательством запуска ARM64.

Дополнительно: `scripts/build_llama_audio.py`, `scripts/bootstrap_android_audio.py`,
`scripts/build_android_host.py`, `scripts/package_offline_models.sh`,
`scripts/install_android_audio.py`, `eval/scripts/run_android_pipeline.py`.
Host harness вызывает тот же C ABI; Python занимается данными и scoring.
Версии/хеши: `config/*lock.json`, `uv.lock`. Веса, аудио и raw logs исключены
из Git. [src/audio/README.md](../src/audio/README.md) содержит команды API.
