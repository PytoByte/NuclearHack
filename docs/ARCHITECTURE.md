# Аудиомодуль: текущая архитектура

Обновлено: 07.11.2026. Реализованный код и принятые ограничения; этапы,
эксперименты и ADR — в [RESEARCH.md](RESEARCH.md).

## Границы и стек

Самостоятельный C++17 SDK с C ABI: `src/audio/include/nuclear_audio.h`.
CMake/Ninja, Linux x86_64 для разработки, NDK r27d/API 26 для Android
ARM64/x86_64. Android Java/JNI host — тонкий тестовый клиент, не ядро SDK.
Без Gradle/Kotlin/Compose в новом модуле; существующий UI не изменяется.

```text
клиент → libnuclear_audio.so / C ABI
  nh_decode_file → miniaudio → mono 16-kHz f32 blocks
  nh_transcribe_file:
    decode → temporary disk PCM → CTC chunks → release ASR
      → mmap PCM → segmentation + embeddings + auto clustering → release diarizer
      → CTC word spans + maximum speaker overlap → strict transcript JSON
  nh_summarize_file (отдельное действие):
    transcript JSON → local llama.cpp / Qwen3 → отдельный summary.txt
```

Низкоуровневые ASR/diarizer API доступны независимо от файлового orchestrator.
Runtime — sherpa-onnx 2.0.1 / ONNX Runtime 1.28.2 CPU и pinned llama.cpp.
Модели передаются локальными путями. Скачивания и сетевого inference в SDK нет.

## Файловый пайплайн

miniaudio 0.11.23 потоково декодирует MP3/WAV с настоящим ресемплированием
(linear + low-pass 8-го порядка). Один PCM-блок переиспользуется. Временный
PCM создаётся через mkstemp в scratch клиента, сразу unlink, удаляется при
закрытии. Размер на диске 64 KB/s; ASR читает ограниченные чанки 1–25 s.
После ASR PCM mmap используется whole-file diarizer. Это ограничивает heap
декодера, но не доказывает постоянную память всего inference.

Текущий принятый preset ограничен **600 s**. API принимает явный бюджет
до3600s (+1ms для codec rounding); часовая обработка ещё не сертифицирована
длинным stress-run. Последний хвост перераспределяется, чтобы не оставлять
один отсчёт отдельным ASR-чанком; input<1s дополняется нулями только для модели. В файловом orchestrator VAD,
silence-aware chunks и overlap/dedup ещё не реализованы.
Отдельный incremental `nh_vad_*` API реализует Silero: 512-sample windows,
30-s circular buffer, немедленная доставка unpadded source-frame intervals,
flush/release. Research harness проверяет padding и исходные offsets;
VAD не включён в принятый preset без A/B.
Стереоканалы сводятся в mono; channel-aware диаризации пока нет.

ASR файлового API: GigaAM-v3 CTC INT8, 4 CPU threads — host preset;
другие CTC, RNNT и Whisper доступны через низкоуровневые constructors.
`nh_asr_create` задаёт decoder/language явно: RNNT greedy/modified beam,
Whisper ru/auto. CTC/Whisper beam без FST graph отклоняется. Hotwords —
только поддерживаемый RNNT beam, не корректор текста.
ASR текст не редактируется. CTC char/BPE timestamps собираются в word spans с учётом пробелов внутри token,
последний символ +40 ms; это не forced alignment. При несовпадении
реконструированных слов с исходным текстом сохраняется whole-chunk span,
с явным `chunk_fallback` в trace, без подмены текста.

Diarization: pyannote segmentation FP32 → ERes2Net embeddings → автоматическая
agglomerative clustering. Число участников не задаётся. Порог — cosine
**dissimilarity** в (0,2], provisional .8 по AMI validation. minDurationOn/Off
пока .3/.5 s. ID канонизируются по первому появлению и стабильны внутри файла.
Межфайловая идентификация отсутствует. Короткие реплики остаются слабым местом.

`nh_transcribe_file_with_options` позволяет A/B minDurationOn/Off и
maximum-overlap/midpoint attribution, не ломая исходный C ABI. Oracle доступен
только низкоуровневому diagnostic config; файловый production API всегда auto.
Word→speaker preset — максимальное пересечение интервалов; без пересечения
`speaker_unknown`. Соседние слова одного speaker объединяются при gap≤1200 ms.
Экспорт содержит только `transcript` и обязательные поля
`speaker_id/start_ms/end_ms/text`; временные метки целые ms исходной timeline.
MP3 encoder delay и точность границ ещё требуют отдельного измерения.
Backend ASR, word spans и raw speaker turns хранятся в отдельном trace JSON.
Вывод атомарный (temp/fsync/rename); перезапись входа/модели/trace запрещена.

## Локальная LLM и ресурсы

Отдельный `nh_summarize_file`: Qwen3-0.6B Q8_0 GGUF, CPU mmap, context 4096,
output cap 256, greedy, ChatML no-thinking. Текст транскрипта токенизируется
без интерпретации control tokens. Переполнение context возвращает явную ошибку,
молчаливого усечения нет. Резюме сохраняется отдельно; основной JSON не меняется.
ASR и diarizer уже освобождены до вызова LLM; RAII освобождает model/context/sampler.
Отсутствующий optional llama runtime явно сообщает unavailable.

Handles освобождаются явно; один handle обслуживает одну операцию, повторный
вход — NH_BUSY. Разные handles независимы; общий бюджет контролирует клиент.
Буферы callbacks заимствованы до возврата, исключения через C ABI запрещены.
ASR/diar/VAD handles используют atomic busy guard, безопасный при reentry.
Высокоуровневые file/summary вызовы совместно допускают один тяжёлый job
на процесс; конкурентный вызов возвращает NH_BUSY. Для low-level handles
суммарный бюджет остаётся обязанностью клиента.
Progress: queued/decode/asr_load/asr/diarization_load/diarization/merge/done;
LLM имеет отдельные load/prefill/generate/done stages. Отмена кооперативная
между PCM-блоками, ASR-чанками, LLM batches/tokens и стадиями. Whole-file
вызов diarization пока непрерываемый: upstream progress callback игнорирует
возвращаемый код. Отмена проверяется до/после него; это реальное ограничение
latency отмены, не обещание мгновенного прерывания.

Опциональный private checkpoint сохраняет завершённые ASR-чанки атомарно.
Идентичность: SHA256 фактического decoded PCM, модели/tokens, ABI/платформы,
runtime, chunk/thread/padding policy. Version2 cache с flock не допускает
конкурентной записи. Повреждённый cache отклоняется; cache metadata≤64MiB.
Resume повторно декодирует MP3, переиспользует только валидные ASR-чанки;
при полном cache ASR модель вообще не загружается. Diarization пока
пересчитывается целиком. Основной JSON публикуется только после завершения;
частичный ASR checkpoint не выдаётся за готовый transcript.

## Android host и offline-доставка

`src/audio/android/`: минимальный Java host, JNI → тот же C ABI. SAF импорт MP3,
просмотр реплик, экспорт JSON, отдельная кнопка резюме и отмена. Модели
предварительно устанавливаются в private files; Android-код их не скачивает.
APK собирается javac/d8/aapt2/zipalign/apksigner без Gradle. API 35, min26,
ARM64/x86_64; в проверенном manifest **нет INTERNET**.

Изолированный AVD NuclearAudio4G: API35 Google APIs/x86_64, 4096 MiB, 4 cores,
headless, adb5039/emulator-5558, airplane mode. `AudioInstrumentation` проводит
три MP3 через ASR/diar/JSON/optional LLM, пишет stage events, wall time,
per-case sampled PSS и **process-lifetime** peak RSS. Доставка весов — локальный
bundle с лицензиями/manifest, SHA256 проверяются перед упаковкой и на устройстве.

## Проверка и воспроизводимость

`make check native-test native-sanitize mobile-build research-test`.
ASan/UBSan инструментируют наш код, не готовые sherpa/ONNX binaries.
Release без fast-math; переносимый CPU baseline. Проверяются ABI и 16-KiB
LOAD alignment. Cross-build ARM64 не является доказательством запуска ARM64.

Дополнительно: `scripts/build_llama_audio.py`, `scripts/bootstrap_android_audio.py`,
`scripts/build_android_host.py`, `scripts/package_offline_models.sh`,
`scripts/install_android_audio.py`, `eval/scripts/run_android_pipeline.py`.
Host harness вызывает тот же C ABI; Python занимается данными и scoring.
Post-build provenance сохраняет source tar, SDK/CLI/runtime binaries и hashes;
каждый новый run копирует actual Python harness. APK содержит buildinfo
обоих ABI и runtime notices. Android runner сверяет SHA установленного APK
с локальным и проверяет реальную RAM/ABI/airplane mode.
Версии/хеши: `config/*lock.json`, `uv.lock`. Веса, аудио и raw logs исключены
из Git. [src/audio/README.md](../src/audio/README.md) содержит команды API.


### Исследование пунктуации и архитектур (не принято в production)

Принятый native pipeline сохраняет CTC INT8,chunk20s,ERes2Net+FP32 segmentation,threshold.8,window shift.1.
Window.5 остаётся кандидатом: synthetic cpWER лучше,отложенный AMI DER хуже. Отдельный RUPunct INT829MB
с ORT CPU исследуется после ASR; сейчас это eval-компонент,не часть C ABI. Его output хранится отдельно,
лексическая последовательность обязана совпадать с ASR. Метрики различают lexical/punctuation ошибки и unknown speakers.
Короткие фрагменты — повторный offline decode,не causal streaming. Android ARM64 cross-build существует,
но execution через x86 AVD native bridge падает: качество/RTF физического ARM пока не измерены.

Исследование79 подтвердило риск смены ASR: на вручную размеченных телефонных OpenSTT40 e2e WER20.59%
против CTC17.65%. В production ничего не переключено. `make research-pilot` воспроизводит ограниченную
последовательную очередь,включая разговорный silver/телефонный lexical eval,пунктуацию и короткие offline фрагменты.
