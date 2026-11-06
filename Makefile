.PHONY: help doctor check hooks test android-check
help:
	@echo 'doctor        Show missing audio/Android tools (strict)'
	@echo 'check         Check task protection and source manifests'
	@echo 'hooks         Enable repository pre-commit hook'
	@echo 'test          Test automation'
	@echo 'android-check Build, lint, unit tests, APK permission check'
	@echo 'More: python3 scripts/audio_tools.py --help'
doctor:
	python3 scripts/audio_tools.py doctor
check:
	python3 scripts/audio_tools.py check
hooks:
	python3 scripts/audio_tools.py hooks
test:
	python3 -m unittest discover -s scripts/tests -v
android-check:
	cd src/mobile/android && sh ./gradlew :app:assembleDebug :app:lintDebug :app:testDebugUnitTest
	python3 scripts/audio_tools.py apk src/mobile/android/app/build/outputs/apk/debug/app-debug.apk
