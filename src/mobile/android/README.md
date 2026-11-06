# Neurostenographer Android

Полностью офлайн-прототип Android-приложения на Jetpack Compose с MVVM-архитектурой.

## Возможности
- импорт MP3/M4A/WAV через SAF;
- эмуляция локального конвейера ASR → диаризация → speaker turns;
- просмотр расшифровки с таймлайном;
- редактирование структуры;
- экспорт результата в JSON через Storage Access Framework;
- настройки точности и приватности;
- отсутствие permission `INTERNET` в манифесте.

## Сборка
1. Установите Android Studio и Android SDK 35.
2. Откройте каталог `src/mobile/android`.
3. Выполните `./gradlew assembleDebug`.

Для реальной модели замените заглушку конвейера в `MainViewModel` на AndroidRuntime inference adapter. Формат JSON экспорта соответствует `transcript`, `speaker_id`, `start_ms`, `end_ms`, `text`.
