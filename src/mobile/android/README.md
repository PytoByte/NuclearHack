# Neurostenographer Android

Офлайн-клиент Jetpack Compose к нативному C++ SDK `src/audio`.
Приложение импортирует аудиофайл, выполняет локальные ASR и диаризацию
через JNI и сохраняет строгий JSON. Сеть не используется: permission
`INTERNET` отсутствует в манифесте.

## Возможности
- импорт MP3/M4A/WAV через Storage Access Framework;
- реальный локальный конвейер `nh_transcribe` → ASR → диаризация → speaker turns;
- прогресс по стадиям native SDK и отмена задания;
- просмотр, редактирование структуры и экспорт расшифровки в JSON через SAF;
- повторная обработка сохранённых результатов из библиотеки;
- опциональная локальная сводка Qwen, если в APK добавлена модель и llama runtime;
- настройки точности, потоков и приватности.

## Сборка
Нужны JDK/SDK/NDK из `.tools` и локальные модели.

```sh
make mobile-bootstrap                 # native-зависимости и NDK
make android-host-bootstrap           # JDK, Android SDK, build-tools, AVD (если ещё нет)
make mobile-build                     # .so для arm64-v8a и x86_64
.venv/bin/python scripts/bootstrap_models.py giga-v3-ctc pyannote-eres2net-fp32
make android-app                      # APK в .build/android-app/
```

`make android-app` запускает `scripts/build_android_app.py`: проверяет
нативные библиотеки и модели, собирает debug APK с `-PrequireNativeAudio=true`,
копирует его в `.build/android-app/neurostenographer-debug.apk` и проверяет
наличие `.so`, assets и отсутствие `INTERNET`.

Ручная сборка:

```sh
export JAVA_HOME="$PWD/.tools/jdk" ANDROID_HOME="$PWD/.tools/android-sdk"
cd src/mobile/android
sh gradlew :app:assembleDebug -PrequireNativeAudio=true
```

Без `-PrequireNativeAudio=true` Gradle собирает UI-заглушку без native
библиотек и моделей; такой APK не выполняет распознавание.

## Модели и runtime
`AudioModelStore` один раз копирует `assets/models` в `filesDir/models`.
Если присутствует финальный preset, используется
`giga-v3-ctc-punct` + `nemotron3-diarization`; иначе совместимый
`giga-v3-ctc` + `diarization`. Сводка доступна только при наличии
`qwen3-0.6b-q8/Qwen3-0.6B-Q8_0.gguf` и собранного llama runtime.
Модели и веса не входят в Git.

## Ограничения
- Обрабатывается готовый файл до 3600 секунд (1 часа); это лимит SDK, а не файловый формат. Для гарантируемого качества и RAM более длинные записи должны быть сегментированы или обработаны с более строгими ресурсными профилями; это не real-time микрофон.
- Запуск на физическом Android-устройстве и ARM-метрики качества/RTF/RAM
  не измерены; проверены cross-build и упаковка APK.
- JSON содержит `transcript` с `speaker_id`, `start_ms`, `end_ms`, `text`.
- Экспорт и импорт работают только через SAF; приложение не пишет во внешние
  каталоги без выбора пользователя.
