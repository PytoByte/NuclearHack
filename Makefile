export PATH := $(CURDIR)/.venv/bin:$(CURDIR)/.tools/bin:$(PATH)
.PHONY: help doctor check hooks test android-check audio-bootstrap mobile-bootstrap native-build native-test native-sanitize mobile-build
help:
	@echo 'doctor        Show missing native audio tools (strict)'
	@echo 'check         Check task protection and source manifests'
	@echo 'hooks         Enable repository pre-commit hook'
	@echo 'test          Test automation'
	@echo 'android-check Build, lint, unit tests, APK permission check'
	@echo 'audio-bootstrap Install pinned native development dependencies locally'
	@echo 'native-test   Build native SDK, CTest, and Python C ABI tests'
	@echo 'native-sanitize ASan/UBSan build and tests'
	@echo 'mobile-bootstrap Also install NDK for cross-compilation'
	@echo 'mobile-build  Cross-compile ARM64 and x86_64 SDK (no UI)'
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
native-test: native-build
	.venv/bin/ctest --test-dir .build/audio --output-on-failure
	. scripts/audio-env.sh && python3 -m unittest discover -s scripts/tests -v
native-sanitize:
	.venv/bin/cmake -S src/audio -B .build/audio-asan -G Ninja -DCMAKE_BUILD_TYPE=Debug -DNH_SANITIZE=ON
	.venv/bin/cmake --build .build/audio-asan -j 4
	.venv/bin/ctest --test-dir .build/audio-asan --output-on-failure
mobile-build:
	.venv/bin/python scripts/build_mobile_audio.py
