# Исследования и решения

07.11.2026. Рабочая ветка `dev`. Реализованный пайплайн — [ARCHITECTURE.md](ARCHITECTURE.md).

## Текущий этап по AGENT_AUDIO_HACKATHON.md

**Сейчас: этап 2, приоритет A–D из AUDIO_RESEARCH_AGENT_SHORT.md: натуральные русские диалоги → ASR/пунктуация → diarization → границы → ARM.**
Рекомендации короткого агента приняты как ориентиры, не жёсткие правила. Дальнейшая работа — audio/native/eval;
UI/SAF/APK-поставка, LLM и длительный stress не расширяются. Существующий test host используется только для inference.
Baseline и подготовка завершены, исследование продолжается. Gate A/C ещё **не пройдены**: нет независимо проверенного
русского verbatim/word GT и разделения по людям; синтетический Dialogs и английский AMI этого не заменяют.

Новые условия пользователя: сравнить ASR с собственной пунктуацией и отдельный русский пунктуатор;
одновременно normalized WER, raw/punctuation-aware WER, CER и отдельные precision/recall/F1 пунктуации;
проверить ARM-бинарник и деградацию при коротких фрагментах. Chunked offline inference не называется causal streaming.

Завершено после exp_0046: checkpoints v2 на host и Android (47,57–59); FP32 ASR на host/Android хуже INT8 (51,60);
window shift (48–50,62–67); e2e CTC, hotwords,25s chunks,INT8 segmentation (52–55). .5 ускоряет diarization
в парном host dev опыте, но **AMI holdout DER36.10% против31.75%**, поэтому не принят глобально.
Synthetic cpWER gain не перекрывает holdout-регрессию. Между сериями произошёл сдвиг wall-time host/AVD:
не приписывать его алгоритмическим изменениям.

Сейчас собран silver pilot: три натуральных русских YouTube-разговора, ~8.9мин,2–3 голоса,
публичные Label Studio-аннотации с ручными исправлениями (7/10/29 текстовых сегментов относительно предсказаний).
Это **не независимо проверенный gold**; происхождение лицензии исходных видео не документировано,
publisher декларирует Apache-2.0. Данные не публикуем, храним revision/SHA и локальные RTTM/JSON.
Другой открытый источник DataHive CC-BY4:20 естественных разговоров,3ч,стереоканалы участников,но **без транскриптов**.
[YouTube источник](https://huggingface.co/datasets/leshinsky/ru-youtube-diarization),
[DataHive источник](https://huggingface.co/datasets/datahiveai/russian-conversations-sample).

Следующее: baseline на pilot и честное сравнение CTC/e2e/CTC+RUPunct; сегменты без разметки слов не использовать
для заявления timestamp MAE. Нужны проверка silver эталонов, независимые люди/сессии и полноценный русский test.

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
| 6 — метрики и журнал | частично | WER/CER/DER/time/RSS, hashes, CI и raw logs; cpWER есть; Android PSS/JER измерены; word timestamp GT/ошибки ещё отсутствуют |
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
| E01 | GigaAM v3/v2/Whisper | Android val40 exp_0028–31 завершён; CTC v3 сохраняет лучший компромисс |
| E02 | CTC/RNNT/e2e | e2e CTC Android WER6.47%, CI включает0; exp52/64/65: WER smoke прежний, но unknown 1/4/1; сравнение на натуральном pilot exp70 |
| E03 | greedy/beam | RNNT modified beam реально поддержан; exp26/34 завершены, тексты40/40 одинаковы; beam медленнее; CTC/Whisper greedy-only без FST graph |
| E04 | ru/autodetect | explicit language/auto API реализован; exp27 завершён: тексты40/40 одинаковы с ru |
| E05 | chunks/overlap/silence/dedup | 10s ухудшает WER8.19%,20/25s7.13%; overlap/dedup ещё не включён |
| E06 | VAD off/on и padding | Silero .5/pad250ms WER7.00%, .35/400ms7.13%; ускорения нет, off сохранён; short strata впереди |
| E07 | INT8/FP32/FP16 | FP32 ASR exp51/60 WER7.66%, Android~984MiB PSS; INT8 сохранён; FP32 segmentation лучшеINT8 |
| E08 | resample/gain/denoise | gain−18dB ухудшил WER7.79%; codec lag exp46~.125ms; denoise A/B не измерен |
| E09 | hints/hotwords | RNNT поддерживает; exp53 hints ухудшили WER7.66%, отвергнуты |
| E10 | segmentation/embeddings/clustering | WeSpeaker LM .4/.55/.8: DER26.05/24.04/35.31% dev; хуже ERes2Net13.10%, не принят |
| E11 | auto/oracle dev | exp_0024: oracle4 даёт DER16.19% хуже auto .8 (13.10%); production остаётся auto |
| E12 | thresholds/minDuration/smoothing | .8 frozen testDER31.75%; min.1/.2 не помог русскому short и ухудшил noisy cpWER; window.5 exp66 ухудшил AMI testDER36.10%; русский pilot exp71 |
| E13 | midpoint/overlap/frame attribution | midpoint идентичен max-overlap на3smoke; frame posteriors C API не отдаёт, не имитировать |
| E14 | short/overlap/similar voices/gain | Short cpWER46.67% остаётся; minDuration не исправил. Нужны альтернативная segmentation/embedding и отдельные strata |
| E15 | overlap и source separation | исследовать реально поддерживаемую speech separation; не выдавать music separation за неё |
| E16 | raw diarization при ASR denoise | только после E08, сравнить WER и DER раздельно |
| E17 | Android CPU threads 1/2/4 | exp_0020–22: RTF1.632/1.013/.826, WER одинаковый; 4t provisional, повтор впереди |
| E18 | quantization/load/inference/memory | ASR host+Android FP32/INT8 завершён; Q4 модель подготовлена, LLM research отложен |
| E19 | lazy load/release ASR→diar→LLM | ASR lifecycle probe есть; полный pipeline+Android measured; Q4 LLM не исследуется сейчас |
| E20 | streaming PCM/ограниченные chunks | файловый disk spool + ограниченные ASR chunks реализованы; long-file profile впереди |
| E21 | 5/15/30/60 min, cancel/resume | checkpoint v2 exp47/57–59 passed; long stress отложен ради точности |
| E22 | NNAPI/NPU/CPU fallback | CPU measured x86 AVD; ARM64 translation exp68 SIGSEGV; NPU/physical ARM не measured |
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
| exp_0020–22 | Android CPU1/2/4t, без LLM | FullRTF1.632/1.013/.826; WER3.53%, PSS~310MiB; 4t provisional |
| exp_0017 | Frozen .8, AMI test180 | DER31.75%, JER43.80%, 13/4speakers; лучше .5, но сильная fragmentation остаётся |
| exp_0023 | WeSpeaker LM / AMI dev / .8 | DER35.31%, JER82.99%, 1/4speaker; порог ERes2Net не переносится автоматически |
| exp_0024 | ERes2Net oracle4 / AMI dev | DER16.19%, JER43.16%, 3 output speakers; не лучше auto, oracle не принимать |

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

**ADR-014 — E17 Android preset (предварительно).** В одном serial раунде
1/2/4t: fullRTF1.632/1.013/.826, WER3.53% неизменен, PSS310/308/310MiB.
Baseline4t с LLM между файлами дал .773: заметен разброс/cache/lifecycle.
Сохраняем4t; повторить пары2/4t перед заявлением устойчивого ускорения.

**ADR-015 — первая альтернатива embedding (не принята).**
[WeSpeaker ResNet34-LM](https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM),
CC-BY4, SHA и исходная card в model lock. При .8 сливает dev4→1, DER35.31%.
Это отклоняет перенос порога, а не весь класс embeddings: следующий grid .4/.55
на validation, затем независимое подтверждение. Oracle4 на ERes2Net не исправил
ошибки; вероятны segmentation/embedding проблемы, а не только cluster count.

## Раунд 2: accuracy и перенос на Android

Android4GB/x86_64, FLEURS validation40, 4 CPU threads, без одновременных
нагрузочных задач. RTF ниже включает decode+ASR, отдельно от загрузки.

| Run | Модель | WER | RTF | Peak PSS MiB |
| --- | --- | --- | --- | --- |
| exp_0028 | GigaAM-v3 CTC INT8 | 7.13% | .223 | 333 |
| exp_0029 | GigaAM-v2 CTC INT8 | 7.53% | .338 | 659 |
| exp_0030 | GigaAM-v3 RNNT INT8 | 7.13% | .221 | 506 |
| exp_0031 | Whisper base INT8 ru | 27.08% | .325 | 620 |
| exp_0032 | GigaAM-v3 e2e CTC INT8 | 6.47% | .194 | 334 |

Paired bootstrap по37 source sentences/10k, e2e−CTC95%CI=[−3.28;+2.09]п.п.:
доказанного выигрыша нет. У RNNT Android исправилась одна substitution
«исносу→износу» относительно host; мобильные результаты считать основными.
Сравнение/10 худших клипов: `eval/results/android-asr-comparison.json`.

Host exp_0033–40: fresh CTC7.13%; RNNT greedy7.27%, beam exp_0026 дал
**идентичные40 текстов**, но медленнее matched4t greedy (.224 vs .145 RTF).
Whisper ru/auto exp_0005/27 также идентичны40/40. e2e CTC6.47%, CER2.13%.
SileroVAD .5/pad250ms7.00%, .35/pad400ms7.13%; small effect без ускорения,
поэтому off. Чанки10s8.19%,20s7.13%,25s7.13%; −18dB7.79% — не улучшение.

Host exp_0041/42 WeSpeaker dev DER26.05/24.04% при thresholds.4/.55:
точные4speakers при .55 **не означают** хорошую DER. exp_0043 minOn/Off.1/.2:
short cpWER46.67% сохраняется, noisy cpWER20.51% хуже baseline17.95%; reject.
exp_0044 midpoint byte-identical baseline3/3; max-overlap сохранён.

**ADR-016 — воспроизводимость.** Старые runs сохраняют git SHA/dirty flag,
model/config/SDK hashes; точного source snapshot у них нет. Старый SDK/CLI/APK
сохранён локально в `.audio-runs/pre-checkpoint-build` перед новой сборкой.
Новые `make native-build`/`mobile-build` сохраняют source tar, бинарники,
runtime hashes и CMake cache в `.audio-runs/builds`, а harness копируется
в каждый run. Не выдавать ранние dirty-tree runs за bit-reproducible builds.

**ADR-017 — FP32 без подмены опыта.** У sherpa HF export есть только INT8.
Взят исходный FP32 `istupakov/gigaam-v3-onnx` revision322c3b29492673eb7d0b434bfa9dfb8653e34d02;
добавлены только sherpa metadata по upstream exporter. Тензоры не меняются,
initializer SHA и итоговый SHA зафиксированы. Не считать dequantized INT8
настоящим FP32 A/B. Dev bootstrap воспроизводит адаптацию onnx1.17.0.

**Следующие три гипотезы:** (1) window shift.25/.5 уменьшит повторные
segmentation/embedding вычисления при допустимой DER; (2) FP32 покажет,
не теряет ли INT8 слова; (3) source/codec/denoise A/B проверит границы и
устойчивость, прежде чем переносить предобработку в основной SDK.
Checkpoint exp_0045 и long stress проверяют устойчивость отдельно от качества.

**Этап exp_0045 закрыт:** реальный cancel после первого ASR-чанка, resume,
полный replay без ASR load, побайтное совпадение с fresh control. Native
PCM/model SHA совпали с Python. Изменённый input/chunk не использует cache;
повреждённый cache отклонён, исходный исправный cache не затронут.
После этого добавлены tail-safe policy/cachev2 и общий heavy-job guard;
повторная проверка — exp_0047.

**exp_0056 — подтверждение нового APK:** offline3MP3 + separate LLM3/3,
WER3.53%, strict JSON3/3; основная расшифровка не меняется. Повторный
Android smoke после существенных изменений обязателен и выполнен.
Новый Java/JNI JobOptions передаёт явные ASR/diar/window/checkpoint параметры.

**Следующий запущенный раунд:** `experiments/phase2-runtime-queue.json` —
checkpointv2, matched window.1/.25/.5, FP32, e2e full-file, RNNT hotwords,
chunks25, INT8 segmentation, Android cancel/resume/cache и FP32 deployment.
Qwen Q4 подготовлен локально из pinned Q8 (604→373MiB tensor data);
это ещё не измеренный peak RAM/качество. Source GGUF, quantizer SHA и
результирующий SHA в model lock; официальный Q4 артефакт не утверждается.


## ADR — дополнительные условия, 07.11.2026

- **Метрики text-v2 (до новых результатов):** прежняя NFC/lower/ё→е normalization v1 неизменна. Raw WER сохраняет case/пунктуацию;
  punctuation-token WER отделяет каждый знак от lexical tokens и нормализует только case/ё. CER — normalized и raw.
  Пунктуация `. , ? ! : ; — - … « » " ( )` считается по отдельным символам: TP только после совпавшего слова
  в edit alignment (и BOS), остальные FP/FN; micro/per-mark P/R/F1. Дополнительно conditional F1 только на совпавших
  словах: не скрывать lexical errors за этим условным числом. Повторы/междометия/числа не удаляются.
- **Кандидат:** [RUPunct_small INT8 ONNX](https://huggingface.co/ekhodzitsky/rupunct-small-onnx),
  revision `c4a35be7e4a413cdfb08427db75b621b571569c9`,29.3MB,MIT по card,русский tagger33labels.
  Eval backend ORT CPU1.23.2 отдельно от native ORT1.28.2; не объявлять mobile integration готовой.
  Реконструируем исходные слова, разрешаем только case/marks; lexical invariant проверяется. Контекст100слов,без truncation.
- **Спикеры:** старый `predicted_speakers` включает `speaker_unknown`. Добавлены `known_speakers_count`, unknown utterance/word fractions;
  исторические метрики не перезаписываются. Улучшение cpWER с ростом unknown не принимается автоматически.
- **ARM:** AVD API35 объявляет arm64-v8a через `libndk_translation.so`. exp_0068 реально установил ARM64-вариант,
  но получил SIGSEGV в translated `/memfd:exec`,до результата; повтор с non-incremental install тоже упал.
  Это блокер данного способа проверки, **не** доказательство дефекта на физическом ARM и **не** подтверждение ARM-качества.
  Native cross-build остаётся пройденным отдельно; для скорости/памяти целевого ARM требуется физический девайс.


## Натуральные русские данные: выбор источников

Популярные [OpenSTT](https://github.com/snakers4/open_stt) и [Golos](https://openslr.org/114/) подходят для ASR-проверки,
но не заменяют размеченные speaker turns. В OpenSTT `asr_calls_2_val` publisher указывает ручную разметку телефонной речи;
[описание Microsoft](https://learn.microsoft.com/en-us/azure/open-datasets/dataset-open-speech-text).
Архив Zenodo4899885:805251737bytes,MD5`5146eef0aa64af41e17c5ec18a9cab5c`,CC-BY-NC4.0;
используется только для исследования,не для поставки. В отличие от него `asr_public_phone_calls_2` помечен Internet+ASR:
не выдавать автоматические тексты за ручной эталон. YouTube silver pilot выбран для первоначального совместного ASR/diar анализа,
потому что сохраняет длинные реальные разговоры и исправленные speaker labels; его малый размер/неясный speaker split отмечены явно.

| Опыты | Проверка | Решение |
| --- | --- | --- |
| 47,57–59 | checkpoints v2 host/Android,cancel/resume и fully cached без ASR load | принято, текст byte-equal |
| 48–50,62–67 | window shift.1/.25/.5; AMI и русский smoke | .5 кандидат,не общий default: holdout DER+4.35pp |
| 51,60,61 | действительный FP32 checkpoint vs INT8 | FP32 отвергнут: WER7.66%,больше RAM; разные экспорты — confound |
| 52,64,65 | e2e CTC в полном pipeline | inconclusive: normalized WER прежний,ранние слова чаще unknown |
| 53–55 | hotwords,chunk25,INT8 segmentation | отвергнуты,выигрыша нет/есть ухудшения |
| 68 | ARM64 runtime через native bridge | crash,качество не измерено |
| 69–71 | натуральный silver pilot: baseline,e2e,window.5 | завершено; предварительные метрики,не независимый test |
| 72–79 | punctuation/короткие offline фрагменты/DER-JER/OpenSTT | завершено; ARM и gold-валидация впереди |


### exp_0069–0072 — первый натуральный silver pilot (3 записи,1203 нормализованных слова)

| Вариант | normalized WER | punctuation-token WER | normalized CER | punctuation micro F1 | cpWER |
| --- | --- | --- | --- | --- | --- |
| CTC,window.1 | 14.30% | 30.55% | 7.67% | 0 | 54.20% |
| e2e CTC,window.1 | 14.21% | 21.67% | 7.56% | 65.18% | 52.95% |
| CTC + RUPunct INT8 | 14.30% | 27.15% | 7.67% | 40.68% | не пересчитывался: ASR-текст/спикеры не менялись |
| CTC,window.5 | 14.30% | — | — | — | 43.64% |

E2e−CTC lexical WER CI95 по3записям: [-1.02;+1.53]pp,2000bootstrap,seed42: **inconclusive**.
RUPunct lexical sequence сохранена во всех файлах; пунктуация помогает относительно отсутствующей,но уступает e2e.
Не переносить эти цифры на gold: publisher исправлял исходные ASR-гипотезы,неизвестна полнота проверки/стиль знаков.
Window.5 даёт2/3/3 известных голоса против6/8/5 baseline и меньше cpWER; это поддерживает гипотезу over-splitting,
но не отменяет английскую holdout-регрессию. Основной preset не изменён.
exp73 остановлен **до inference** из-за ошибочного формата путей в новом fragment harness; сохранён как failure,
исправленный повтор получает новый ID75,не затирает73.


### exp_0074–0075 — diarization и короткие фрагменты

На silver pilot DER26.07%→21.52% при window.5,но JER34.81%→40.59%.
Последний файл DER33.87%→34.20%: выигрыш неравномерен,редкие голоса остаются проблемой.
Политика: collar250ms,UEM0..clip_end,overlap включён; время ошибок суммируется для DER,
JER учитывает эталонных говорящих. Никакого word timestamp MAE без word GT.

Fragment test75: **только4 не-overlap реплики /97слов**,8–25s по publisher turns.
Одинаковое аудио и CTC: целая реплика WER10.31%;10s11.34%;5s14.43%;2s23.71%.
Это потеря контекста на малом диагностическом срезе host; не целый длинный файл,не ARM,не causal streaming.
Далее гипотеза76: threshold1.1 с исходным window.1 может уменьшить fragmentation без изменения ASR;
критерии: DER+cpWER,minority JER и ошибки по файлам,а не только число найденных голосов.


### exp_0076–0077 — число кластеров не является метрикой качества

Threshold1.1 при window.1: известные голоса2/2/3 вместо6/8/5,но DER26.27% (baseline26.07%),
JER48.70% (34.81%),cpWER54.45% (54.20%). **Reject**: over-merging теряет меньшинство,
простое уменьшение числа спикеров не решает задачу. Следующие причинные гипотезы:
(1) другой embedding с собственным порогом;(2) границы/слова у коротких turn;
(3) boundary-aware chunking вместо2s нарезки. Не возвращаться к blind threshold sweep на test.


### exp_0078–0079 — популярный OpenSTT, ручные телефонные транскрипты

Заморожены40 lexical-dev фрагментов,140.65s,408слов: hash-ranked выбор из source validation,
2..20s,>=3слова. Архив проверен по publisher MD5,дополнительно сохранён SHA256.
Никаких speaker/word-time/punctuation gold; принадлежность людей/исходных звонков неизвестна,
поэтому эта выборка не объявляется speaker-disjoint test и не используется для доказательства значимости.

CTC INT8 WER17.65%,CER6.62%; e2e CTC WER20.59%,CER10.02%.
**Не заменять CTC на e2e глобально:** улучшение пунктуации на YouTube silver не компенсирует lexical-регрессию телефона.
Отдельный RUPunct пока остаётся research-кандидатом: lexical-preserving,но F1 недостаточен для принятия в SDK.

Воспроизведение: `make research-pilot` подготавливает pinned runtime/модели,YouTube silver+OpenSTT40
и исполняет `experiments/phase3-russian-pilot.json` последовательно. Имеющиеся завершённые IDs пропускаются,
частично упавшие не перезаписываются; ошибка73 сохранена отдельно,исправленный job75 включён в очередь.
Данные/сырые результаты остаются локально,в Git — manifests/хеши/агрегаты. Тесты scoring/automation проходят.

**Текущий итог:** этап2 продвинут до натурального silver baseline,пунктуации и fragment-quality; это не завершение gate A–D.
**Далее:** проверенный независимый русский conversational gold,другой embedding/границы слов,
физический ARM64 (вопрос о доступном устройстве задан),chunk boundary/overlap policy с сохранением слов.
UI/LLM/длинный stress не расширяются. Timestamp MAE и ARM throughput по-прежнему не измерены.


### exp_0080 — проверка обновлённого Android eval

Actual app ABI x86_64,AVD4096MiB,offline,APK SHA verified; provenance соответствует выбранной ABI.
FLEURS40 WER7.1334% совпал с baseline,все text-v2 метрики выгружены. Это functional revalidation,
не ARM-подтверждение и не доказательство ускорения: wall-time между сериями существенно дрейфовал.
`make research-pilot` проверен до конца; frozen datasets воспроизвелись без изменения hashes,
готовые опыты сохранены. Проверены model SHA,Python syntax,scoring и automation; `task/` не изменён.
