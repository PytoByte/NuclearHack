# Native SDK: зависимости и референсы

| Компонент | Версия / источник | Лицензия | Использование |
| --- | --- | --- | --- |
| sherpa-onnx | v2.0.1 / af2d8d81dbfa61c4cea4c568da78f3982edca005 | Apache-2.0 | C API ASR и diarization |
| ONNX Runtime | 1.28.2, бинарник в sherpa CPU distribution v2.0.1 | MIT | CPU inference; версия проверена через OrtGetApiBase |
| miniaudio | 0.11.23 / f40cf03f80cdb7e741d43e53b7e706e8c1394bcf | public domain или MIT No Attribution, на выбор | Native MP3/WAV decoder + resampler |
| Android NDK | r27d / 27.3.13750724 | Android SDK/NDK license и bundled notices | Только сборка |
| imageio-ffmpeg | 0.6.0 / FFmpeg binary 7.0.2 в Linux wheel | BSD-2-Clause wrapper; FFmpeg binary имеет собственную лицензию | Только fixtures/eval на dev-машине |
| CMake / Ninja | 3.31.6 / 1.11.1.4 wheel | BSD-3-Clause / Apache-2.0 | Только сборка |

Ссылки: [sherpa](https://github.com/k2-fsa/sherpa-onnx/tree/v2.0.1),
[ONNX Runtime](https://github.com/microsoft/onnxruntime),
[miniaudio license](https://github.com/mackron/miniaudio/blob/f40cf03f80cdb7e741d43e53b7e706e8c1394bcf/LICENSE),
[imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg).

SHA256 загружаемых native-артефактов закреплены в
`config/audio-toolchain.lock.json`; wheels — в `uv.lock`.
Никакие веса пока не входят в SDK. Лицензии каждого модельного файла
будут записаны отдельно до его использования/распространения.
Перед поставкой SDK переносить license/NOTICE тексты бинарных зависимостей
и проверять их условия; таблица не заменяет bundled notices.
FFmpeg не линкуется и не поставляется в мобильной библиотеке.

## Инспекция Anti-Vocale

Референс прочитан локально, commit
`aca3eaf8b41fa97c94a421de9e9652c9d188ce8e`, исходники Apache-2.0.
Инспектированы PROJECT_INDEX, quality-matrix, FAQ, transcription/audio и eval.
Код не копировался. Применимые решения:

- общий backend interface и отдельный orchestrator;
- отдельные lifecycle моделей и явное освобождение runtime;
- ограниченные PCM-чанки и сохранение исходных offsets;
- единый eval harness с закреплёнными моделями;
- отдельные измерения decoder chain и runtime;
- checksum-манифесты и проверка ABI перед отладкой интеграции;
- прогресс/очередь как контракт SDK, независимо от визуального клиента.

Конфликты с нашим ТЗ, которые не переносим:

- загрузка моделей приложением из сети/Hugging Face;
- remote offload пользовательского аудио;
- Firebase/аналитика и сетевые возможности отдельных вариантов;
- полное декодирование длинного аудио в RAM на части VAD-пути;
- автоматическое редактирование/обрезание слов вместо буквального результата.

Их quality-matrix описывает чужие тесты; результаты не считаются нашими
WER/DER/RTF или доказательством качества на Android 4 ГБ.
