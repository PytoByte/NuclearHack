# Аудиомодуль: архитектура

Самостоятельный C++17 SDK с C ABI. Публичный файловый API — `nh_transcribe`.
Preset — `ru-offline-v1` (`config/audio-sdk-preset.json`).

## Конвейер

```text
decode MP3/WAV → mono 16 kHz f32 → unlinked disk PCM
GigaAM-v3 CTC INT8 (25 с чанки) → текст с пунктуацией
Nemotron3 Diarization Q8 (stream 1 с) → speaker per word (160 ms anchor)
merge adjacent same-speaker words, gap ≤ 1200 ms → strict transcript JSON
```

- GigaAM — ASR; Nemotron — только диаризация.
- Пунктуация/case генерируются ASR, без LLM-переписывания.
- До 8 speaker-слотов, но без гарантии для всех.

## Модели

- ASR: `GigaAM-v3 CTC INT8` — текст с пунктуацией.
- Diarization: `Nemotron3 Q8`.
- Qwen/summary optional, вне базового scope, не меняет transcript JSON.
- Все модели офлайн, веса поставляются заранее.

## Ключевые технические решения

- `nh_transcribe` блокирующий; отмена между блоками и инференсами.
  Текущий синхронный вызов нейросети не прерывается.
- Один high-level job на процесс (`NH_BUSY` при повторе).
- PCM spool на диске; ASR читает чанки, speaker backend stream 16000 samples.
- ASR checkpoint v2 по SHA256 PCM + params; диаризация пересчитывается.
- JSON строго: `speaker_id`, `start_ms`, `end_ms`, `text`.
- Атомарная запись каждого output/trace-файла; это не общая транзакция двух файлов.
  Внешняя сеть отсутствует.

## Слои

- `pipeline.cpp` — C ABI adapters / preset.
- `file_transcriber.*` — стадии, отмена, экспорт.
- `pipeline_ports.hpp` / `pipeline_factory.cpp` — контракты и backend-выбор.
- `pipeline_storage.*` — RAII для PCM, mmap, checkpoint, atomic JSON.
- DSP: `mel.*`, `speaker_cache.*`, `posterior_merge.hpp`.

## Android клиент

Jetpack Compose/MVVM + JNI. Gradle не собирает native SDK: использует
готовые `.build/android-<abi>` libs, sherpa libs и local models. Foreground
service с progress; manifest без `INTERNET`. Final preset выбирается при
наличии assets, иначе legacy.

## Build/tests

- Runtime: sherpa-onnx 2.0.1, ONNX Runtime 1.28.2, miniaudio 0.11.23.
- Linux x86_64, NDK r27d/API 26 for Android.
- Gates: `make check native-test native-sanitize leak-check mobile-build`.
- Android: ktlint, detekt, lint.
- ASan/UBSan покрывают проектный код, не предсобранный ORT/sherpa.

## Не входит в scope

- Real-time микрофонный ASR.
- Запись аудио в приложении.
- Full Android-app benchmark на physical ARM (not measured).
- Cross-file speaker identity.

## Границы качества и измерений

- Короткие голоса, музыка и одновременная речь остаются сложными.
  Один ASR-поток не гарантирует расшифровку обоих наложенных голосов.
- Стереоканалы сводятся в mono; отдельной channel-aware обработки нет.
- Таймкоды получены из CTC-токенов; без ручных времён слов timestamp MAE не измерен.
- Русские диалоги оценивались на известном publisher-reviewed silver-наборе,
  а не независимом blind gold. FLEURS — чтение, не диалоги.
- Android RTF/PSS в презентации относятся к native SDK CLI на x86_64 AVD с 4 ГБ RAM,
  а не полному Compose APK или инструментированному ARM-бенчмарку.
  Время трёх повторов одного файла различалось в 2,46 раза.
- Бюджет C API по умолчанию — 3600 с, явный бюджет задаёт вызывающий код.
  Это не жёсткий максимум и не сертификация многочасового качества.

Материалы релиза: [презентация](../artifacts/presentation.pdf),
[видео приложения](../artifacts/demo.mp4). Конфигурации и результаты экспериментов — `eval/results/`.
