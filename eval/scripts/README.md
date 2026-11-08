# Скрипты eval

Воспроизводимые research и eval entry points. Не входят в SDK bundle.

## Подготовка данных

- `prepare_fleurs.py`, `prepare_russian_pilot.py`, `prepare_openstt_calls.py`,
  `prepare_ami.py`, `prepare_dialogs.py`, `prepare_potatohd_asr.py`,
  `prepare_ru_book_mix.py`, `prepare_audio_variants.py` — подготовка corpora/references.

## Запуски

- `run_asr.py`, `run_file_pipeline.py`, `run_diarization.py`,
  `run_fragment_asr.py` — основные пути ASR/diarization.
- `run_research_queue.py` — запуск очереди экспериментов из `experiments/*.json`.
- `run_android_asr.py`, `run_android_pipeline.py` — Android test host path.

## Сравнение/scoring

- `compare_asr.py`, `compare_punctuation.py`,
  `compare_refinement_profiles.py`, `compare_speaker_candidates.py`
- `score_conversation_diarization.py`, `scoring.py`
- `ctc_alignment.py`, `ctc_surrogate_correlation.py`, `punctuation.py`

## Probes/analysis

- `probe_*` — узкие эксперименты по decode/ASR/speaker/punctuation/memory.
- `analyze_*` — агрегированный анализ metrics/provenance.
- `verify_refinement.py`, `verify_sdk_bundle.py` — verification helpers.
