"""Start page (Home of the full-window library), laid out like Word's start
screen: a greeting, a collapsible "Continue watching" row of thumbnails, filter
pills, then a table of everything recently played with its name, where it's
saved, its format and when it was last played, newest first."""

from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

import theme as T
from icons import pixmap
from library_page import LIST_QSS, TileDelegate, TileList
from credits import footer_label
from library_store import AUDIO_EXTS, is_url

ROW_H = 58
COL_FORMAT = 330    # distance of the Format column from the right edge
COL_PLAYED = 170    # distance of the Last played column from the right edge


def greeting(now: datetime | None = None) -> str:
    h = (now or datetime.now()).hour
    return "Good morning" if 5 <= h < 12 else "Good afternoon" if 12 <= h < 18 else "Good evening"


def when_played(ts: float, now: datetime | None = None) -> str:
    """Word-style dates: Just now / 12 min ago / Today at 13:53 / Wed at 13:53 / 5 October."""
    if not ts:
        return ""
    now = now or datetime.now()
    t = datetime.fromtimestamp(ts)
    secs = (now - t).total_seconds()
    if secs < 60:
        return "Just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    hm = t.strftime("%H:%M")
    if t.date() == now.date():
        return f"Today at {hm}"
    if t.date() == (now - timedelta(days=1)).date():
        return f"Yesterday at {hm}"
    if secs < 6 * 86400:
        return f"{t.strftime('%a')} at {hm}"
    day = f"{t.day} {t.strftime('%B')}"
    return day if t.year == now.year else f"{day} {t.year}"


def location(item: str) -> str:
    """Where it's saved, as a » trail (relative to your user folder when inside it)."""
    if is_url(item):
        u = urlparse(item)
        return u.netloc or u.scheme
    parent = Path(item).parent
    try:
        parts = parent.relative_to(Path.home()).parts
    except ValueError:
        parts = parent.parts
    return " » ".join(p.rstrip("\\") for p in parts) or str(parent)


def file_format(item: str, kind: str) -> str:
    if is_url(item):
        return f"{urlparse(item).scheme.upper()} stream"
    ext = Path(item).suffix.lstrip(".").upper() or "File"
    return f"{ext} {'audio' if kind == 'audio' or Path(item).suffix.lower() in AUDIO_EXTS else 'video'}"


class RecentDelegate(QStyledItemDelegate):
    def __init__(self, start):
        super().__init__(start)
        self.start = start
        self._thumbs = TileDelegate(start.page, "list")   # reuse its thumbnail painting

    def sizeHint(self, option, index):
        return QSize(400, ROW_H)

    def paint(self, p, option, index):
        e = index.data(Qt.UserRole)
        if e is None:
            return
        page = self.start.page
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect)
        if option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#1d1d1d"))
            p.drawRect(r)
        p.setPen(QColor("#232323"))
        p.drawLine(r.bottomLeft(), r.bottomRight())

        audio = e.extra["kind"] == "audio"
        thumb = QRectF(r.left() + 8, r.center().y() - 18, 36 if audio else 64, 36)
        self._thumbs._thumb(p, e, thumb, radius=4, icon_size=16)
        p.setClipping(False)
        if e.progress is not None or e.dim:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.ACCENT))
            p.drawRect(QRectF(thumb.left(), thumb.bottom() + 1, thumb.width() * (1.0 if e.dim else e.progress), 2))

        current = page.current is not None and e.target == page.current
        text_x = r.left() + 8 + 64 + 16
        name_w = r.width() - COL_FORMAT - (text_x - r.left()) - 16
        f = QFont(option.font)
        f.setPixelSize(14)
        p.setFont(f)
        p.setPen(QColor(T.ACCENT if current else "#d6d6d6"))
        fm = p.fontMetrics()
        p.drawText(QRectF(text_x, r.top() + 9, name_w, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(e.label, Qt.ElideRight, int(name_w)))
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(QColor("#7e7e7e"))
        fm = p.fontMetrics()
        p.drawText(QRectF(text_x, r.top() + 30, name_w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(e.extra["location"], Qt.ElideMiddle, int(name_w)))

        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor("#a8a8a8"))
        p.drawText(QRectF(r.right() - COL_FORMAT, r.top(), COL_FORMAT - COL_PLAYED - 10, r.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, e.extra["format"])
        p.drawText(QRectF(r.right() - COL_PLAYED, r.top(), COL_PLAYED - 10, r.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, e.extra["when"])
        p.restore()


class StartPage(QWidget):
    FILTERS = [("all", "Recent"), ("video", "Videos"), ("audio", "Music"), ("stream", "Streams")]
    SORTS = {"name": "Name", "format": "Format", "played": "Last played"}

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.filter = "all"
        self.sort_key, self.sort_desc = "played", True
        self.cw_open = True
        self.setObjectName("start")
        self.setStyleSheet("#start{background:transparent} QLabel{background:transparent}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 0)
        lay.setSpacing(6)

        self.hello = QLabel()
        self.hello.setStyleSheet("color:#ececec;font-size:22px;padding:4px 2px 0")
        lay.addWidget(self.hello)

        self.cw_btn = QPushButton()
        self.cw_btn.setCursor(Qt.PointingHandCursor)
        self.cw_btn.setIconSize(QSize(16, 16))
        self.cw_btn.setStyleSheet("QPushButton{background:transparent;border:none;color:#d6d6d6;font-size:17px;"
                                  "text-align:left;padding:8px 0 2px}QPushButton:hover{color:#fff}")
        self.cw_btn.clicked.connect(self._toggle_cw)
        lay.addWidget(self.cw_btn)
        self.cw_row = TileList(page, "wide", wrap=False)
        self.cw_row.setFixedHeight(page.cell_size("wide").height() + 6)
        lay.addWidget(self.cw_row)

        pills = QHBoxLayout()
        pills.setContentsMargins(0, 12, 0, 6)
        pills.setSpacing(8)
        self.pill_btns = {}
        for key, label in self.FILTERS:
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(32)
            b.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self.pill_btns[key] = b
            pills.addWidget(b)
        pills.addStretch(1)
        lay.addLayout(pills)

        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 0, 0)
        head.setSpacing(0)
        self.col_btns = {}
        for key in ("name", "format", "played"):
            b = QPushButton()
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton{background:transparent;border:none;color:#9a9a9a;font-size:12px;"
                            "text-align:left;padding:4px 0}QPushButton:hover{color:#e0e0e0}")
            b.clicked.connect(lambda _=False, k=key: self._set_sort(k))
            self.col_btns[key] = b
        head.addWidget(self.col_btns["name"], 1)
        self.col_btns["format"].setFixedWidth(COL_FORMAT - COL_PLAYED)
        self.col_btns["played"].setFixedWidth(COL_PLAYED)
        head.addWidget(self.col_btns["format"])
        head.addWidget(self.col_btns["played"])
        lay.addLayout(head)
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#2a2a2a")
        lay.addWidget(line)

        self.table = QListWidget()
        self.table.setMouseTracking(True)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setSelectionMode(QListWidget.NoSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setItemDelegate(RecentDelegate(self))
        self.table.setStyleSheet(LIST_QSS)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(page._item_menu)
        self.table.itemClicked.connect(page._clicked)
        lay.addWidget(self.table, 1)

        self.empty = QLabel("Nothing played yet. Open a file and it will show up here.")
        self.empty.setStyleSheet("color:#6a6a6a;font-size:14px;padding:24px 8px")
        lay.addWidget(self.empty)
        lay.addWidget(footer_label())       # design / VLC credit and the donate link

    # ---- state ------------------------------------------------------------
    def _toggle_cw(self):
        self.cw_open = not self.cw_open
        self.refresh()

    def _set_filter(self, key):
        self.filter = key
        self.refresh()

    def _set_sort(self, key):
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, key == "played"
        self.refresh()

    # ---- content ----------------------------------------------------------
    def _rows(self, query: str):
        page, store = self.page, self.page.store
        rows = []
        for item, h in store.recent(500):
            kind = "stream" if is_url(item) else h.get("kind") or (
                "audio" if Path(item).suffix.lower() in AUDIO_EXTS else "video")
            if self.filter != "all" and kind != self.filter:
                continue
            e = page._file_entry(item)
            if kind == "audio":
                artist = h.get("artist") or store.d["music_index"].get(item, {}).get("artist", "")
                if artist:
                    e.label = f"{e.label} - {artist}"
            e.extra.update(kind=kind, location=location(item), format=file_format(item, kind),
                           when=when_played(h.get("last", 0)), ts=h.get("last", 0))
            if query and query not in e.label.lower() and query not in e.extra["location"].lower():
                continue
            rows.append(e)
        key = {"name": lambda e: e.label.lower(), "format": lambda e: (e.extra["format"], -e.extra["ts"]),
               "played": lambda e: e.extra["ts"]}[self.sort_key]
        rows.sort(key=key, reverse=self.sort_desc)
        return rows

    def refresh(self, query: str = ""):
        self.hello.setText(greeting())

        cw = self.page._home_entries("continue")
        has_cw = bool(cw) and not query
        self.cw_btn.setVisible(has_cw)
        self.cw_btn.setText("  Continue watching")
        self.cw_btn.setIcon(QIcon(pixmap("chevron_down" if self.cw_open else "chevron_right", "#bdbdbd", 16)))
        self.cw_row.setVisible(has_cw and self.cw_open)
        if has_cw:
            self.cw_row.set_entries(cw[:12])

        for key, b in self.pill_btns.items():
            on = key == self.filter
            b.setStyleSheet(
                f"QPushButton{{background:{T.ACCENT if on else 'transparent'};color:{'#1b1b1b' if on else '#cfcfcf'};"
                f"border:1px solid {T.ACCENT if on else '#4a4a4a'};border-radius:16px;padding:0 16px;font-size:14px}}"
                + ("" if on else "QPushButton:hover{border-color:#8a8a8a;color:#fff}"))

        for key, label in self.SORTS.items():
            arrow = (" ↓" if self.sort_desc else " ↑") if key == self.sort_key else ""
            self.col_btns[key].setText(label + arrow)

        rows = self._rows(query)
        self.table.clear()
        for e in rows:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, e)
            it.setSizeHint(QSize(400, ROW_H))
            it.setToolTip(e.target)
            self.table.addItem(it)
        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        if not rows and self.filter != "all":
            self.empty.setText("Nothing of this kind played yet.")
        elif not rows and query:
            self.empty.setText("No recent media matches your search.")
        else:
            self.empty.setText("Nothing played yet. Open a file and it will show up here.")
        return (cw[:12] if has_cw and self.cw_open else []) + rows



class ClassicHome(QScrollArea):
    """The original Figma Home: a row of tiles per section (Continue Watching,
    Listen Again, frequent folders, playlists and artists). Chosen in
    Settings > General > Home page style."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QScrollArea{background:transparent}" + LIST_QSS)
        self.viewport().setStyleSheet("background:transparent")

    def refresh(self, query: str = ""):
        page = self.page
        body = QWidget()
        body.setObjectName("homebody")
        body.setStyleSheet("#homebody{background:transparent} QLabel{background:transparent}")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(4)
        entries = []
        for key, title, mode in page.HOME_SECTIONS:
            es = [e for e in page._home_entries(key) if not query or query in e.label.lower()]
            if not es:
                continue
            h = QPushButton(f"{title}  ›")
            h.setCursor(Qt.PointingHandCursor)
            h.setStyleSheet("QPushButton{background:transparent;border:none;color:#bdbdbd;font-size:16px;"
                            "text-align:left;padding:10px 6px 2px}QPushButton:hover{color:#fff}")
            h.clicked.connect(lambda _=False, k=key: page.go(("home", k)))
            lay.addWidget(h)
            row = TileList(page, mode, wrap=False)
            row.set_entries(es[:12])
            row.setFixedHeight(page.cell_size(mode).height() + 6)
            lay.addWidget(row)
            entries += es[:12]
        if not entries:
            empty = QLabel("Nothing here yet. Play something and it will show up on Home.")
            empty.setStyleSheet("color:#6a6a6a;font-size:14px;padding:30px 8px")
            lay.addWidget(empty)
        lay.addStretch(1)
        self.setWidget(body)
        return entries
