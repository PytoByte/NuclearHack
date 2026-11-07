# Ограничения решения

Этот документ собирает известные ограничения оффлайн-конвейера
Neurostenographer / Nuclear Audio SDK. Он нужен для честной оценки результатов и
планирования дальнейших улучшений.

## Функциональные ограничения

- Это **buffered file processing**, а не real-time микрофонный ASR. Приложение
  работает с уже записанным файлом, а не со входом микрофона в реальном времени.
- Один вызов `nh_transcribe` выполняет один тяжёлый file/summary job на процесс;
  повторный вход возвращает `NH_BUSY`.
- Жёсткого лимита 3600 с больше нет; API принимает explicit `max_audio_seconds`
  больше 3600 s. Для надёжной памяти, RTF, timestamps drift и checkpoint восстановления
  длинные записи рекомендуется всё равно сегментировать.
- В приложении нет записи аудио. Импорт и экспорт работают только через SAF
  (Storage Access Framework); приложение не пишет во внешние каталоги без выбора
  пользователя.
- `nh_transcribe` — blocking-вызов; клиент должен запускать его на worker thread.
- ID спикеров стабильны только внутри одного файла. Межфайловая идентичность
  говорящих не поддерживается.

## Качество распознавания и диаризации

- Короткий третий голос, одновременная речь/overlap и тяжёлые записи остаются
  сложными сценариями.
- Diarization может предсказать больше слотов, чем реально говорящих
  (`predicted_speakers` != `reference_speakers` в экспериментах).
- Automatic voice count использует до 8 слотов, но это не гарантия распознавания
  всех 8 говорящих.
- Stereo сводится в mono; channel-aware diarization не поддерживается.
- ASR текст post-processing не улучшает lexical ASR: output JSON содержит текст,
  сгенерированный ASR, без LLM-переписывания. Punctuation также генерируется ASR.
- ASR checkpoint ускоряет resume, но при изменении decoded PCM, модели, tokens,
  runtime или architecture повторно декодирует вход и пересчитывает diarization.
- Временные метки слов — token spans, last character + 40 ms, не forced alignment.
  При невозможности точной реконструкции сохраняется whole-chunk span и
  `chunk_fallback` в trace. MAE таймстампов слов без ручной ground truth
  неизвестен.

## Модели и runtime

- Все модели выполняются офлайн. Веса поставляются до сборки/развёртывания.
- GigaAM-v3 CTC INT8 генерирует punctuated text и не заменяется другой ASR без
  отдельного исследования.
- Nemotron3 Q8 используется только для диаризации и не заменяет ASR.
- Qwen/summary — optional compatibility capability, вне текущего пользовательского
  scope транскрибации. Qwen веса не входят в минимальный bundle, а summary не
  меняет transcript JSON.
- ASR и speaker работают буферно: политика 20 с ASR chunks, chunk 25 с и
  buffered speaker profile фиксированы основным API.
- Физические ARM- measurements (RAM, RTF, качество) не измерены; есть только
  cross-build и host/AVD данные.

## Benchmarks и оценка

- Полный Android-app benchmark не заявляется; host numbers имеют метки `host`,
  AVD/physical ARM. Не путать Android host metrics с доказательством устройства.
- Независимого gold-корпуса и ручных word timestamps нет.
- Качество оценивается на silver natural RU dialog sets:
  - heldout/movie/astrology/movie sessions уже многократно использованы, поэтому
    `heldout` в имени не делает их новым blind test.
  - OpenSTT phone40 — отдельный домен, без speaker/word-time GT.
  - FLEURS RU — read speech.
  - AMI — английская диаризация.
  - Dialogs smoke — структурные/synthetic проверки.
- Host decode benchmark измеряет только decoder, без model inference.
- ARM cross-build и 16 KiB ELF alignment не заменяют запуск на устройстве.

## Данные и происхождение метрик

- Test/train split должен делиться по исходным сессиям/людям, не случайными
  строчками.
- Аудио, reference transcripts и скрипты не должны распространяться без прав.
- Веса, аудио, логи и `.audio-runs` не коммитятся.
- `eval/results/exp_*` хранят configs, aggregate/per-case metrics, environment и
  invalidity, но не raw outputs/traces.

## Совместимость сборок

- Release artifacts создаются из pinned tool versions (clang-format, CMake,
  SDK/NDK, uv.lock).
- `make android-app` собирает debug APK с native libs/assets и проверяет
  отсутствие `INTERNET`.
- Release APK подписывается отдельным keystore; temporary keystore из `/tmp`
  не должен использоваться для публикации.
- `task/` read-only и не должен изменяться automation/scripts.
