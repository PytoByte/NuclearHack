# Исследования и решения

07.11.2026. Рабочая ветка `dev`. Реализованный пайплайн — [ARCHITECTURE.md](ARCHITECTURE.md).

## Текущий этап по AGENT_AUDIO_HACKATHON.md

**Сейчас: этап2, posterior merge перенесён в полный native file API; квалификация203–214 завершена.**
Завершены window/turn-embedding/избирательные short-turn опыты132–139; два последних
метода не приняты из-за регрессии чистого двухголосого диалога. Screening Sortformer
v2.1 завершён:bounded context/state,buffered vs low-latency,whole vs window frontend143–148.
149–161: MatMul-only INT8/transfer завершены; **Sortformer v2.1 не проходит regression**,
несмотря на dev выигрыш. Frontend control164 завершён;новая8slot-модель smoke165 прошла,
natural dev/known transfer166–174 завершены. Additive native streaming CABI реализован/проверен175;
Natural parity176 и4GBx86AVD177–183 завершены; low-профиль не выдерживает real-time.
Q4 A/B184–185 завершён и отклонён. Проверен целиком NeMo-Speech.cpp187–194,
заимствование posterior merge190 улучшило cpWER. Новый opt-in file API203–214
реализован и проверен на host/x86 AVD; основной файловыйpreset сохранён.
В `src/audio` реализован opt-in `nh_transcribe_file_with_refinement`; старые ABI/default вызовы сохранены.
Exact native/prototype parity5/5,граница EOF исправлена,ASan/UBSan и ARM64/x86 cross-build пройдены.
На AVD4096MiB/x86_64 три пары:cpWER42.97→33.16%,medianRTF.302→.312 (+3.2% wall),sampledPSS~369MiB.
WAV filename-hint bug найден/исправлен; decoder PCM host/Android совпал поSHA всех2802748frames.
**ARM runtime/Word timestamp MAE не измерены**: пользователь подтвердил только доступное окружение;
ручных word GT нет. UI/SAF/LLM/длинный stress не расширяются. Исследование продолжается,а не останавливается на gates.

Данные:3 natural RU silver dev +3 source-file transfer snippets,OpenSTT manual phone40,FLEURS40/40,
AMI English,Dialogs3 structural. Source corpus small/publisher-reviewed,люди не верифицированы как disjoint;
strict gold gate A/C не заявлен. Шесть full-source аннотаций дополнительно проверены на shared6grams:
ни одна пара не превысила2%;это исключает крупные текстовые дубликаты,не доказывает независимость людей.

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

Baseline,embeddings,punctuation и native refinement завершены (69–128). Далее — короткие голоса; сегменты без разметки слов не использовать
для заявления timestamp MAE. Нужны проверка silver эталонов, независимые люди/сессии и полноценный русский test.

| Исходный пункт | Статус | Что осталось / свидетельство |
| --- | --- | --- |
| 0, 1, 2 — ТЗ, Q&A, ограничения/оценка | разобраны | Offline, verbatim JSON, 4-GB Android; никаких внешних вычислений пользовательского аудио |
| 3 — архитектура | частично | Native SDK принят пользователем; минимальный Android test host, без разработки визуального продукта |
| K.1 — окружение | готово | JDK17, API35/NDK27d, AVD4096MiB/x86_64/4cores; версии и хеши pinned |
| K.2/K.2a — runtime, веса, референсы | готово для baseline | sherpa/llama/ASR/diar/Qwen pinned; offline tar + лицензии; SHA проверены на AVD |
| K.3 — данные | частично | FLEURS40/40,OpenSTT40,AMI,Dialogs3,6naturalRU silver RTTM; manual word CTM нет |
| K.4 — gate подготовки | пройден | APK/JNI/веса работают offline на AVD4096MiB, exp_0019 |
| 1.1 — desktop ASR screening | основное выполнено | CTC v3/v2, RNNT v3, Whisper base; дальнейшие ASR A/B по этапу 2 |
| 1.2 — ASR Android / файл | выполнено | Тот же C API через APK/JNI, Android текст совпал с host |
| 1.3 — diarization/merge | baseline выполнен | Auto diar + word overlap merge реализованы; dev threshold .8 выбран, короткие реплики проблемны |
| 1.4 — LLM/JSON | baseline выполнен | JSON3/3 и genuine Qwen3 summary3/3 на Android; SAF export проверить отдельно |
| 1.5 — gate baseline | native pipeline пройден; UI вне scope | Offline Android3/3 + LLM, WER3.53%, fullRTF .773, pipelinePSS314MiB, LLMPSS1166MiB |
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
| E08 | resample/gain/denoise | gain−18dB ухудшил WER7.79%; codec lag exp46~.125ms; DPDFNet A/B202 без выигрыша (WER3.53→4.12%), off |
| E09 | hints/hotwords | RNNT поддерживает; exp53 hints ухудшили WER7.66%, отвергнуты |
| E10 | segmentation/embeddings/clustering | WeSpeaker/TitaNet отвергнуты; native ERes global.4 opt-in проверен99–128; Sortformer v2 отклонён; Q8 posterior file API203–214 проверен |
| E11 | auto/oracle dev | exp_0024: oracle4 даёт DER16.19% хуже auto .8 (13.10%); production остаётся auto |
| E12 | thresholds/minDuration/smoothing | .8 frozen testDER31.75%; min.1/.2 не помог русскому short и ухудшил noisy cpWER; window.5 exp66 ухудшил AMI testDER36.10%; русский pilot exp71 |
| E13 | midpoint/overlap/frame attribution | midpoint идентичен max-overlap на3smoke; старый diarizer API не отдаёт posteriors; новый Nemotron C ABI отдаёт, posterior merge190 перенесён в file API203–214 |
| E14 | short/overlap/similar voices/gain | Short baseline46.67%; turn/selective135–139 дают6.67%,но clean регрессирует — reject; другая segmentation143–147 |
| E15 | overlap и source separation | исследовать реально поддерживаемую speech separation; не выдавать music separation за неё |
| E16 | raw diarization при ASR denoise | только после E08, сравнить WER и DER раздельно |
| E17 | Android CPU threads 1/2/4 | exp_0020–22: RTF1.632/1.013/.826, WER одинаковый; 4t provisional, повтор впереди |
| E18 | quantization/load/inference/memory | ASR host+Android FP32/INT8 завершён; Q4 модель подготовлена, LLM research отложен |
| E19 | lazy load/release ASR→diar→LLM | ASR lifecycle probe есть; полный pipeline+Android measured; Q4 LLM не исследуется сейчас |
| E20 | streaming PCM/ограниченные chunks | disk spool/ASR chunks + bounded speaker pass203–214 реализованы; long-file stress впереди |
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


## Спринт embeddings/телефонного ASR — exp_0081–0084, завершён

Пользователь подтвердил: пока **только доступное окружение**,физический ARM недоступен.
Продолжаем на host и x86 Android AVD; ARM runtime quality/performance остаются непроверенными,
повторно устройство не запрашиваем. Native bridge SIGSEGV68 не трактуется как физический ARM результат.

Причинная гипотеза: ERes2Net baseline обучен в другом домене; WeSpeaker с собственным порогом
может уменьшить speaker confusion на натуральных русских разговорах. Уже проверенные на AMI пороги
.4/.55 переносятся в pilot-development без просмотра новых результатов; остальные параметры baseline69 неизменны.
Очередь `experiments/phase4-embeddings.json`:81/82 full pipeline,83 DER/JER из frozen traces.
Сравниваем DER/JER/cpWER/unknown и каждый файл. Pilot остаётся silver dev,не независимым тестом.

Разбор5 худших OpenSTT файлов baseline78: два случая грубой фонетической подмены/конца фразы;
один — ошибка числительного и слитное/раздельное написание сложного слова;
ещё два — нестандартные слитные написания в reference и потеря междометия.
Normalization v1 **не меняется после просмотра**; ошибки орфографии эталонов не исправляем скрыто,
удаление filler остаётся deletion. Следующая ASR-гипотеза: RNNT на том же phone dev40 может
лучше справляться с фонетическими ошибками,даже если не выигрывал на FLEURS.


### exp_0081–0083 — WeSpeaker на натуральном русском pilot

| Embedding / threshold | DER | JER | cpWER | Known speakers по файлам |
| --- | --- | --- | --- | --- |
| ERes2Net/.8 (69) | 26.07% | 34.81% | 54.20% | 6/8/5 |
| WeSpeaker/.4 (81) | 38.87% | 47.72% | 80.88% | 5/12/6 |
| WeSpeaker/.55 (82) | 33.05% | 45.57% | 68.33% | 2/6/3 |

WER14.30% одинаков во всех случаях: менялся embedding+его порог,не ASR.
Оба проверенных варианта **reject** относительно69; это не утверждение о любых порогах/доменах WeSpeaker.
Простой переход к другому embedding не устранил confusion. Следующая модель-кандидат — совместимый TitaNet,
но потребуется pinned source/license и отдельный dev threshold; никаких выводов из чужих benchmark numbers.


### exp_0084 — RNNT на телефонном dev40

RNNT WER16.42% (67/408 ошибок) против CTC17.65% (72/408),но CER7.24% против6.62%,
deletions20 против14,inference RTF.059 против.036 и process RSS~648 против417MiB.
Небольшой lexical выигрыш не подтверждён независимыми звонками/спикерами,а CER/fillers и стоимость хуже:
**inconclusive**,основной CTC не заменяется. Это отдельные host прогоны,не controlled ARM speed comparison.

Очередь81–84 завершена последовательно,ошибочные гипотезы не приняты. Далее:
новый embedding с собственной калибровкой и refinement границ коротких turn;
ARM остаётся deferred по подтверждённому ограничению окружения. Без UI/LLM и повторных запросов устройства.


## TitaNet и диагностика alignment (85–89, завершено)

TitaNet-large ONNX pinned:csukuangfj revision0743f301…,SHA d51abcf3…,101405493bytes.
[Upstream NVIDIA card](https://huggingface.co/nvidia/speakerverification_en_titanet_large),CC-BY4,
upstream revision0dc382f4…; card и canonical license сохранены с hashes. Модель другого training domain,
не ожидаем автоматически русского выигрыша. Предварительно зафиксированы cosine-distance thresholds.4/.6/.8,
window.1,minDuration.3/.5,тот же ASR и pilot-development. Ни один test для подбора не используется.

**exp85:** Python diagnostic reproduces native merge byte-for-byte по3файлам; при замене только diarization
на publisher speaker turns cpWER54.20%→17.46% (WER14.30% неизменен). Основной резерв здесь — diarization,
не переписывание ASR-текста. Чувствительность reference-turn oracle к shift слов:-200ms21.36%,-100ms19.45%,
0ms17.46%,+100ms16.54%,+200ms16.21%. **Oracle only**,не production и не timestamp MAE:
publisher boundaries не word GT; не подбирать общий offset по этим числам.


До просмотра результатов TitaNet выбран четвёртый publisher recording `clips/sFt2qKDPrj4.opus`
(project35 JSON той же frozen revision) для **silver session holdout**,первые<=180s,полные turn.
Ни thresholds,ни clip selection не подбираются по его распознаванию. Люди/источник лицензии всё ещё не независимо
проверены; source silver не превращается в gold. Сначала baseline,затем один выбранный на dev кандидат.
Повторное использование этой сессии для выбора следующих настроек не будет называться независимым test.


Следующая preregistered hypothesis — **global reclustering**,research-only:
до3 самых длинных predicted spans≥.8s,центр каждого≤8s,в сумме2..20s на initial cluster;
pinned native sherpa embedding,complete-link cosine thresholds.2/.3/.4.
Predicted одновременно активные голоса — cannot-link; oracle speaker count/labels не используются.
Baseline69 words сохраняются,DER/JER/cpWER оцениваются после выбора mappings.
Прототип хранит PCM только исследовательских3min fixtures в памяти; это не production RAM-профиль.


### exp_0086–0089 — TitaNet dev screening

| Порог | DER | JER | cpWER | Known speakers |
| --- | --- | --- | --- | --- |
| .4 | 43.59% | 49.20% | 87.61% | 12/19/15 |
| .6 | 28.75% | 40.23% | 58.52% | 6/11/8 |
| .8 | **21.09%** | **34.17%** | **45.22%** | 4/6/6 |

Baseline ERes2Net.8:26.07/34.81/54.20%. Только TitaNet.8 улучшил все3метрики;
он выбран **до** запуска single-session holdout90–92. Reference speaker independence неизвестна,
это проверка переноса между записями,не gate gold. Рабочий preset пока прежний.
93/94 проверяют global reclustering на dev отдельно для ERes2Net baseline69 и TitaNet88.


### exp_0090–0094 — перенос и global reclustering

Single-session holdout (`sFt2qKDPrj4`,177.9s,2 reference voices):
ERes2Net baseline90 DER12.98%,JER11.13%,cpWER20.65%; frozen TitaNet.8 candidate91
DER54.03%,JER72.96%,cpWER103.23%. WER13.55% совпадает. **Reject TitaNet promotion**:
предварительный dev выигрыш не переносится,сильный speaker confusion при сходном числе кластеров.
После просмотра этот holdout считается известной regression-сессией,не новым независимым test.

| Global reclustering / threshold | dev DER | dev JER | dev cpWER |
| --- | --- | --- | --- |
| ERes2Net/.2 | 26.07% | 34.81% | 54.20% |
| ERes2Net/.3 | 22.54% | 32.06% | 48.38% |
| ERes2Net/.4 | 21.16% | 32.97% | 44.64% |
| TitaNet/.2 | 18.80% | 31.37% | 39.32% |
| TitaNet/.3–.4 | 17.87% | 30.71% | 37.16% |

Выбран для дальнейшей проверки **ERes2Net global.4**: уменьшает DER/cpWER без замены embedding,
хотя на dev меньше JER у.3. Выбор сделан по dev93,не по результату нового global holdout.
Повторное вычисление cluster embedding использует runtime C API,эталоны — только scoring,
reference count не передаётся. Production ещё не менялся. TitaNet global не считается решением регрессии91
без отдельной проверки; не прикрывать плохую переносимость хорошими dev числами.


### exp_0095–0098 — проверка global refinement и второго пунктуатора

На известной regression-сессии global ERes2Net.4 не меняет baseline (DER12.98%,cpWER20.65%).
Новая movie-сессия заранее frozen:175.17s,3голоса,377слов; zero shared6grams с тремя dev snippets.
Publisher исправил90 текстовых сегментов в полной записи; provenance всё равно silver.
WAV-префикс получен Range0..34560349 (точный диапазон/хеш — в lock),полный1.145GB source **не** скачан/не SHA-verified.
Диапазон и source revision закреплены; производный mono16k WAV имеет собственный SHA; аудио не перекодировано перед native eval.
Выбран только threshold.4,без подбора на этой сессии:
DER25.02→21.25%,JER19.44→16.59%,cpWER43.24→33.42%,WER15.38% неизменен.
Это основание переносить **опциональный** refinement в SDK и проверять parity/4GB,но не объявлять gold gate пройденным.

Пунктуация98: Horizon-small268MB,Apache2,revision12b02a85…,last-subtoken labels,CPU ORT,
100words/window,max512tokens,сохраняет слова/case. MicroF146.55% противRUPunct40.68% и e2e65.18%;
punctuation-token WER24.93% против27.15% и21.67%. Lexical sequence сохранена3/3.
Большая модель улучшает RUPunct,но не оправдывает production integration против текущего e2e tradeoff;
ни один отдельный пунктуатор пока не принят в SDK.

**План перед99–128 (выполнен ниже):** перенос global ERes2Net.4 в native как opt-in `nh_transcribe_file_with_refinement`.
Существующие структуры и default API не меняются. После diarizer/release — embedding/release → clustering → merge.
Рабочая PCM-выборка≤20s/cluster,до3spans,cluster cap128default/256max; cannot-links сохраняются complete linkage.
Далее native/prototype parity,ASan/UBSan,ABI cross-build,Android4GB и callback cancel/budget checks.


Native99 на3dev файлах завершён. Native100 обнаружил ограничение валидатора: upstream последний
segmentation frame заканчивается177927ms при audio177900ms. Сбой до export,не crash; сохранён.
Коррекция: исходные diar timestamps допускают backend EOF quantization,а чтение PCM всегда clamp к frames;
слова/исходные turn timestamps не переписываются. Повтор104 получает новыйID,далее parity102.


### Decoder regression115 и невалидные Android106–112

Host controls105 прошли:cap1→NH_INVALID_ARGUMENT до refinement load;mid-stage cancel→NH_CANCELLED;
callback reentry→NH_BUSY;во всех случаях нетfinalexport. Native parity102 exact5/5.

AVD106–111 **не являются валидными performance/quality измерениями**: header-identical movie WAV,
сохранённый под legacy test-host `.mp3` именем,декодировался всего в279frames вместо2802748.
Это extension-priority miniaudio,false-positive MPEG sync внутриPCM; повторено на host115.
Детерминированный synthetic WAV с MPEG-sync bytes:16000frames при`.wav`,28840при`.mp3`.
Предварительная проверка другого WAV по1s не выявляла data-dependent false positive; вывод об общем sniffing был слишком широким.
Cancel112 поэтому не достиг embedding-stage и сохранён как failure. Сырые результаты106–112 не переписываются.

Исправление SDK:RIFF/RF64 WAVE header явно выбирает WAV backend до filename hint.
Добавлен regression test,который падает на старом SDK;после исправления сравнивает весь PCM/offsets.
Android eval теперь сверяет decoded frames с frozen duration/host probe (tolerance2ms) до публикации метрик;
ошибка останавливает очередь. Повторы117–125 получают новыеIDs;source bytes/модели не меняются.


### exp_0116–0128 — исправление декодера и квалификация native opt-in

После WAV-header priority fix regression116 даёт полную PCM-идентичность при разных suffix:
synthetic16000/16000frames,movie2802748/2802748. Тест сначала воспроизвёл ошибку на старом SDK,
затем прошёл;повторены native-tests,ASan/UBSan,mobile-build и APK/офлайн проверки.

Три свежих процесса baseline117/119/121 vs refinement118/120/122,одинаковые SHA входа/моделей/APK:
median52.916→54.592s,RTF.3021→.3116,median paired ratio1.03167;
max sampledPSS377947→378014KiB (~369MiB),process-lifetimeRSS458540→458308KiB.
ASR words/timestamps и initial diarization внутри каждой A/B пары exact equal.
Android cpWER42.97→33.16%,model-load/feature stage cancellation123 безfinalJSON.
MP3 regression125:WER3.53%,cpWER3.23/46.67/17.95% — прежние результаты,без ухудшения.

Strict host/Android full-JSON equality analysis124 не прошёл и сохранён отдельно.
В Android есть5 lexical substitutions относительноhost;сумма ошибок противэталона меньше на1.
Анализ126 не скрывает дельту и проверяет инвариантность **внутри target A/B**.
Input PCM128 побайтно совпадает сhost SHA`3ed9bd9e…`;различия появляются послеdecode,
но конкретные feature/inference операции не локализованы. Нельзя приравнивать fresh-process reload к coldboot:
OS file cache не сбрасывался. Эти timings — x86 AVD,не физический ARM.

**Решение:** принять реализацию/контроль ресурсов experimental opt-in ERes2Net global.4;
сохранитьdefaultoff и исходный main preset до более независимого корпуса.
Dispatch теперь сохраняет stdout/stderr/config/failure и требуетmetrics приexit0;
failed/invalid IDs не повторяются. Три model-free lifecycle tests проверяют эти правила.

### exp_0129–0131 — короткий третий голос

Initial threshold.5 +global.4:short cpWER46.67% прежний,noisy17.95→33.33% — reject.
Threshold.65:все3структурных результата прежние — выигрыша нет.
Oracle3 diagnostic131 всё ещё возвращает2голоса иcpWER46.67%;oracle source occupancy
даёт6.67% при тех же ASR words. Точное число голосов не входит вproduction.
Это свидетельствует о проблеме segmentation/local speaker visibility,не только финальногоthreshold;
следующая гипотеза — локальные voice masks/другая segmentation и embeddings отдельных speech turns.

### exp_0132–0139 — видимость короткого голоса и цена splitting

Window shift.25/.5 +global.4 на structural smoke: короткие реплики cpWER46.67→36.67%;
шумный случай17.95→20.51%/.5→2.56%. Оба режима всё ещё пропускают короткий третий голос.
Прежняя AMI/natural JER-регрессия.5 сохраняет запрет глобального переключения.

Turn-unit embeddings135 (300ms minimum, complete-link.2/.3/.4) восстанавливают3голоса и
cpWER6.67% на коротком случае. Но clean3.23→22.58%,noise17.95→25.64–33.33%:
общий cpWER17.65→21.18–24.71%.134 — сохранённая ошибка harness доinference
(synthetic manifest безaudio_seconds); исправлено получение duration изPCM.
Dialogs occupancy содержит тишину: DER/JER для этих fixtures намеренно не вычисляются.

Selective136–139: только isolated300–1500ms turns; assigned speaker имеет long-turn anchor
из≥2s; distance>.4 ко **всем** anchors; novel embeddings complete-link.25;
новая группа≥2turns/≥1s с разницейstart≥2s. Пороги заморожены до запуска; эталоны только scoring.
Short46.67→6.67%,noise17.95% unchanged,но clean3.23→22.58% с ложным третьим голосом.
Итог17.65% unchanged: общий показатель скрывает противоположные срезы.
На3natural dev и2известных transfer sessions ни одного принятогоsplit,метрики unchanged.
**ADR: reject whole-turn и selective splitting для SDK.** Cosine novelty короткой реплики
не отличает нового человека от вариативности того же голоса; repetition одного фрагмента
в structural fixture не является независимым подтверждением speaker identity.

Следующая гипотеза — заменить локальные masks/кластеризацию на slot-based streaming model.
Публичный Sortformer v2.1 ONNX492242946bytes закреплён revision/SHA,лицензия
[NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/).
[Official card/config](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2.1/tree/cd03eee90fbec18297ac31b8c21546e596b7f71c),
[ONNX export](https://huggingface.co/cgus/diar_streaming_sortformer_4spk-v2.1-onnx/tree/6418561696a11506e38eb0babd64d7d1081554d5).
Model имеет4sigmoid slots,число голосов не подаётся; больше4неподдерживается.
Research NumPy frontend/state по
[NeMo](https://github.com/NVIDIA-NeMo/NeMo/blob/cd61689d41b1962d3e1957ae8faf28bf8bee0e3b/nemo/collections/asr/modules/sortformer_modules.py),
CPU ORT1.23.2/4threads,безTorch; NeMo numerical parity пока не доказана.
Frontend:128Slaney,FFT512/hop160,symmetricHann400,preemph.97,no norm,ditheroff.
Config извлечён первым tar member из pinned upstream.nemo; полные upstream веса не скачаны.
140 — harness provenance error до загрузки модели:не был передан sdk_sha256; сохранён,
повтор143 с правильным hash существующего SDK.141/142 не запускались.

### exp_0143–0148 — stateful Sortformer screening (завершён)

Frozen profiles из official card: buffered chunk340/right40/FIFO40/update300 (buffer30.4s),
low chunk6/right7/FIFO188/update144 (buffer1.04s),cache188,left1 — frames по80ms.
Это buffer latency без compute; postprocessing пока offline (.5posterior,.3s speech,.5s gap),
не готовый causal API. Host research хранит≤180s PCM,но attention/state окна ограничены.
Ни слово,ни word timestamp не пересчитываются: используется тот же frozen ASR trace.

Smoke143/144/145 (buffered-whole/low-whole/low-window): общийcpWER25.29% во всех3режимах
против17.65% ERes; clean6.45%,short20.00%,noise42.31%.
RTF толькоdiarizer .022/.523/.569; process-lifetimeRSS1332352/755676/747712KiB.
Whole vs window **не exact**: centeredSTFT/preemphasis на границах окон меняют posteriors;
фактические intervals/cpWER в этих fixtures совпадают. Не путать это с NeMo parity.
Четыре model-free tests проверяют LC/RC trimming,arrival-window пределы,cache compression/reset,
finite silence/subframe features. Model inference в этих tests не симулирует качество.

Natural buffered146:cpWER30.51% против44.64% принятогоnativeopt-in99;
per-file21.53/14.07/56.35% против22.73/46.29/66.24%.
Host diarizerRTF.0355,peak processRSS1472196KiB≈1.40GiB,без одновременногоASR.

| Native opt-in99 / Sortformer | DER | JER | cpWER | Host diarizer RTF | peak process RSS KiB |
| --- | --- | --- | --- | --- | --- |
| ERes global.4 | 21.16% | 32.97% | 44.64% | не парный current замер | 763500 (весьpipeline) |
| Buffered146 | 14.67% | 25.49% | 30.51% | .0355 | 1472196 |
| Low/window147 | 14.41% | 23.59% | 29.93% | .8318 | 824640 |

Analysis148: lexical sequence/timestamps/attribution воспроизводятся из одногоASRtrace.
Paired10k bootstrap по3записям,seed42: buffered−native cpWER95%CI[-32.23,-1.20]pp,
DER[-17.16,+.63]pp,JER[-23.30,+4.82]pp. Low−native cp[-30.69,-3.83]pp,
DER[-16.04,-.65]pp,JER[-22.34,+2.36]pp. Малые exploratory CI на known silver
не подтверждают people-disjoint обобщение; no gold gate. Whole/window controls144/145
дают posterior maxdelta .071/.101/.042 и1/0/2 flips по.5threshold,хотя экспорт/счёт совпал.
**Решение:** сохранитьоба как research candidates,SDK/default не менять; low существенно дорожеCPU,
buffered требует30.4sвходного буфера. Postprocessing offline,arrival-paced end-to-end latency не измерена.

Далее149–152: [ORT dynamic quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)
только constant-weightMatMul,per-channelQInt8,Conv остаётсяFP32,без calibration/reference данных.
492242946→182478884bytes; SHA718f5457…,две независимые конверсии byte-identical.
Алгоритм/parentSHA/onnx1.17.0/ORT1.23.2 закреплены вlock; `bootstrap_models.py` воспроизводит derivation.
Сначала dev+smoke A/B,затем выбрать доtransfer и проверить2известные regression sessions.

**До transfer153–159:** по149 выбран **buffered MatMul-INT8 для file-mode исследования**:
dev cpWER29.34% противFP32buffered30.51%,diarizerRTF.0247,peakRSS1171748KiB.
Это выбор кандидата,не SDK/default. Low151 ещё завершается;1.04sрежим — отдельный latency tradeoff.
Дополнительно заморожен план нового source-file holdout `astrology.wav` из того жеpublisher:
сначала native baseline155,затем единственный заранее выбранный кандидат156;без подборапорогов.
Исходный WAV1,030,418,366bytes:Range-префикс44.1kHz/stereo16bit,полныйsourceне скачивается.
Разделение людей/независимыйgold всё ещё не подтверждены;2старых transfer уже known regressions.

### exp_0149–0161 — INT8 и переносимость: кандидат отклонён

Buffered INT8:dev DER13.38%,JER24.07%,cpWER29.34%,RTF.0247,RSS1171748KiB.
Low INT8:DER15.11%,JER24.69%,cpWER30.59%,RTF.4630,RSS516896KiB;
FP32low29.93%cp/.8318RTF/824640KiB. Direct low quantization analysis161:
cp delta+.665pp,record bootstrap95%CI[0,+2.03]pp — экономия ресурсов с риском качества.
Buffered vsFP32 cp delta−1.16pp,CI[-2.87,0]pp; не объявлять достоверное улучшение квантованием.
Smoke150 остаётся25.29%cpWER (хужеERes17.65%); короткий третийslot неактивен даже вFP32.

Frozen bufferedINT8 transfer (baseline — native EResglobal.4,тот жеASR):

| Source file / baseline→candidate | DER | JER | cpWER |
| --- | --- | --- | --- |
| sFt153/157 | 12.98→52.13% | 11.13→72.08% | 20.65→100.22% |
| movie154/158 | 21.25→18.29% | 16.59→19.21% | 33.42→30.77% |
| new astrology155–156/159 | 10.23→4.39% | 26.09→4.67% | 15.57→12.93% |

Astrology:178.85s,3reference voices,379words,normalizedWER8.71% одинаковый;
85publisher text edits по full-sourceannotation,по-прежнему silver/no manualwordGT.
Range0..31752077,sourceprefixSHA7584633d…,безfullsourceSHA;models/пороги выбраны доquality outputs.
157–159 имеютn=1:bootstrap intervals вырожденные,не использовать как статистическое доказательство.

**ADR: reject promotion Sortformer v2.1 FP32/MatMul-INT8 в текущем frontend/state.**
FP32 control160 наsFt повторяетcp100.22%,DER52.07%: ошибка не вызванаINT8.
Пересеченияpredicted/GT по27.2sокнам показываютslot0 на обоихreferenceголосах почти весьфайл,
slot1только~3.4s — speaker collapse,а не доказанная перестановка двухstableID.
Точная первопричина/model-vs-frontend parity не локализована; это отказ кандидату,не всему семейству моделей.
Native SDK/default и принятый opt-in остаются прежними.

Все19research tests,task/manifest checks иmodel SHA verification прошли.
Dispatch теперь сам фиксируетgit/host/CPU/affinity/thread env **перед** каждым следующимjob,
включаяfailure; новые161артефакты это проверяют. Историческим timings эти поля заднимчислом не приписываются.
Далее: [Nemotron3Diarization](https://huggingface.co/nvidia/Nemotron-3-Diarization)8slots
и frontend/state conformance; найденpublicONNXQ8≈120MB externalweights,но пока не измерен.

### exp_0162–0164 — независимый frontend control (завершён)

Отдельный`.tools/frontend-env`:Torch2.9.0+cpu/librosa0.11.0/numpy2.2.6/SciPy1.18.1;
SDK/research основноеокружение не меняются.162 сравнивает logmel наsilence/impulse/sine/realPCM:
maxdelta1.316e-4,meanreal6.76e-7,строгий заранее заданныйmax5e-5непройден;failure сохранён.
163 исправляет float32Hann arithmetic иcast-before-Slaney по reference source:
realmax6.20e-5,sinemax1.163e-4,meanreal5.31e-7;тотжедопуск всё ещё **не** пройден.
Не расширять tolerance молча и не заявлять numerical parity.164 подаёт **реальныеTorch/librosa features**
в тотжеFP32 Sortformer/state наfailedsFt — контроль влияния FFT/rounding без новой модели/порогов.
Child Torch memory/time выделены отдельно;этот diagnostic не device performance profile.
Nemotron3Q8 weights/config/cards закреплены вlock (export353b6f8…,upstreamf667ed7…,OpenMDW-1.1),
externaldataSHA002d7483….

164 даёт **те же** cpWER100.22%,DER52.07%,JER72.06%,полные turns/utterances exact equal160.
Posterior maxdelta1.97e-6,0threshold flips. Следовательно,наблюдаемые NumPy/Torch
frontend-различия не объясняют speaker collapse на этомsource;fullstate parity не проверена.

### exp_0165–0174 — новая8slot-архитектура (завершён screening)

Nemotron3Q8/ORT1.23.2:graph+externalweights120844247bytes;Transformers reference0f53828…,
learned silence embedding,cache264×512,FIFO40buffered/264low,LC0,10msoutput.
Published buffered340/right40/update300,low9/right4/update222;buffer30.4s/1.04s.
State считает80ms pooledsigmoid дляcache,выдаёт10ms logits→sigmoid;GTcountнеподаётся.
Пятый model-free test проверяет8slots,encoder-ratemask,learnedsilencecompression иrealEOFgrid.
165 structural:clean3.23%,short20.00%,noise10.26%,общийcpWER9.41% противERes17.65%;
третийкороткийголос **не восстановлен** (2known+unknown),не путать снижениеcpWER с полным решением.
Host diarizerRTF.0200примерно,processRSS311472KiB;толькоscreening,не targetRAM.
Далее natural dev166/167,pairedanalysis168;доtransferникакихновыхпорогов.

До169–174 выбран buffered8slotQ8 дляfile-mode по166 (cp31.59%,RTF.0194,RSS566548KiB):
это быстрее/экономнее предыдущегоbuffered4slot,ноthirddevcp67.26% противnative66.24% — regression.
Low167ещёидёт;выборfile-mode не меняется по контрольным результатам.
169–174 проверятвсе3 **уже известные** source-file regressions;это не новый независимыйtest.

166 buffered:DER15.78%,JER25.46%,cpWER31.59%,RTF.0194,peakRSS566548KiB.
167 low:DER16.40%,JER26.10%,cpWER33.25%,RTF.5285,RSS463628KiB;
pairedCI168vsnativeвключают0 дляDER/JER/cpWER (thirddevregression),не заявлять значимость.

| Known transfer / nativeglobal.4→Nemotron3Q8 buffered | DER | JER | cpWER |
| --- | --- | --- | --- |
| sFt169/172 | 12.98→10.82% | 11.13→10.26% | 20.65→18.92% |
| movie170/173 | 21.25→16.67% | 16.59→19.04% | 33.42→30.50% |
| astrology171/174 | 10.23→6.55% | 26.09→4.55% | 15.57→10.55% |

**ADR: принять для native prototype,не default promotion.** Все3transfer cpWER/DER лучше,
collapse прежнеймодели не повторился;но thirddev/JERmovie хуже,6smallknown silver files
не независимыйgold/people-disjoint test. Host buffered transferRSS~384–386MiB/RTF~.031;
это покаPythonORT1.23.2,не Android/ARM. Следующее: C++17/CABI additive streaming handle,
bounded PCM/features/cache,host parity/resource/cancel tests,затем4GBx86AVD.
Существующие API/preset остаются прежними;frontends имеют измеренные floating-point differences.

### exp_0175 — native streaming C ABI: smoke/controls завершены

Добавлен отдельный `nh_streaming_diarizer_*`:C++17,прямой pinnedORT1.28.2CPU,
16kPCMring→sparseSlaney128/FFT512→8slotmodel→boundedcache→10msposterior callbacks.
Старые структуры/ABI1/filepreset сохранены. Config:threads1..16,profile0low/1buffered,
duration0→600s/hard3600;accept≤400000finite samples;flush/reset/stats/destroy.
LC0;stable source offset,однократная выдача;последние<160PCM samples не даютполной10msrow.
model runtime/cancel failure требуетreset;onehandlebusyguard;model sessionreuseнаreset.
Native нельзя называть готовым whole ASRstreaming:новыйAPI выдаёт speaker posteriors.

175hostbuffered:smoke cpWER9.41% (3.23/20.00/10.26%),какпрототип165;
posterior maxdelta≤2.39e-6,0thresholdflips. RTF.02778,load.0573s,
peakprocessRSS316016KiB (~308.6MiB);отдельныйраунд,не paired speedup claim.
Транспорт997vs400000samples даёт **exact** posterior arrays/callbackoffsets наclean31.36s.
Cancel→4,nestedreset→5,flushпослеcancel→1;reset очищаетtimeline;
1sbudgetextra sample→1 безconsumption,flushidempotent,NaNrejected безconsumption.
Модель/decoderнеперезапускаются на каждом transport fragment;Oraclecount отсутствует.

Проверки:3nativeCTest +14PythonCABI,3ASan/UBSanCTest,20research tests,
ARM64/x86_64cross-build/16KiBELF ивсеmodelSHA прошли.
ФизическийARM/Androidexecution новогоbackend **ещё не** проверены.
Usercheckpoint выполнен:175 и проверки закоммичены94d0929,HEAD проверен наorigin/dev; работа продолжена176+.

### exp_0176–0183 — standalone SDK: натуральная речь и x86 AVD

Завершено. В 176 native buffered на трёх natural dev: cpWER 31.59%, RTF .02046,
peak RSS 488104 KiB. Против Python166: posterior max delta ≤7.63e-6,
ни одного изменения решения на пороге .5; исходные ASR words сохранены.

Добавлен `nh-audio-stream`: декодирование блоками → speaker API → f32LE файл,
без APK/UI/Python runtime. Выход создаётся эксклюзивно, PCM SHA считается
инкрементально. CLI и его SHA входят в host/Android build provenance.
Runner проверяет SHA бинарников, модели и источника; PSS снимается внутри device shell.
ASR слова зафиксированы на host: это оценка diarization, не полный target ASR.

177 host, movie 175.172 s: обработка 4.516 s, RTF .02578, RSS 283136 KiB.
178–180, три свежих процесса AVD 4096 MiB/x86_64: 7.082/9.228/11.096 s,
RTF .04043/.05268/.06334, peak PSS ≤291971 KiB (~285 MiB), RSS ≤318120 KiB.
Аудит181: все три target posterior arrays побитно совпадают; против host
max delta 2.74e-6, ноль изменений порога. PCM SHA3ed9bd9e… совпал,
2802748 samples /17517 rows. cpWER/DER/JER одинаковы с host и прототипом170.
OS page cache не очищался; разброс времени не доказывает ускорения алгоритма.
Sampling nominal 50 ms, actual median 90–110 ms; PSS — наблюдаемый, не гарантированный peak.

| Movie / профиль | Host RTF | x86 AVD RTF | cpWER | DER | JER |
| --- | --- | --- | --- | --- | --- |
| Q8 buffered177–180 | .02578 | .04043–.06334 | 30.50% | 16.67% | 19.04% |
| Q8 low182–183 | .48989 | **1.19211** | 36.34% | 23.13% | 22.42% |

Low: 244 model calls, peak PCM buffer16881 samples; AVD PSS279456 KiB/RSS305316 KiB.
Первый callback .260 s, максимальный интервал1.167 s, p95 1.088 s при обычном
шаге выдачи .72 s. Это unpaced replay файла, не live capture latency.
**ADR: low Q8 не рекомендовать для real-time в доступном окружении:** RTF>1
и качество хуже. Короткий nominal buffer1.04 s не гарантирует скорость вычисления.
Buffered остаётся кандидатом для файлов; основной preset не меняется.
ARM execution и полный target ASR здесь не измерялись.

Исправлен registry reducer: учитывает CLI `processing_seconds`, не подменяет
отсутствующее время нулём. Regression tests проверяют units, fallback и duration weighting.

### exp_0184–0185 — Q4: screening завершён, продвижение отклонено

Тот же export353b6f8…: Q4 graph + external weights83127731 bytes против
120844247 у Q8; SHA закреплены в lock. Stock ORT1.28.2 CPU загружает MatMulNBits.
Native host/movie/4 threads/postprocess прежние; ASR и PCM SHA неизменны.

| Профиль | Host RTF | Peak RSS, KiB | cpWER | DER | JER |
| --- | --- | --- | --- | --- | --- |
| Q4 buffered184 | .02319 | 245472 | 31.03% | 17.61% | 18.68% |
| Q4 low185 | .49075 | 233548 | 43.50% | 26.15% | 24.16% |

**ADR: Q4 не продвигать.** Low не ускорился в одиночном host screening,
а качество ухудшилось относительно Q8 low182. Buffered имеет небольшую
cpWER/DER регрессию; непарные времена не доказывают ускорения.
Меньшие веса/RSS не компенсируют регрессию. Target Q4 не запускался:
качество на host не прошло проверку, поэтому дополнительный target замер отложен.

Проверки после изменений: 25 research tests, 3 native CTests +14 Python C ABI,
3 ASan/UBSan CTests, ARM64/x86_64 cross-build и все pinned model SHA прошли.
Следующий шаг: Q8 buffered в file pipeline через отдельный opt-in API;
online turn postprocessing, cancel/checkpoint parity и полный target pipeline.
Основной ERes preset сохранён; независимый RU gold и ARM runtime пока отсутствуют.

### exp_0186 — повторная проверка полного файлового API

Завершено: native `nh_transcribe_file_with_options` через CLI, без checkpoint/кешированного ASR.
Movie 175.172 s → decode → GigaAM-v3 CTC INT8 → pyannote/ERes2Net
→ word/speaker attribution → strict JSON. Exit0, JSON validation passed,
22 utterances; processing wall 30.626 s, full RTF 0.1748,
sampled peak PSS 614540 KiB. Word alignment fallback chunks: 0.
Это host execution текущего default, не новый Nemotron backend; summary не запускался.
Код полного pipeline реализован; новая speaker-модель пока доступна отдельно.

### Сравнение готовых native пайплайнов — начато после186

Пробел предыдущего цикла: сравнивали отдельные ASR/embedding/diarization модели,
но не измеряли целиком альтернативный готовый native runtime. Замена одного
threshold не отвечает на вопрос, лучше ли архитектура другого проекта.

| Решение | Соответствие платформе и действие |
| --- | --- |
| [sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/index.html) | Текущая база, C/C++, Android/iOS/ARM, offline; уже исполняется нашим SDK. Сохранить контроль186. |
| [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp/tree/v0.3.0) | Официальный C++/ggml ASR + word timestamps + diarization. Есть Linux ARM64 CPU binaries; Android NDK ещё не квалифицирован. Проверить готовый pipeline на host. |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | C/C++, Android, квантование/VAD. Tinydiarize example использует small.en и выдаёт speaker turns, не готовую русскую идентификацию участников. Отдельный вариант ASR, не полная замена speaker pipeline. |
| [WhisperX](https://github.com/m-bain/whisperX) | VAD → Whisper → language-specific forced alignment → pyannote; есть CPU int8. Полезен как reference для alignment, но весь Python pipeline не является готовым NDK SDK. |

Выбран для первого исполнения NeMo-Speech.cpp **0.3.0**, source tag20999cc…,
официальный Linux x86_64 CPU archive SHA255f12b7…; установлен отдельной
`python scripts/bootstrap_nemo_reference.py`, не включается в shipped SDK.
Nemotron3.5 ASR Q8:742090464 bytes, rev ea30d66…, SHA3fc991d3…;
Nemotron3 Diarization GGUF Q8:107012128 bytes, rev f667ed7…, SHA08456d9e….
Оба ungated, pinned в model lock. Это другие quantization/runtime,
нельзя объявлять эквивалентность уже проверенному ONNX Q8.

187/188/189: одна frozen movie запись, native CLI, CPU4 threads, explicit ru-RU,
без warmup/batching/ITN; offline ASR, recorded streaming160ms ASR, streaming ASR +
официальный buffered diarizer v3-offline. Считаем text-v2 WER/CER/punctuation F1,
wall/RTF/PSS/RSS; cpWER только при полном воспроизведении текста word list.
JSON ASR содержит word speaker labels, не сырые speaker spans: DER из них не выдумывать.
Default offline ASR использует attention right3, streaming right1: это сравнение
готовых режимов, не чистое влияние transport chunk size. Raw settings/logs сохраняются.
Пока идут прогоны, никаких заявлений о победителе/Android performance/default promotion.

187 завершён: официальный offline ASR, WER18.04%, CER7.77%, punctuation F1 61.68%,
wall188.952 s / audio175.172 s (RTF1.0787), sampled PSS2973500 KiB.
У GigaAM CTC в186 на этом же источнике WER15.38%, полный ASR+ERes pipeline30.626 s;
это не paired timing/same work, поэтому не вычислять из него чистое ASR ускорение.
Word list полностью воспроизводит текст, интервалы в пределах исходной записи.
188/189 ещё идут. Команда подготовки: `make nemo-reference-bootstrap`.

Из source tag20999cc… отдельно взята **гипотеза назначения спикера**, не код целиком:
`sortformer_model.h::word_anchor_frames` и `diar_pipeline.cpp::speaker_for_word_time`
усредняют posteriors первых160ms слова и выбирают argmax без пороговых turns.
190 сравнит этот подход, whole-word posterior mean и прежний threshold/turn overlap
на всех6 известных silver files. ASR слова/время и ONNX Q8 posterior arrays фиксированы;
baseline обязан воспроизвестись, число говорящих из GT не используется.
Это самостоятельный опыт по архитектуре merge; DER не меняется, поскольку diarization field тот же.

188: recorded streaming ASR160ms, WER20.16%, CER8.69%, punctuation F1 58.10%,
wall46.937 s, RTF.26795, PSS920284 KiB. Это финальный текст, не оценка live partials.
189: тот же ASR + официальный diarizer: wall52.416 s, RTF.29923,
PSS1057518 KiB, **3 speakers**, cpWER20.69%; ASR текст совпал с188.
Для сравнения:186 default GigaAM+ERes cpWER43.24%, movie GigaAM+ONNXQ8 cpWER30.50%.
Один известный source не доказывает общее превосходство; pipeline выбран до191–193,
которые проверяют оставшиеся5 известных записей без настройки по ответам.

190 завершён, все6 threshold-turn baselines воспроизвелись:
общий cpWER25.70% → whole-word posterior23.47% / first160ms23.43%.
Anchor улучшил все6 относительно turn overlap; относительно whole-word выигрыш всего1слово
(568 vs569 ошибок /2424 words), поэтому не заявлять доказанную лучшую длину anchor.
Words и timestamps сохранены; прямой argmax всегда назначает слот, включая слабую уверенность.
Это кандидат для native merge A/B, не автоматическое изменение default.
Runtime0.3.0 тестируется с явно выбранным официальным ASR export ea30d66…;
встроенный model index релиза указывает другой export1c8deae…/SHAa5c435f….
Все результаты относятся к записанной паре runtime/weights, не ко всем версиям NeMo.

### exp_0191–0194 — перенос готового pipeline и итог архитектурного сравнения

Завершено: runtime/ASR/diarizer/threads/language/preset одинаковы для6 записей,
проверены194; все source/reference denominators совпали. Bootstrap10000, seed42.
189 +191–193 — полный native NeMo ASR + diarization, не переиспользование GigaAM.

| Все6 известных silver записей /2424 reference words | WER | cpWER |
| --- | --- | --- |
| GigaAM + ONNX Q8, threshold-turn merge | 13.45% | 25.70% |
| Те же GigaAM/ONNX posteriors + first160ms posterior merge190 | 13.45% | **23.43%** |
| Полная native связка NeMo-Speech.cpp + Nemotron3.5 ASR + GGUF diarizer | 19.51% | 28.59% |

Полная NeMo связка: RTF.281–.302, sampled PSS1057518–1060052 KiB (~1.01 GiB).
На movie она улучшила cpWER до20.69%, но на yCX/p0/astrology/sFt хуже ONNX Q8 baseline.
Третий трудный dev остаётся плохим:cpWER65.99%, против67.26% threshold baseline
и61.68% нашего posterior-anchor варианта. Качество ASR хуже GigaAM на всех6.
Для cpWER NeMo−threshold delta+2.89pp, record CI95[-2.82,+7.92]pp;
NeMo−anchor+5.16pp, CI95[-.08,+9.16]pp. Не заявлять статистическое превосходство:
все записи известные, серебряные эталоны, независимость участников не установлена.

**ADR:** весь протестированный runtime/model pair не продвигать в default;
GigaAM сохраняется. Взять для native merge A/B идею прямого posterior attribution,
после проверки коротких реплик и профилей официального diarizer с фиксированным GigaAM.
Следующие конкретные проверки: hybrid GigaAM + official diarizer geometry/word assignment;
потом bounded интеграция выигравшего варианта в полный file API и x86 AVD.
Новые runtime/models/CLI зафиксированы отдельно; проверка моделей и30 research tests пройдены.
Это расширяет исследование архитектур; текущий shipped SDK не заменён непроверенной библиотекой.

### Блоковый research вместо перебора параметров — следующий цикл

Цель: переносить конкретный алгоритм/инженерный приём с первичным источником,
держать остальные части фиксированными, измерять вклад блока и его стоимость.
Не считать популярность GitHub или чужую GPU/Apple метрику доказательством пользы на нашем CPU.

| Блок / проблема | Источник и что берём | Статус |
| --- | --- | --- |
| Word→speaker теряет информацию после binarization | NeMo-Speech.cpp: direct posterior mean/160ms word anchor | Проверен190:25.70→23.43% cpWER; native file integration впереди |
| Recurrent сопровождение спикеров вместо embedding/clustering/cache Sortformer | [LS-EEND](https://github.com/Audio-WestlakeU/FS-EEND), [FluidAudio](https://github.com/FluidInference/FluidAudio), public ONNX export | Проверены195–200; недостаточное качество, не продвигать |
| Acoustic enhancement отдельно перед ASR, не перед speaker embeddings | [DPDFNet native sherpa](https://k2-fsa.github.io/sherpa/onnx/speech-enhancement/dpdfnet.html); у [speech-core](https://github.com/soniqo/speech-core) изучен DeepFilterNet3 DSP/delay compensation |201 выявил source-grid mismatch;202 проверяет явное padding/latency выравнивание и ASR A/B |
| Точные интервалы слов вместо CTC peak+40ms | [WhisperX](https://github.com/m-bain/whisperX), [NeMo Forced Aligner](https://github.com/NVIDIA-NeMo/Speech/tree/main/tools/nemo_forced_aligner): CTC Viterbi alignment неизменного ASR текста | Источники разобраны; проверить доступность GigaAM logits и стоимость bounded alignment; word MAE пока без GT не заявлять |
| Автооценка числа голосов вместо одного cosine threshold | [NME-SC](https://github.com/tango4j/Auto-Tuning-Spectral-Clustering), NeMo offline clustering; FluidAudio VBx | Источники разобраны; нужны исходные segment embeddings/подходящий PLDA, один только distance matrix после constraints недостаточен для честной реплики |
| Стабильная timeline и ограниченные buffers | FluidAudio finalized/tentative timeline; speech-core model-agnostic C++ interfaces | Применимо архитектурно; наш C ABI пока выдаёт только committed frames. Не добавлять UI/voice-agent/TTS ради копирования проекта |

Приоритет:202 завершён без выигрыша; далее native opt-in posterior merge и A/B alignment/гибридной
геометрии speaker-модели при сохранении GigaAM. Новый backend добавлять только при
измеримом выигрыше, не начинать очередной произвольный threshold sweep.

### exp_0195–0200 — LS-EEND как отдельный streaming блок

ONNX44,486,905 bytes, exporter GradientDescent2718/LS-EEND-ONNX,
revcc40a1e…, SHA587ad263…; DIHARD3,8kHz,10real slots +2special,
100ms output,6 recurrent/cache tensors, total state1,916,352 bytes.
Pinned publisher feature/state code исполняется в отдельном frontend-reference env;
CPU ORT1.23.2/4threads. Python reference RSS не является native/mobile RAM.
Подготовка: `make lseend-reference-bootstrap`.

Metadata заявляет FFT1024, но publisher code и original LS-EEND feature.py
(revadcdde1…) вычисляют next-power-of-two(window200)=256. Использован actual code256;
не подменяли frontend числом из metadata. Полная Torch/checkpoint→ONNX parity не доказана.
195 whole-feature smoke:cpWER25.88%, против NemotronQ8 9.41%.
196 input1s: maxposterior delta≤1.73e-5,0threshold flips на всех3; качество совпало195.
State/transport control пройден, но это не gold quality gate.

197–200: все6 известных натуральных RU записей, прежние GigaAM words и thresholds.
cpWER yCX97.13%,p041.18%,nr68.27%,movie84.88%,sFt100.22%,astrology95.78%.
На yCX/sFt модель оставила один known voice; не выдавать скорость за решение задачи.
Reference processing RTF.069–.087 с tentative previews; generic Python/frontend overhead
и cold imports отделены в wall_seconds, нет ARM/per-device latency claim.
**ADR:** этот export/runtime pair не включать в SDK. Выбор другого diarization механизма
проверен фактически; менять frontend/пороги по этим ответам для спасения метрик не будем.

### exp_0201–0202 — отдельная ветвь enhancement→ASR

DPDFNet baseline16kHz,8,722,707 bytes, revdd6818d…/SHA371d2618…,Apache2;
native sherpa C API, никаких новых inference frameworks. ASR GigaAM CTC INT8/4threads,
20s chunks, raw/enhanced на том же PCM. Diarization здесь не пересчитывается.
201 сохранён как failed diagnostic: native STFT/ISTFT возвращает hop-rounded длину,
а `ShiftWaveform(2*window_length)` сдвигает сигнал и zero-fills конец.
Без выравнивания нельзя считать временные метрики или молча менять timeline.
202: явное right-padding ровно из model metadata (40ms delay + до1hop), проверка
native padded output, удаление только объявленного padding до исходного Nsamples;
ASR сравнивается на одинаковых chunk ranges. Число reference speakers не используется.

202 завершён: identical chunk ranges и исходный Nsamples сохранены во всех3 случаях,
никакого скрытого изменения длительности. Суммарный WER raw3.53% → enhanced4.12%,
CER1.10% →1.40%. Clean и short лексические ошибки прежние; noisy2/78 →3/78.
Native denoising занимает1.13–2.20 s на24–40 s аудио; это не ARM timing.
**ADR:** baseline denoise не включать по умолчанию: выигрыш не наблюдается, выборка мала,
одна дополнительная ошибка не доказывает общую непригодность DPDFNet.

Итог блока research195–202: модели/state/frontend разных архитектур проверены на коде,
а не только занесены в таблицу. LS-EEND на6known RU дал81.89%cpWER против25.70% уQ8;
ONNX/native parity с оригинальным Torch checkpoint не заявлена. DPDFNet выявил реальную
задачу DSP alignment, но не дал ASR improvement в smoke. Главный положительный результат
остаётся posterior merge190:25.70→23.43%cpWER без замены GigaAM/diarizer/word times.
Дальнейшее расширение — через конкретные блоковые гипотезы с первичным источником,
фиксацией остальных компонентов и accept/reject; arbitrary parameter sweep не приоритет.

### exp_0203–0214 — перенос результата в полный C++ pipeline

Завершено: additive `nh_transcribe_file_with_streaming_diarizer` и CLI
`nh-audio transcribe-stream`. Это реальный полный путь decode→GigaAM→release ASR
→bounded speaker inference→word posterior merge→strict JSON, не подстановка host ASR.
Старые C ABI структуры и entry points сохранены. Базовый ERes default не переключается.

203 повторил old-default movie JSON186 **exact**. 204 smoke: cpWER5.88%
(clean3.23/short20.00/noise2.56%) против threshold-turn Q8 9.41%; третий короткий голос
всё ещё не восстановлен (2known), снижение общего cpWER не выдавать за решение этого кейса.
205–208: все6 known natural source files: ASR words/times exact с исходными baseline,
slot assignments exact с prototype190. Полный host RTF.0768–.0860,
PSS551698–582027KiB. Новый код не накапливает полные posteriors; word accumulators
и опциональные diagnostic turns ограничены source duration/65536 turns.

| Все6 known RU /2424 words | cpWER |
| --- | --- |
| Старый native ERes с global refinement (99/101/104/155) |33.75% |
| Q8 с прежним threshold-turn overlap |25.70% |
| Новый полный native API с first160ms posterior merge |**23.43%** |

Новый vs ERes: −10.31pp, record bootstrap10000/seed42 CI95[−19.56,−5.05]pp.
Это exploratory known silver corpus, не новый blind/people-disjoint test.
WER не менялся:13.45% на тех же6 источниках. Трудный nr остаётся61.68%cpWER;
movie имеет4known вместо3. Улучшение не означает, что все speaker ошибки устранены.

209:7 real-model C ABI controls: cancel before speaker load/after completed NN,
nested NH_BUSY, resume, shared ASR cache с legacy backend, duration reject до ASR,
защита external weights от output alias. Отмена/ошибка до export сохраняет существующие JSON/trace;
PCM SHA exact; cache ASR words/backend JSON exact. Progress исправлен на монотонные
emitted frames; input read-ahead не подменяет выполненную speaker работу.
210 повторил latest host movie для source/build-сопоставления с target.

211–213: полная standalone SDK обработка на offline AVD4096MiB/x86_64,
свежие процессы, настоящие device ASR+speaker NN. Movie175.172s:
30.156/28.496/28.392s, RTF.17215/.16268/.16208; PSSpeak≤340132KiB (~332MiB),
kernel RSS≤364652KiB. cpWER27.85%, WER15.12%; host movie cpWER28.12%,WER15.38%.
Source PCM SHA совпадает, raw speaker turns exact; ASR words междуplatform builds отличаются,
не приписывать текстовое изменение diarizer. Все3target transcript/words/slots/turns exact.
Sampling nominal50ms, actualmedian110ms; OS cache не очищался. Это не ARM/coldboot
и не доказательство causal speedup относительно старых несинхронных AVD серий.
214 подтвердил code/model/source identity,6case prototype parity,controls и3target repeats.

**ADR:** принять как проверенный opt-in file backend. Никакого обязательного Python/reference
runtime в shipped SDK; sequential models, raw source timeline, atomic exports сохранены.
Глобальную смену default отложить до независимого corpus/short-speaker/stress проверок.
Следующие блоковые гипотезы: source-based CTC forced alignment и официальный diarizer
geometry/word assignment при фиксированном GigaAM; никакого произвольного threshold sweep.

215: полный новый file API прошёл3 real-model диалога под ASan/UBSan с
`halt_on_error=1`; GigaAM words/times иcpWER совпалиrelease. Sanitizer timings/RSS
диагностические, не используются для performance claims. Проверки:3nativeCTest,
14PythonCABI,3ASan/UBSanCTest,32research tests,ARM64/x86_64 cross-build/16KiBELF,
всеmodelSHA,ktlint/detekt/AndroidLint passed.
