"""Full-window library (Figma library frames): a labelled nav on the left, a
breadcrumb header with item count, sort, view, search, add and more, then the
content as a thumbnail grid or a compact list. Home shows rows of tiles per
section. A draggable mini player keeps the current video playing."""

import os
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QPushButton,
    QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

import theme as T
from icons import pixmap
from library import Entry, LibraryLogic
from library_store import AUDIO_EXTS, LibraryStore
from menus import add, styled_menu
from widgets import IconButton

PAGE_BG = "#141414"
LIST_QSS = """
    QListWidget { background:transparent; border:none; outline:0; }
    QListWidget::item, QListWidget::item:selected, QListWidget::item:hover { background:transparent; border:none; }
    QScrollBar:vertical { width:8px; background:transparent; }
    QScrollBar::handle:vertical { background:#333; border-radius:4px; min-height:30px; }
    QScrollBar::add-line, QScrollBar::sub-line { height:0; width:0; }
    QScrollBar::add-page, QScrollBar::sub-page { background:none; }
    QScrollBar:horizontal { height:0; }
"""
PLACEHOLDER = {  # kind / icon -> (tile background, icon)
    "video": ("#1d1d1d", "video"), "music": ("#2f3d33", "music"), "folder": ("#222222", "m_folder"),
    "stream": ("#1f2328", "m_network"), "playlist": ("#262321", "r_queue"),
}


def _rounded(p: QPainter, rect: QRectF, radius=8):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.setClipPath(path)


class TileDelegate(QStyledItemDelegate):
    """Paints an Entry as a tile. mode: grid (16:9 + name), wide (Home video row),
    square (Home music / folder rows, name + sub line) or list (tiny thumb + name)."""

    def __init__(self, page, mode):
        super().__init__(page)
        self.page, self.mode = page, mode

    def sizeHint(self, option, index):
        return self.page.cell_size(self.mode)

    def paint(self, p, option, index):
        e: Entry = index.data(Qt.UserRole)
        if e is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(option.rect)
        hovered = bool(option.state & QStyle.State_MouseOver)
        current = self.page.current is not None and e.target == self.page.current
        text_col = QColor(T.ACCENT if current else ("#5e5e5e" if e.dim else "#b4b4b4"))
        f = QFont(option.font)
        f.setPixelSize(13)
        p.setFont(f)

        if self.mode == "list":
            if hovered:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#1f1f1f"))
                p.drawRoundedRect(r.adjusted(2, 1, -6, -1), 5, 5)
            thumb = QRectF(r.left() + 6, r.center().y() - 11, 22, 22)
            self._thumb(p, e, thumb, radius=3, icon_size=14)
            if e.progress is not None or e.dim:
                p.setClipping(False)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(T.ACCENT))
                p.drawRect(QRectF(thumb.left(), thumb.bottom() + 1, thumb.width() * (1 if e.dim else e.progress), 2))
            p.setClipping(False)
            p.setPen(text_col)
            tr = r.adjusted(36, 0, -12, 0)
            p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, p.fontMetrics().elidedText(e.label, Qt.ElideRight, int(tr.width())))
            p.restore()
            return

        pad = 8
        cell_w = r.width() - 2 * pad
        if self.mode in ("grid", "wide"):
            th = cell_w * 9 / 16
        else:
            th = cell_w
        thumb = QRectF(r.left() + pad, r.top() + pad, cell_w, th)
        self._thumb(p, e, thumb)
        p.setClipping(False)
        if hovered:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 16))
            p.drawRoundedRect(thumb, 8, 8)
        if e.progress is not None or e.dim:
            # Watched (full) or partly watched: orange line along the bottom of the thumbnail.
            frac = 1.0 if e.dim else e.progress
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.ACCENT))
            p.drawRoundedRect(QRectF(thumb.left(), thumb.bottom() - 3, thumb.width() * frac, 3), 1.5, 1.5)
        p.setPen(text_col)
        tr = QRectF(thumb.left(), thumb.bottom() + 8, thumb.width(), 20)
        p.drawText(tr, Qt.AlignLeft | Qt.AlignTop, p.fontMetrics().elidedText(e.label, Qt.ElideRight, int(tr.width())))
        sub = e.extra.get("line2") or ""
        if sub:
            p.setPen(QColor("#6a6a6a"))
            p.drawText(tr.translated(0, 22), Qt.AlignLeft | Qt.AlignTop,
                       p.fontMetrics().elidedText(sub, Qt.ElideRight, int(tr.width())))
        p.restore()

    def _thumb(self, p, e: Entry, rect: QRectF, radius=8, icon_size=None):
        p.save()
        _rounded(p, rect, radius)
        px = self.page.thumb_for(e)
        if px is not None and not px.isNull():
            scaled = px.scaled(rect.size().toSize() * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = (scaled.width() - rect.width() * 2) / 2
            sy = (scaled.height() - rect.height() * 2) / 2
            p.drawPixmap(rect, scaled, QRectF(sx, sy, rect.width() * 2, rect.height() * 2))
        else:
            bg, icon = self.page.placeholder(e)
            p.fillRect(rect, QColor(bg))
            s = icon_size or int(min(rect.width(), rect.height()) * 0.28)
            color = "#3ed160" if icon == "music" else "#6f6f6f"
            p.drawPixmap(QRect(int(rect.center().x() - s / 2), int(rect.center().y() - s / 2), s, s),
                         pixmap(icon, color, s, accent=color))
        p.restore()


class TileList(QListWidget):
    """QListWidget in icon mode showing Entries with TileDelegate."""

    def __init__(self, page, mode, wrap=True):
        super().__init__()
        self.page, self.mode = page, mode
        # Icon mode centres items in their cells; the compact list should hug the left edge.
        self.setViewMode(QListView.ListMode if mode == "list" else QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setWrapping(wrap)
        self.setFlow(QListView.LeftToRight)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSelectionMode(QListWidget.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if not wrap:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setItemDelegate(TileDelegate(page, mode))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(page._item_menu)
        self.itemClicked.connect(page._clicked)
        self.setStyleSheet(LIST_QSS)

    def set_entries(self, entries):
        self.clear()
        for e in entries:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, e)
            it.setSizeHint(self.gridSize() if self.gridSize().isValid() and self.mode in ("grid", "list")
                           else self.page.cell_size(self.mode))
            it.setToolTip(e.target if isinstance(e.target, str) else "")
            self.addItem(it)
        if not (self.gridSize().isValid() and self.mode in ("grid", "list")):
            self.setGridSize(self.page.cell_size(self.mode))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.mode in ("grid", "list"):
            self.page.relayout(self)

    def wheelEvent(self, e):
        if self.isWrapping():
            super().wheelEvent(e)
        else:
            e.ignore()   # Home rows: let the page scroll


class NavButton(QPushButton):
    def __init__(self, icon, label):
        super().__init__(f"   {label}")
        self.icon_name = icon
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self.setIconSize(QSize(18, 18))
        self.set_active(False)

    def set_active(self, on):
        col = T.ACCENT if on else T.ICON
        self.setIcon(QIcon(pixmap(self.icon_name, col, 18, accent=col)))
        self.setStyleSheet(
            f"QPushButton{{background:{'#232323' if on else 'transparent'};color:{'#e8e8e8' if on else '#a8a8a8'};"
            "border:none;border-radius:6px;text-align:left;padding-left:10px;font-size:13px}"
            "QPushButton:hover{background:#1f1f1f;color:#e8e8e8}")


class MiniPlayer(QFrame):
    """Floating card with the live video, progress, title and labels. Drag it by
    its frame; click the video or title to go back to the player."""

    open_player = Signal()
    show_queue = Signal()
    close_media = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("mini")
        self.setStyleSheet("#mini{background:#1c1c1c;border:1px solid #2c2c2c;border-radius:10px}"
                           "QLabel{background:transparent}")
        self.setFixedSize(300, 262)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 8)
        lay.setSpacing(6)
        self.video_holder = QWidget()
        self.video_holder.setFixedHeight(160)
        self.video_lay = QVBoxLayout(self.video_holder)
        self.video_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.video_holder)
        self.progress = _MiniProgress()
        lay.addWidget(self.progress)
        self.title = QLabel()
        self.title.setStyleSheet("color:#cfcfcf;font-size:13px;padding:2px 4px 0")
        self.title.setCursor(Qt.PointingHandCursor)
        self.title.mousePressEvent = lambda e: self.open_player.emit()
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(self.title, 1)
        # ✕ stops playback and leaves you on the library (it sits beside the title because
        # nothing can be drawn over libVLC's video area).
        self.close_btn = IconButton("close", "Stop and close", size=16, box=26)
        self.close_btn.clicked.connect(self.close_media.emit)
        title_row.addWidget(self.close_btn)
        lay.addLayout(title_row)
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 0, 0)
        row.setSpacing(4)
        self.folder_icon, self.folder = QLabel(), QLabel()
        self.artist_icon, self.artist = QLabel(), QLabel()
        self.folder_icon.setPixmap(pixmap("m_folder", T.ICON, 16, accent=T.ICON))
        self.artist_icon.setPixmap(pixmap("m_profile", T.ICON, 16, accent=T.ICON))
        for w in (self.folder, self.artist):
            w.setStyleSheet("color:#9a9a9a;font-size:12px")
        row.addWidget(self.folder_icon)
        row.addWidget(self.folder)
        row.addSpacing(10)
        row.addWidget(self.artist_icon)
        row.addWidget(self.artist)
        row.addStretch(1)
        self.queue_btn = IconButton("playlist", "Queue", size=16, box=28)
        self.queue_btn.clicked.connect(self.show_queue.emit)
        row.addWidget(self.queue_btn)
        lay.addLayout(row)
        self._drag = None
        self._placed = False

    def set_info(self, title, folder, artist, frac):
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(title, Qt.ElideRight, 240))
        self.folder.setText(folder)
        self.artist.setText(artist)
        self.artist.setVisible(bool(artist))
        self.artist_icon.setVisible(bool(artist))
        self.progress.set_frac(frac)

    def place_default(self):
        if not self._placed:
            par = self.parentWidget()
            self.move(par.width() - self.width() - 18, par.height() - self.height() - 18)

    def keep_inside(self):
        par = self.parentWidget()
        x = min(max(self.x(), 8), par.width() - self.width() - 8)
        y = min(max(self.y(), 8), par.height() - self.height() - 8)
        self.move(x, y)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(self.mapToParent(e.position().toPoint() - self._drag))
            self.keep_inside()
            self._placed = True

    def mouseReleaseEvent(self, e):
        self._drag = None


class _MiniProgress(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(10)
        self._f = 0.0

    def set_frac(self, f):
        if abs(f - self._f) > 0.001:
            self._f = f
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        p.setBrush(QColor(T.TRACK))
        p.drawRoundedRect(r, 4, 4)
        if self._f > 0:
            p.setBrush(QColor(T.SEEK_FILL))
            p.drawRoundedRect(QRectF(1, 1, (r.width() - 2) * self._f, r.height() - 2), 3, 3)


class LibraryPage(QFrame, LibraryLogic):
    play_items = Signal(list, int, str, bool)
    enqueue = Signal(list)
    toast = Signal(str)
    rescan = Signal()
    _fetched = Signal(str, str, list)
    back_requested = Signal()
    command = Signal(str)        # open_file / open_folder / open_stream / shortcuts / settings / about

    # Word-style extras in the left column (Word's Open / Account / Options).
    COMMANDS = [("open_file", "m_file", "Open file"), ("open_folder", "m_folder", "Open folder"),
                ("open_stream", "m_network", "Network stream")]
    FOOTER = [("shortcuts", "m_keyboard", "Shortcuts"), ("settings", "settings", "Settings"),
              ("about", "m_info", "About")]

    NAV = [("home", "home", "Home"), ("videos", "video", "Videos"), ("music", "music", "Music"),
           ("network", "m_network", "Network"), ("playlists", "r_queue", "Playlists"), ("recent", "m_recent", "Recent")]
    HOME_SECTIONS = [("continue", "Continue Watching", "wide"), ("listen", "Listen Again", "square"),
                     ("folders", "Frequently Visited Folders", "square"),
                     ("playlists", "Frequently Visited Playlists", "square"),
                     ("artists", "Frequently Listened Artists", "square")]

    def __init__(self, store: LibraryStore, thumbnailer, parent=None):
        super().__init__(parent)
        self._init_logic(store)
        self.thumbs = thumbnailer
        self._px: dict[str, QPixmap] = {}
        self.view_mode = "grid"
        self.setObjectName("libpage")
        self.setStyleSheet(f"#libpage{{background:{T.SHELL}}} QLabel{{background:transparent}}")

        root = QHBoxLayout(self)
        root.setContentsMargins(T.FRAME_MARGIN, 0, T.FRAME_MARGIN, T.FRAME_MARGIN)
        root.setSpacing(T.FRAME_MARGIN)

        nav = QFrame()
        nav.setObjectName("nav")
        nav.setFixedWidth(168)
        nav.setStyleSheet(f"#nav{{background:{PAGE_BG};border-radius:{T.VIDEO_RADIUS}px}}")
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(8, 10, 8, 10)
        nl.setSpacing(2)
        self.back_btn_nav = NavButton("chevron_left", "Back")
        self.back_btn_nav.setToolTip("Back to what's playing (Esc)")
        self.back_btn_nav.clicked.connect(self.back_requested.emit)
        nl.addWidget(self.back_btn_nav)
        self.back_line = QFrame()
        self.back_line.setFixedHeight(1)
        self.back_line.setStyleSheet("background:#262626; margin:4px 6px;")
        nl.addWidget(self.back_line)
        self.nav_btns = {}
        for key, icon, label in self.NAV:
            b = NavButton(icon, label)
            b.clicked.connect(lambda _=False, k=key: self.go((k,)))
            self.nav_btns[key] = b
            nl.addWidget(b)
        self.add_btn = NavButton("add", "Add item")
        self.add_btn.clicked.connect(self._add_menu)
        nl.addWidget(self.add_btn)
        # Pinned folders (added with "Add folder"), like Word's pinned places.
        self.pin_title = QLabel("Pinned")
        self.pin_title.setStyleSheet("color:#6f6f6f;font-size:11px;padding:10px 10px 2px")
        nl.addWidget(self.pin_title)
        self.pin_box = QVBoxLayout()
        self.pin_box.setSpacing(2)
        nl.addLayout(self.pin_box)
        self.pin_btns: dict[str, NavButton] = {}
        for group in (self.COMMANDS, self.FOOTER):
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet("background:#262626; margin:6px 6px;")
            if group is self.FOOTER:
                nl.addStretch(1)
            nl.addWidget(line)
            for key, icon, label in group:
                b = NavButton(icon, label)
                b.clicked.connect(lambda _=False, k=key: self.command.emit(k))
                nl.addWidget(b)
        root.addWidget(nav)

        main = QFrame()
        main.setObjectName("main")
        main.setStyleSheet(f"#main{{background:{PAGE_BG};border-radius:{T.VIDEO_RADIUS}px}}")
        ml = QVBoxLayout(main)
        ml.setContentsMargins(14, 8, 14, 0)
        ml.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(2)
        self.back_btn = IconButton("chevron_left", "Back", size=18, box=30)
        self.fwd_btn = IconButton("chevron_right", "Forward", size=18, box=30)
        self.back_btn.clicked.connect(self.go_back)
        self.fwd_btn.clicked.connect(self.go_forward)
        head.addWidget(self.back_btn)
        head.addWidget(self.fwd_btn)
        self.crumbs = QHBoxLayout()
        self.crumbs.setSpacing(0)
        crumb_box = QWidget()
        crumb_box.setLayout(self.crumbs)
        head.addSpacing(6)
        head.addWidget(crumb_box)
        head.addStretch(1)
        self.count = QLabel()
        self.count.setStyleSheet("color:#7a7a7a;font-size:12px;padding-right:8px")
        head.addWidget(self.count)
        self.sort_btn = IconButton("sort", "Sort", size=18, box=30)
        self.sort_btn.clicked.connect(self._sort_menu)
        self.view_btn = IconButton("grid", "Switch to list", size=18, box=30)
        self.view_btn.clicked.connect(self._toggle_view)
        head.addWidget(self.sort_btn)
        head.addWidget(self.view_btn)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.addAction(QIcon(pixmap("search", "#7a7a7a", 16)), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(240)
        self.search.setStyleSheet("QLineEdit{background:#1e1e1e;border:1px solid #262626;border-radius:6px;"
                                  "color:#ddd;padding:5px 6px;font-size:13px} QLineEdit:focus{border-color:#3a3a3a}")
        self.search.textChanged.connect(self.refresh)
        head.addSpacing(6)
        head.addWidget(self.search)
        head.addSpacing(6)
        self.plus_btn = IconButton("add", "Add", size=18, box=30)
        self.plus_btn.clicked.connect(self._add_here)
        self.more_btn = IconButton("more", "More", size=18, box=30)
        self.more_btn.clicked.connect(self._more_menu)
        head.addWidget(self.plus_btn)
        head.addWidget(self.more_btn)
        ml.addLayout(head)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#232323")
        ml.addWidget(line)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color:#8a8a8a;font-size:13px;padding:6px 4px 2px")
        ml.addWidget(self.desc)

        self.stack = QStackedWidget()
        self.grid = TileList(self, "grid")
        self.listv = TileList(self, "list")
        from start_page import ClassicHome, StartPage   # they import this module, so load them late
        self.home = StartPage(self)
        self.classic_home = ClassicHome(self)
        self.home_style = "Start screen"      # Settings > General > Home page style
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.listv)
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.classic_home)
        ml.addWidget(self.stack, 1)
        root.addWidget(main, 1)

        self.mini = MiniPlayer(self)
        self.mini.hide()

        self.thumbs.ready.connect(self._thumb_ready)
        self._fetched.connect(self._stream_fetched)
        self.store.changed.connect(self.refresh)
        self._grid_cell = QSize(240, 186)
        self.refresh()

    # ---- sizes ----------------------------------------------------------
    def cell_size(self, mode):
        if mode == "grid":
            return self._grid_cell
        if mode == "list":
            return QSize(max(260, self._grid_cell.width() + 40), 31)
        if mode == "wide":
            return QSize(246, 138 + 16 + 30)
        return QSize(160, 144 + 16 + 50)   # square

    def relayout(self, lst):
        """Fit whole columns: thumbnails grow to fill the width, like the design's 5-across grid."""
        vw = lst.viewport().width() - 4
        if lst.mode == "grid":
            cols = max(1, vw // 230)
            w = vw // cols
            size = QSize(w, int((w - 16) * 9 / 16) + 16 + 30)
            if size != self._grid_cell:
                self._grid_cell = size
                lst.setGridSize(size)
                for i in range(lst.count()):
                    lst.item(i).setSizeHint(size)
        else:
            cols = max(1, vw // 290)
            size = QSize(vw // cols, 31)
            if lst.gridSize() != size:
                lst.setGridSize(size)
                for i in range(lst.count()):
                    lst.item(i).setSizeHint(size)
                lst.doItemsLayout()

    # ---- thumbnails -----------------------------------------------------
    def thumb_for(self, e: Entry) -> QPixmap | None:
        if e.kind != "file":
            return None
        path = e.target
        if path in self._px:
            return self._px[path]
        jpg = self.thumbs.lookup(path)
        if jpg:
            self._px[path] = QPixmap(jpg)
            return self._px[path]
        return None

    def placeholder(self, e: Entry):
        if e.kind == "file":
            key = "music" if Path(e.target).suffix.lower() in AUDIO_EXTS else "video"
        elif e.kind == "stream":
            key = "stream"
        elif e.kind == "playlist":
            key = "playlist"
        elif e.kind == "folder":
            key = "folder"
        else:
            return "#222222", e.icon or "m_folder"
        return PLACEHOLDER[key]

    def _thumb_ready(self, path, jpg):
        self._px[path] = QPixmap(jpg)
        for lst in self.findChildren(TileList):
            lst.viewport().update()

    # ---- header ---------------------------------------------------------
    def crumb_parts(self, loc):
        k = loc[0]
        names = {"home": "Home", "videos": "Videos", "music": "Music", "network": "Network",
                 "playlists": "Playlists", "recent": "Recent"}
        if k == "folder":
            path, kind = Path(loc[1]), loc[2]
            roots = sorted(self.store.d[f"{kind}_roots"], key=len, reverse=True)
            root = next((r for r in roots if str(path).startswith(r)), None)
            top = ("Music", ("music",)) if kind == "music" else ("Videos", ("videos",))
            if root is None:
                parts = path.parts[-3:]
                base = Path(*path.parts[:-3]) if len(path.parts) > 3 else Path(path.anchor)
                out, acc = [], base
                for part in parts:
                    acc = acc / part
                    out.append((part, ("folder", str(acc), kind)))
                return out
            out, acc = [top], Path(root)
            for part in path.relative_to(root).parts:
                acc = acc / part
                out.append((part, ("folder", str(acc), kind)))
            return out
        if k == "home" and len(loc) > 1:
            title = next(t for key, t, _ in self.HOME_SECTIONS if key == loc[1])
            return [("Home", ("home",)), (title, loc)]
        if k == "music" and len(loc) >= 2:
            sub = loc[1] if len(loc) == 2 else loc[1] + "s"
            out = [("Music", ("music",)), (sub.title(), ("music", sub))]
            if len(loc) == 3:
                out.append((loc[2], loc))
            return out
        if k == "network" and len(loc) > 1:
            g = next((s for s in self.store.d["streams"] if s["url"] == loc[1]), {"name": "Stream"})
            return [("Network", ("network",)), (g["name"], loc)]
        if k == "playlist":
            return [("Playlists", ("playlists",)), (loc[1], loc)]
        return [(names.get(k, ""), loc)]

    def _render_crumbs(self):
        while self.crumbs.count():
            w = self.crumbs.takeAt(0).widget()
            if w:
                w.deleteLater()
        parts = self.crumb_parts(self.loc)
        for i, (label, loc) in enumerate(parts):
            last = i == len(parts) - 1
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:transparent;border:none;color:{'#ececec' if last else '#a8a8a8'};"
                            f"font-size:14px;{'font-weight:600;' if last else ''}padding:2px 4px}}"
                            "QPushButton:hover{color:#ffffff}")
            b.clicked.connect(lambda _=False, l=loc: self.go(l))
            self.crumbs.addWidget(b)
            if not last:
                sep = QLabel("▸")
                sep.setStyleSheet("color:#5a5a5a;font-size:10px;padding:0 2px")
                self.crumbs.addWidget(sep)

    def _sort_icon(self):
        changed = self.sort != "Name A→Z"
        px = pixmap("sort", T.ICON, 18, accent=T.ICON)
        if changed:   # orange dot = a non-default sort is on
            p = QPainter(px)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.ACCENT))
            p.drawEllipse(QRectF(13, 0, 6, 6))
            p.end()
        self.sort_btn._normal = px
        self.sort_btn.setIcon(px)

    def _toggle_view(self):
        self.view_mode = "list" if self.view_mode == "grid" else "grid"
        self.view_btn.set_icon("list_view" if self.view_mode == "list" else "grid")
        self.view_btn.setToolTip("Switch to grid" if self.view_mode == "list" else "Switch to list")
        self.refresh()

    def _add_here(self):
        k = self.loc[0]
        kind = self.loc[2] if k == "folder" else None
        if k == "videos" or kind == "video":
            self._action("add_video_root")
        elif k == "music" or kind == "music":
            self._action("add_music_root")
        elif k == "network":
            self.add_stream_dialog()
        elif k in ("playlists", "playlist"):
            self.create_playlist_dialog()
        else:
            self._add_menu()

    # ---- content --------------------------------------------------------
    def _home_entries(self, key):
        es = self._entries_for(("home", key))
        for e in es:
            if e.kind == "file":
                h = self.store.d["history"].get(e.target, {})
                tags = self.store.d["music_index"].get(e.target, {})
                e.extra["line2"] = h.get("artist") or tags.get("artist") or ""
            elif e.kind == "playlist":
                e.extra["line2"] = f"{len(self.store.playlists().get(e.label, []))} items"
        return es

    def refresh(self, *_):
        if not hasattr(self, "stack"):
            return
        q = self.search.text().strip().lower()
        if self.loc == ("home",) and self.home_style == "Classic":
            self._entries = self.classic_home.refresh(q)
            n = len(self._entries)
            self.stack.setCurrentWidget(self.classic_home)
        elif self.loc == ("home",):
            self._entries = self.home.refresh(q)
            n = self.home.table.count()
            self.stack.setCurrentWidget(self.home)
        else:
            es = [e for e in self._entries_for(self.loc) if e.kind not in ("header", "action")]
            if q:
                es = [e for e in es if q in e.label.lower()]
            for e in es:
                if e.kind in ("nav", "playlist", "folder") and e.sub:
                    e.extra["line2"] = e.sub
                elif e.kind == "file" and e.sub and self.loc[0] != "folder":
                    e.extra["line2"] = e.sub
            self._entries = es
            n = len(es)
            target = self.grid if self.view_mode == "grid" else self.listv
            target.set_entries(es)
            self.relayout(target)
            self.stack.setCurrentWidget(target)
        self.count.setText(f"{n} item{'s' if n != 1 else ''}")
        self._render_crumbs()
        self._sort_icon()
        self.back_btn.setEnabled(bool(self.back_stack))
        self.fwd_btn.setEnabled(bool(self.fwd_stack))
        active = self._rail_key(self.loc)
        pin_active = self._rebuild_pins()
        for key, b in self.nav_btns.items():
            b.set_active(key == active and not pin_active)
        text = self.DESCRIPTIONS.get(self.loc) if len(self.loc) == 1 else None
        self.desc.setText(text or "")
        self.desc.setVisible(bool(text))

    # What each section is for, shown under the header (people asked).
    DESCRIPTIONS = {
        ("videos",): "Your video folders: films, shows and clips. Click + (or Add item › Add folder) to add a "
                     "folder; it also gets pinned to the left for quick access.",
        ("music",): "Songs from your music folders. Songs shows the folders; Albums, Artists and Genres group "
                    "them using the tags inside the files.",
        ("network",): "Things that play from the internet instead of a file: radio stations, live TV, podcasts or "
                      "any direct video/stream link. Click + and paste a link to save it. A channel list "
                      "(an .m3u link) opens as a list of channels.",
        ("playlists",): "Your own lists of videos and songs, played in order. Click + to make one, or right-click "
                        "any file › Add to playlist.",
        ("recent",): "Everything you've played, newest first.",
    }

    def _rebuild_pins(self) -> bool:
        """Sync the pinned-folder buttons with the store; True if one matches where we are."""
        pins = self.store.pinned()
        wanted = [p["path"] for p in pins]
        if list(self.pin_btns) != wanted:
            for b in self.pin_btns.values():
                self.pin_box.removeWidget(b)   # take it out now; deleteLater alone leaves it showing a moment
                b.hide()
                b.deleteLater()
            self.pin_btns = {}
            for p in pins:
                b = NavButton("m_folder", Path(p["path"]).name or p["path"])
                b.setToolTip(p["path"])
                b.clicked.connect(lambda _=False, p=p: self.go(("folder", p["path"], p["kind"])))
                b.setContextMenuPolicy(Qt.CustomContextMenu)
                b.customContextMenuRequested.connect(lambda pos, p=p, b=b: self._pin_menu(p, b.mapToGlobal(pos)))
                self.pin_box.addWidget(b)
                self.pin_btns[p["path"]] = b
        self.pin_title.setVisible(bool(pins))
        here = self.loc[1] if self.loc[0] == "folder" else None
        hit = None
        if here:
            # the deepest pinned folder that contains where we are
            for path in sorted(self.pin_btns, key=len, reverse=True):
                if here == path or here.startswith(path.rstrip("\\/") + os.sep):
                    hit = path
                    break
        for path, b in self.pin_btns.items():
            b.set_active(path == hit)
        return hit is not None

    def _pin_menu(self, pin, gpos):
        m = styled_menu(self)
        add(m, "m_folder", "Open", lambda: self.go(("folder", pin["path"], pin["kind"])))
        add(m, "r_play", "Play all", lambda: self._play_folder(pin["path"]), color=T.ACCENT)
        add(m, None, "Show in Explorer", lambda: os.startfile(pin["path"]))
        m.addSeparator()
        add(m, None, "Unpin from sidebar", lambda: self.store.unpin(pin["path"]))
        add(m, None, "Remove from library", lambda: self.store.remove_root(pin["kind"], pin["path"]))
        m.exec(gpos)

    def set_back_visible(self, on: bool):
        self.back_btn_nav.setVisible(on)
        self.back_line.setVisible(on)

    def set_current(self, item):
        self.current = item
        for lst in self.findChildren(TileList):
            lst.viewport().update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.mini.isVisible():
            if self.mini._placed:
                self.mini.keep_inside()
            else:
                self.mini.place_default()

