"""Menus and popups styled after the Figma frames: the ••• menu, the right-click
menu, and the audio / subtitles / video tracks popup."""

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import theme as T
from icons import pixmap

MENU_BG = "#1c1c1c"
MENU_BORDER = "#2c2c2c"
MENU_TEXT = "#c8c8c8"
MENU_HINT = "#8a8a8a"

MENU_QSS = f"""
QMenu {{
    background:{MENU_BG}; border:1px solid {MENU_BORDER}; border-radius:10px;
    padding:6px; color:{MENU_TEXT}; font-size:14px;
}}
QMenu::item {{ padding:9px 34px 9px 12px; border-radius:6px; }}
QMenu::item:selected {{ background:#2a2a2a; color:#ececec; }}
QMenu::item:disabled {{ color:#5c5c5c; }}
QMenu::icon {{ padding-left:10px; }}
QMenu::separator {{ height:1px; background:#2c2c2c; margin:5px 4px; }}
QMenu::right-arrow {{ width:10px; height:10px; margin-right:10px; }}
"""


class StyledMenu(QMenu):
    """Rounded menu (translucent, frameless window). Shortcut hints are painted
    by hand at the right edge, as in the design; Qt's stylesheet engine would
    otherwise left-align them in their own column."""

    SHORTCUT_GAP = 40

    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(MENU_QSS)
        self.setToolTipsVisible(True)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setFont(self.font())
        for a in self.actions():
            hint = a.data()
            if isinstance(hint, str) and hint:
                r = self.actionGeometry(a).adjusted(0, 0, -16, 0)
                p.setPen(QColor("#4c4c4c" if not a.isEnabled() else MENU_HINT))
                p.drawText(r, Qt.AlignRight | Qt.AlignVCenter, hint)


def styled_menu(parent=None, title="") -> QMenu:
    return StyledMenu(title, parent)


def menu_icon(name: str, color: str = T.ICON) -> QIcon:
    return QIcon(pixmap(name, color, 20))


def add(menu: QMenu, icon: str | None, text: str, slot=None, shortcut: str = "", color=T.ICON,
        enabled=True, tip="", checked=None):
    """Add an item; the shortcut is shown right-aligned like in the design."""
    a = menu.addAction(menu_icon(icon, color), text) if icon else menu.addAction(text)
    if shortcut:
        a.setData(shortcut)   # painted by StyledMenu
        f = QFont(menu.font())
        f.setPixelSize(14)
        fm = QFontMetrics(f)
        need = fm.horizontalAdvance(text) + fm.horizontalAdvance(shortcut) + StyledMenu.SHORTCUT_GAP + 110
        menu.setMinimumWidth(max(menu.minimumWidth(), need))
    if slot:
        a.triggered.connect(slot)
    a.setEnabled(enabled)
    if tip:
        a.setToolTip(tip)
    if checked is not None:
        a.setCheckable(True)
        a.setChecked(checked)
    return a


def submenu(menu: QMenu, icon: str, text: str, color=T.ACCENT) -> QMenu:
    sub = styled_menu(menu, text)
    sub.setIcon(menu_icon(icon, color))
    menu.addMenu(sub)
    return sub


# ---------------------------------------------------------------- tracks popup
class _Row(QWidget):
    """A selectable row: orange check when selected, then the label."""

    clicked = Signal()

    def __init__(self, text, selected=False, icon=None):
        super().__init__()
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)
        mark = QLabel()
        mark.setFixedSize(16, 16)
        if selected:
            mark.setPixmap(pixmap("check", T.ACCENT, 16))
        elif icon:
            mark.setPixmap(pixmap(icon, T.ICON, 16))
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{'#ececec' if selected else MENU_TEXT}; font-size:14px;")
        lay.addWidget(mark)
        lay.addWidget(lbl, 1)

    def paintEvent(self, e):
        if self.underMouse():
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#262626"))
            p.drawRoundedRect(self.rect(), 6, 6)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class TracksPopup(QFrame):
    """Audio / Subtitles / Video popup opened from the control bar.

    `provider` is the player window; it supplies track lists and setters, so
    this widget only handles presentation."""

    TABS = [("audio", "eq", "Audio"), ("subtitles", "subtitles", "Subtitles"), ("video", "video", "Video")]

    def __init__(self, provider, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.provider = provider
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.tab = "audio"

        self.card = QFrame(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet(f"""
            #card {{ background:{MENU_BG}; border:1px solid {MENU_BORDER}; border-radius:10px; }}
            QLabel {{ background:transparent; }}
            QScrollArea, #body {{ background:transparent; border:none; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.tab_btns = {}
        for key, icon, label in self.TABS:
            b = QPushButton(f"  {label}")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(34)
            b.clicked.connect(lambda _=False, k=key: self.show_tab(k))
            self.tab_btns[key] = (b, icon)
            tabs.addWidget(b)
        lay.addLayout(tabs)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{MENU_BORDER};")
        lay.addWidget(line)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollBar:vertical{width:6px;background:transparent}"
                                  "QScrollBar::handle:vertical{background:#3a3a3a;border-radius:3px}")
        lay.addWidget(self.scroll, 1)

        self.prefs = QPushButton("Show Preferences")
        self.prefs.setCursor(Qt.PointingHandCursor)
        self.prefs.setFixedHeight(36)
        self.prefs.setStyleSheet(f"QPushButton{{background:#262626;color:{MENU_TEXT};border:none;border-radius:6px;font-size:13px}}"
                                 "QPushButton:hover{background:#303030;color:#eee}")
        self.prefs.clicked.connect(lambda: provider.show_preferences(self.tab))
        lay.addWidget(self.prefs)
        self.setFixedWidth(340)

    def show_tab(self, key):
        self.tab = key
        for k, (b, icon) in self.tab_btns.items():
            active = k == key
            col = T.ACCENT if active else T.ICON
            b.setIcon(QIcon(pixmap(icon, col, 18)))
            b.setStyleSheet(
                f"QPushButton{{background:{'#262626' if active else 'transparent'};color:{'#ececec' if active else MENU_HINT};"
                f"border:none;border-radius:6px;font-size:13px;padding:0 10px}}"
                "QPushButton:hover{background:#262626;color:#ececec}")
        self._rebuild()

    def _section(self, lay, title, button=None):
        row = QHBoxLayout()
        row.setContentsMargins(12, 10, 6, 2)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{MENU_HINT}; font-size:12px;")
        row.addWidget(lbl, 1)
        if button:
            row.addWidget(button)
        lay.addLayout(row)

    def _rebuild(self):
        body = QWidget()
        body.setObjectName("body")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        p = self.provider

        def rows(items, current, setter):
            if not items:
                empty = QLabel("Nothing here for this media")
                empty.setStyleSheet("color:#5c5c5c; font-size:13px; padding:8px 12px;")
                lay.addWidget(empty)
            for ident, name in items:
                r = _Row(name, ident == current)
                # Rebuild on the next loop turn: the row being clicked is replaced.
                r.clicked.connect(lambda i=ident: (setter(i), QTimer.singleShot(0, self._rebuild)))
                lay.addWidget(r)

        if self.tab == "audio":
            self._section(lay, "Embedded Tracks")
            rows(*p.audio_tracks())
            refresh = QPushButton()
            refresh.setIcon(QIcon(pixmap("refresh", T.ICON, 16)))
            refresh.setFixedSize(26, 26)
            refresh.setCursor(Qt.PointingHandCursor)
            refresh.setToolTip("Refresh devices")
            refresh.setStyleSheet("QPushButton{background:transparent;border:none;border-radius:5px}"
                                  "QPushButton:hover{background:#2a2a2a}")
            refresh.clicked.connect(lambda: QTimer.singleShot(0, self._rebuild))
            self._section(lay, "Output Device", refresh)
            rows(*p.audio_devices())
        elif self.tab == "subtitles":
            self._section(lay, "Embedded Tracks")
            rows(*p.subtitle_tracks())
            self._section(lay, "External")
            add_row = _Row("Add subtitle file…", icon="add")
            add_row.clicked.connect(lambda: (self.close(), p.add_subtitle_file()))
            lay.addWidget(add_row)
        else:
            self._section(lay, "Video Tracks")
            rows(*p.video_tracks())

        lay.addStretch(1)
        self.scroll.setWidget(body)
        h = min(440, body.sizeHint().height() + 34 + 36 + 34)
        self.setFixedHeight(max(220, h))

    def open_at(self, anchor: QWidget, tab: str):
        self.show_tab(tab)
        self.adjustSize()
        g = anchor.mapToGlobal(QPoint(anchor.width(), 0))
        screen = anchor.screen().availableGeometry()
        x = min(g.x() - self.width() + 40, screen.right() - self.width() - 8)
        self.move(max(screen.left() + 8, x), g.y() - self.height() - 8)
        self.show()
