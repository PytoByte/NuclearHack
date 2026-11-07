export PATH := $(CURDIR)/.venv/bin:$(CURDIR)/.tools/bin:$(PATH)
.PHONY: help doctor check hooks test android-check audio-bootstrap mobile-bootstrap native-build native-test native-sanitize mobile-build
.PHONY: research-bootstrap research-test
.PHONY: llama-build android-host-bootstrap android-host-build offline-package android-app
llama-build:
	.venv/bin/python scripts/build_llama_audio.py
android-host-bootstrap: mobile-bootstrap
	.venv/bin/python scripts/bootstrap_android_audio.py
android-host-build:
	.venv/bin/python scripts/build_llama_audio.py --android arm64-v8a
	.venv/bin/python scripts/build_llama_audio.py --android x86_64
	$(MAKE) mobile-build
	.venv/bin/python scripts/build_android_host.py
offline-package:
	.venv/bin/python scripts/package_offline_models.py
help:
	@echo 'doctor        Show missing native audio tools (strict)'
	@echo 'check         Check task protection and source manifests'
	@echo 'hooks         Enable repository pre-commit hook'
	@echo 'test          Test automation'
	@echo 'android-check Build, lint, unit tests, APK permission check'
	@echo 'audio-bootstrap Install pinned native development dependencies locally'
	@echo 'native-test   Build native SDK, CTest, and Python C ABI tests'
	@echo 'native-sanitize ASan/UBSan build and tests'
	@echo 'leak-check      cppcheck + clang-tidy + ASan/LSan + Valgrind over src/audio (Linux host/WSL)'
	@echo 'mobile-bootstrap Also install NDK for cross-compilation'
	@echo 'mobile-build  Cross-compile ARM64 and x86_64 SDK (no UI)'
	@echo 'android-app   Build offline Compose APK with native SDK and models'
	@echo 'research-bootstrap Prepare pinned models and FLEURS validation40'
	@echo 'research-test Test fixed WER normalization and scoring'
	@echo 'More: python3 scripts/audio_tools.py --help'
doctor:
	. scripts/audio-env.sh && python3 scripts/audio_tools.py doctor
check:
	python3 scripts/audio_tools.py check
hooks:
	python3 scripts/audio_tools.py hooks
test:
	python3 -m unittest discover -s scripts/tests -v
android-check:
	cd src/mobile/android && sh ./gradlew :app:assembleDebug :app:lintDebug :app:testDebugUnitTest
	python3 scripts/audio_tools.py apk src/mobile/android/app/build/outputs/apk/debug/app-debug.apk
audio-bootstrap:
	uv sync --frozen
	.venv/bin/python scripts/bootstrap_audio.py
mobile-bootstrap: audio-bootstrap
	.venv/bin/python scripts/bootstrap_audio.py --android
native-build:
	.venv/bin/cmake -S src/audio -B .build/audio -G Ninja -DCMAKE_BUILD_TYPE=Release
	.venv/bin/cmake --build .build/audio -j 4
	.venv/bin/python scripts/stamp_audio_build.py --build .build/audio
native-test: native-build
	.venv/bin/ctest --test-dir .build/audio --output-on-failure
	. scripts/audio-env.sh && python3 -m unittest discover -s scripts/tests -v
native-sanitize:
	.venv/bin/cmake -S src/audio -B .build/audio-asan -G Ninja -DCMAKE_BUILD_TYPE=Debug -DNH_SANITIZE=ON
	.venv/bin/cmake --build .build/audio-asan -j 4
	.venv/bin/python scripts/stamp_audio_build.py --build .build/audio-asan
	.venv/bin/ctest --test-dir .build/audio-asan --output-on-failure
mobile-build:
	.venv/bin/python scripts/build_mobile_audio.py
android-app:
	.venv/bin/python scripts/build_android_app.py
research-bootstrap: audio-bootstrap
	uv sync --frozen --group research
	$(MAKE) native-build
	.venv/bin/python scripts/bootstrap_models.py
	.venv/bin/python eval/scripts/prepare_fleurs.py --split validation
research-test:
	.venv/bin/python -m unittest discover -s eval/tests -v

.PHONY: frontend-reference-bootstrap
frontend-reference-bootstrap:
	test -x .tools/frontend-env/bin/python || uv venv .tools/frontend-env --python .venv/bin/python
	uv pip install --python .tools/frontend-env/bin/python 'torch==2.9.0+cpu' 'librosa==0.11.0' 'numpy==2.2.6' 'scipy==1.18.1' --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match

.PHONY: research-pilot
research-pilot: audio-bootstrap
	uv sync --frozen --group research
	$(MAKE) native-build
	.venv/bin/python scripts/bootstrap_models.py giga-v3-ctc giga-v3-ctc-punct pyannote-eres2net-fp32 rupunct-small-int8
	.venv/bin/python eval/scripts/prepare_russian_pilot.py
	.venv/bin/python eval/scripts/prepare_openstt_calls.py
	.venv/bin/python eval/scripts/run_research_queue.py experiments/phase3-russian-pilot.json
	.venv/bin/python scripts/sync_audio_registry.py

.PHONY: nemo-reference-bootstrap
nemo-reference-bootstrap:
	.venv/bin/python scripts/bootstrap_nemo_reference.py
	.venv/bin/python scripts/bootstrap_models.py nemotron35-asr-q8 nemotron3-diarization-gguf-q8

.PHONY: lseend-reference-bootstrap
lseend-reference-bootstrap: frontend-reference-bootstrap
	uv pip install --python .tools/frontend-env/bin/python 'onnxruntime==1.23.2' 'matplotlib==3.10.7'
	.venv/bin/python scripts/bootstrap_models.py lseend-dih3-onnx

.PHONY: native-format native-format-check sdk-package leak-check
native-format:
	.venv/bin/python scripts/format_audio.py
native-format-check:
	.venv/bin/python scripts/format_audio.py --check
leak-check: native-format-check
	.venv/bin/python scripts/leak_check.py
sdk-package: native-format-check
	.venv/bin/python scripts/package_audio_sdk.py
