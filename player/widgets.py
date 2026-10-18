from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPolygonF, QRegion
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget,
)

import theme as T
from icons import pixmap
from music_view import MusicView


def fmt_time(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}"


class IconButton(QToolButton):
    """Flat icon button that brightens on hover, like the Figma controls."""

    def __init__(self, name, tooltip="", size=T.ICON_SIZE, box=36, hover_bg=T.HOVER_BG, parent=None):
        super().__init__(parent)
        self._size = size
        self._hover_bg = hover_bg
        self.setToolTip(tooltip)
        self.setFixedSize(box, box if box < 40 else 32)
        self.setIconSize(QSize(size, size))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.set_icon(name)

    def set_icon(self, name):
        self._name = name
        # Buttons are single-colour: the accent of two-tone menu icons follows the stroke.
        self._normal = pixmap(name, T.ICON, self._size, accent=T.ICON)
        self._hover = pixmap(name, T.ICON_HOVER, self._size, accent=T.ICON_HOVER)
        self.setIcon(self._hover if self.underMouse() else self._normal)

    def enterEvent(self, e):
        self.setIcon(self._hover)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setIcon(self._normal)
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self._hover_bg))
            p.drawRoundedRect(self.rect(), 6, 6)
        ic = self.icon().pixmap(QSize(self._size, self._size))
        x = (self.width() - self._size) // 2
        y = (self.height() - self._size) // 2
        p.drawPixmap(x, y, self._size, self._size, ic)


class PlayButton(QAbstractButton):
    """The orange pill play/pause button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(54, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("Play / Pause (Space)")
        self._playing = False
        self._px = {k: pixmap(k, "#1b1b1b", 16) for k in ("play", "pause")}

    def set_playing(self, playing: bool):
        if playing != self._playing:
            self._playing = playing
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT_HOVER if self.underMouse() else T.ACCENT))
        p.drawRoundedRect(self.rect(), 5, 5)
        px = self._px["pause" if self._playing else "play"]
        p.drawPixmap((self.width() - 16) // 2, (self.height() - 16) // 2, 16, 16, px)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class SeekBar(QWidget):
    """Dark trough, dim-orange played region and a bright orange handle.
    With peaks set it draws the waveform instead: orange bars for the played
    part and grey bars for the rest, as in the Figma music frame."""

    WAVE_PITCH = 4.5
    WAVE_BAR = 2.0

    seek = Signal(float)  # 0..1
    hovered = Signal(float, float)   # position 0..1, x in widget coordinates (for the scrub preview)
    hover_left = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 0.0
        self._hover_x = None
        self._dragging = False
        self._markers: list[tuple[float, float]] = []   # subtitle cues as 0..1 spans
        self._peaks: list[float] = []                    # waveform, 0..1 per bin
        self.setMouseTracking(True)

    def set_peaks(self, peaks):
        self._peaks = peaks or []
        self.update()

    def set_markers(self, spans):
        self._markers = spans
        self.update()

    def set_position(self, frac: float):
        if not self._dragging:
            self._pos = min(max(frac, 0.0), 1.0)
            self.update()

    def _frac(self, x):
        return min(max((x - 4) / max(1, self.width() - 8), 0.0), 1.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._pos = self._frac(e.position().x())
            self.hovered.emit(self._pos, e.position().x())
            self.update()

    def mouseMoveEvent(self, e):
        self._hover_x = e.position().x()
        if self._dragging:
            self._pos = self._frac(self._hover_x)
        self.hovered.emit(self._frac(self._hover_x), self._hover_x)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.seek.emit(self._pos)
            if not self.rect().contains(e.position().toPoint()):
                self.hover_left.emit()

    def leaveEvent(self, e):
        self._hover_x = None
        if not self._dragging:
            self.hover_left.emit()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.TRACK))
        p.drawRoundedRect(r, 5, 5)
        inner = r.adjusted(3, 3, -3, -3)
        x = inner.left() + inner.width() * self._pos
        if self._peaks:
            self._paint_wave(p, inner, x)
        elif self._pos > 0:
            p.setBrush(QColor(T.SEEK_FILL))
            p.drawRoundedRect(QRectF(inner.left(), inner.top(), x - inner.left(), inner.height()), 3, 3)
        if self._hover_x is not None and not self._dragging and not self._peaks:
            p.setBrush(QColor(255, 255, 255, 18))
            hx = min(max(self._hover_x, inner.left()), inner.right())
            p.drawRoundedRect(QRectF(inner.left(), inner.top(), hx - inner.left(), inner.height()), 3, 3)
        if self._markers:
            # Subtitle timeline: a thin strip along the bottom where lines appear.
            p.setBrush(QColor("#8a8a8a"))
            for a, b in self._markers:
                if b < 0 or a > 1:
                    continue
                ax = inner.left() + inner.width() * max(a, 0)
                bx = inner.left() + inner.width() * min(b, 1)
                p.drawRect(QRectF(ax, inner.bottom() - 4, max(bx - ax, 1.5), 3))
        p.setBrush(QColor(T.ACCENT))
        if self._peaks:
            p.drawRoundedRect(QRectF(x - 2.5, inner.top() - 1, 5, inner.height() + 2), 2, 2)
        else:
            p.drawRoundedRect(QRectF(x - 2.5, inner.top(), 5, inner.height()), 2, 2)

    def _paint_wave(self, p, inner, x_pos):
        played, rest, hover = QColor(T.ACCENT), QColor("#404040"), QColor("#6a6a6a")
        hx = self._hover_x if (self._hover_x is not None and not self._dragging) else None
        mid = inner.center().y()
        max_h = inner.height() * 0.62
        n = len(self._peaks)
        left = inner.left() + 4
        width = inner.width() - 8
        count = int(width / self.WAVE_PITCH)
        for i in range(count):
            bx = left + i * self.WAVE_PITCH
            # Peak of the bins this bar covers, so short spikes stay visible.
            a = int(i / count * n)
            b = max(a + 1, int((i + 1) / count * n))
            h = max(2.0, max(self._peaks[a:b]) * max_h)
            if bx < x_pos:
                p.setBrush(played)
            elif hx is not None and bx < hx:
                p.setBrush(hover)
            else:
                p.setBrush(rest)
            p.drawRoundedRect(QRectF(bx, mid - h / 2, self.WAVE_BAR, h), 1, 1)


class VolumeWedge(QWidget):
    """Volume shown as a rising wedge, filled green up to the current level."""

    changed = Signal(int)  # 0..100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(86, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Volume (scroll or ↑ ↓)")
        self._value = 70

    def value(self):
        return self._value

    def set_value(self, v: int, emit=True):
        v = min(max(int(v), 0), 100)
        if v != self._value:
            self._value = v
            self.update()
            if emit:
                self.changed.emit(v)

    def _from_x(self, x):
        self.set_value(round(x / self.width() * 100))

    def mousePressEvent(self, e):
        self._from_x(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._from_x(e.position().x())

    def wheelEvent(self, e):
        self.set_value(self._value + (5 if e.angleDelta().y() > 0 else -5))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        w, h = self.width(), self.height()
        # Trough: a wedge that grows taller to the right; the fill is the same
        # wedge inset by 2px and clipped to the volume level.
        def wedge(inset):
            return QPolygonF([QPointF(inset, h * 0.30 + inset * 0.6), QPointF(w - inset, inset),
                              QPointF(w - inset, h - inset), QPointF(inset, h * 0.70 - inset * 0.6)])
        p.setBrush(QColor(T.TRACK))
        p.drawPolygon(wedge(0))
        p.setClipRect(QRectF(0, 0, 2 + (w - 4) * self._value / 100, h))
        p.setBrush(QColor(T.VOLUME))
        p.drawPolygon(wedge(2))


class TitleBar(QFrame):
    """Custom title bar: cone, menu, sidebar, breadcrumb, centered title, window buttons."""

    library_clicked = Signal()
    menu_clicked = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.setFixedHeight(T.TITLE_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(4)

        # The cone opens the start page, like Word's File button.
        self.logo_btn = IconButton("vlc", "Menu: start page and recent media", box=32)
        self.logo_btn.clicked.connect(self.menu_clicked.emit)
        lay.addWidget(self.logo_btn)

        self.more_btn = IconButton("more", "Menu", box=32)
        self.sidebar_btn = IconButton("sidebar", "Toggle sidebar", box=32)
        lay.addWidget(self.more_btn)
        lay.addWidget(self.sidebar_btn)

        self.sep = QFrame()
        self.sep.setFixedSize(1, 16)
        self.sep.setStyleSheet("background:#333;")
        lay.addSpacing(4)
        lay.addWidget(self.sep)
        lay.addSpacing(4)

        # Folder icon + the show's folder name: clicking either opens the library.
        self.folder_btn = IconButton("folder", "Open library (L)", box=32)
        self.crumb = QLabel("Videos")
        self.crumb.setStyleSheet(f"QLabel{{color:{T.TEXT}; font-size:13px; padding:4px 6px; border-radius:5px;}}"
                                 f"QLabel:hover{{background:{T.HOVER_BG}; color:{T.ICON_HOVER};}}")
        self.crumb.setCursor(Qt.PointingHandCursor)
        self.crumb.setToolTip("Open library (L)")
        self.crumb.mousePressEvent = lambda e: self.library_clicked.emit()
        self.folder_btn.clicked.connect(self.library_clicked.emit)
        self.sidebar_btn.clicked.connect(self.library_clicked.emit)
        lay.addWidget(self.folder_btn)
        lay.addWidget(self.crumb)
        lay.addStretch(1)

        self.min_btn = IconButton("minimize", "Minimize", box=40)
        self.max_btn = IconButton("maximize", "Maximize", box=40)
        self.fs_btn = IconButton("fullscreen", "Fullscreen (F)", box=40)
        self.close_btn = IconButton("close", "Close", box=40, hover_bg=T.CLOSE_HOVER)
        for b in (self.min_btn, self.max_btn, self.fs_btn, self.close_btn):
            lay.addWidget(b)

        # Title is centered on the whole bar, independent of the side widgets.
        self.title = QLabel("VLC Reskin", self)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"color:{T.TITLE_TEXT}; font-size:13px;")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_title(self, text):
        self.title.setText(text)
        self._place_title()

    def _place_title(self):
        w = min(600, self.width() - 600)
        self.title.setGeometry((self.width() - max(w, 100)) // 2, 0, max(w, 100), self.height())

    def resizeEvent(self, e):
        self._place_title()
        super().resizeEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win.toggle_maximize()


class ControlBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(T.CONTROLS_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(4)

        self.prev_btn = IconButton("previous", "Previous", size=18, box=32)
        self.back_btn = IconButton("back15", "Back 15 s (←)", box=32)
        self.play_btn = PlayButton()
        self.fwd_btn = IconButton("fwd15", "Forward 15 s (→)", box=32)
        self.next_btn = IconButton("next", "Next", size=18, box=32)
        for w in (self.prev_btn, self.back_btn, self.play_btn, self.fwd_btn, self.next_btn):
            lay.addWidget(w)
        # The video frame in the design has no 15 s skip buttons (only the music frame
        # does); the arrow keys still skip.
        self.back_btn.hide()
        self.fwd_btn.hide()

        time_style = f"color:{T.TEXT}; font-size:13px;"
        self.cur = QLabel("00:00:00")
        self.cur.setStyleSheet(time_style)
        self.dur = QLabel("00:00:00")
        self.dur.setStyleSheet(time_style)
        self.seek = SeekBar()
        lay.addSpacing(14)
        lay.addWidget(self.cur)
        lay.addSpacing(10)
        lay.addWidget(self.seek, 1)
        lay.addSpacing(10)
        lay.addWidget(self.dur)
        lay.addSpacing(18)

        self.vol_btn = IconButton("volume", "Mute (M)", box=32)
        self.volume = VolumeWedge()
        lay.addWidget(self.vol_btn)
        lay.addWidget(self.volume)
        lay.addSpacing(18)

        self.eq_btn = IconButton("eq", "Audio tracks and output", box=32)
        self.sub_btn = IconButton("subtitles", "Subtitles (V to cycle)", box=32)
        self.settings_btn = IconButton("settings", "Preferences", box=32)
        self.playlist_btn = IconButton("playlist", "Playlist", box=32)
        for w in (self.eq_btn, self.sub_btn, self.settings_btn):
            lay.addWidget(w)
        lay.addSpacing(10)
        lay.addWidget(self.playlist_btn)


# 21x17 pixel cat from the design's idle artwork. # = white, o = light grey, k = black, p = pink
_CAT = [
    "..#...........#......",
    "..o#.........#o......",
    "..oo#########oo......",
    "..oooooooooo#oo......",
    "kkokkooooookkookk....",
    "..oppooooooppoo......",
    "kkoooookoooooookk....",
    "..ooookokooooo.......",
    "...ooooooooooo.......",
    "....ooooo#ooo....#...",
    "....ooooo#ooo.....#..",
    "....oooooooooo.....#.",
    "....o#oo#ooooooo...#.",
    "....o#oo#oooooooo##..",
    "....o#oo#oo#oooo.....",
    "....o#oo#o#ooooo.....",
    "...##o##o#oooo.......",
]
_CAT_COLORS = {"#": "#ffffff", "o": "#e0e0e0", "k": "#000000", "p": "#f6c8d6"}


class VideoSurface(QFrame):
    """Rounded video area. libVLC draws into the native child `canvas`;
    when nothing is loaded we paint the pixel cat and a hint instead."""

    double_clicked = Signal()
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{T.VIDEO_BG}; border-radius:{T.VIDEO_RADIUS}px;")
        self.canvas = QWidget(self)
        self.canvas.setAttribute(Qt.WA_NativeWindow)
        self.canvas.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.canvas.setStyleSheet("background:#000;")
        self.canvas.hide()
        self.music_view = MusicView(self)
        self.music_view.hide()

    def show_video(self, on: bool):
        self.canvas.setVisible(on)
        self.update()

    def set_music(self, on: bool):
        self.music_view.setVisible(on)
        if on:
            self.canvas.hide()
            self.music_view.raise_()

    def resizeEvent(self, e):
        self.canvas.setGeometry(self.rect())
        self.music_view.setGeometry(self.rect())
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), T.VIDEO_RADIUS, T.VIDEO_RADIUS)
        self.canvas.setMask(QRegion(path.toFillPolygon().toPolygon()))
        super().resizeEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.double_clicked.emit()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.canvas.isVisible():
            return
        p = QPainter(self)
        p.setPen(Qt.NoPen)
        cell = max(6, min(self.width(), self.height()) // 40)
        cw, ch = len(_CAT[0]) * cell, len(_CAT) * cell
        ox, oy = (self.width() - cw) // 2, (self.height() - ch) // 2 - cell * 2
        for y, row in enumerate(_CAT):
            for x, c in enumerate(row):
                if c in _CAT_COLORS:
                    p.setBrush(QColor(_CAT_COLORS[c]))
                    p.drawRect(ox + x * cell, oy + y * cell, cell, cell)
        p.setPen(QColor("#6f6d6a"))
        f = QFont()
        f.setPointSize(11)
        p.setFont(f)
        p.drawText(QRectF(0, oy + ch + cell * 2, self.width(), 30), Qt.AlignHCenter,
                   "Drop a video here, or press Ctrl+O to open one")
