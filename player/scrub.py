"""Scrub preview: hover the seek bar and see the frame at that point.

A background "storyboard" grabs 100 evenly spaced frames from the video with a
headless libVLC player. They're taken in a spread-out order (0%, 50%, 25%,
75%, …) so the whole timeline gets rough coverage within a few seconds and
then fills in. Finished storyboards are cached as one sprite image."""

import threading
from pathlib import Path

import vlc
from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

import thumbnails

FRAMES = 100
GRID = 10            # sprite is GRID x GRID tiles
TILE_W = 192


def spread_order(n: int) -> list[int]:
    """0..n-1 ordered so every prefix covers the range evenly (bit-reversed order)."""
    bits = max(1, (n - 1).bit_length())
    slots = 1 << bits
    out, seen = [], set()
    for k in range(slots):
        idx = int(int(format(k, f"0{bits}b")[::-1], 2) * n / slots)
        if idx not in seen:
            seen.add(idx)
            out.append(idx)
    return out


class Storyboard(QObject):
    """Frames for the current video. `updated` fires as more frames arrive."""

    updated = Signal()

    def __init__(self):
        super().__init__()
        self._job = 0
        self.path: str | None = None
        self.frames: dict[int, QImage] = {}
        self._lock = threading.Lock()          # the worker adds frames while the UI reads them

    def request(self, path: Path):
        self._job += 1
        self.path = str(path)
        self.frames = {}
        threading.Thread(target=self._run, args=(self._job, self.path), daemon=True).start()

    def cancel(self):
        self._job += 1
        self.path = None
        self.frames = {}

    def frame_for(self, frac: float) -> QImage | None:
        with self._lock:
            frames = dict(self.frames)
        if not frames:
            return None
        idx = min(FRAMES - 1, max(0, int(frac * FRAMES)))
        if idx in frames:
            return frames[idx]
        return frames[min(frames, key=lambda k: abs(k - idx))]

    def _sprite_path(self, path: str) -> Path | None:
        c = thumbnails.cache_path(path)
        return c.with_name(c.stem + "_storyboard.jpg") if c else None

    def _run(self, job, path):
        sprite = self._sprite_path(path)
        if sprite and sprite.exists():
            img = QImage(str(sprite))
            if not img.isNull():
                tw, th = img.width() // GRID, img.height() // GRID
                frames = {i: img.copy(i % GRID * tw, i // GRID * th, tw, th) for i in range(FRAMES)}
                if job == self._job:
                    self.frames = frames
                    self.updated.emit()
                return
        inst = vlc.Instance(["--quiet", "--intf=dummy", "--no-audio", "--avcodec-hw=none",
                             "--no-video-title-show", "--no-osd"])
        grabber = thumbnails.FrameGrabber(inst, path, TILE_W)
        try:
            if not grabber.start():
                return
            for n, idx in enumerate(spread_order(FRAMES)):
                if job != self._job:
                    return
                img = grabber.grab((idx + 0.5) / FRAMES)
                if img is None:
                    continue
                if job != self._job:
                    return
                with self._lock:
                    self.frames[idx] = img
                if n < 8 or n % 6 == 0:
                    self.updated.emit()
            self.updated.emit()
            if len(self.frames) == FRAMES and sprite is not None:
                self._save_sprite(sprite)
        finally:
            grabber.close()
            inst.release()

    def _save_sprite(self, dst: Path):
        any_img = next(iter(self.frames.values()))
        tw, th = any_img.width(), any_img.height()
        sheet = QImage(tw * GRID, th * GRID, QImage.Format_RGB32)
        sheet.fill(QColor("black"))
        p = QPainter(sheet)
        for i, img in self.frames.items():
            p.drawImage(i % GRID * tw, i // GRID * th, img)
        p.end()
        dst.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(str(dst), "JPG", 80)


class ScrubPreview(QWidget):
    """Floating bubble above the seek bar: the frame (when there is one) and the time.
    A separate top-level window so it can sit over libVLC's native video."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._img: QImage | None = None
        self._text = ""

    def show_at(self, center_x: int, bottom_y: int, img: QImage | None, text: str):
        self._img, self._text = img, text
        if img is not None:
            w = TILE_W + 8
            h = int(TILE_W * img.height() / max(1, img.width())) + 8 + 24
        else:
            w, h = 84, 30
        self.resize(w, h)
        screen = self.screen().availableGeometry() if self.screen() else None
        x = center_x - w // 2
        if screen is not None:
            x = min(max(x, screen.left() + 4), screen.right() - w - 4)
        self.move(x, bottom_y - h)
        self.update()
        if not self.isVisible():
            self.show()
        self.raise_()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QColor("#2c2c2c"))
        p.setBrush(QColor("#1c1c1c"))
        p.drawRoundedRect(r, 8, 8)
        text_rect = QRectF(r)
        if self._img is not None:
            img_r = QRectF(4, 4, self.width() - 8, self.height() - 8 - 24)
            path = QPainterPath()
            path.addRoundedRect(img_r, 5, 5)
            p.save()
            p.setClipPath(path)
            p.drawImage(img_r, self._img)
            p.restore()
            text_rect = QRectF(0, img_r.bottom() + 2, self.width(), 22)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor("#ececec"))
        p.drawText(text_rect, Qt.AlignCenter, self._text)
