"""Waveform peaks for the seek bar.

A separate headless libVLC instance transcodes the file's audio to a small
mono WAV (stream output isn't paced by the clock, so a 3-minute song takes a
fraction of a second), then the samples are reduced to peak heights. Results
are cached per file so each one is only analysed once."""

import array
import hashlib
import json
import os
import tempfile
import threading
import time
import wave
from pathlib import Path

import vlc
from PySide6.QtCore import QObject, Signal

BINS = 900
CACHE = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "vlc-redesign" / "waveforms"


def _cache_file(path: Path) -> Path:
    st = path.stat()
    key = f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    return CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".json")


def _decode_peaks(path: Path) -> list[float]:
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    inst = vlc.Instance(["--quiet", "--no-sout-video", "--no-sout-spu", "--no-video", "--intf=dummy"])
    try:
        m = inst.media_new(str(path))
        dst = tmp.replace("\\", "/")
        m.add_option(f":sout=#transcode{{acodec=s16l,channels=1,samplerate=4000}}:std{{access=file,mux=wav,dst='{dst}'}}")
        p = inst.media_player_new()
        p.set_media(m)
        p.play()
        deadline = time.time() + 300
        while p.get_state() not in (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped) and time.time() < deadline:
            time.sleep(0.05)
        p.stop()
        p.release()
        with wave.open(tmp) as w:
            samples = array.array("h", w.readframes(w.getnframes()))
    finally:
        inst.release()
        try:
            os.remove(tmp)
        except OSError:
            pass
    if not samples:
        return []
    step = max(1, len(samples) // BINS)
    peaks = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        peaks.append(max(max(chunk), -min(chunk)))
    top = max(peaks) or 1
    # Square root lifts quiet passages so the shape stays readable.
    return [round((v / top) ** 0.5, 3) for v in peaks]


class WaveformLoader(QObject):
    """Computes peaks off the UI thread; `ready(path, peaks)` arrives on the UI thread."""

    ready = Signal(str, list)

    def __init__(self):
        super().__init__()
        self._job = 0

    def request(self, path: Path):
        self._job += 1
        job = self._job
        threading.Thread(target=self._run, args=(job, Path(path)), daemon=True).start()

    def _run(self, job, path):
        try:
            cache = _cache_file(path)
            if cache.exists():
                peaks = json.loads(cache.read_text())
            else:
                peaks = _decode_peaks(path)
                if peaks:
                    CACHE.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(peaks))
        except Exception:
            peaks = []
        if job == self._job:          # ignore results for a file we've moved past
            self.ready.emit(str(path), peaks)
