# Состояние аудиомодуля

- Стек: самостоятельный C++17 SDK / C ABI, CMake/Ninja, CPU sherpa-onnx 2.0.1
  с ONNX Runtime 1.28.2; MP3/WAV miniaudio 0.11.23; NDK r27d, API 26+.
- Окружение готово локально в .tools/.venv; версии и контрольные суммы закреплены.
- Готово: публичный C API decoder/CTC/diarizer, CLI probe, bootstrap,
  проверки, benchmark wall/RSS, локальные hooks и конфигурация CI.
- Проверено: 13 Python-тестов, Release C ABI test, ASan/UBSan C ABI/decoder test,
  ARM64 и x86_64 cross-compilation и ELF/16-KiB alignment runtime-зависимостей.
- Измерено: exp_0001, только Linux decoder на синтетическом MP3 10/600 секунд;
  peak RSS 13092/13116 KiB, decode wall 0.0276/1.6489 секунды.
- ASR/DER/WER/RTF/peak Android RAM: not measured. Реальные веса не запускались;
  native adapters проверены сборкой/валидацией аргументов, не качеством inference.
- SDK пока предоставляет низкоуровневые операции. Следующие задачи: закрепить
  веса/лицензии и dataset; file orchestrator с global offsets/IDs и JSON;
  VAD/resampler A/B; отдельный llama.cpp adapter; headless Android execution.
- UI не является частью текущей работы. task/ и пользовательский план не меняются.
- Документация: docs/AUDIO_WORKFLOW.md, docs/AUDIO_ARCHITECTURE.md, src/audio/README.md.
