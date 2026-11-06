# Состояние аудиомодуля

- Готово: `dev` от `main`, fast-forward `origin/ui`, локальный pre-commit hook,
  команды диагностики, валидации JSON/моделей/APK и сохранения логов команд.
- Проверено: 7 тестов автоматизации, `make check`, smoke запуска команды с логами.
- Android baseline: отсутствует; UI возвращает подготовленные реплики.
- WER/DER/RTF/peak Android RAM: not measured — нет runtime, моделей, размеченных
  данных и подготовленного Android-окружения.
- Блокеры: Java, Android SDK/adb/emulator/build-tools, ffmpeg/ffprobe отсутствуют в PATH;
  закоммиченный local.properties содержит путь SDK с Windows.
- Следующий шаг: подготовить окружение и AVD 4 ГБ, выбрать совместимые ABI/модели,
  закрепить лицензии и SHA256; затем реализовать настоящий baseline.
- Подробные команды и ограничения: `docs/AUDIO_WORKFLOW.md`.
