# Работа с native audio SDK

Актуальное решение: самостоятельный **C++17 SDK с C ABI**, без UI/JVM/Gradle.
Архитектура и ограничения: `docs/AUDIO_ARCHITECTURE.md`.
Публичный API: `src/audio/include/nuclear_audio.h`.

## Воспроизведение окружения

Из корня проекта, на Linux x86_64 с установленными git, g++ и uv:

```sh
make audio-bootstrap
make doctor
make native-test
make native-sanitize
make mobile-bootstrap
make mobile-build
```

Bootstrap устанавливает инструменты в `.venv/` и `.tools/`, без sudo и изменений
системного окружения. Python 3.12 выбирает uv. CMake/Ninja/FFmpeg закреплены
в `uv.lock`, native runtime/miniaudio/NDK — в `config/audio-toolchain.lock.json`.
NDK скачивается только при `mobile-bootstrap`. После подготовки сборка
CMake не обращается в сеть. Повторный bootstrap пропускает готовые артефакты.
Для интерактивной работы из корня: `. scripts/audio-env.sh`.

## Автоматические проверки

- `make native-test`: Release SDK, CTest с настоящим C-клиентом и Python ctypes
  тесты C ABI, decoder, WAV/MP3, ресемплирования, alias, отмены, ошибок и concurrency.
- `make native-sanitize`: Debug SDK с ASan/UBSan, CTest decoder и границ ABI.
- `make mobile-build`: сборка ARM64/x86_64 API 26 и проверка ELF/16-KiB LOAD
  выравнивания нашего SDK, sherpa C API и ONNX Runtime; без устройства/интерфейса.
- `make check`: защита task/, source INTERNET permission, diff whitespace.
- `make hooks`: включает локальный pre-commit, читает staged manifest из индекса,
  не перезаписывает существующие пользовательские hooks.
- `.github/workflows/audio-sdk.yml`: host tests + sanitizers и mobile ABI build.
  Проверки локально выполнены; запуск CI в GitHub пока не проверен.

Source permission check не заменяет merged manifest APK. Если команда UI
собирает приложение, использовать `make android-check` (дополнительное окружение)
и `python3 scripts/audio_tools.py apk <APK>`.

## Эксперименты и контракты

```sh
.build/audio/nh-audio native-info
.build/audio/nh-audio probe input.mp3
python3 scripts/benchmark_decode.py input.mp3
python3 scripts/audio_tools.py transcript export.json
python3 scripts/audio_tools.py models models/manifest.json
python3 scripts/audio_tools.py run -- .build/audio/nh-audio probe input.mp3
```

Benchmark измеряет decoder на Linux: время, decode RTF и process peak RSS
через wait4. ASR/diarization/Android RAM этим не измеряются. Обычный `run`
сохраняет команду, git SHA, статус дерева, платформу, stdout/stderr, код возврата
и время команды в уникальном `.audio-runs/<UTC timestamp>/`.
Старые запуски не перезаписываются, каталог игнорируется Git.
Не передавать секреты через argv: команда сохраняется в метаданных.

Манифест моделей: `{"files": [...]}`; для каждого файла `path` относительно
репозитория, `source`, `version`, `license`, `sha256`. Включать веса,
токенизаторы и конфигурации. Пустой manifest не проходит. Загрузчик и
упаковщик весов появятся после выбора конкретных моделей, без фиктивных хешей.

Сейчас SDK предоставляет низкоуровневые runtime-операции, а не полный файловый
pipeline. Для baseline остаются model bootstrap, file orchestrator, VAD,
глобальная диаризация, экспорт и отдельная LLM. Модельные измерения пока отсутствуют.

## История репозитория

`dev` создана от `main`, UI влит fast-forward. Пользовательский
`docs/AGENT_AUDIO_HACKATHON.md` сохраняется без изменения и не добавляется в Git.
Его Android-app-first последовательность заменена текущим запросом на SDK.
`task/` — read-only. Из ui ранее перенеслись только executable bits файлов task/;
новых изменений этого каталога не делаем.
В UI уже tracked build/.gradle/.idea и Windows local.properties; SDK их не
использует и не изменяет. .gitignore не снимает существующие файлы с учёта.
