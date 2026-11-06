# Исследования и решения

07.11.2026. Рабочая ветка `dev`. Реализованный пайплайн — [ARCHITECTURE.md](ARCHITECTURE.md).

## Этапы

- [x] K0: C++17/C ABI SDK, локальные зависимости, Linux tests/sanitizers,
  cross-compilation ARM64/x86_64 и проверка 16-KiB ELF alignment.
- [x] K1: выбраны проверяемые ASR-кандидаты, закреплены версии/хеши/лицензии
  GigaAM CTC v3/v2 и RNNT v3; dev-only bootstrap.
- [x] K2: заморожены 40 FLEURS ru validation clips, 20 male/20 female,
  длительность 1–25 s, deterministic selection до inference.
- [x] K3: native ASR baseline, одинаковый WER, time/RSS, выбор модели/потоков;
  независимый frozen test40 пройден без перенастройки.
- [ ] K4: diarization baseline на разговорной речи с RTTM, затем VAD/chunking.
- [ ] K5: file orchestrator, стабильные IDs/таймкоды/JSON; отдельный LLM adapter.
- [ ] K6: headless Android execution и 4-GB RAM verification.

## Эксперименты

| ID | Проверка | Результат / решение |
| --- | --- | --- |
| exp_0001 | Host decoder, synthetic MP3 10/600 s | RSS 13092/13116 KiB; decode 0.0276/1.6489 s. Оставить начальный decoder; качество речи не измеряет |
| exp_0002 | GigaAM-v3 CTC INT8 / 2t / val40 | WER 7.13% (54/757), RTF 0.159, RSS 439 MiB; CTC-кандидат |
| exp_0003 | GigaAM-v2 CTC INT8 / 2t / val40 | WER 7.79% (59/757), RTF 0.290, RSS 768 MiB; не выбирать вместо v3 |
| exp_0004 | GigaAM-v3 RNNT INT8 / 2t / val40 | WER 7.27%, RTF 0.172, RSS 687 MiB; оставить альтернативой |
| exp_0005 | Whisper base INT8 / ru / 2t / val40 | WER 27.34%, RTF 0.308, RSS 649 MiB; отклонить как основной |
| exp_0006 | CTC v3 / 1t / val40 | WER 7.13%, RTF 0.267; медленнее 2t |
| exp_0007 | CTC v3 / 4t / val40 | WER 7.13%, RTF 0.105, RSS 447 MiB; выбран host preset |
| exp_0008 | CTC v3 / 4t / frozen test40 | WER 6.34% (43/678), RTF 0.108, RSS 454 MiB; preset подтверждён на read-speech |
| exp_0009 | Diarization FP32 / AMI180 | Native turns сохранены; DER import failed (typing_extensions), время/RSS не сохранены |
| exp_0010 | Diarization FP32 / AMI180 / threshold .5 | DER 64.27%, 23 вместо 4 speakers, RTF .314, RSS 299 MiB; отклонить конфигурацию |
| exp_0011 | Diarization INT8 / AMI180 / threshold .5 | DER 43.96%, 16 вместо 4 speakers, RTF .287, RSS 300 MiB; тоже не принят |
| exp_0012–13 | 5 ASR load/infer/release cycles, без/с trim | Монотонного роста нет; host malloc_trim возвращает RSS к ~65 MiB |

Агрегаты: `eval/results/<id>/`; конфигурации, hypotheses, stdout/stderr —
`.audio-runs/<id>/`. Старые эксперименты не перезаписывать. Machine registry:
`experiments/registry.csv`. Desktop WER/RTF/RSS отдельно от Android; Android
WER/DER/RTF/RAM сейчас **not measured**.

Baseline: 40 clips / 456.54 s; RSS включает Python harness и native runtime.
Raw WER 33.20% из-за регистра/пунктуации, normalized WER считается по ADR-002.

## Короткие ADR

**ADR-001 — native SDK (принято).** C++17 + C ABI, прямой C API sherpa,
явное владение памятью. UI/managed wrappers остаются клиентами. Сам язык
не доказывает ускорение: сравниваем одинаковые модели/конфигурации.

**ADR-002 — точность текста (принято).** Основной текст дословный, без LLM
переписывания и удаления повторов/заполнителей. Normalization v1: Unicode NFC,
lowercase, ё→е, punctuation/symbols→space, whitespace collapse. Числа остаются
как написаны. Сохраняются raw и normalized corpus WER; знаменатель — сумма
эталонных слов, не среднее WER отдельных клипов.

**ADR-003 — screening data (принято с ограничением).** Google FLEURS ru_ru,
CC-BY-4.0, revision 70bb2e84b976b7e960aa89f1c648e09c59f894dd. Validation
используется для сравнения кандидатов; test не используется для настройки.
Это read-speech, не разговоры; speaker identities/RTTM нет. Не считать gender
меткой спикера и не считать этот screening доказательством качества диаризации.
Выборка: manifest SHA ce63e83088d93eae3150d679f2dc8f64ca14d21bf191a0aee0747f8563b25f4d.

**ADR-004 — model provenance (принято).** Веса по immutable revision + SHA256,
вместе с tokens и лицензией каждого файла. В GigaAM-v2 export файл LICENSE —
сохранённая HTML-страница GitHub; для комплекта взят канонический MIT LICENSE
оригинального GigaAM из закреплённого commit. Никаких загрузок внутри SDK.

**ADR-005 — CTC-кандидат (предварительно принято).** v3 быстрее и требует
меньше RAM, чем v2, на val40. Разница WER — всего 5 ошибок; статистический
выигрыш по качеству не заявляется. Базовый CTC-кандидат — v3, RNNT не улучшил WER и потребовал больше RAM. Whisper base заметно хуже;
не переносить этот вывод на Whisper small/large. Paired bootstrap (37 sentence
groups, 10k resamples) для v2−v3: [−0.41; +1.93] п.п., RNNT−CTC:
[−0.80; +1.34] п.п.; доказанного различия качества между GigaAM нет.
Большая часть худших ошибок — числительные/имена/латинские сокращения;
не менять normalization после просмотра результатов. В 7 клипах с цифрами
в эталоне — 40 из 54 ошибок v3; основная WER остаётся 7.13%, не заменяем
её более удобным подмножеством без цифр (диагностически 2.50%).

## Лицензии и первичные источники

| Компонент | Версия | Лицензия / источник |
| --- | --- | --- |
| sherpa | 2.0.1 | Apache-2.0, [C API](https://k2-fsa.github.io/sherpa/onnx/c-api/index.html) |
| ONNX Runtime | 1.28.2 | MIT, bundled CPU binary sherpa |
| miniaudio | 0.11.23 | MIT-0/public domain, [manual](https://miniaud.io/docs/manual/index.html) |
| GigaAM v2/v3 exports | revisions в model lock | MIT, [GigaAM](https://github.com/salute-developers/GigaAM), [v3 export](https://huggingface.co/csukuangfj/sherpa-onnx-nemo-ctc-giga-am-v3-russian-2025-12-16) |
| FLEURS ru_ru | revision выше | CC-BY-4.0, [Google dataset card](https://huggingface.co/datasets/google/fleurs) |
| NDK/CMake/Ninja | r27d/3.31.6/1.11.1.4 wheel | SDK terms/BSD-3-Clause/Apache-2.0; build-only |
| imageio-ffmpeg | 0.6.0 / FFmpeg 7.0.2 | BSD wrapper + own binary notices; dev-only, не в SDK |

При поставке переносить реальные license/NOTICE тексты, таблица их не заменяет.
Anti-Vocale просмотрен как референс (aca3eaf8), код не копируется: полезны
backend ports, chunk limits, model lifecycle и единый eval; не переносим
runtime downloads, remote offload, Firebase, full-RAM VAD path и text rewriting.

**ADR-006 — diarization smoke (принято с ограничением).** До русского
RTTM-набора используем ровно первые 180 s AMI IHM test row0 (4 спикера),
CC-BY-4.0, frozen revision/hash. Это отдельный English smoke, не calibration
и не доказательство качества на русских подкастах. DER: collar 0.25 s, overlap
включён, UEM [0,180], оптимальное сопоставление ID через pyannote.metrics.
Segmentation pyannote-3.0 MIT, embedding ERes2Net Apache-2.0; лицензия
checkpoint подтверждена ModelScope card и [upstream collaborator](https://github.com/modelscope/3D-Speaker/issues/268).

**ADR-007 — host preset (принято).** CTC v3 INT8, 4 CPU threads: RTF
0.105 против 0.159/0.267 на 2/1 потоках; одинаковый WER. Это single-pass
screening на i5-12450H, не универсальная Android-политика. Конфигурация
зафиксирована в `experiments/best_config.json` до запуска test40. После
release текущий RSS остаётся ~305 MiB против ~47 MiB до загрузки: нельзя
считать освобождение handle доказательством возврата всей RAM ОС; проверить
повторные циклы/allocator retention перед совмещением с diarizer/LLM.

Русские разговорные данные изучены: [ESpeech podcasts](https://huggingface.co/datasets/ESpeech/ESpeech-podcasts)
требуют принятия условий и CC-BY-NC; автоматически не скачиваются.
[ru-book-mix](https://huggingface.co/datasets/mexus/ru-book-mix-10h) — синтетика
из аудиокниг, не подмена настоящих разговоров. Нужен отдельный русский
conversation/RTTM набор с подтверждёнными условиями использования.

Тест: 40 новых записей / 415.56 s, load 2.31 s, полный RTF 0.114.
Параметры после test не менялись. Это read-speech подтверждение, не оценка
русских встреч. CTC отдаёт char tokens/timestamps; words пуст, отдельного
word alignment пока нет.

**ADR-008 — diarization baseline не принят.** FP32 при threshold .5
даёт сильную over-segmentation: confusion 40.81 s / total 79.91 s.
Не подставлять oracle num_speakers=4. Следующий шаг — порог на отдельном
validation и проверка embedding-модели; test-фрагмент не использовать
для выбора порога.

**ADR-009 — lifetime (принято).** После пяти циклов нет монотонного
роста RSS. Диагностический glibc malloc_trim(0) снижает RSS до ~65 MiB:
результаты согласуются с allocator retention, не с утечкой handles.
Не добавлять glibc-specific trim в переносимый SDK; контролировать фактический
RSS и lifecycle на Android отдельно.

**ADR-010 — clustering API (исправление).** Порог sherpa — cosine
dissimilarity `1−cos`, диапазон [0,2], а не вероятность. Снято ошибочное
ограничение `<1`; C ABI принимает (0,2]. Значение по умолчанию не меняется
без validation. Dataset preview API AMI validation вернул 500/501; берём
закреплённый исходный parquet вместо viewer, не меняем test на dev.

## Очередь

1. Test40 завершён; конфигурацию не перенастраивать по его результатам.
2. Выполнить FP32/INT8 diarization smoke и ASR lifetime probe.
3. Далее: VAD/chunking, resampler/MP3 A/B, согласованные русские диалоги с RTTM.
4. Затем file orchestrator/JSON, LLM и headless Android.
