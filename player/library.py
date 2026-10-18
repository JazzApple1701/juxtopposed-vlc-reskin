"""Compact library sidebar (Figma "sidebar" frames).

An icon rail (Home, Videos, Music, Network, Playlists, Recent, Add) next to a
browser with back / forward, breadcrumb, item count, sort, view and search.
Sections: Home (Continue Watching, Listen Again, frequent folders, playlists
and artists), Videos and Music folders, Music by album / artist / genre,
saved network streams (m3u lists open as channel lists) and playlists."""

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QStyle, QStyledItemDelegate, QVBoxLayout,
)

import theme as T
from icons import pixmap
from library_store import AUDIO_EXTS, MEDIA_EXTS, LibraryStore, fetch_m3u, guess_folder_kind, is_url
from menus import add, styled_menu
from widgets import IconButton

PANEL_BG = "#151515"
ROW_H = 32
HEADER_H = 40


@dataclass
class Entry:
    kind: str                    # header | action | nav | folder | file | stream | playlist
    label: str
    icon: str = ""
    target: object = None        # location tuple, path or URL
    sub: str = ""                # right-hand detail text
    progress: float | None = None
    dim: bool = False
    extra: dict = field(default_factory=dict)


class _Delegate(QStyledItemDelegate):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self._px = {}

    def _icon(self, name, color):
        key = (name, color)
        if key not in self._px:
            self._px[key] = pixmap(name, color, 18)
        return self._px[key]

    def sizeHint(self, option, index):
        e = index.data(Qt.UserRole)
        return QSize(100, HEADER_H if e and e.kind == "header" else ROW_H)

    def paint(self, p, option, index):
        e: Entry = index.data(Qt.UserRole)
        if e is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect)
        hovered = bool(option.state & QStyle.State_MouseOver)
        f = QFont(option.font)

        if e.kind == "header":
            f.setPixelSize(14)
            p.setFont(f)
            p.setPen(QColor("#b8b8b8" if hovered else "#a0a0a0"))
            text_w = p.fontMetrics().horizontalAdvance(e.label)
            p.drawText(r.adjusted(8, 10, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, e.label)
            p.drawPixmap(int(r.left() + 14 + text_w), int(r.center().y() + 5 - 8), 16, 16,
                         self._icon("chevron_right", "#a0a0a0"))
            p.restore()
            return

        if hovered:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#222222"))
            p.drawRoundedRect(r.adjusted(2, 1, -2, -1), 6, 6)

        current = self.panel.current is not None and e.target == self.panel.current and e.kind in ("file", "stream")
        if current:
            color = T.ACCENT
        elif e.dim:
            color = "#626262"
        elif e.kind == "action":
            color = "#8a8a8a"
        else:
            color = "#b4b4b4"
        icon_color = T.ACCENT if current else ("#5a5a5a" if e.dim else T.ICON)
        if e.icon:
            p.drawPixmap(int(r.left() + 10), int(r.center().y() - 9), 18, 18, self._icon(e.icon, icon_color))
        if e.progress is not None and e.progress > 0:
            # Orange line under the icon: how much of it you've watched.
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#3a3a3a"))
            p.drawRect(QRectF(r.left() + 10, r.center().y() + 11, 18, 2))
            p.setBrush(QColor(T.ACCENT))
            p.drawRect(QRectF(r.left() + 10, r.center().y() + 11, 18 * min(e.progress, 1), 2))

        f.setPixelSize(13)
        p.setFont(f)
        fm = p.fontMetrics()
        sub_w = 0
        if e.sub and self.panel.details:
            p.setPen(QColor("#6a6a6a"))
            sub_w = fm.horizontalAdvance(e.sub) + 12
            p.drawText(r.adjusted(0, 0, -10, 0), Qt.AlignRight | Qt.AlignVCenter, e.sub)
        p.setPen(QColor(color))
        text_rect = r.adjusted(38 if e.icon else 12, 0, -10 - sub_w, 0)
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(e.label, Qt.ElideRight, int(text_rect.width())))
        p.restore()


def _fmt_len(ms):
    s = max(0, int(ms or 0)) // 1000
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class LibraryLogic:
    """Navigation, entries, sorting and actions shared by the sidebar and the
    full-window library. Views provide: store, loc, current, sort, _entries,
    search (QLineEdit), add_btn / more_btn / sort_btn, signals and refresh()."""

    def _init_logic(self, store: LibraryStore):
        self.store = store
        self.loc: tuple = ("home",)
        self.current: str | None = None
        self.back_stack: list[tuple] = []
        self.fwd_stack: list[tuple] = []
        self.sort = "Name A→Z"
        self.details = False
        self._entries: list[Entry] = []

    # ---- navigation ------------------------------------------------------
    def go(self, loc: tuple, remember=True):
        if remember and loc != self.loc:
            self.back_stack.append(self.loc)
            self.fwd_stack.clear()
        self.loc = loc
        self.search.clear()
        self.refresh()

    def go_back(self):
        if self.back_stack:
            self.fwd_stack.append(self.loc)
            self.go(self.back_stack.pop(), remember=False)

    def go_forward(self):
        if self.fwd_stack:
            self.back_stack.append(self.loc)
            self.go(self.fwd_stack.pop(), remember=False)

    def _parent(self, loc):
        if loc[0] == "folder":
            path, section = Path(loc[1]), loc[2]
            top = ("music", "songs") if section == "music" else ("videos",)
            roots = self.store.d[f"{section}_roots"]
            if str(path) in roots or str(path.parent) in roots or path.parent == path:
                return top
            return ("folder", str(path.parent), section)
        if len(loc) > 1:
            if loc[0] == "music" and len(loc) == 3:
                return ("music", {"album": "albums", "artist": "artists", "genre": "genres"}[loc[1]])
            return loc[:1]
        return None

    def go_up(self):
        parent = self._parent(self.loc)
        if parent:
            self.go(parent)

    def show_folder(self, folder: Path, kind: str | None = None):
        if kind is None:
            kind = "music" if any(str(folder).startswith(r) for r in self.store.d["music_roots"]) else "video"
        self.go(("folder", str(folder), kind))

    def set_current(self, item: str | None):
        self.current = item
        self.list.viewport().update()

    # ---- building the list ---------------------------------------------
    def _file_entry(self, item: str, label: str | None = None, icon: str | None = None):
        ext = Path(item).suffix.lower() if not is_url(item) else ""
        h = self.store.d["history"].get(item, {})
        tags = self.store.d["music_index"].get(item, {})
        if icon is None:
            icon = "music" if (ext in AUDIO_EXTS or h.get("kind") == "audio") else "video"
        name = label or h.get("title") or tags.get("title") or (Path(item).name if not is_url(item) else item)
        length = h.get("length") or tags.get("length")
        sub = _fmt_len(length) if length else ""
        prog = self.store.progress(item)
        return Entry("stream" if is_url(item) else "file", name, icon, item, sub,
                     progress=prog if prog and prog < 0.95 else None, dim=self.store.watched(item))

    def _folder_entries(self, folder: Path, kind: str):
        try:
            kids = list(folder.iterdir())
        except OSError:
            return []
        exts = AUDIO_EXTS if kind == "music" else MEDIA_EXTS
        dirs = [Entry("folder", p.name, "m_folder", ("folder", str(p), kind))
                for p in kids if p.is_dir() and not p.name.startswith(".")]
        files = [self._file_entry(str(p), p.name) for p in kids if p.suffix.lower() in exts]
        return self._sorted(dirs) + self._sorted(files, files=True)

    def _roots_entries(self, kind):
        """What's inside the library folders, merged (the design lists Shows, Films, …
        rather than the Videos folder itself)."""
        out = []
        for r in self.store.d[f"{kind}_roots"]:
            if Path(r).is_dir():
                out += self._folder_entries(Path(r), kind)
        return out

    def _sorted(self, entries, files=False):
        s = self.sort

        def key(e):
            if files and s == "Date modified":
                try:
                    return -os.path.getmtime(e.target)
                except OSError:
                    return 0
            return e.label.lower()
        entries = sorted(entries, key=key, reverse=(s == "Name Z→A"))
        if files and s in ("Unwatched first", "Watched first"):
            entries.sort(key=lambda e: (e.dim, e.progress is not None) if s == "Unwatched first"
                         else (not e.dim, e.progress is None))
        return entries

    def _entries_for(self, loc):
        st = self.store
        k = loc[0]
        if k == "home":
            sub = loc[1] if len(loc) > 1 else None
            out = []

            def section(key, title, items, limit):
                if sub is None:
                    if items:
                        out.append(Entry("header", title, target=("home", key)))
                        out.extend(items[:limit])
                elif sub == key:
                    out.extend(items)
            section("continue", "Continue Watching", [self._file_entry(i) for i, _ in st.continue_watching()], 3)
            section("listen", "Listen Again", [self._file_entry(i) for i, _ in st.listen_again()], 3)
            section("folders", "Frequently Visited Folders",
                    [Entry("folder", Path(f).name, "m_folder", ("folder", f, "video" if not any(
                        f.startswith(r) for r in st.d["music_roots"]) else "music")) for f in st.frequent_folders()], 3)
            section("playlists", "Frequently Visited Playlists",
                    [Entry("playlist", n, "r_queue", ("playlist", n)) for n in st.frequent_playlists()], 3)
            section("artists", "Frequently Listened Artists",
                    [Entry("nav", a, "m_profile", ("music", "artist", a)) for a in st.frequent_artists()], 3)
            if not out and sub is None:
                out.append(Entry("action", "Nothing here yet. Play something!", "", None))
            return out
        if k == "videos":
            return [Entry("action", "Add", "add", "add_video_root")] + self._roots_entries("video")
        if k == "music":
            if len(loc) == 1:
                return [Entry("action", "Add", "add", "add_music_root"),
                        Entry("nav", "Songs", "music", ("music", "songs")),
                        Entry("nav", "Albums", "m_disc", ("music", "albums")),
                        Entry("nav", "Artists", "m_profile", ("music", "artists")),
                        Entry("nav", "Genres", "m_keyboard", ("music", "genres"))]
            if loc[1] == "songs":
                return self._roots_entries("music")
            if loc[1] in ("albums", "artists", "genres"):
                fieldname = loc[1][:-1]
                icon = {"album": "m_disc", "artist": "m_profile", "genre": "m_keyboard"}[fieldname]
                return [Entry("nav", g, icon, ("music", fieldname, g), sub=f"{len(v)}")
                        for g, v in st.group_music(fieldname).items()]
            if loc[1] in ("album", "artist", "genre"):
                files = st.group_music(loc[1]).get(loc[2], [])
                return self._sorted([self._file_entry(f) for f in files], files=True)
        if k == "folder":
            return self._folder_entries(Path(loc[1]), loc[2])
        if k == "network":
            if len(loc) == 1:
                out = [Entry("action", "Add Network Stream", "add", "add_stream")]
                for s in st.d["streams"]:
                    if s.get("channels"):
                        out.append(Entry("nav", s["name"], "m_folder", ("network", s["url"]), sub=str(len(s["channels"]))))
                    else:
                        out.append(Entry("stream", s["name"], "m_network", s["url"]))
                return out
            group = next((s for s in st.d["streams"] if s["url"] == loc[1]), None)
            return [Entry("stream", c["name"], "m_network", c["url"]) for c in (group or {}).get("channels", [])]
        if k == "playlists":
            return [Entry("action", "Create playlist", "add", "create_playlist")] + [
                Entry("playlist", n, "r_queue", ("playlist", n), sub=str(len(v))) for n, v in st.playlists().items()]
        if k == "playlist":
            items = st.playlists().get(loc[1], [])
            return [self._file_entry(i) for i in items]
        if k == "recent":
            return [self._file_entry(i) for i, _ in st.recent()]
        return []

    def _crumb(self, loc):
        names = {"home": "Home", "videos": "Videos", "music": "Music", "network": "Network",
                 "playlists": "Playlists", "recent": "Recent"}
        k = loc[0]
        if k == "folder":
            parts = Path(loc[1]).parts
            tail = " › ".join(parts[-2:]) if len(parts) > 1 else loc[1]
            return ("… › " if len(parts) > 2 else "") + tail
        if k == "home" and len(loc) > 1:
            return "Home › " + {"continue": "Continue Watching", "listen": "Listen Again", "folders": "Folders",
                                "playlists": "Playlists", "artists": "Artists"}[loc[1]]
        if k == "music" and len(loc) == 2:
            return "Music › " + loc[1].title()
        if k == "music" and len(loc) == 3:
            return f"… › {loc[1].title()}s › {loc[2]}"
        if k == "network" and len(loc) > 1:
            g = next((s for s in self.store.d["streams"] if s["url"] == loc[1]), {"name": "Stream"})
            return "Network › " + g["name"]
        if k == "playlist":
            return "Playlists › " + loc[1]
        return names.get(k, "")

    def _rail_key(self, loc):
        k = loc[0]
        if k == "folder":
            return "music" if loc[2] == "music" else "videos"
        return {"playlist": "playlists"}.get(k, k)

    # ---- clicks ----------------------------------------------------------
    def _playable(self):
        return [e.target for e in self._entries if e.kind in ("file", "stream")]

    def _clicked(self, item):
        self.activate(item.data(Qt.UserRole))

    def activate(self, e: Entry):
        if e.kind in ("header", "nav", "folder", "playlist"):
            self.go(e.target)
        elif e.kind == "action":
            self._action(e.target)
        elif e.kind in ("file", "stream"):
            items = self._playable()
            name = self.loc[1] if self.loc[0] == "playlist" else ""
            if self.loc[0] in ("home", "recent") and e.kind == "file":
                items = [e.target]           # history lists aren't a queue; play the file and its folder
            # Continue Watching / Listen Again pick up where you left off without asking.
            resume = self.loc[0] == "home" and e.progress is not None
            self.play_items.emit(items, items.index(e.target), name, resume)

    def _action(self, what):
        if what in ("add_folder", "add_video_root", "add_music_root"):
            d = QFileDialog.getExistingDirectory(self, "Add a folder to your library")
            if not d:
                return
            folder = Path(d)
            kind = what.split("_")[1] if what != "add_folder" else guess_folder_kind(folder)
            # Added folders go into Videos / Music and are pinned to the sidebar for quick access.
            self.store.add_root(kind, folder)
            self.store.pin(folder, kind)
            self.go(("folder", str(folder), kind))
            where = "Music" if kind == "music" else "Videos"
            self.toast.emit(f"Added \"{folder.name}\" to {where} and pinned it to the sidebar"
                            + (" (reading music tags in the background)" if kind == "music" else ""))
        elif what == "add_stream":
            self.add_stream_dialog()
        elif what == "create_playlist":
            self.create_playlist_dialog()

    def add_stream_dialog(self, url: str = ""):
        url, ok = QInputDialog.getText(self, "Add network stream",
                                       "Stream or playlist URL (an .m3u list becomes a channel list):", text=url)
        if not ok or not url.strip():
            return
        url = url.strip()
        name, ok = QInputDialog.getText(self, "Add network stream", "Name:", text=url.rstrip("/").rsplit("/", 1)[-1])
        if not ok:
            return
        name = name.strip() or url
        self.toast.emit("Adding stream…")

        def work():
            try:
                channels = fetch_m3u(url) if url.lower().startswith("http") else []
            except Exception:
                channels = []
            self._fetched.emit(name, url, channels)
        threading.Thread(target=work, daemon=True).start()

    def _stream_fetched(self, name, url, channels):
        self.store.add_stream(name, url, channels)
        self.toast.emit(f"Added {len(channels)} channels" if channels else f"Added \"{name}\"")
        self.go(("network", url) if channels else ("network",))

    def create_playlist_dialog(self, items=None):
        name, ok = QInputDialog.getText(self, "Create playlist", "Playlist name:")
        if not ok or not name.strip():
            return None
        name = name.strip()
        if items is None:
            exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
            files, _ = QFileDialog.getOpenFileNames(self, "Choose files for the playlist", "", f"Media ({exts})")
            items = files
        self.store.create_playlist(name, [str(Path(i)) if not is_url(i) else i for i in items])
        return name

    # ---- menus ----------------------------------------------------------
    def _add_menu(self):
        m = styled_menu(self)
        add(m, "m_folder", "Add folder…", lambda: self._action("add_folder"))
        add(m, "m_network", "Add network stream…", self.add_stream_dialog)
        add(m, "r_queue", "Create playlist…", self.create_playlist_dialog)
        m.exec(self.add_btn.mapToGlobal(QPoint(self.add_btn.width() + 4, 0)))

    def _more_menu(self):
        m = styled_menu(self)
        k = self.loc[0]
        if k == "folder":
            folder = self.loc[1]
            add(m, None, "Play all", lambda: self._play_all())
            add(m, None, "Add folder to playlist…", lambda: self._to_playlist_menu(self._playable()))
            add(m, None, "Show in Explorer", lambda: os.startfile(folder))
        if k in ("videos", "music") or (k == "folder" and self.loc[2] in ("video", "music")):
            kind = "music" if k == "music" or (k == "folder" and self.loc[2] == "music") else "video"
            roots = styled_menu(m, "Library folders")
            m.addMenu(roots)
            for r in self.store.d[f"{kind}_roots"]:
                sub = styled_menu(roots, r)
                roots.addMenu(sub)
                add(sub, None, "Remove from library", lambda _=False, r=r: self.store.remove_root(kind, r))
            add(roots, "add", "Add folder…", lambda: self._action(f"add_{kind}_root"))
        if k == "music":
            add(m, None, "Rescan music tags", self.rescan.emit)
        if k == "playlist":
            add(m, None, "Play playlist", lambda: self._play_all())
            add(m, None, "Delete playlist", lambda: (self.store.delete_playlist(self.loc[1]), self.go(("playlists",))))
        add(m, None, "Refresh", self.refresh)
        m.exec(self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height())))

    def _play_all(self):
        items = self._playable()
        if items:
            self.play_items.emit(items, 0, self.loc[1] if self.loc[0] == "playlist" else "", False)

    def _sort_menu(self):
        m = styled_menu(self)
        for opt in ("Name A→Z", "Name Z→A", "Date modified", "Unwatched first", "Watched first"):
            add(m, "check" if opt == self.sort else None, opt, lambda _=False, o=opt: self._set_sort(o))
        m.exec(self.sort_btn.mapToGlobal(QPoint(0, self.sort_btn.height())))

    def _set_sort(self, opt):
        self.sort = opt
        self.refresh()

    def _toggle_search(self):
        self.search.setVisible(not self.search.isVisible())
        if self.search.isVisible():
            self.search.setFocus()
        else:
            self.search.clear()

    def _to_playlist_menu(self, items, at=None):
        m = styled_menu(self)
        self._fill_playlist_menu(m, items)
        m.exec(at or QCursor.pos())

    def _fill_playlist_menu(self, m, items):
        for n in self.store.playlists():
            add(m, None, n, lambda _=False, n=n: (self.store.add_to_playlist(n, items),
                                                  self.toast.emit(f"Added to \"{n}\"")))
        if self.store.playlists():
            m.addSeparator()
        add(m, "add", "New playlist…", lambda: self.create_playlist_dialog(items))

    def _item_menu(self, pos):
        lst = self.sender() if isinstance(self.sender(), QListWidget) else self.list
        item = lst.itemAt(pos)
        if item is None:
            return
        self.entry_menu(item.data(Qt.UserRole), lst.viewport().mapToGlobal(pos))

    def entry_menu(self, e: Entry, gpos):
        m = styled_menu(self)
        if e.kind in ("file", "stream"):
            add(m, "r_play", "Play", lambda: self.activate(e), color=T.ACCENT)
            add(m, "r_queue", "Add to queue", lambda: (self.enqueue.emit([e.target]), self.toast.emit("Added to queue")))
            pl = styled_menu(m, "Add to playlist")
            m.addMenu(pl)
            self._fill_playlist_menu(pl, [e.target])
            if e.kind == "file":
                add(m, "m_folder", "Show in folder", lambda: self.show_folder(Path(e.target).parent))
            m.addSeparator()
            if self.loc[0] == "playlist":
                add(m, None, "Remove from playlist", lambda: self.store.remove_from_playlist(self.loc[1], e.target))
            elif self.loc[0] in ("home", "recent"):
                add(m, None, "Remove from history", lambda: self.store.forget(e.target))
            if self.loc[0] == "network" and len(self.loc) == 1:
                add(m, None, "Remove stream", lambda: self.store.remove_stream(e.target))
        elif e.kind == "folder":
            path = e.target[1]
            add(m, "m_folder", "Open", lambda: self.go(e.target))
            add(m, "r_play", "Play all", lambda: self._play_folder(path), color=T.ACCENT)
            for kind in ("video", "music"):
                if path in self.store.d[f"{kind}_roots"]:
                    add(m, None, "Remove from library", lambda k=kind: self.store.remove_root(k, path))
        elif e.kind == "playlist":
            name = e.target[1]
            add(m, "r_play", "Play", lambda: self._play_playlist(name), color=T.ACCENT)
            add(m, None, "Delete playlist", lambda: self.store.delete_playlist(name))
        elif e.kind == "nav" and self.loc[0] == "network":
            add(m, None, "Remove list", lambda: self.store.remove_stream(e.target[1]))
        else:
            return
        m.exec(gpos)

    def _play_folder(self, path):
        files = sorted((str(p) for p in Path(path).iterdir() if p.suffix.lower() in MEDIA_EXTS), key=str.lower)
        if files:
            self.play_items.emit(files, 0, "", False)

    def _play_playlist(self, name):
        items = self.store.playlists().get(name, [])
        if items:
            self.play_items.emit(items, 0, name, False)


class LibraryPanel(QFrame, LibraryLogic):
    play_items = Signal(list, int, str, bool)   # items, start index, playlist name, resume now
    enqueue = Signal(list)
    toast = Signal(str)
    rescan = Signal()
    open_full = Signal()
    _fetched = Signal(str, str, list)     # name, url, channels (from a worker thread)

    RAIL = [("home", "home", "Home"), ("videos", "video", "Videos"), ("music", "music", "Music"),
            ("network", "m_network", "Network"), ("playlists", "r_queue", "Playlists"),
            ("recent", "m_recent", "Recent")]

    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self._init_logic(store)
        self.setFixedWidth(330)
        self.setObjectName("library")
        self.setStyleSheet(f"#library {{ background:{PANEL_BG}; border-radius:{T.VIDEO_RADIUS}px; }}"
                           "QLabel { background:transparent; }")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        rail = QVBoxLayout()
        rail.setContentsMargins(4, 8, 4, 8)
        rail.setSpacing(2)
        self.rail_btns = {}
        for key, icon, tip in self.RAIL:
            b = IconButton(icon, tip, size=18, box=32)
            b.clicked.connect(lambda _=False, k=key: self.go((k,)))
            self.rail_btns[key] = b
            rail.addWidget(b)
        add_btn = IconButton("add", "Add item", size=18, box=32)
        add_btn.clicked.connect(self._add_menu)
        self.add_btn = add_btn
        rail.addWidget(add_btn)
        rail.addStretch(1)
        root.addLayout(rail)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background:#232323;")
        root.addWidget(sep)

        body = QVBoxLayout()
        body.setContentsMargins(6, 6, 8, 6)
        body.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(0)
        self.back_btn = IconButton("chevron_left", "Back", size=16, box=28)
        self.fwd_btn = IconButton("chevron_right", "Forward", size=16, box=28)
        self.back_btn.clicked.connect(self.go_back)
        self.fwd_btn.clicked.connect(self.go_forward)
        self.crumb = QLabel()
        self.crumb.setStyleSheet(f"color:{T.TITLE_TEXT}; font-size:13px; padding-left:4px;")
        self.crumb.setCursor(Qt.PointingHandCursor)
        self.crumb.setToolTip("Go up a level")
        self.crumb.mousePressEvent = lambda e: self.go_up()
        self.more_btn = IconButton("more", "More", size=16, box=28)
        self.more_btn.clicked.connect(self._more_menu)
        self.popout_btn = IconButton("popout", "Open the full library (Ctrl+L)", size=16, box=28)
        self.popout_btn.clicked.connect(self.open_full.emit)
        head.addWidget(self.back_btn)
        head.addWidget(self.fwd_btn)
        head.addWidget(self.crumb, 1)
        head.addWidget(self.more_btn)
        head.addWidget(self.popout_btn)
        body.addLayout(head)

        sub = QHBoxLayout()
        sub.setContentsMargins(8, 0, 0, 0)
        self.count = QLabel()
        self.count.setStyleSheet("color:#7a7a7a; font-size:12px;")
        self.sort_btn = IconButton("sort", "Sort", size=16, box=28)
        self.sort_btn.clicked.connect(self._sort_menu)
        self.view_btn = IconButton("playlist", "Show details", size=16, box=28)
        self.view_btn.clicked.connect(self._toggle_details)
        self.search_btn = IconButton("search", "Search", size=16, box=28)
        self.search_btn.clicked.connect(self._toggle_search)
        sub.addWidget(self.count, 1)
        sub.addWidget(self.sort_btn)
        sub.addWidget(self.view_btn)
        sub.addWidget(self.search_btn)
        body.addLayout(sub)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#262626; margin:4px 4px;")
        body.addWidget(line)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search")
        self.search.setStyleSheet("QLineEdit{background:#202020;border:1px solid #2c2c2c;border-radius:6px;"
                                  "color:#ddd;padding:5px 8px;font-size:13px}")
        self.search.textChanged.connect(self.refresh)
        self.search.hide()
        body.addWidget(self.search)

        self.list = QListWidget()
        self.list.setMouseTracking(True)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setItemDelegate(_Delegate(self))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._item_menu)
        self.list.setStyleSheet("""
            QListWidget { background:transparent; border:none; outline:0; }
            QListWidget::item { border:none; }
            QListWidget::item:selected { background:transparent; }
            QScrollBar:vertical { width:6px; background:transparent; }
            QScrollBar::handle:vertical { background:#333; border-radius:3px; }
            QScrollBar::add-line, QScrollBar::sub-line { height:0; }
            QScrollBar::add-page, QScrollBar::sub-page { background:none; }
        """)
        self.list.itemClicked.connect(self._clicked)
        body.addWidget(self.list, 1)
        root.addLayout(body, 1)

        self._fetched.connect(self._stream_fetched)
        self.store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        if not hasattr(self, "list"):
            return
        q = self.search.text().strip().lower()
        entries = self._entries_for(self.loc)
        if q:
            entries = [e for e in entries if e.kind not in ("header", "action") and q in e.label.lower()]
        self._entries = entries
        scroll = self.list.verticalScrollBar().value()
        self.list.clear()
        for e in entries:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, e)
            it.setToolTip(str(e.target) if e.kind in ("file", "stream", "folder") and not isinstance(e.target, tuple)
                          else (e.target[1] if e.kind == "folder" else ""))
            self.list.addItem(it)
        self.list.verticalScrollBar().setValue(scroll)
        n = sum(1 for e in entries if e.kind not in ("header", "action"))
        self.count.setText(f"{n} item{'s' if n != 1 else ''}")
        self.crumb.setText(self._crumb(self.loc))
        self.back_btn.setEnabled(bool(self.back_stack))
        self.fwd_btn.setEnabled(bool(self.fwd_stack))
        active = self._rail_key(self.loc)
        for key, b in self.rail_btns.items():
            col = T.ACCENT if key == active else T.ICON
            b._normal = pixmap(b._name, col, b._size, accent=col)
            b.setIcon(b._normal)

    def _toggle_details(self):
        self.details = not self.details
        self.view_btn.setToolTip("Hide details" if self.details else "Show details")
        self.list.viewport().update()
