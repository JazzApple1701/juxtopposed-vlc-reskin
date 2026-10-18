"""Thumbnails for the full-window library.

Videos: a headless libVLC player renders into memory through video callbacks;
we seek to ~30% and keep the first frame drawn after the seek. Music: the
embedded cover (libVLC extracts it when parsing) or a cover image in the
folder. Results are cached as JPEGs, keyed by path + size + mtime."""

import ctypes
import hashlib
import os
import queue
import tempfile
import threading
import time
from pathlib import Path

import vlc
from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QImage

from library_store import AUDIO_EXTS
from music_view import find_folder_cover

CACHE = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "vlc-redesign" / "thumbs"
WIDTH = 320

_U = ctypes.POINTER(ctypes.c_uint)
# python-vlc passes the chroma as an immutable bytes copy, so declare our own prototype.
_FormatCb = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_char), _U, _U, _U, _U)
_CleanupCb = ctypes.CFUNCTYPE(None, ctypes.c_void_p)


def cache_path(path: str) -> Path | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    return CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".jpg")


class FrameGrabber:
    """A headless player that renders into memory, so we can pull frames at any
    position: one for a thumbnail, many for the seek bar's scrub preview."""

    def __init__(self, inst, path: str, width: int = WIDTH):
        self.width = width
        self.mp = inst.media_player_new()
        self.media = inst.media_new(path)
        self.media.add_option(":no-audio")
        self.media.add_option(":no-sub-autodetect-file")
        self.mp.set_media(self.media)
        self._st = {"w": 0, "h": 0, "buf": None, "armed": False}
        self._got = threading.Event()
        st, got = self._st, self._got

        @_FormatCb
        def setup(opaque, chroma, w, h, pitches, lines):
            tw = self.width
            th = max(2, int(round(tw * h[0] / max(1, w[0]) / 2)) * 2)
            ctypes.memmove(chroma, b"RV32", 4)
            w[0], h[0] = tw, th
            pitches[0], lines[0] = tw * 4, th
            st.update(w=tw, h=th, buf=(ctypes.c_ubyte * (tw * th * 4))())
            return 1

        @_CleanupCb
        def cleanup(opaque):
            pass

        @vlc.CallbackDecorators.VideoLockCb
        def lock(opaque, planes):
            planes[0] = ctypes.cast(st["buf"], ctypes.c_void_p).value
            return None

        @vlc.CallbackDecorators.VideoUnlockCb
        def unlock(opaque, picture, planes):
            pass

        @vlc.CallbackDecorators.VideoDisplayCb
        def display(opaque, picture):
            if st["armed"]:
                got.set()

        self._cbs = (setup, cleanup, lock, unlock, display)   # keep them alive
        fn = vlc.dll.libvlc_video_set_format_callbacks
        fn.argtypes = [ctypes.c_void_p, _FormatCb, _CleanupCb]
        fn.restype = None
        fn(self.mp._as_parameter_, setup, cleanup)
        self.mp.video_set_callbacks(lock, unlock, display, None)

    def start(self, timeout=6.0) -> bool:
        self.mp.play()
        t0 = time.time()
        while self.mp.get_state() not in (vlc.State.Playing, vlc.State.Error, vlc.State.Ended)                 and time.time() - t0 < timeout:
            time.sleep(0.02)
        return self.mp.get_state() == vlc.State.Playing

    def grab(self, frac: float, timeout=3.0) -> QImage | None:
        """The first frame drawn after seeking to `frac` (0..1)."""
        if self.mp.get_state() != vlc.State.Playing and not self.start():
            return None
        if self.mp.is_seekable():
            self.mp.set_position(min(max(frac, 0.0), 0.999))
            time.sleep(0.15)
        self._got.clear()
        self._st["armed"] = True
        ok = self._got.wait(timeout) and self._st["buf"] is not None
        self._st["armed"] = False
        if not ok:
            return None
        st = self._st
        return QImage(bytes(st["buf"]), st["w"], st["h"], st["w"] * 4, QImage.Format_RGB32).copy()

    def close(self):
        self.mp.stop()
        self.mp.release()
        self.media.release()


def _video_frame(inst, path: str, dst: Path) -> bool:
    g = FrameGrabber(inst, path)
    try:
        img = g.grab(0.3) if g.start() else None
        return bool(img is not None and img.save(str(dst), "JPG", 85))
    finally:
        g.close()


def _audio_cover(inst, path: str, dst: Path) -> bool:
    m = inst.media_new(path)
    m.parse_with_options(vlc.MediaParseFlag.local | vlc.MediaParseFlag.fetch_local, 3000)
    t0 = time.time()
    while m.get_parsed_status() == 0 and time.time() - t0 < 3.5:
        time.sleep(0.02)
    art = m.get_meta(vlc.Meta.ArtworkURL) or ""
    m.release()
    src = Path(QUrl(art).toLocalFile()) if art.startswith("file:") else find_folder_cover(Path(path))
    if not src or not src.exists():
        return False
    img = QImage(str(src))
    if img.isNull():
        return False
    return img.scaled(WIDTH, WIDTH, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation).save(str(dst), "JPG", 88)


class Thumbnailer(QObject):
    """`request(path)` → `ready(path, jpg_path)` on the UI thread. One worker, newest requests first."""

    ready = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._q: "queue.LifoQueue[str]" = queue.LifoQueue()
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        threading.Thread(target=self._run, daemon=True).start()

    def lookup(self, path: str) -> str | None:
        """Cached thumbnail if there is one; otherwise queue it and return None."""
        c = cache_path(path)
        if c is None:
            return None
        if c.exists():
            return str(c)
        if path not in self._pending and path not in self._failed:
            self._pending.add(path)
            self._q.put(path)
        return None

    def _run(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        inst = vlc.Instance(["--quiet", "--intf=dummy", "--no-audio", "--avcodec-hw=none",
                             "--no-video-title-show", "--no-osd"])
        while True:
            path = self._q.get()
            dst = cache_path(path)
            ok = False
            try:
                if dst is not None:
                    if Path(path).suffix.lower() in AUDIO_EXTS:
                        ok = _audio_cover(inst, path, dst)
                    else:
                        ok = _video_frame(inst, path, dst)
            except Exception:
                ok = False
            self._pending.discard(path)
            if ok:
                self.ready.emit(path, str(dst))
            else:
                self._failed.add(path)
