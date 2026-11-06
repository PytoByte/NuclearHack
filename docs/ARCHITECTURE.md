# Аудиомодуль: текущая архитектура

Обновлено: 07.11.2026. Этот файл описывает реализованный код; гипотезы,
будущие шаги и результаты — в [RESEARCH.md](RESEARCH.md).

## Границы и стек

Самостоятельный C++17 SDK с C ABI, без UI/JVM/Gradle. CMake/Ninja,
Linux x86_64 для разработки, NDK r27d/API 26 для Android ARM64/x86_64.
Публичный контракт: `src/audio/include/nuclear_audio.h`.
Исходники: `src/audio/src/`; CLI: `src/audio/tools/main.cpp`.

```text
Клиент → C ABI libnuclear_audio.so
  nh_decode_file → miniaudio MP3/WAV → mono f32 PCM + frame offsets
  nh_asr_*      → sherpa C API → CPU ONNX Runtime → text + backend JSON
  nh_diarizer_* → sherpa segmentation + embedding + auto clustering → turns
```

Операции независимы. Готового сквозного файлового orchestrator, VAD,
глобальной привязки спикеров и LLM пока нет. JSON ASR — диагностический
backend output; это не финальный экспорт конкурса.

## Декодирование

miniaudio 0.11.23 читает файл потоково. Настоящее ресемплирование, linear
resampler + low-pass 8-го порядка; mono f32. Один переиспользуемый PCM-блок,
callback получает начальный frame offset в resampled timeline.
Предел блока — 1 920 000 frames, обычный размер — 16 000 (64 KB при f32).
Callback отменяет чтение ненулевым возвратом. Независимые стереоканалы пока
сводятся: channel-aware диаризация не реализована. MP3 encoder padding нужно
учесть при последующей проверке таймкодов относительно исходного контейнера.

## Модели и владение ресурсами

sherpa-onnx 2.0.1 / ONNX Runtime 1.28.2, только CPU provider, 1–16 потоков
задаются клиентом. Модели и tokens передаются локальными путями; сетевой
загрузки в SDK нет. CTC принимает GigaAM/NeMo ONNX. Также реализованы transducer (RNNT) и multilingual Whisper constructors;
Whisper зафиксирован на ru/transcribe. Сравнение качества — в RESEARCH.md.

Текущий исследовательский host preset: GigaAM-v3 CTC INT8 / 4 threads
(`experiments/best_config.json`); это не автоматически выбранный режим Android.

ASR: mono 16 kHz, до 400 000 samples (25 секунд) на вызов. Текст модели
не редактируется. У текущего CTC backend есть char tokens/timestamps,
word alignment отсутствует. Diarizer: contiguous mono 16 kHz до 600 секунд, порог
clustering (cosine dissimilarity, (0,2]) задаётся клиентом, число спикеров определяется автоматически.
Speaker ID ограничен одним вызовом; межоконная стабильность не реализована.
Сейчас min_duration_on/off = 0.3/0.5 s, это конфигурация, не итог калибровки.

Handles освобождаются явно; внутри RAII. На одном handle одновременно одна
операция, повторный вход возвращает NH_BUSY. Разные handles независимы;
суммарный CPU/RAM бюджет контролирует клиент. Вызовы синхронные, inference
непрерываемый; отмена действует при чтении/доставке результата.
Буферы callback заимствованы до его возврата; исключения через C ABI запрещены.
Передача PCM не создаёт managed-объекты, но runtime может копировать признаки.

## Проверка и воспроизводимость

`make audio-bootstrap`, `make native-test`, `make native-sanitize`;
`make mobile-bootstrap mobile-build` — cross-compilation без приложения.
Release без fast-math/host-specific CPU flags; ASan/UBSan для нашего кода,
готовые sherpa/ONNX binaries не инструментированы.
Проверяются ELF machine и 16-KiB LOAD alignment SDK и двух runtime-зависимостей.
Сборка под ABI не означает проверенный запуск и память на Android 4 ГБ.

Версии/хеши: `config/audio-toolchain.lock.json`, `config/audio-models.lock.json`,
`uv.lock`. Bootstrap выполняется на dev-машине. Весов/аудио/сырых логов в Git нет.
Research harness `eval/scripts/` вызывает тот же C ABI через ctypes; Python
не выполняет ASR. FLEURS extraction и scoring — только инструменты исследования.
Команды интеграции: [src/audio/README.md](../src/audio/README.md).
