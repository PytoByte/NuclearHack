# Самостоятельный аудио SDK

## Решение

Ядро: **C++17 + стабильный C ABI**, сборка CMake/Ninja, inference CPU через
sherpa-onnx/ONNX Runtime. Android NDK r27d, API 26+, ABI arm64-v8a и x86_64.
Обёртка Kotlin/JNI — будущий адаптер интеграции; Compose, Activity, Gradle
и JVM не требуются для разработки и тестирования самого SDK.

Это выбор для управления памятью, жизненным циклом и переносимости runtime.
Сам по себе перенос управляющего кода с Kotlin на C++ не доказывает ускорения:
при одинаковых весах и конфигурации основное время обычно занимает нативный
inference. Качество определяется моделью, декодированием и сегментацией.
Ни один стек пока не объявляется победителем по измеренному WER/RTF.

| Вариант | Оценка для этого проекта |
| --- | --- |
| C++17 + C ABI | Выбран: прямой доступ к C API runtime, RAII, явные буферы, Android/Linux |
| Kotlin + native runtime | Подходит как клиент SDK; переносить обработку PCM в JVM необходимости нет |
| Rust + FFI | Технически подходит; добавляет toolchain и обёртки поверх уже имеющихся C/C++ runtime |
| Flutter/React Native | Возможные UI-клиенты; не решают задачу ядра и производительности inference |
| Python/PyTorch | Исследования и измерения; не runtime мобильного SDK |

## Компоненты и границы

```text
Клиент (Kotlin/JNI, C++, Python ctypes для тестов)
  → nuclear_audio.h / libnuclear_audio.so
    → miniaudio: MP3/WAV → PCM f32 mono, настоящее ресемплирование
    → sherpa-onnx C API: ASR / speaker segmentation + embedding + clustering
    → будущий file orchestrator: VAD, offsets, speaker matching, строгий JSON
    → будущий отдельный llama.cpp adapter: анализ текста по запросу
```

API v1 предоставляет независимые низкоуровневые операции:

- `nh_decode_file`: потоковое чтение и ресемплирование, callback с исходным
  frame offset, один переиспользуемый блок, отмена после блока.
- `nh_asr_create_ctc` / `nh_asr_decode` / `nh_asr_destroy`: локальный CTC
  inference, mono 16 kHz, до 25 секунд на вызов, явное число CPU-потоков.
- `nh_diarizer_create` / `nh_diarizer_process` / `nh_diarizer_destroy`:
  segmentation + embedding + auto clustering, до 600 секунд PCM на вызов.
- `nh_last_error`, коды ошибок, `NH_BUSY` для повторного входа на один handle.

Данные callback заимствованы до его возврата. В API нет передачи каждой
выборки через JNI и не создаются managed-объекты на каждый аудиофрейм.
Runtime может копировать PCM при построении признаков: zero-copy внутри
ONNX/sherpa не обещается. Несколько handles могут работать параллельно;
ответственность за суммарные CPU/RAM бюджеты несёт orchestrator.

Все вызовы синхронные: клиент вызывает их на рабочем потоке. Native inference
в текущем адаптере не прерывается; отмена действует при чтении/доставке результата.
Нельзя уничтожать handle во время его использования. Callback не должен бросать
исключения через C ABI. Буферы PCM должны оставаться доступны до возврата вызова.

## Производительность и качество

Release без `-ffast-math` и без привязки к CPU разработчика; Android ABI получает
свой target через NDK. Debug с ASan/UBSan проверяет наш код и decoder;
готовые бинарники ONNX/sherpa санитайзерами не инструментированы.
На Android используется выравнивание LOAD segments 16 KiB; совместимость
зависимостей и запуск на конкретной версии Android проверяются отдельно.

Декодер использует miniaudio linear resampler с low-pass фильтром 8-го порядка.
Есть синтетическая проверка подавления alias при 48→16 kHz. Это начальный
вариант, не доказательство оптимального WER. В следующих A/B сравнить его
с более дорогим sinc/polyphase resampler и контрольной ffmpeg-цепочкой.
Mono-сведение не подходит для независимых спикеров в разных стереоканалах:
channel-aware обработка — отдельный следующий этап API.

ASR-кандидат: **GigaAM-v3 CTC INT8**, обычный verbatim-вариант, затем сравнить
FP32, RNNT и Whisper на одинаковых данных. E2E-варианты с нормализацией текста
не подменяют дословную основную расшифровку. VAD — кандидат Silero,
включение только после A/B на коротких репликах и паузах.

Диаризация требует contiguous PCM в текущем sherpa API: 600 секунд f32/16kHz
занимают около 38.4 MB только на вход. Не заявляем постоянную память
диаризации и не выдаём chunk-local speaker IDs за стабильные IDs всего файла.
План: дисковый PCM spool, глобальные embeddings/clustering или проверенная
межоконная привязка; освободить ASR перед diarizer, diarizer перед LLM.
Лимит 600 секунд — технический предел одного вызова, не готовый long-form режим.

LLM: отдельный будущий llama.cpp CPU adapter, компактная квантованная модель
примерно 0.5–0.6B как стартовый кандидат, ограниченный контекст. Она не участвует
в основном verbatim-тексте. Модель и лицензия закрепляются после реального теста.

## Что проверено и что осталось

Подготовка SDK включает C ABI, decoder, runtime adapters, headless тесты и
cross-compilation. Нет готового сквозного файлового ASR+diarization orchestrator,
глобального speaker tracking, VAD и LLM adapter. Веса ещё не выбраны по нашим
измерениям, поэтому native inference нельзя считать проверенным только по линковке.
В JSON от ASR хранится **диагностический backend output**, а не финальный
экспорт конкурса. Проверка финального контракта остаётся отдельной командой.

Порядок экспериментов: (1) baseline модели на размеченных русских диалогах,
(2) threads 1/2/4 и INT8/FP32, (3) границы VAD и ресемплер,
(4) diarization/overlap/глобальные IDs, (5) Android CPU/RAM без UI.
Desktop и Android результаты не смешиваются; сборка под ABI не заменяет запуск.

## Первичные источники

- [sherpa C API](https://k2-fsa.github.io/sherpa/onnx/c-api/index.html)
- [sherpa v2.0.1, закреплённый runtime](https://github.com/k2-fsa/sherpa-onnx/releases/tag/v2.0.1)
- [GigaAM: модели, ONNX export и ограничения](https://github.com/salute-developers/GigaAM)
- [miniaudio: decoder, resampling и ownership](https://miniaud.io/docs/manual/index.html)
- [llama.cpp: Android NDK](https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md)
