"""Music view (Figma "Player - Music"): the cover art large in the middle over a
blurred, darkened copy of itself, with "title - artist" underneath."""

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

import theme as T

COVER_NAMES = ("cover", "folder", "front", "albumart", "album")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

# Pixel music note from the design's "Listen Again" tiles.
_NOTE = [
    "....############",
    "....#..........#",
    "....#..........#",
    "....#..######..#",
    "....#..#....#..#",
    "....#..#....#..#",
    "....#..#....#..#",
    "....#..#....#..#",
    "....#..#....#..#",
    "....#..#....#..#",
    "..###..#..###..#",
    ".#...#.#.#...#.#",
    "#.....##.#....##",
    "#.....#.#.....#.",
    ".#...#...#...#..",
    "..###.....###...",
]


def find_folder_cover(media: Path | None) -> Path | None:
    """cover.jpg / folder.png / … next to the file, else the only image there."""
    if not media:
        return None
    try:
        images = [p for p in media.parent.iterdir() if p.suffix.lower() in IMAGE_EXTS]
    except OSError:
        return None
    for p in images:
        if p.stem.lower() in COVER_NAMES or p.stem.lower().startswith("albumart") or p.stem == media.stem:
            return p
    return images[0] if len(images) == 1 else None


def _blurred(img: QImage, size: QSize) -> QPixmap:
    """Cheap heavy blur: shrink to a few dozen pixels, then scale back up smoothly."""
    small = img.scaled(28, 28, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    mid = small.scaled(size.width() // 6 + 1, size.height() // 6 + 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return QPixmap.fromImage(mid.scaled(size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))


class MusicView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cover: QImage | None = None
        self._title = ""
        self._artist = ""
        self._bg_cache: tuple[QSize, QPixmap] | None = None

    def set_track(self, title: str, artist: str = "", cover: Path | str | None = None):
        self._title, self._artist = title, artist
        img = QImage(str(cover)) if cover else QImage()
        self._cover = img if not img.isNull() else None
        self._bg_cache = None
        self.update()

    def has_cover(self):
        return self._cover is not None

    def _backdrop(self) -> QPixmap | None:
        if self._cover is None:
            return None
        if self._bg_cache is None or self._bg_cache[0] != self.size():
            self._bg_cache = (self.size(), _blurred(self._cover, self.size()))
        return self._bg_cache[1]

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), T.VIDEO_RADIUS, T.VIDEO_RADIUS)
        p.setClipPath(clip)

        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#050505"))
        bg = self._backdrop()
        if bg:
            p.drawPixmap(0, 0, bg)
            p.fillRect(self.rect(), QColor(0, 0, 0, 200))
        else:
            g = QRadialGradient(w / 2, h * 0.42, max(w, h) * 0.6)
            g.setColorAt(0, QColor("#1a2a1e"))
            g.setColorAt(1, QColor("#050505"))
            p.fillRect(self.rect(), g)

        side = int(min(h * 0.72, w * 0.62))
        block = side + 70
        x = (w - side) / 2
        y = max(16, (h - block) / 2)
        art = QRectF(x, y, side, side)

        # Soft glow behind the cover.
        for i in range(6, 0, -1):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 4))
            p.drawRoundedRect(art.adjusted(-i * 3, -i * 3, i * 3, i * 3), 14 + i * 3, 14 + i * 3)

        path = QPainterPath()
        path.addRoundedRect(art, 14, 14)
        p.save()
        p.setClipPath(path, Qt.IntersectClip)
        if self._cover is not None:
            img = self._cover.scaled(QSize(side * 2, side * 2), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            src = QRectF((img.width() - side * 2) / 2, (img.height() - side * 2) / 2, side * 2, side * 2)
            p.drawImage(art, img, src)
        else:
            p.fillRect(art, QColor("#2f3d33"))
            cell = side / 26
            ox = x + (side - cell * len(_NOTE[0])) / 2
            oy = y + (side - cell * len(_NOTE)) / 2
            p.setBrush(QColor("#3ed160"))
            for r, row in enumerate(_NOTE):
                for c, ch in enumerate(row):
                    if ch == "#":
                        p.drawRect(QRectF(ox + c * cell, oy + r * cell, cell + 0.5, cell + 0.5))
        p.restore()

        text = self._title + (f" - {self._artist}" if self._artist else "")
        f = QFont(self.font())
        f.setPixelSize(max(16, min(24, int(side / 26))))
        p.setFont(f)
        p.setPen(QColor("#a8a8a8"))
        p.drawText(QRectF(0, y + side + 22, w, 40), Qt.AlignHCenter | Qt.AlignTop,
                   p.fontMetrics().elidedText(text, Qt.ElideRight, int(w * 0.8)))
