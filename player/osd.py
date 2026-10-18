"""On-screen play / pause flash: a round icon in the middle of the video that
fades out, so you can see the click (or Space) did something.

It's a separate top-level window because libVLC's native video window can't be
covered by ordinary widgets."""

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from icons import pixmap

SIZE = 84


class PlayPauseFlash(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(SIZE, SIZE)
        self._icon = "play"
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(450)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.InQuad)
        self._fade.finished.connect(self.hide)
        self._hold = QTimer(self, singleShot=True, interval=350, timeout=self._fade.start)

    def flash(self, icon: str, center: QPoint):
        """Show `icon` ("play" or "pause") centred on `center` (global coordinates)."""
        self._fade.stop()
        self._icon = icon
        self.move(center.x() - SIZE // 2, center.y() - SIZE // 2)
        self.setWindowOpacity(1.0)
        self.update()
        self.show()
        self.raise_()
        self._hold.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        s = 38
        p.drawPixmap((SIZE - s) // 2, (SIZE - s) // 2, s, s, pixmap(self._icon, "#f2f2f2", s))
