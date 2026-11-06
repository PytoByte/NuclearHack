# Исследования и решения

07.11.2026. Рабочая ветка `dev`. Реализованный пайплайн — [ARCHITECTURE.md](ARCHITECTURE.md).

## Текущий этап по AGENT_AUDIO_HACKATHON.md

**Сейчас: этап 2, контролируемый раунд E17/E10–E12/E03/E04.**
Android baseline exp_0019 прошёл instrumentation на 4 ГБ; ручной SAF import/export
ещё проверяется отдельно и не считается пройденным только по instrumentation. Отдельный ASR screening не считается прохождением gate 1.5.
После baseline работа продолжается по E01–E23; останавливаться на baseline нельзя.

| Исходный пункт | Статус | Что осталось / свидетельство |
| --- | --- | --- |
| 0, 1, 2 — ТЗ, Q&A, ограничения/оценка | разобраны | Offline, verbatim JSON, 4-GB Android; никаких внешних вычислений пользовательского аудио |
| 3 — архитектура | частично | Native SDK принят пользователем; минимальный Android test host, без разработки визуального продукта |
| K.1 — окружение | готово | JDK17, API35/NDK27d, AVD4096MiB/x86_64/4cores; версии и хеши pinned |
| K.2/K.2a — runtime, веса, референсы | готово для baseline | sherpa/llama/ASR/diar/Qwen pinned; offline tar + лицензии; SHA проверены на AVD |
| K.3 — данные | частично | FLEURS val40/test40, AMI dev/test, 3 русских Dialogs MP3; natural Russian RTTM/CTM ещё нет |
| K.4 — gate подготовки | пройден | APK/JNI/веса работают offline на AVD4096MiB, exp_0019 |
| 1.1 — desktop ASR screening | основное выполнено | CTC v3/v2, RNNT v3, Whisper base; дальнейшие ASR A/B по этапу 2 |
| 1.2 — ASR Android / файл | выполнено | Тот же C API через APK/JNI, Android текст совпал с host |
| 1.3 — diarization/merge | baseline выполнен | Auto diar + word overlap merge реализованы; dev threshold .8 выбран, короткие реплики проблемны |
| 1.4 — LLM/JSON | baseline выполнен | JSON3/3 и genuine Qwen3 summary3/3 на Android; SAF export проверить отдельно |
| 1.5 — gate baseline | pipeline пройден; SAF pending | Offline Android3/3 + LLM, WER3.53%, fullRTF .773, pipelinePSS314MiB, LLMPSS1166MiB |
| 6 — метрики и журнал | частично | WER/CER/DER/time/RSS, hashes, CI и raw logs; cpWER есть; Android PSS profile идёт, JER/ошибка timestamps ещё нужны |
| 8 — автономный цикл | действует | A/B, worst cases, ≥3 гипотезы, accept/reject, сохранение лучшей конфигурации, следующий run |
| 9 — Anti-Vocale | исследован | Ports/chunks/lifecycle/eval полезны; сетевые части/remote/Firebase не копируются |
| 10 — команды/проверки | частично | Host tests/ABI есть; APK manifest без INTERNET, offline Android smoke идёт |
| 11 — поставка | впереди | SDK + offline модели/минимальный Android host, воспроизводимость, ограничения и demo |
| 12 — отчётность | действует | Статусы/ADR/гипотезы здесь, архитектура отдельно, сырые файлы в .audio-runs |

Файлы assumptions/model_licenses/progress/decisions/hypotheses из инструкции
сведены в этот документ по требованию пользователя; машинные hashes/configs/logs
хранятся отдельно. `task/` и пользовательский исходный план не изменяются.

## Этап 2 — покрытие E01–E23 (после gate baseline)

Ранние прогоны ниже — screening, а не объявление этапа 2 завершённым.

| ID | Проверяемая группа | Статус |
| --- | --- | --- |
| E01 | GigaAM v3/v2/Whisper | host screening есть; повтор на Android |
| E02 | CTC/RNNT/e2e | CTC/RNNT screening есть; e2e/verbatim ещё проверить |
| E03 | greedy/beam | проверить поддержку и A/B; не имитировать отсутствующий decoder |
| E04 | ru/autodetect | сравнить на поддерживаемом Whisper |
| E05 | chunks/overlap/silence/dedup | после файлового baseline |
| E06 | VAD off/on и padding | после baseline; отдельно короткие реплики |
| E07 | INT8/FP32/FP16 | diar smoke начат; ASR и Android A/B впереди |
| E08 | resample/gain/denoise | decoder alias test есть; ASR/DER A/B впереди |
| E09 | hints/hotwords | проверить capability выбранного decoder; без LLM-подстановок |
| E10 | segmentation/embeddings/clustering | baseline .5 отклонён; нужны альтернативные embeddings |
| E11 | auto/oracle dev | auto уже используется; oracle только диагностическая абляция |
| E12 | thresholds/minDuration/smoothing | dev threshold grid идёт; перенос на test без подбора |
| E13 | midpoint/overlap/frame attribution | после merge baseline, отдельные тесты |
| E14 | short/overlap/similar voices/gain | собрать и измерить strata |
| E15 | overlap и source separation | исследовать реально поддерживаемую speech separation; не выдавать music separation за неё |
| E16 | raw diarization при ASR denoise | только после E08, сравнить WER и DER раздельно |
| E17 | Android CPU threads 1/2/4 | host screening есть, Android впереди |
| E18 | quantization/load/inference/memory | host ASR/diar начат; LLM + Android впереди |
| E19 | lazy load/release ASR→diar→LLM | ASR lifecycle probe есть; полный pipeline + Android впереди |
| E20 | streaming PCM/ограниченные chunks | файловый disk spool + ограниченные ASR chunks реализованы; long-file profile впереди |
| E21 | 5/15/30/60 min, cancel/resume | после baseline; без ложного extrapolation коротких файлов |
| E22 | NNAPI/NPU/CPU fallback | проверить возможности реального AVD/runtime; hardware-only варианты отдельно |
| E23 | explicit memory budget/config | после Android RAM profile; без silent fallback |

Продвинутые realtime/cross-session/separation/UI из §7.4 — только после
стабильного baseline, с явной оценкой полезности/стоимости и причин неприменимости.

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
| exp_0014–16 | AMI validation, thresholds .5/.8/1.1 | DER 25.84/13.10/16.19%; auto 15/9/3 при 4 reference; .8 provisional |
| exp_0018 | Host full pipeline + отдельная LLM, 3 MP3 | WER 3.53% (6/170); cpWER 3.23/46.67/17.95%; short: 2 вместо 3 голосов. JSON3/3, LLM3/3, исходный SHA не изменён |
| exp_0019 | Android4096MiB offline, те же 3 MP3 + LLM | WER3.53%, cpWER17.65%, fullRTF .773; peakPSS314MiB, LLMPSS1166MiB; JSON/LLM3/3 |
| exp_0020 | Android CPU1t, те же 3 MP3, без LLM | WER3.53%, короткий speaker defect сохраняется; медленнее4t, сравнение2/4t идёт |

Агрегаты: `eval/results/<id>/`; конфигурации, hypotheses, stdout/stderr —
`.audio-runs/<id>/`. Старые эксперименты не перезаписывать. Machine registry:
`experiments/registry.csv`. Desktop WER/RTF/RSS отдельно от Android; Android
WER/RTF/PSS измерены в exp_0019; Android DER **not measured** (нет корректного русского RTTM).

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

| Validation-порог | DER | Auto speakers |
| --- | --- | --- |
| 0.5 (exp_0014) | 25.84% | 15 / 4 |
| 0.8 (exp_0015) | 13.10% | 9 / 4 |
| 1.1 (exp_0016) | 16.19% | 3 / 4 |

Validation/test аудио, эталоны и ID спикеров различны. Ранние viewer ошибки
не меняют источник: validation извлечён из pinned parquet с проверкой SHA256.

**ADR-011 — baseline file pipeline.** Disk spool вместо полного heap PCM,
ASR→release→diar→release→optional LLM. Char timestamps дают приближение,
не forced alignment; fallback не меняет текст. max600s — измеряемый baseline
лимит, не обещание поддержки часовых записей. Выход/trace атомарны и раздельны.

**ADR-012 — минимальный Android host.** Java/JNI без Gradle/Compose:
SAF импорт/экспорт, просмотр, отдельное summary. Это проверка standalone SDK.
Pinned SDK/JDK/AVD и локальная доставка tar не требуют сети на устройстве.

**ADR-013 — русские smoke данные.** Dialogs preview, 3 актёра,
OpenRAIL, revision a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd. Из реальных
записанных реплик детерминированно собраны 2/3-speaker MP3, pauses/short,
noise15dB/overlap350ms. Это structural smoke, не естественные встречи.
Интервалы размещения исходников включают тишину: не считать их speech RTTM
и не публиковать фиктивную DER. Эталоны доступны только scoring harness.
Host exp_0018 выполнялся при параллельной подготовке: timing функциональный,
не контролируемое сравнение скорости. WER/cpWER и валидность применимы.

## Очередь и причинные гипотезы

1. exp_0019 завершён; текущий раунд задан `experiments/phase2-queue.json`,
   выполняется serial runner без одновременных performance-тестов. Далее SAF smoke.
2. H1 (высокий приоритет): ERes2Net zh embeddings объединяют короткие русские
   голоса; WeSpeaker VoxCeleb ResNet34-LM может снизить confusion. Проверить
   на dev AMI, затем отдельное подтверждение; source license CC-BY4.
3. H2 (высокий): fixed20s разрезает слова; chunk10/25s и silence boundaries
   могут снизить deletions. Сравнить на тех же данных, без LLM-коррекции.
4. H3 (средний): threshold .8 снижает fragmentation, но склеивает short voices;
   отдельно minDuration/атрибуция, WER и cpWER, не задавая oracle в production.
5. H4 (средний): Android1/2/4t меняет RTF/RAM; host4t не доказывает optimum AVD.
6. H5 (средний): Q8→Q4 и доступный CPU ISA снизят память/время LLM;
   измерить отдельно качество резюме, не смешивать с основным transcript.
