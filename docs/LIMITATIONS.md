# Ограничения решения

## Общие

- Это обработка готового аудиофайла, не real-time микрофонный ASR.
- Один тяжёлый вызов на процесс; повторный вход возвращает `NH_BUSY`.
- Приложение не записывает аудио; импорт/экспорт только через SAF.
- ID говорящих стабильны только внутри одного файла.

## Качество

- До 8 speaker-слотов, но это не гарантия распознавания всех говорящих.
- Короткие реплики, overlap и шумные записи остаются сложными.
- Stereo сводится в mono; channel-aware diarization нет.
- Timestamps — token spans, не forced alignment; MAE не измерен.
- Нет независимого gold/ручной разметки; метрики на silver-данных.
- Не смешивать plain `nh_transcribe_file*` с финальным preset.

## Модели и runtime

- Все модели офлайн; веса поставляются заранее.
- GigaAM-v3 CTC INT8 — ASR; Nemotron3 Q8 — только диаризация.
- Qwen/summary — optional, не входит в базовый bundle и не меняет JSON.
- Межфайловая идентичность говорящих не поддерживается.

## Benchmarks

- Host/RSS/RTF не являются доказательством Android performance.
- Физический ARM runtime/RAM/RTF/качество не измерены.
- Qwen/summary и исследовательские модели не входят в shipped bundle.

## Совместимость

- Release artifacts собираются из pinned tool versions.
- `task/` read-only.
- Не коммитить `.build`, модели, аудио, weights, raw logs.
