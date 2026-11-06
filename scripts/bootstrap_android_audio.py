#!/usr/bin/env python3
"""Prepare the isolated 4-GB headless Android test environment (no sudo)."""
import json
import os
from pathlib import Path
import subprocess
import re
from bootstrap_audio import install, ROOT


def environment():
    tools = ROOT / '.tools'
    env = dict(os.environ)
    env.update(JAVA_HOME=str(tools / 'jdk'), ANDROID_HOME=str(tools / 'android-sdk'),
        ANDROID_SDK_ROOT=str(tools / 'android-sdk'), ANDROID_USER_HOME=str(tools / 'android-user'),
        ANDROID_AVD_HOME=str(tools / 'android-avd'), ANDROID_ADB_SERVER_PORT='5039')
    env['PATH'] = ':'.join(str(tools / p) for p in ('jdk/bin', 'android-sdk/platform-tools',
        'android-sdk/emulator', 'android-sdk/cmdline-tools/19.0/bin')) + ':' + env['PATH']
    return env


def main():
    lock = json.loads((ROOT / 'config/android-host.lock.json').read_text())
    for item in lock['artifacts']:
        install(item)
    env = environment()
    Path(env['ANDROID_USER_HOME']).mkdir(parents=True, exist_ok=True)
    Path(env['ANDROID_AVD_HOME']).mkdir(parents=True, exist_ok=True)
    logs = ROOT / '.audio-runs/android-setup'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / 'licenses.log').open('w') as output:
        subprocess.run(['sdkmanager', '--sdk_root=' + env['ANDROID_HOME'], '--licenses'],
                       input='y\n' * 100, text=True, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
    # Emulator archives contain source.properties but no package.xml. Older
    # avdmanager cannot discover that generic package without local metadata.
    emulator_package = Path(env['ANDROID_HOME']) / 'emulator/package.xml'
    if not emulator_package.exists():
        template = (Path(env['ANDROID_HOME']) / 'platform-tools/package.xml').read_text()
        properties = (Path(env['ANDROID_HOME']) / 'emulator/source.properties').read_text()
        version = re.search(r'Pkg.Revision=(\S+)', properties).group(1).split('.')
        template = template.replace('path="platform-tools"', 'path="emulator"')
        revision = '<revision>' + ''.join(f'<{name}>{part}</{name}>' for name, part in zip(('major','minor','micro'), version)) + '</revision>'
        template = re.sub(r'<revision>.*?</revision>', revision, template)
        template = re.sub(r'<display-name>.*?</display-name>', '<display-name>Android Emulator</display-name>', template)
        emulator_package.write_text(template)
    path = Path(env['ANDROID_AVD_HOME']) / 'NuclearAudio4G.avd'
    if not path.exists():
        with (logs / 'avd-create.log').open('w') as output:
            subprocess.run(['avdmanager', 'create', 'avd', '-n', 'NuclearAudio4G', '-k',
                'system-images;android-35;google_apis;x86_64', '--device', 'pixel_5'],
                input='no\n', text=True, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
    config = path / 'config.ini'
    entries = dict(line.split('=', 1) for line in config.read_text().splitlines() if '=' in line)
    entries.update({'hw.ramSize': '4096', 'hw.cpu.ncore': '4', 'disk.dataPartition.size': '6G',
        'hw.lcd.width': '720', 'hw.lcd.height': '1280', 'hw.lcd.density': '320',
        'fastboot.forceColdBoot': 'yes', 'fastboot.forceFastBoot': 'no'})
    config.write_text(''.join(f'{k}={v}\n' for k,v in entries.items()))
    result = subprocess.run(['emulator', '-accel-check'], env=env, capture_output=True, text=True)
    (logs / 'accel-check.log').write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit('Android acceleration unavailable; see setup log')
    print('Ready: NuclearAudio4G, API35 x86_64, 4096 MB, 4 vCPU, isolated adb port 5039')


if __name__ == '__main__':
    main()
