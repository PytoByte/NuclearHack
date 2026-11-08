# Результаты бенчмарка аудио-ядра

Этот файл — человекочитаемая сводка результатов **принятого baseline SDK**
`ru-offline-v1` / `nh_transcribe`. Он не заменяет машинные артефакты:
детальные runs находятся в `eval/results/exp_NNNN/metrics.json`.

## Базовый run

- **Run ID:** `exp_0244`
- **Scope:** `selected final native SDK audit; known RU silver quality, exact
  refactor parity, x86 AVD, controls and explicitly synthetic 600s capacity`
- **Корпус:** 6 natural RU silver dialog snippets, 2424 reference words
- **Платформа:** Linux x86_64 host
- **Статус:** `accept` в `experiments/registry.csv`

## Качество распознавания (среднее по 6 cases)

| Метрика | Значение |
| --- | ---: |
| Normalized WER | 13,78% |
| Raw WER | 26,95% |
| Normalized CER | 7,36% |
| Raw CER | 10,51% |
| Punctuation-token WER | 21,78% |
| cpWER | 23,51% (согласно `cpwer` run) |
| DER (среднее) | 13,80% |
| JER (среднее) | 17,50% |
| Punctuation F1 end-to-end | 64,86% |
| Punctuation precision | 57,56% |
| Punctuation recall | 74,28% |
| Conditional punctuation F1 на равных словах | 77,29% |

## Сравнение с plain CTC предыдущей версии

| Метрика | Текущий SDK | Legacy plain CTC |
| --- | ---: | ---: |
| Normalized WER | 13,78% | 13,45% |
| Raw WER | 26,95% | 49,62% |
| Normalized CER | 7,36% | 7,68% |
| Raw CER | 10,51% | 13,97% |

Комментарий: финальный SDK заметно лучше по raw WER/CER и пунктуации, но на
phone40 plain CTC всё ещё имеет лучший WER (17,65% против 20,59%). Это уже
зафиксировано в research как измеренный компромисс, а не дефект оформления.

## Производительность на host x86_64

| Параметр | Значение |
| --- | ---: |
| Full RTF, target repeats | 0,217 – 0,223 |
| Peak PSS | 332 – 340 MiB |
| Synthetic 600s capacity, RTF | 0,098 |
| Native stream model calls / emitted frames | 23 / 60000 |
| Peak buffered samples | 486 641 |

Это host-числа. Они не являются доказательством performance на Android device
и не заменяют AVD/physical ARM измерения.

## Как воспроизвести

```sh
# Данные
make research-bootstrap
.venv/bin/python eval/scripts/prepare_russian_pilot.py
.venv/bin/python eval/scripts/prepare_openstt_calls.py

# Полный research/run queue
uv run python eval/scripts/run_research_queue.py experiments/...
```

При каждом запуске сохранять run ID и provenance:
- machine/OS, git SHA, dirty flag;
- threads, model files and SHA;
- audio corpus and reference;
- output in `eval/results/exp_NNNN/`.

## Интерпретация ограничений

- CPU/RSS числа получены на host и могут отличаться от Android runtime.
- Dataset — six known RU silver snippets, не независимый blind test и не gold.
- DER/JER измерены на этих же snippets.
- Timestamp MAE не измерен, потому что нет ручной word-level ground truth.
- Qwen/summary не входит в transcription baseline.
- Benchmark size APK не является целевой метрикой проекта.

## Тестовые данные и запуск

Подготовка pinned audio/data:

```sh
make research-bootstrap
# эквивалентно: models + prepare_fleurs.py --split validation
.venv/bin/python eval/scripts/prepare_russian_pilot.py
.venv/bin/python eval/scripts/prepare_openstt_calls.py
```

Запуск измерений:

```sh
.venv/bin/python eval/scripts/run_asr.py
.venv/bin/python eval/scripts/run_file_pipeline.py
.venv/bin/python eval/scripts/run_diarization.py
.venv/bin/python eval/scripts/run_fragment_asr.py
.venv/bin/python eval/scripts/run_research_queue.py experiments/...
```

Результаты сохраняются в `eval/results/exp_NNNN/`.
