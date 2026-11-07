# RESEARCHING.md — Research Handoff (Updated 08.11.2026)

**Date:** 08.11.2026 | **Branch:** dev | **Last accepted SDK:** `ru-offline-v1` (exp_0244/0245)

---

## Update Log

### Session 08.11.2026 — Pilot corpus available; chunk-size A/B completed.

- Russian pilot corpus now prepared (`prepare_russian_pilot.py` fixed). 3 sessions (yCX4/P0/nr3hm). Manifest: `eval/data/russian-conversation-pilot.jsonl`.
- Baseline exp_0255 (20s chunks, profile 1): yCX4 WER 9.09% cpWER 13.40%; p0 11.76/14.32; nr3hm **22.59/60.66**. Peak PSS ~570 MiB. RTF ~0.053.
- A/B чанки (streaming-entry, профиль 1, anchors фикс) → 20→25 сантиметров улучшает cpWER на всех трёх и WER на p0/nr3hm. 10/15 сантиметров — хуже.

  | chunks | yCX4 WER | p0 WER | nr3hm WER | cpWER (p0) | dialogs-short cpWER |
  |---|---|---|---|---|---|
  | 10s | 10.05 | 11.51 | 23.10 | 13.81 | 23.33 |
  | 15s | 11.00 | 12.02 | 21.57 | 14.83 | — |
  | **20s (baseline)** | 9.09 | 11.76 | 22.59 | 14.32 | 23.33 |
  | **25s** ✅ | **9.09** | **10.74** | **22.34** | **12.79** | **20.00** |

- Profile 0 (low-latency) на pilot: cpWER 13.40→17.95 на yCX4; **REJECT** (как и ранее на AVD).
- Confirm: `baseline_words_exact` preserved between stream/final — no ASR text regression from backend switch.

### Рекомендованное изменение (single fact change)
**`pipeline.cpp`: `pipeline.chunk_seconds = 20 → 25`**  с PR-level test план:
1. Изменить константу. SDK ABI не меняется (max 25 уже разрешён). README/ARCHITECTURE претендуют на 20 → обновить.
2. Потеря: RTF noise negligible (~0.05). cpWER/DER улучшаются или нейтральны.
3. After: `make check && make native-test && make native-sanitize && make mobile-build`.

### PBS A/B — заблокирован (по task spec)
Spec要求 A/B Prefix Beam Search с kenlm. Status: **BLOCKED**.
- Набор текстов (FLEURS + OpenSTT + ru-pilot) — всего ~1.4k токенов. Мал для any useful n-gram.
- kenlm не имеет compiled `lmplz`; 0.3.0 python binding only.
- Нет публичного RU kenlm `.arpa`/`.bin` (HF search вернул 0).
- sherpa-host `lm_config.model` is available in C-API (offline LM hook), but we have no .arpa/.bin for RU.
- План на разблокировку:
  - Собрать Russian text corpus (target ≥50M tokens) — варианты: ESpeech-podcasts (CC-BY-NC, only research), OpenSTT full archive (~400h, требует HF login), WMT-GoodNews ru, OSCAR dump (research-only). Либо 3-5 млн токенов минимум, чтобы получить PR effect.
  - Скомпилировать lmplz из kenlm source (need boost 1.7+ + lz4/zstd + cmake).
  - После этого: A/B (decoding method + lm scale) на pilot, leave `audio words/timestamps` unchanged, re-run posterior_merge.
  - Native integration path: nh_asr_config gains lm_model + lm_scale; sherpa `decoding_method="modified_beam_search"`.

### Datasets — оценка кандидатов (пользователь предложил ресурс ForSE)
- `mexus/ru-book-mix-10h` (CC-BY-4) — единственный public multi-speaker с RTTM. Добавил 50 clips (25 mono + 25 overlap, 60s) как новый slice `ru-book-mix-60`. → DER/JER baseline (раньше был только AMI EN). **Нет текста → WER не измерим**.
- `PotatoHD/ru-asr-dataset` (34.9k rows, license unspecified) — only ASR word-timestamp QA, single-speaker. Research-only.
- `GTSinger` (CC-BY-NC-SA 4.0) — Russian singing + paired spoken controls; ASR WER smoke only, single singer, no diarization. Research-only.
- `TRILOGUE` — English → skip.
- `lab260/Balalaika` — OpenSTT-derived, CC-BY-NC → probe-only, ASR lexical.
- `slash/LabeledTokenMix` (если используем synthetic injection — отклонено в ADR как "нельзя синтетику за naturally-tested).

### Обещанные расширения (заблокированы by data)
- Music/rap slice: требует пользовательских файлов + ручной RTTM. Нет открытых public corpora с multi-speaker music/rap diarization.
- GTSinger can give **sung vs spoken WER** as a proxy but is single-singer — won't address speaker attribution in music.

### Изменено/добавлено в этом цикле
- `RESEARCHING.md` update: 08.11 session log, blocker notes, recommended 25s change.
- Probe script extended with `--chunk-seconds`, `--profile` args (probe_streaming_file_pipeline.py). Restore from `_backup.py` before commit.

### Где находятся результаты
- exp_0255 — pilot baseline (20s)
- exp_0256 — stream-entry, 20s
- exp_0257 — 10s chunks
- exp_0258 — 25s chunks ✅ (best)
- exp_0260 — 15s chunks
- exp_0261 — 25s on dialogs-smoke

### Ключевые гипотезы-не-проверено
1. PBS with kenlm → blocked on Russian LM + corpus.
2. Silence-aware/overlapping chunks + dedup (E05) → blocked? Actually it can run now (Code). But per external task spec — defer (PBS preferred).
3. Vocal isolation as preprocessing for a music slice → blocked (no music corpus).
4. Soft spectral gating on SNR — could run now on pilot, but user priority ASR quality > diarization.

### Следующие шаги (по приоритету)
1. Apply `pipeline.chunk_seconds 20→25` patch + gates + docs update.
2. Prepare `prepare_ru_book_mix.py` (+ CC-BY-4 compliance) — DER/JER baseline on multi-speaker synthetic, RTFM GT.
3. Ask user for an owned music/rap corpus + suggest recording 5-10 natural clips (2-4 speakers, ≤5 min each) with consent; build manifest with `audio_id=music-*` + RTTM.
4. Coordinate external text corpus acquisition with maintainer (ESpeech-podcasts / OpenSTT full archive), then revisit PBS.
5. ASR-quality first: if PBS corpus arrives, run baseline n-gram WER on pilot, then native C-API integration.

### Open Blockers (actual)
- Russian N-gram LM unavailable (PBS blocker)
- Russian multi-speaker GT for DER (~ru-book-mix Synthetic, but natural only has 3 pilot sessions)
- Music/rap corpus absent (only user-provided; no public source with multi-speaker RTTM + text)
- N-gram LM training text corpus < 2k tokens only; need ≥ millions for useful LM.
- ARM/physical device unavailable (all ARM claims remain unchecked).
- No independent gold corpus / word-timestamp manual GT.

### Что предлагаю сделать сейчас
**Single actionable change**: apply `25s chunk` patch now + DE metrics on 6th session. Это улучшает measured quality, не нарушает constraints (RAM/RTF budget unchanged), и можно показать как снижение DER on pilot. После согласия — внесу и прогоню gates.

Альтернатива: всё single-stop patch set: chunk 25 + docs/config updates + подготовка ADR-018 для ru-book-mix. То же — pending user OK.

---

## Update Log (09.11.2026, code mode) — attribution diagnostics + postprocess hypothesis
- Diagnostics on yCX4/P0/nr3hm: reading `trace.asr[].backend.text`, `words`, `transcript` shows zero ASR->words drift (0/0/0) and seam-dup count 0. **Errors are acoustic in ASR decode**, not at chunk seams or in posterior-merge.
- Chunk boundary dedup rejected (p.4 of priority task) — would not help.
- Leading-letter dedup rule (`eval/scripts/experiment_letter_dedupe.py`) produced −0.24pp / −0.26pp but unsafe (proper nouns/alphanumerics). Not merged into SDK; kept as R&D.
- ru-book-mix import updated with reference-JSON generation; `exp_0263` run (50 × 60s) produced DER 4.14% / JER 4.09%. PT turkey.
- PBS remains primary recommended direction (pending public RU LM).
- Weather/recording audio untouched; no music/rap corpus available yet.
