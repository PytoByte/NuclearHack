# Нейростенографист / Nuclear Audio SDK

Локальный офлайн-конвейер для транскрибации аудиодиалогов с диаризацией.

## Установка

Скачайте и установите готовый APK из GitHub Releases

## Использование

1. На главном экране выберите аудио файл.
2. Дождитесь завершения транскрибации.
3. Результат доступен по нажатию на расшифровку в списке недавних или списке всех записей.
4. После открытия расшифровки можно скачать её в формате JSON по кнопке в правом верхнем углу.

## Сборка с моделями

```sh
uv run python scripts/bootstrap_models.py giga-v3-ctc-punct nemotron3-diarization-q8
uv run python scripts/audio_tools.py models config/audio-models.lock.json
make mobile-build
make android-app
```

## Дебаг-сборка

```sh
cd src/mobile/android
sh gradlew :app:assembleDebug -PrequireNativeAudio=true
```

Результат: `.build/android-app/neurostenographer-debug.apk`.

## Релиз-сборка

```sh
make android-release
```

Результат: `.build/android-app/neurostenographer-release-signed.apk`.

## Документация

- Архитектура и модели: `docs/ARCHITECTURE.md`
- Ограничения: `docs/LIMITATIONS.md`
- Результаты тестов: `docs/BENCHMARK.md`
- Репозиторий/infra: `docs/RESEARCH.md`
