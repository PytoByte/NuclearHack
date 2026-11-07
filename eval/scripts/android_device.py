"""Verified access to the project's isolated offline 4GB emulator only."""
import json
import subprocess
import sys
from pathlib import Path
from native_sdk import ROOT
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_android_audio import environment
from bootstrap_models import sha256

PACKAGE='com.hexteam.audiohost'

class AndroidDevice:
    def __init__(self):
        self.env=environment()
        self.adb=[str(ROOT/'.tools/android-sdk/platform-tools/adb'),'-P','5039','-s','emulator-5558']
        if self.shell('getprop','ro.kernel.qemu').strip()!='1':raise RuntimeError('Expected isolated emulator')
        self.abi=self.shell('getprop','ro.product.cpu.abi').strip()
        if self.abi!='x86_64':raise RuntimeError('Expected measured x86_64 AVD profile')
        if self.shell('settings','get','global','airplane_mode_on').strip()!='1':raise RuntimeError('Airplane mode required')
        self.memory=self.shell('cat','/proc/meminfo')
        kib=int(next(l.split()[1] for l in self.memory.splitlines() if l.startswith('MemTotal:')))
        if not 3700*1024<=kib<=4096*1024:raise RuntimeError('AVD memory differs from 4GB profile')
        self.apk=ROOT/'.build/android-host/audio-sdk-host.apk';self.apk_sha256=sha256(self.apk)
        installed=self.shell('pm','path',PACKAGE).strip().removeprefix('package:')
        actual=self.shell('toybox','sha256sum',installed).split()[0]
        if actual!=self.apk_sha256:raise RuntimeError('Installed APK differs from local APK; install current build')
    def shell(self,*command):
        return subprocess.check_output(self.adb+['shell',*command],env=self.env,text=True)
    def pull(self,run,name,destination):
        data=subprocess.check_output(self.adb+['exec-out','run-as',PACKAGE,'cat','files/results/'+run+'/'+name],env=self.env)
        path=destination/name;path.write_bytes(data);return path
    def logs(self,destination):
        with (destination/'logcat.txt').open('w') as log:
            subprocess.run(self.adb+['logcat','-d','-t','3000'],env=self.env,stdout=log)
    def metadata(self):
        return dict(meminfo=self.memory,cpuinfo=self.shell('cat','/proc/cpuinfo'),
            build=self.shell('getprop','ro.build.fingerprint'),airplane_mode=True,
            connectivity=self.shell('dumpsys','connectivity'),git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
