# exp_0001: bounded decoder memory screening

Synthetic stereo MP3, 48 kHz, 1 kHz sine, lengths 10 and 600 seconds.
One cold process per length. Linux x86_64 developer host; no Android or ML models.
Input generated with pinned FFmpeg; output is 16 kHz mono PCM.
Maximum callback buffer: 16000 float frames = 64000 bytes.

Commands from repository root:

```sh
.tools/bin/ffmpeg -v error -y -f lavfi -i sine=frequency=1000:sample_rate=48000:duration=600 -ac 2 -q:a 5 .audio-runs/fixtures/long.mp3
.tools/bin/ffmpeg -v error -y -i .audio-runs/fixtures/long.mp3 -t 10 .audio-runs/fixtures/short.mp3
python3 scripts/benchmark_decode.py .audio-runs/fixtures/short.mp3
python3 scripts/benchmark_decode.py .audio-runs/fixtures/long.mp3
```

Raw logs remain at `.audio-runs/<run_id>/`; aggregate metadata is in metrics.json.
Source revision was f7d85cb plus the uncommitted native SDK preparation now stored
in this change. This is one screening run, not a latency distribution or proof
of bounded peak memory for arbitrary MP3s. RSS includes the decoder process and
loaded native libraries, no inference. Sine signals do not measure speech quality.
Results suggest bounded decoder memory for these inputs; ASR/diarization/LLM
and Android WER/DER/RTF/RAM remain **not measured**.
