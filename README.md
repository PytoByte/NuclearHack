# Нейростенографист / Nuclear Audio SDK

Локальный офлайн-конвейер для транскрибации аудиодиалогов с диаризацией на
Android. Каталог `task/` read-only и содержит исходный brief хакатона.

## Быстрый старт

```sh
make audio-bootstrap
uv run python scripts/bootstrap_models.py giga-v3-ctc-punct nemotron3-diarization
make native-test native-sanitize
make mobile-build
make android-app
```

APK появится в `.build/android-app/neurostenographer-debug.apk`.

## Загрузка моделей

Модели скачивает разработчик, они не хранятся в Git. Приложение не имеет
доступа в интернет.

Основной набор:

```sh
uv run python scripts/bootstrap_models.py giga-v3-ctc-punct nemotron3-diarization
```

Для проверки хешей и структуры:

```sh
uv run python scripts/audio_tools.py models config/audio-models.lock.json
```

## Ветки проверок

- `make check` — базовые проверки репозитория и whitespace.
- `make native-test native-sanitize native-format-check` — проверка C++ SDK.
- `make mobile-build` — Android ABI и packaging libs.
- `cd src/mobile/android && ./gradlew ktlintCheck detekt :app:lintDebug` — Android quality gates.

## Ограничения

- Обрабатывается готовый файл до 600 секунд, это не realtime-микрофон.
- ID спикеров стабильны только внутри одного файла.
- Физический ARM runtime и word timestamp не валидировались.
- Полный Android-benchmark приложения здесь не заявляется.

## Документация

- Архитектура: `docs/ARCHITECTURE.md`
- Цели и статусы: `docs/GOALS.md`
- Исследования: `docs/RESEARCH.md`
- Правила репозитория: `AGENTS.md`
- SDK: `src/audio/README.md`
- Android-клиент: `src/mobile/android/README.md`