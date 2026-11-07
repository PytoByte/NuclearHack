# Scripts

Рабочие скрипты репозитория. Запускать из корня проекта, если явно не указано иное. Python-зависимости поставляются через `uv sync`; большинство проверок используют только стандартную библиотеку. 
Скрипты импортируют соседние модули из `scripts/`, поэтому запускать их следует через `uv run python ...` или `.venv/bin/python ...`, а не системным `python3`. `make` и shell-обёртки уже используют правильный интерпретатор.

## Основные команды

```sh
make check                      # защита task/, permission INTERNET, diff whitespace
make test                      # unit tests из scripts/tests
make doctor                    # проверка локальных инструментов
uv run python scripts/audio_tools.py transcript result.json
uv run python scripts/audio_tools.py models config/audio-models.lock.json
uv run python scripts/audio_tools.py apk app.apk
uv run python scripts/audio_tools.py run -- uv run python -m unittest discover -s scripts/tests
```

Android-проверки запускаются из `src/mobile/android`:
```sh
./gradlew assembleDebug
./gradlew :app:lintDebug
```

## Группы скриптов

### Проверки и отчёты
- `audio_tools.py` — `doctor`, `hooks`, `check`, `transcript`, `apk`, `models`, `run`
- `benchmark_decode.py` — время и RSS нативного декодера, без inference
- `verify_models.py` — проверка модели по lock-манифесту

### Окружение и модели
- `bootstrap_audio.py` — установка pinned native-зависимостей без sudo
- `bootstrap_models.py` — developer-only загрузка pinned-моделей
- `bootstrap_android_audio.py` — подготовка изолированного Android host/test-окружения
- `bootstrap_nemo_reference.py`, `bootstrap_clustering_reference.py` — reference-материалы исследования
- `derive_audio_models.py` — воспроизведение pinned-дериваций моделей
- `sync_audio_registry.py` — индекс экспериментов

### Сборка и поставка
- `format_audio.py` — применение/проверка `src/audio/.clang-format`
- `stamp_audio_build.py` — фиксация бинарников и hashes после сборки
- `build_mobile_audio.py` — cross-compile native SDK для Android
- `build_llama_audio.py` — сборка CPU-only llama runtime
- `build_android_host.py` — минимальный offline SDK test APK
- `package_audio_sdk.py`, `package_offline_models.py` — комплекты SDK/моделей
- `install_android_audio.py` — установка debug APK и моделей на emulator

### Shell-обёртки
- `audio-env.sh`, `android-env.sh` — настройка PATH/переменных среды
- `bootstrap_models.sh`, `package_offline_models.sh` — запуск соответствующих Python-скриптов
- `cppcheck.sh`, `pre-commit.sh`, `pre-push.sh` — локальные quality gates

## Исследовательские скрипты

`eval/scripts/` содержит подготовку данных, запуски и скоринг. Там же находятся `probe_*`, `compare_*`, `run_*`, `prepare_*`. Они не входят в shipped SDK и могут требовать research-зависимости (`uv sync --group research`).

## Тесты

```sh
uv run python -m unittest discover -s scripts/tests -v
```

Тесты в `scripts/tests/test_audio_tools.py` и `test_native_audio.py` не требуют сетевых загрузок, кроме уже собранных нативных артефактов для `test_native_audio.py`.

## Важные соглашения

- `task/` доступен только для чтения; скрипты и хуки блокируют изменения там.
- Модели, аудио, логи и `.audio-runs` не коммитятся.
- Любые изменения в нативном C++ должны проходить `make native-test native-sanitize native-format-check`.
- Новые команды документируются здесь только если это стабильные точки входа CLI.