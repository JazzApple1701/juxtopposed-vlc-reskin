"""VLC Reskin: Juxtopposed's "VLC Redesign" Figma design (CC BY 4.0) applied as a new
interface on top of VLC. PySide6 draws the UI; libVLC (VideoLAN) does all the playback."""

import json
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QPushButton, QToolTip, QVBoxLayout, QWidget,
)

import vlc

import theme as T
from icons import pixmap
from library import AUDIO_EXTS, LibraryPanel
from library_page import LibraryPage
from thumbnails import Thumbnailer
from library_store import DEFAULT_FILE as LIBRARY_FILE, LibraryStore, MusicIndexer, is_url
from menus import TracksPopup, add, styled_menu, submenu
from mousehook import LeftClickHook, window_is_under
from scrub import ScrubPreview, Storyboard
from credits import AboutDialog
from osd import PlayPauseFlash
import prefs as P
from prefs_panel import PrefsPanel
from music_view import find_folder_cover
from waveform import WaveformLoader
from widgets import ControlBar, TitleBar, VideoSurface, fmt_time

MEDIA_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg", ".ts", ".3gp",
    ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma",
}
SUB_EXTS = "*.srt *.ass *.ssa *.vtt *.sub *.idx *.smi"
RESIZE_MARGIN = 6
SKIP_MS = 15_000
HOVER_ZONE = 16       # extra px beyond a bar's height that still reveals it
RECENT_MAX = 15
BASE_ARGS = ["--quiet", "--no-video-title-show"]

SHORTCUTS = [
    ("Space", "Play / Pause"), ("S", "Stop"), ("N / P", "Next / Previous item"),
    ("← / →", "Back / forward 15 s"), ("↑ / ↓", "Volume up / down"), ("M", "Mute"),
    ("V", "Cycle subtitle track"), ("F / F11", "Fullscreen"), ("Esc", "Leave fullscreen"),
    ("Ctrl + \\", "Hide / show UI"), ("L", "Library sidebar"), ("Ctrl + O", "Open file(s)"),
    ("Ctrl + F", "Open folder"), ("Ctrl + N", "Open network stream"), ("Ctrl + D", "Open disc"),
    ("Ctrl + C", "Open capture device"), ("Ctrl + P", "Preferences"), ("Shift + F1", "About"),
    ("Ctrl + Q", "Quit"),
]


def _text(b) -> str:
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)


class BarOverlay(QWidget):
    """Floating window that holds the title bar or control bar while the UI is
    hidden (fullscreen or Hide UI). It has to be its own top-level window:
    libVLC draws into a native child window that ordinary widgets can't cover."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("overlay")
        self.setStyleSheet(f"#overlay {{ background:{T.SHELL}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

    def hold(self, w: QWidget):
        self.layout().addWidget(w)
        w.show()


class ResumePrompt(QWidget):
    """"Continue from 12:34?" shown just above the play controls (the video's
    point: the old prompt sat far from where you're looking)."""

    def __init__(self, player_window):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.win = player_window
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._at = 0
        card = QWidget(self)
        card.setObjectName("card")
        card.setStyleSheet("#card{background:#1c1c1c;border:1px solid #2c2c2c;border-radius:10px}"
                           "QLabel{color:#cfcfcf;font-size:13px;background:transparent}")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        self.label = QLabel()
        go = QPushButton("Continue")
        go.setCursor(Qt.PointingHandCursor)
        go.setStyleSheet(f"QPushButton{{background:{T.ACCENT};color:#1b1b1b;border:none;border-radius:6px;"
                         "padding:5px 14px;font-size:13px}} QPushButton:hover{{background:#e58a2a}}")
        go.clicked.connect(self._continue)
        no = QPushButton("✕")
        no.setCursor(Qt.PointingHandCursor)
        no.setFixedSize(26, 26)
        no.setStyleSheet("QPushButton{background:transparent;color:#8a8a8a;border:none;border-radius:5px}"
                         "QPushButton:hover{background:#2a2a2a;color:#ddd}")
        no.clicked.connect(self.hide)
        lay.addWidget(self.label)
        lay.addWidget(go)
        lay.addWidget(no)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.timer = QTimer(self, singleShot=True, interval=10_000, timeout=self.hide)

    def offer(self, at_ms: int):
        self._at = at_ms
        self.label.setText(f"Continue from {fmt_time(at_ms)}?")
        self.adjustSize()
        c = self.win.controls
        anchor = c.mapToGlobal(QPoint(c.play_btn.x(), 0)) if c.isVisible() else \
            self.win.mapToGlobal(QPoint(20, self.win.height() - T.CONTROLS_H))
        self.move(anchor.x() - 8, anchor.y() - self.height() - 10)
        self.show()
        self.raise_()
        self.timer.start()

    def _continue(self):
        self.win.player.set_time(self._at)
        self.hide()


class PlayerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("VLC Reskin")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(760, 440)
        self.resize(1280, 720)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setObjectName("root")
        self.setStyleSheet(f"""
            #root {{ background:{T.SHELL}; }}
            QLabel {{ font-family:{T.FONT_FAMILY}; }}
            QToolTip {{ background:#262626; color:#ddd; border:1px solid #3a3a3a; padding:4px 6px; }}
        """)
        # Storage keeps its original name so settings survive the rename to "VLC Reskin".
        self.settings = QSettings("VLCRedesign", "player")
        self.state = dict(P.DEFAULTS)
        try:
            self.state.update(json.loads(self.settings.value("prefs_state", "{}") or "{}"))
        except ValueError:
            pass
        self.presets = P.PresetStore(self.settings)

        self.title_bar = TitleBar(self)
        self.surface = VideoSurface()
        self.controls = ControlBar()
        self.store = LibraryStore(LIBRARY_FILE)
        self.indexer = MusicIndexer(self.store)
        self.library = LibraryPanel(self.store)
        self.library.hide()
        self.thumbnailer = Thumbnailer()
        self.library_page = LibraryPage(self.store, self.thumbnailer)
        self.library_page.hide()
        if self.state.get("home_style") not in P.HOME_STYLES:   # e.g. the old name "Word-style"
            self.state["home_style"] = P.DEFAULTS["home_style"]
        self.library_page.home_style = self.state["home_style"]
        self.library_mode = False
        self.resume_prompt = ResumePrompt(self)
        self.tracks_popup = TracksPopup(self)
        self.prefs_panel = PrefsPanel(self.state, self.presets)
        self.prefs_panel.hide()

        self.body = QWidget()
        self.body_lay = QHBoxLayout(self.body)
        self.body_lay.setContentsMargins(T.FRAME_MARGIN, 0, T.FRAME_MARGIN, 0)
        self.body_lay.setSpacing(T.FRAME_MARGIN)
        self.body_lay.addWidget(self.library)
        self.body_lay.addWidget(self.surface, 1)
        self.body_lay.addWidget(self.prefs_panel)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(0)
        self.root.addWidget(self.title_bar)
        self.root.addWidget(self.body, 1)
        self.root.addWidget(self.controls)
        self.root.addWidget(self.library_page, 1)

        self.top_overlay = BarOverlay()
        self.bottom_overlay = BarOverlay()
        self.overlay_mode = False
        self.ui_hidden = False

        # libVLC
        self._muted = False
        self._engine_args = P.engine_args(self.state)
        self._make_engine()

        self.playlist: list[Path | str] = []    # local files (Path) and stream URLs (str)
        self.index = -1
        self.current: Path | None = None
        self._repeat = False
        self._last_cursor = QPoint()
        self._idle_ms = 0
        # One click on the video pauses; wait briefly in case it's the first half of a double-click.
        self._click_timer = QTimer(self, singleShot=True, timeout=self._click_pause,
                                   interval=min(QApplication.doubleClickInterval(), 300))
        self.storyboard = Storyboard()
        self.scrub = ScrubPreview()
        self.flash = PlayPauseFlash()
        self._slaves: list[str] = []          # subtitle files added to the current media
        self._restore = None                  # state to restore after an engine restart
        self._new_media = False               # apply per-file defaults once it starts
        self._markers_dirty = True
        self._stop_after_current = False
        self.music_mode = False
        self._meta_tries = 0
        self.waves = WaveformLoader()
        self.waves.ready.connect(self._wave_ready)
        self.sleep_timer = QTimer(self, singleShot=True, timeout=self._sleep_fired)
        self.engine_timer = QTimer(self, singleShot=True, interval=700, timeout=self._rebuild_engine)
        self.save_timer = QTimer(self, singleShot=True, interval=600,
                                 timeout=lambda: self.settings.setValue("prefs_state", json.dumps(self.state)))

        self._wire()
        self._shortcuts()
        self._music_roots = list(self.store.d["music_roots"])
        self._auto_resume = False
        self._ticks = 0
        QTimer.singleShot(1500, self.indexer.scan)

        self.timer = QTimer(self, interval=200, timeout=self._tick)
        self.timer.start()
        self.hover_timer = QTimer(self, interval=50, timeout=self._hover_tick)
        QApplication.instance().installEventFilter(self)
        self.click_hook = LeftClickHook(lambda x, y: QTimer.singleShot(0, lambda: self._video_press(x, y)))

    # ---- wiring ---------------------------------------------------------
    def _wire(self):
        tb, c = self.title_bar, self.controls
        tb.min_btn.clicked.connect(self.showMinimized)
        tb.max_btn.clicked.connect(self.toggle_maximize)
        tb.fs_btn.clicked.connect(self.toggle_fullscreen)
        tb.close_btn.clicked.connect(self.close)
        tb.more_btn.clicked.connect(self._show_more_menu)
        tb.library_clicked.connect(self.toggle_library)

        c.play_btn.clicked.connect(self.toggle_play)
        c.prev_btn.clicked.connect(lambda: self.step(-1))
        c.next_btn.clicked.connect(lambda: self.step(1))
        c.back_btn.clicked.connect(lambda: self.skip(-SKIP_MS))
        c.fwd_btn.clicked.connect(lambda: self.skip(SKIP_MS))
        c.seek.seek.connect(self._seek_to)
        c.volume.changed.connect(self._set_volume)
        c.vol_btn.clicked.connect(self.toggle_mute)
        c.eq_btn.clicked.connect(lambda: self.tracks_popup.open_at(c.eq_btn, "audio"))
        c.sub_btn.clicked.connect(lambda: self.tracks_popup.open_at(c.sub_btn, "subtitles"))
        c.settings_btn.clicked.connect(lambda: self.show_preferences())
        c.playlist_btn.clicked.connect(self._show_playlist_menu)

        self.library.play_items.connect(self._play_items)
        self.library.enqueue.connect(self._enqueue)
        self.library.toast.connect(lambda t: self.toast(self.library.crumb, t))
        self.title_bar.menu_clicked.connect(self.toggle_menu)
        self.controls.seek.hovered.connect(self._scrub_hover)
        self.controls.seek.hover_left.connect(self.scrub.hide)
        self.storyboard.updated.connect(self._scrub_refresh)
        self.library_page.back_requested.connect(self.exit_library)
        self.library_page.command.connect(self._page_command)
        self.library.open_full.connect(lambda: self.enter_library(self.library.loc))
        pg = self.library_page
        pg.play_items.connect(self._play_from_page)
        pg.enqueue.connect(self._enqueue)
        pg.toast.connect(lambda t: self.toast(pg.search, t))
        pg.rescan.connect(self.indexer.scan)
        pg.mini.open_player.connect(self.exit_library)
        pg.mini.show_queue.connect(self._show_mini_queue)
        pg.mini.close_media.connect(self.close_media)
        self.indexer.done.connect(lambda n: pg.refresh())
        self.library.rescan.connect(self.indexer.scan)
        self.indexer.done.connect(lambda n: self.library.refresh())
        self.store.changed.connect(self._store_changed)
        self.prefs_panel.changed.connect(self._pref_changed)
        self.prefs_panel.preset_chosen.connect(self._choose_preset)
        self.prefs_panel.preset_saved.connect(self._save_preset)
        self.prefs_panel.advanced.connect(
            lambda: self.toast(self.prefs_panel, "The full settings window is a later screen"))

    def _shortcuts(self):
        keys = {
            "Space": self.toggle_play,
            "S": self.stop,
            "Ctrl+O": self.open_dialog,
            "Ctrl+F": self.open_folder,
            "Ctrl+N": self.open_url,
            "Ctrl+D": self.open_disc,
            "Ctrl+C": self.open_capture,
            "Ctrl+P": lambda: self.show_preferences(),
            "Shift+F1": self.about,
            "F": self.toggle_fullscreen,
            "F11": self.toggle_fullscreen,
            "Escape": self._escape,
            "Ctrl+L": self.toggle_full_library,
            "Ctrl+\\": self.toggle_hide_ui,
            "L": self.toggle_library,
            "Left": lambda: self.skip(-SKIP_MS),
            "Right": lambda: self.skip(SKIP_MS),
            "Up": lambda: self.controls.volume.set_value(self.controls.volume.value() + 5),
            "Down": lambda: self.controls.volume.set_value(self.controls.volume.value() - 5),
            "M": self.toggle_mute,
            "V": self.cycle_subtitles,
            "N": lambda: self.step(1),
            "P": lambda: self.step(-1),
            "Ctrl+Q": self.close,
        }
        for seq, fn in keys.items():
            # Application-wide so they still work after clicking a floating bar.
            QShortcut(QKeySequence(seq), self, activated=fn, context=Qt.ApplicationShortcut)

    # ---- opening media --------------------------------------------------
    def open_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
        paths, _ = QFileDialog.getOpenFileNames(self, "Open file(s)", "", f"Media ({exts});;All files (*)")
        if len(paths) == 1:
            self.open_path(Path(paths[0]))
        elif paths:
            self.playlist = [Path(p) for p in paths]
            self.play_index(0)

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open folder")
        if not d:
            return
        files = sorted((p for p in Path(d).iterdir() if p.suffix.lower() in MEDIA_EXTS), key=lambda p: p.name.lower())
        self.library.show_folder(Path(d))
        if files:
            self.playlist = files
            self.play_index(0)
        else:
            self.toast(self.title_bar.crumb, "No media files in that folder")

    def open_url(self, url: str | None = None):
        if url is None:
            url, ok = QInputDialog.getText(self, "Open network stream", "URL:")
            if not ok:
                return
        url = url.strip()
        if url:
            self.playlist = [url]
            self.play_index(0)

    def open_disc(self):
        self.playlist, self.index, self.current = [], -1, None
        self._play_mrl("dvd://", "Disc", "Disc")

    def open_capture(self):
        self.playlist, self.index, self.current = [], -1, None
        self._play_mrl("dshow://", "Capture device", "Capture")

    def open_path(self, path: Path):
        """Play `path` and queue the other media files in its folder for prev/next."""
        path = Path(path)
        try:
            siblings = sorted((p for p in path.parent.iterdir() if p.suffix.lower() in MEDIA_EXTS),
                              key=lambda p: p.name.lower())
        except OSError:
            siblings = []
        if path not in siblings:
            siblings.append(path)
        self.playlist = siblings
        self.play_index(siblings.index(path))

    def play_index(self, i: int):
        if 0 <= i < len(self.playlist):
            self._save_position()
            self.index = i
            p = self.playlist[i]
            if isinstance(p, str):                       # network stream
                self.current = None
                name = self._stream_name(p)
                self._play_mrl(p, name, "Network")
                self.store.record_play(p, "stream", name)
                self.library.set_current(p)
                self.library_page.set_current(p)
                return
            self.current = p
            bound = self.presets.for_folder(p.parent)
            if bound and bound != self.prefs_panel.current_preset:
                self._choose_preset(bound, bind=False)
            self._play_mrl(str(p), p.stem, p.parent.name or str(p.parent))
            self.store.record_play(str(p), "audio" if p.suffix.lower() in AUDIO_EXTS else "video", p.stem)
            self.library.set_current(str(p))
            self.library_page.set_current(str(p))

    def _stream_name(self, url: str) -> str:
        for s in self.store.d["streams"]:
            if s["url"] == url:
                return s["name"]
            for c in s.get("channels", []):
                if c["url"] == url:
                    return c["name"]
        return url.rstrip("/").rsplit("/", 1)[-1] or url

    def _item_label(self, item) -> str:
        return item.name if isinstance(item, Path) else self._stream_name(item)

    def _media_key(self) -> str | None:
        """History key of what's playing: the file path or the stream URL."""
        if self.current is not None:
            return str(self.current)
        if 0 <= self.index < len(self.playlist) and isinstance(self.playlist[self.index], str):
            return self.playlist[self.index]
        return None

    def _save_position(self, save=True):
        key = self._media_key()
        length = self.player.get_length()
        # Until the new file has really started, libVLC can still report the previous one's time.
        if self._new_media or self._restore:
            return
        if key and length > 0 and self.player.get_state() in (vlc.State.Playing, vlc.State.Paused):
            self.store.record_position(key, self.player.get_time(), length, save=save)

    def _play_items(self, items, start, playlist_name, resume):
        local = [Path(i) for i in items if not is_url(i)]
        if len(items) == 1 and local:
            self._auto_resume = resume
            self.open_path(local[0])
            return
        self.playlist = [i if is_url(i) else Path(i) for i in items]
        if playlist_name:
            self.store.record_playlist_play(playlist_name)
        self._auto_resume = resume
        self.play_index(start)

    def _enqueue(self, items):
        self.playlist += [i if is_url(i) else Path(i) for i in items]
        if self.player.get_media() is None:
            self.play_index(len(self.playlist) - len(items))

    def _store_changed(self):
        roots = list(self.store.d["music_roots"])
        if roots != self._music_roots:
            self._music_roots = roots
            self.indexer.scan()

    def _play_mrl(self, mrl, title, crumb):
        self.resume_prompt.hide()
        self._slaves = []
        self._new_media = True
        self._markers_dirty = True
        self.controls.seek.set_markers([])
        self.player.set_media(self.vlc.media_new(mrl))
        self.player.play()
        self.controls.seek.set_peaks([])
        self.scrub.hide()
        if self.current is not None and str(self.current) == mrl and self.current.suffix.lower() not in AUDIO_EXTS:
            self.storyboard.request(self.current)     # frames for the scrub preview
        else:
            self.storyboard.cancel()
        is_audio = self.current is not None and self.current.suffix.lower() in AUDIO_EXTS and str(self.current) == mrl
        self._set_music_mode(is_audio)
        if is_audio:
            self.surface.music_view.set_track(title, "", find_folder_cover(self.current))
            self._meta_tries = 25            # read tags / embedded art for the first ~5 s
        if self.state["waveform"] and self.current is not None and str(self.current) == mrl:
            self.waves.request(self.current)
        self.title_bar.set_title(title)
        self.title_bar.crumb.setText(crumb)
        self.setWindowTitle(f"{title} - VLC Reskin")

    # ---- transport ------------------------------------------------------
    def step(self, d: int):
        if self.playlist:
            self.play_index((self.index + d) % len(self.playlist))

    def toggle_play(self):
        if self.player.get_media() is None:
            self.open_dialog()
        elif self.player.get_state() in (vlc.State.Ended, vlc.State.Stopped):
            self.player.stop()
            self.player.play()
            self._flash("play")
        else:
            was_playing = self.player.is_playing()
            self.player.pause()
            self._flash("pause" if was_playing else "play")

    def _flash(self, icon: str):
        """Brief play / pause symbol in the middle of the video, like VLC's."""
        if self.library_mode or not self.surface.isVisible():
            return
        s = self.surface
        self.flash.flash(icon, s.mapToGlobal(s.rect().center()))

    def stop(self):
        self.player.stop()

    def skip(self, ms: int):
        if self.player.is_seekable():
            length = self.player.get_length()
            t = max(0, self.player.get_time() + ms)
            self.player.set_time(min(t, length - 500) if length > 0 else t)

    def _seek_to(self, frac: float):
        if self.player.is_seekable():
            self.player.set_position(frac)

    def _set_volume(self, v: int):
        self._muted = False
        self.player.audio_set_mute(False)
        self.player.audio_set_volume(v)
        self._update_volume_icon()

    def toggle_mute(self):
        self._muted = not self._muted
        self.player.audio_set_mute(self._muted)
        self._update_volume_icon()

    def _update_volume_icon(self):
        v = self.controls.volume.value()
        name = "volume_mute" if self._muted or v == 0 else "volume_low" if v < 40 else "volume"
        self.controls.vol_btn.set_icon(name)

    def set_rate(self, r: float):
        self.player.set_rate(r)

    # ---- tracks (used by TracksPopup and the right-click menu) ---------
    def audio_tracks(self):
        items = [(i, "None" if i == -1 else _text(n)) for i, n in (self.player.audio_get_track_description() or [])]
        return items, self.player.audio_get_track(), self.player.audio_set_track

    def subtitle_tracks(self):
        items = [(i, "None" if i == -1 else _text(n)) for i, n in (self.player.video_get_spu_description() or [])]
        return items, self.player.video_get_spu(), self.player.video_set_spu

    def video_tracks(self):
        items = [(i, "None" if i == -1 else _text(n)) for i, n in (self.player.video_get_track_description() or [])]
        return items, self.player.video_get_track(), self.player.video_set_track

    def audio_devices(self):
        out = []
        head = self.player.audio_output_device_enum()
        node = head
        while node:
            d = node.contents
            out.append((_text(d.device), _text(d.description)))
            node = d.next
        if head:
            vlc.libvlc_audio_output_device_list_release(head)
        cur = self.player.audio_output_device_get()
        # An empty id is libVLC's "Default" device, which is what's in use when none was picked.
        return out, _text(cur) if cur else "", lambda dev: self.player.audio_output_device_set(None, dev)

    def add_subtitle_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add subtitle file",
                                              str(self.current.parent) if self.current else "",
                                              f"Subtitles ({SUB_EXTS});;All files (*)")
        if path:
            self._add_sub(QUrl.fromLocalFile(path).toString())

    def cycle_subtitles(self):
        items, cur, setter = self.subtitle_tracks()
        if not items:
            self.toast(self.controls.sub_btn, "No subtitle tracks in this file")
            return
        ids = [i for i, _ in items]
        nxt = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ids[0]
        setter(nxt)
        self.toast(self.controls.sub_btn, f"Subtitles: {dict(items)[nxt]}")

    def _add_sub(self, uri: str):
        self._slaves.append(uri)
        self._markers_dirty = True
        self.player.add_slave(vlc.MediaSlaveType.subtitle, uri, True)

    # ---- preferences sidebar -------------------------------------------
    def show_preferences(self, tab=None):
        """Open the sidebar (on `tab` if given); toggles it when no tab is asked for."""
        if tab is None and self.prefs_panel.isVisible():
            self.prefs_panel.hide()
            return
        self.prefs_panel.show_tab(tab or self.prefs_panel.tab)
        self.prefs_panel.show()

    def _pref_changed(self, key):
        self.save_timer.start()
        if key == "home_style":
            self.library_page.home_style = self.state["home_style"]
            self.library_page.refresh()
        elif key == "start_on_home":
            pass                                # read at the next launch
        elif key == "waveform":
            if self.state["waveform"] and self.current:
                self.waves.request(self.current)
            else:
                self.controls.seek.set_peaks([])
        elif key in P.ENGINE_KEYS:
            self.engine_timer.start()          # debounced: sliders fire many times
        elif key == "sleep":
            self._arm_sleep()
        elif key == "sub_timeline":
            self._markers_dirty = True
            if not self.state["sub_timeline"]:
                self.controls.seek.set_markers([])
        elif key in ("audio_default", "audio_lang", "sub_default", "sub_lang"):
            pass                                # used when the next file starts
        else:
            P.apply_live(self.player, self.state, key)
            if key == "sub_delay":
                self._markers_dirty = True

    def _load_state(self, values: dict):
        keep = {k: self.state[k] for k in P.APP_KEYS if k in self.state}   # app-wide, not per show
        self.state.clear()
        self.state.update(P.DEFAULTS)
        self.state.update({k: v for k, v in values.items() if k not in P.APP_KEYS})
        self.state.update(keep)
        self.prefs_panel.rebuild()
        P.apply_live(self.player, self.state)
        if P.engine_args(self.state) != self._engine_args:
            self._rebuild_engine()
        self.save_timer.start()

    def _choose_preset(self, name, bind=True):
        if name:
            values = self.presets.get(name)
            if values is None:
                return
            self.prefs_panel.current_preset = name
            self._load_state(values)
        else:
            self.prefs_panel.current_preset = ""
            self.prefs_panel._fill_presets()
        if bind and self.current:
            self.presets.bind(self.current.parent, name or None)

    def _save_preset(self, name):
        folder = self.current.parent if self.current else None
        self.presets.save(name, {k: v for k, v in self.state.items() if k not in P.APP_KEYS}, folder)
        self.prefs_panel.current_preset = name
        self.prefs_panel._fill_presets()
        where = f' and linked to "{folder.name}"' if folder else ""
        self.toast(self.prefs_panel.save_btn, f'Saved preset "{name}"{where}')

    def _arm_sleep(self):
        self.sleep_timer.stop()
        self._stop_after_current = False
        minutes = P.SLEEP.get(self.state["sleep"], 0)
        if minutes > 0:
            self.sleep_timer.start(minutes * 60_000)
        elif minutes < 0:
            self._stop_after_current = True

    def _sleep_fired(self):
        self.player.set_pause(1)
        self.state["sleep"] = "Off"
        self.prefs_panel.rebuild()
        self.toast(self.controls.play_btn, "Sleep timer: paused")

    # ---- engine ---------------------------------------------------------
    def _make_engine(self):
        self.vlc = vlc.Instance(BASE_ARGS + self._engine_args)
        self.player = self.vlc.media_player_new()
        self.player.set_hwnd(int(self.surface.canvas.winId()))
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)
        self.player.audio_set_volume(self.controls.volume.value())
        self.player.audio_set_mute(self._muted)
        P.apply_live(self.player, self.state)

    def _rebuild_engine(self):
        """Restart libVLC with the current engine options, keeping the media,
        position, pause state and chosen tracks."""
        args = P.engine_args(self.state)
        if args == self._engine_args:
            return
        media = self.player.get_media()
        restore = None
        if media is not None and self.player.get_state() not in (vlc.State.Stopped, vlc.State.Ended):
            restore = {"mrl": media.get_mrl(), "time": self.player.get_time(),
                       "paused": self.player.get_state() == vlc.State.Paused,
                       "audio": self.player.audio_get_track(), "spu": self.player.video_get_spu()}
        self.player.stop()
        self.player.release()
        self.vlc.release()
        self._engine_args = args
        self._make_engine()
        if restore:
            self._restore = restore
            self.player.set_media(self.vlc.media_new(restore["mrl"]))
            self.player.play()
            for uri in self._slaves:
                self.player.add_slave(vlc.MediaSlaveType.subtitle, uri, True)

    def _after_start(self):
        """Runs once a file (or a restarted engine) is actually playing."""
        p = self.player
        if self._new_media and not self._restore:
            key = self._media_key()
            at = self.store.resume_point(key) if key else 0
            if at and self._auto_resume:
                p.set_time(at)
            elif at:
                self.resume_prompt.offer(at)
            self._auto_resume = False
        if self._restore:
            r, self._restore = self._restore, None
            if r["time"] > 0:
                p.set_time(r["time"])
            p.audio_set_track(r["audio"])
            if r["spu"] != -1 or self._slaves:
                p.video_set_spu(r["spu"])
            if r["paused"]:
                p.set_pause(1)
            P.apply_live(p, self.state)
            return
        if self._new_media:
            self._new_media = False
            P.apply_live(p, self.state)          # delays reset with every new file
            # Audio-only files with a video extension (e.g. .mp4 podcasts) also get the music view.
            if not self.music_mode and p.has_vout() == 0 and self.audio_tracks()[0] and self.current:
                self._set_music_mode(True)
                self.surface.music_view.set_track(self.current.stem, "", find_folder_cover(self.current))
                self._meta_tries = 25
            a = P.pick_default_track(self.audio_tracks()[0], self.state["audio_default"], self.state["audio_lang"])
            if a is not None:
                p.audio_set_track(a)
            s = P.pick_default_track(self.subtitle_tracks()[0], self.state["sub_default"], self.state["sub_lang"])
            if s is not None:
                p.video_set_spu(s)

    # ---- scrub preview ------------------------------------------------
    def _scrub_hover(self, frac: float, x: float):
        length = self.player.get_length()
        if length <= 0 or not self.player.is_seekable():
            self.scrub.hide()
            return
        self._scrub_at = (frac, x)
        img = None
        if not self.music_mode and self.current is not None and self.storyboard.path == str(self.current):
            img = self.storyboard.frame_for(frac)
        seek = self.controls.seek
        g = seek.mapToGlobal(QPoint(int(x), 0))
        self.scrub.show_at(g.x(), g.y() - 8, img, fmt_time(int(frac * length)))

    def _scrub_refresh(self):
        """New storyboard frames arrived: update the bubble if it's showing."""
        if self.scrub.isVisible() and getattr(self, "_scrub_at", None):
            self._scrub_hover(*self._scrub_at)

    # ---- music ----------------------------------------------------------
    def _set_music_mode(self, on: bool):
        self.music_mode = on
        self.surface.set_music(on)
        # The music frame adds 15 s skip buttons around play; the video frame doesn't.
        self.controls.back_btn.setVisible(on)
        self.controls.fwd_btn.setVisible(on)

    def _wave_ready(self, path, peaks):
        if self.current and path == str(self.current) and self.state["waveform"]:
            self.controls.seek.set_peaks(peaks)

    def _read_music_meta(self):
        """Title / artist / cover from the file's tags. libVLC fills these in
        (and extracts embedded art to its cache) shortly after playback starts."""
        self._meta_tries -= 1
        media = self.player.get_media()
        if media is None or self.current is None:
            return
        title = media.get_meta(vlc.Meta.Title) or self.current.stem
        if title == self.current.name:       # untagged files report the file name
            title = self.current.stem
        artist = media.get_meta(vlc.Meta.Artist) or ""
        art = media.get_meta(vlc.Meta.ArtworkURL) or ""
        cover = None
        if art.startswith("file:"):
            cover = Path(QUrl(art).toLocalFile())
        if cover is None or not cover.exists():
            cover = find_folder_cover(self.current)
        mv = self.surface.music_view
        if (title, artist) != (mv._title, mv._artist) or (cover and not mv.has_cover()):
            mv.set_track(title, artist, cover)
            self.title_bar.set_title(title)
            self.setWindowTitle(f"{title} - VLC Reskin")
        if cover and cover.exists() and art.startswith("file:"):
            self._meta_tries = 0             # embedded art found; nothing more to wait for

    def _update_markers(self, length_ms):
        self._markers_dirty = False
        if not self.state["sub_timeline"] or length_ms <= 0:
            self.controls.seek.set_markers([])
            return
        files = [Path(QUrl(u).toLocalFile()) for u in self._slaves if QUrl(u).isLocalFile()]
        if self.current:
            files += [self.current.with_suffix(ext) for ext in (".srt", ".vtt")]
        cues = []
        for f in dict.fromkeys(files):
            if f.exists() and f.suffix.lower() in (".srt", ".vtt"):
                cues += P.subtitle_cues(f)
        shift = self.state["sub_delay"]
        total = length_ms / 1000
        self.controls.seek.set_markers([((a + shift) / total, (b + shift) / total) for a, b in cues])

    # ---- periodic UI sync ----------------------------------------------
    def _tick(self):
        p, c = self.player, self.controls
        state = p.get_state()
        c.play_btn.set_playing(state in (vlc.State.Playing, vlc.State.Opening, vlc.State.Buffering))
        length = p.get_length()
        c.cur.setText(fmt_time(p.get_time()) if state != vlc.State.Stopped else "00:00:00")
        c.dur.setText(fmt_time(length) if length > 0 else "00:00:00")
        c.seek.set_position(p.get_position() if length > 0 and state != vlc.State.Stopped else 0.0)
        if self.library_mode:
            self._update_mini()
        self.surface.show_video(not self.music_mode and p.has_vout() > 0
                                and state not in (vlc.State.Stopped, vlc.State.Ended))
        if self.music_mode and self._meta_tries > 0 and state == vlc.State.Playing:
            self._read_music_meta()

        if (self._restore or self._new_media) and state == vlc.State.Playing and p.get_time() > 300:
            self._after_start()
        if self._markers_dirty and length > 0:
            self._update_markers(length)

        # Remember where we are (in memory every second, on disk every 30 s).
        self._ticks += 1
        if state == vlc.State.Playing and self._ticks % 5 == 0:
            self._save_position(save=self._ticks % 150 == 0)
        if self.music_mode and self.current is not None and self._meta_tries == 1:
            self.store.set_meta(str(self.current), self.surface.music_view._title, self.surface.music_view._artist)

        if state == vlc.State.Ended and self._media_key():
            length = self.store.d["history"].get(self._media_key(), {}).get("length", 0)
            if length:
                self.store.record_position(self._media_key(), length, length, save=False)

        if state == vlc.State.Ended:
            if self._stop_after_current:
                self._stop_after_current = False
                self.state["sleep"] = "Off"
                self.prefs_panel.rebuild()
            elif self._repeat:
                p.stop()
                p.play()
            elif self.playlist and self.index < len(self.playlist) - 1:
                self.step(1)

    def _hover_tick(self):
        """While the UI is hidden: show a bar only while the cursor is near it."""
        area = self.geometry()
        pos = QCursor.pos()
        busy = QApplication.activePopupWidget() is not None or self.controls.seek._dragging \
            or self.tracks_popup.isVisible()
        if not busy:
            inside = area.contains(pos)
            self._set_overlay(self.top_overlay, inside and pos.y() < area.top() + T.TITLE_H + HOVER_ZONE)
            self._set_overlay(self.bottom_overlay, inside and pos.y() > area.bottom() - T.CONTROLS_H - HOVER_ZONE)

        # In fullscreen, hide the cursor after 2.5 s without movement.
        if self.isFullScreen():
            if pos != self._last_cursor:
                self._last_cursor = pos
                self._idle_ms = 0
                self.unsetCursor()
            else:
                self._idle_ms += self.hover_timer.interval()
                if self._idle_ms > 2500 and not self.top_overlay.isVisible() and not self.bottom_overlay.isVisible():
                    self.setCursor(Qt.BlankCursor)

    def _video_press(self, x: int, y: int):
        """Left press anywhere on screen (physical px), from the mouse hook:
        two quick presses on the playing video toggle fullscreen; in the full
        library one press on the mini player's video opens the player."""
        if not self.surface.canvas.isVisible() or not self.isActiveWindow():
            return
        dpr = self.screen().devicePixelRatio()
        pt = QPoint(round(x / dpr), round(y / dpr))
        if not QRect(self.surface.canvas.mapToGlobal(QPoint(0, 0)), self.surface.canvas.size()).contains(pt):
            return
        if not window_is_under(x, y, int(self.surface.canvas.winId())):
            return                                 # a menu or floating bar was clicked, not the video
        self._video_click()

    def _video_click(self, double=False):
        """Click on the video: pause / play. Double-click: fullscreen."""
        if self.library_mode:
            self.exit_library()
            return
        if double or self._click_timer.isActive():
            self._click_timer.stop()
            self.toggle_fullscreen()
        else:
            self._click_timer.start()

    def _click_pause(self):
        if self.player.get_media() is not None:
            self.toggle_play()

    def _set_overlay(self, ov: BarOverlay, show: bool):
        if show == ov.isVisible():
            return
        if show:
            area = self.geometry()
            if ov is self.top_overlay:
                ov.setGeometry(QRect(area.left(), area.top(), area.width(), T.TITLE_H))
            else:
                ov.setGeometry(QRect(area.left(), area.bottom() - T.CONTROLS_H + 1, area.width(), T.CONTROLS_H))
            ov.show()
            ov.raise_()
        else:
            ov.hide()

    # ---- hidden UI: fullscreen and Hide UI ------------------------------
    def _enter_overlay_mode(self):
        if self.overlay_mode:
            return
        self.overlay_mode = True
        self.top_overlay.hold(self.title_bar)
        self.bottom_overlay.hold(self.controls)
        self.top_overlay.hide()
        self.bottom_overlay.hide()
        self.hover_timer.start()

    def _leave_overlay_mode(self):
        if not self.overlay_mode:
            return
        self.overlay_mode = False
        self.hover_timer.stop()
        self.top_overlay.hide()
        self.bottom_overlay.hide()
        self.root.insertWidget(0, self.title_bar)
        self.root.insertWidget(2, self.controls)
        self.title_bar.show()
        self.controls.show()
        self.unsetCursor()

    def _apply_margins(self):
        if self.isFullScreen():
            self.body_lay.setContentsMargins(0, 0, 0, 0)
        elif self.ui_hidden:
            m = T.FRAME_MARGIN
            self.body_lay.setContentsMargins(m, m, m, m)
        else:
            self.body_lay.setContentsMargins(T.FRAME_MARGIN, 0, T.FRAME_MARGIN, 0)

    def toggle_hide_ui(self):
        if self.library_mode:
            self.exit_library()
        self.ui_hidden = not self.ui_hidden
        if self.ui_hidden:
            self._enter_overlay_mode()
        elif not self.isFullScreen():
            self._leave_overlay_mode()
        self._apply_margins()

    def toggle_fullscreen(self):
        if self.library_mode:
            self.exit_library()
        if self.isFullScreen():
            self.showNormal()
            if not self.ui_hidden:
                self._leave_overlay_mode()
            self.title_bar.fs_btn.set_icon("fullscreen")
        else:
            self._enter_overlay_mode()
            self.showFullScreen()
            self._idle_ms = 0
            self.title_bar.fs_btn.set_icon("fullscreen_exit")
        self._apply_margins()

    # ---- full-window library ------------------------------------------
    def toggle_menu(self):
        """The VLC cone: open the start page, or go back to what's playing."""
        if self.library_mode:
            if self.player.get_media() is not None:
                self.exit_library()
        else:
            self.enter_library(("home",))

    def _page_command(self, cmd):
        before = self.player.get_media()
        if cmd == "open_file":
            self.open_dialog()
        elif cmd == "open_folder":
            self.open_folder()
        elif cmd == "open_stream":
            self.open_url()
        elif cmd == "shortcuts":
            self.show_shortcuts()
        elif cmd == "about":
            self.about()
        elif cmd == "settings":
            # The settings panel lives beside the player, so switch to it (works with nothing playing too).
            self.exit_library()
            self.show_preferences("general")
            return
        if self.player.get_media() is not before:
            self.exit_library()          # something new is playing: show it

    def toggle_full_library(self):
        if self.library_mode:
            self.exit_library()
        else:
            self.enter_library(self.library.loc if self.library.isVisible() else ("home",))

    def enter_library(self, loc=None):
        if self.library_mode:
            return
        if self.isFullScreen():
            self.toggle_fullscreen()
        if self.ui_hidden:
            self.toggle_hide_ui()
        self.library_mode = True
        self.tracks_popup.hide()
        pg = self.library_page
        # The live video moves into the mini player (libVLC keeps drawing into it).
        pg.mini.video_lay.addWidget(self.surface)
        self.body.hide()
        self.controls.hide()
        for w in (self.title_bar.sidebar_btn, self.title_bar.sep, self.title_bar.folder_btn, self.title_bar.crumb):
            w.hide()
        pg.show()
        pg.go(loc or ("home",))
        pg.set_current(self._media_key())
        pg.set_back_visible(self.player.get_media() is not None)
        self.scrub.hide()
        pg.mini.setVisible(self.player.get_media() is not None)
        pg.mini.raise_()
        pg.mini.place_default()
        self._update_mini()

    def exit_library(self):
        if not self.library_mode:
            return
        self.library_mode = False
        self.library_page.hide()
        self.body_lay.insertWidget(1, self.surface, 1)
        self.surface.show()
        self.body.show()
        self.controls.show()
        for w in (self.title_bar.sidebar_btn, self.title_bar.sep, self.title_bar.folder_btn, self.title_bar.crumb):
            w.show()

    def close_media(self):
        """The mini player's ✕: stop, remember where we were, and show the library with nothing playing."""
        self._save_position()
        self.store.save()
        self._click_timer.stop()
        self.player.stop()
        self.player.set_media(None)
        self.playlist, self.index, self.current = [], -1, None
        self._restore, self._new_media = None, False
        self.storyboard.cancel()
        self.scrub.hide()
        self.resume_prompt.hide()
        self._set_music_mode(False)
        self.surface.show_video(False)
        self.controls.seek.set_peaks([])
        self.controls.seek.set_markers([])
        self.title_bar.set_title("VLC Reskin")
        self.title_bar.crumb.setText("")
        self.setWindowTitle("VLC Reskin")
        self.library.set_current(None)
        pg = self.library_page
        pg.set_current(None)
        pg.mini.hide()
        pg.set_back_visible(False)
        pg.refresh()                    # Continue watching picks up the saved position

    def _escape(self):
        if self.library_mode:
            self.exit_library()
        elif self.isFullScreen():
            self.toggle_fullscreen()

    def _play_from_page(self, items, start, name, resume):
        self._play_items(items, start, name, resume)
        self.exit_library()

    def _show_mini_queue(self):
        b = self.library_page.mini.queue_btn
        if not self.playlist:
            self.toast(b, "The queue is empty")
            return
        m = styled_menu(self)
        for i, it in enumerate(self.playlist[:40]):
            add(m, "check" if i == self.index else None, self._item_label(it), lambda _=False, i=i: self.play_index(i))
        m.exec(b.mapToGlobal(QPoint(0, -m.sizeHint().height() - 4)))

    def _update_mini(self):
        mini = self.library_page.mini
        has = self.player.get_media() is not None
        if has and not mini.isVisible():
            mini.show()
            mini.raise_()
            mini.place_default()
        elif not has:
            mini.hide()
            return
        key = self._media_key() or ""
        if self.current is not None:
            title = self.title_bar.title.text()
            folder = self.current.parent.name
            artist = self.surface.music_view._artist if self.music_mode else ""
        else:
            title, folder, artist = self._stream_name(key) if key else "", "Network", ""
        if not artist and self.current is not None and self.current.parent.parent != self.current.parent:
            artist = self.current.parent.parent.name if not self.music_mode else ""
        length = self.player.get_length()
        mini.set_info(title, folder, artist, self.player.get_position() if length > 0 else 0.0)

    def toggle_library(self):
        """The folder name / sidebar button: opens the library at the current show's folder."""
        if self.library.isVisible():
            self.library.hide()
            return
        if self.current is not None:
            self.library.show_folder(self.current.parent)
        self.library.show()

    def toggle_maximize(self):
        if self.isFullScreen():
            return
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange:
            self.title_bar.max_btn.set_icon("restore" if self.isMaximized() else "maximize")
        super().changeEvent(e)

    # ---- frameless resizing --------------------------------------------
    def _edges(self, gpos):
        if self.isMaximized() or self.isFullScreen():
            return Qt.Edge(0)
        p = self.mapFromGlobal(gpos)
        edges = Qt.Edge(0)
        if p.x() <= RESIZE_MARGIN: edges |= Qt.LeftEdge
        if p.x() >= self.width() - RESIZE_MARGIN: edges |= Qt.RightEdge
        if p.y() <= RESIZE_MARGIN: edges |= Qt.TopEdge
        if p.y() >= self.height() - RESIZE_MARGIN: edges |= Qt.BottomEdge
        return edges

    _CURSORS = {
        Qt.LeftEdge: Qt.SizeHorCursor, Qt.RightEdge: Qt.SizeHorCursor,
        Qt.TopEdge: Qt.SizeVerCursor, Qt.BottomEdge: Qt.SizeVerCursor,
        Qt.LeftEdge | Qt.TopEdge: Qt.SizeFDiagCursor, Qt.RightEdge | Qt.BottomEdge: Qt.SizeFDiagCursor,
        Qt.RightEdge | Qt.TopEdge: Qt.SizeBDiagCursor, Qt.LeftEdge | Qt.BottomEdge: Qt.SizeBDiagCursor,
    }

    def eventFilter(self, obj, e):
        """Frameless-window resizing from any widget near the window edge."""
        if isinstance(obj, QWidget) and obj.window() is self:
            if e.type() == QEvent.MouseMove and not e.buttons():
                edges = self._edges(e.globalPosition().toPoint())
                if edges:
                    cursor = self._CURSORS.get(edges, Qt.ArrowCursor)
                    if QApplication.overrideCursor() is None:
                        QApplication.setOverrideCursor(cursor)
                    else:
                        QApplication.changeOverrideCursor(cursor)
                elif QApplication.overrideCursor() is not None:
                    QApplication.restoreOverrideCursor()
            elif e.type() == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
                edges = self._edges(e.globalPosition().toPoint())
                if edges:
                    self.windowHandle().startSystemResize(edges)
                    return True
                if obj is self.surface.music_view:     # the cover in music view acts like the video
                    self._video_click()
                    return True
            elif e.type() == QEvent.MouseButtonDblClick and obj is self.surface.music_view:
                self._video_click(double=True)
                return True
            elif e.type() == QEvent.MouseButtonDblClick and obj is self.surface and not self.surface.canvas.isVisible():
                self.toggle_fullscreen()   # idle screen; while video plays, _video_press handles it
                return True
        return super().eventFilter(obj, e)

    def leaveEvent(self, e):
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        super().leaveEvent(e)

    # ---- menus ----------------------------------------------------------
    def _show_more_menu(self):
        """The ••• menu (Figma 'menu' frame)."""
        m = styled_menu(self)
        add(m, "m_file", "Open File(s)", self.open_dialog, "Ctrl + O")
        add(m, "m_folder", "Open Folder", self.open_folder, "Ctrl + F")
        add(m, "m_network", "Open Network Stream", lambda: self.open_url(), "Ctrl + N")
        add(m, "m_disc", "Open Disc", self.open_disc, "Ctrl + D")
        add(m, "m_capture", "Open Capture Device", self.open_capture, "Ctrl + C")
        add(m, "m_convert", "Convert", None, "Ctrl + R", enabled=False, tip="Not built yet")
        recent = submenu(m, "m_recent", "Open Recent", color=T.ICON)
        self._fill_recent(recent)
        m.addSeparator()
        prof = submenu(m, "m_profile", "Profile (Default)", color=T.ICON)
        add(prof, "check", "Default")
        add(prof, None, "New profile…", enabled=False, tip="Profiles are not built yet")
        add(m, "m_keyboard", "Keyboard Shortcuts", self.show_shortcuts)
        add(m, "m_brush", "Customize Player", enabled=False, tip="Not built yet")
        add(m, "settings", "Settings", lambda: self.show_preferences(), "Ctrl + P")
        add(m, "m_info", "About VLC", self.about, "Shift + F1")
        b = self.title_bar.more_btn
        m.exec(b.mapToGlobal(b.rect().bottomLeft() + QPoint(0, 6)))

    def _fill_recent(self, menu):
        items = [k for k, _ in self.store.recent(RECENT_MAX)]
        if not items:
            add(menu, None, "No recent media", enabled=False)
            return
        for k in items:
            label = self._stream_name(k) if is_url(k) else Path(k).name
            add(menu, None, label, lambda _=False, k=k: self._play_items([k], 0, "", False), tip=k)
        menu.addSeparator()
        add(menu, None, "Clear recent", lambda: [self.store.forget(k) for k in items])

    def _track_items(self, menu, items, cur, setter):
        if not items:
            add(menu, None, "None available", enabled=False)
        for ident, name in items:
            add(menu, "check" if ident == cur else None, name, lambda _=False, i=ident: setter(i))

    def contextMenuEvent(self, e):
        self.show_context_menu(e.globalPos())

    def show_context_menu(self, pos):
        """The right-click menu (Figma 'right-click menu' frame)."""
        A = T.ACCENT
        playing = self.player.is_playing()
        m = styled_menu(self)
        add(m, "r_play", "Pause" if playing else "Play", self.toggle_play, "Space", A)
        add(m, "r_stop", "Stop", self.stop, "S", A)
        add(m, "r_prev", "Previous Item", lambda: self.step(-1), "P", A)
        add(m, "r_next", "Next Item", lambda: self.step(1), "N", A)
        add(m, "r_record", "Record", None, "R", A, enabled=False,
            tip="Recording needs libVLC 4; this build uses VLC 3")
        m.addSeparator()
        add(m, "r_hide", "Show UI" if self.ui_hidden else "Hide UI", self.toggle_hide_ui, "Ctrl + \\", T.ICON)
        m.addSeparator()

        pb = submenu(m, "r_playback", "Playback")
        rate = self.player.get_rate()
        for r in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            add(pb, "check" if abs(rate - r) < 0.01 else None, f"{r:g}×", lambda _=False, r=r: self.set_rate(r))
        pb.addSeparator()
        add(pb, None, "Jump forward 15 s", lambda: self.skip(SKIP_MS), "→")
        add(pb, None, "Jump backward 15 s", lambda: self.skip(-SKIP_MS), "←")
        add(pb, "check" if self._repeat else None, "Repeat current", lambda: setattr(self, "_repeat", not self._repeat))

        vid = submenu(m, "r_video", "Video")
        self._track_items(vid, *self.video_tracks())
        vid.addSeparator()
        ar = styled_menu(vid, "Aspect Ratio")
        vid.addMenu(ar)
        cur_ar = _text(self.player.video_get_aspect_ratio() or "")
        for label, val in (("Default", ""), ("16:9", "16:9"), ("4:3", "4:3"), ("21:9", "21:9"), ("1:1", "1:1")):
            add(ar, "check" if cur_ar == val else None, label,
                lambda _=False, v=val: self.player.video_set_aspect_ratio(v or None))
        add(vid, None, "Fullscreen", self.toggle_fullscreen, "F")
        add(vid, None, "Take Snapshot", self.snapshot)

        aud = submenu(m, "eq", "Audio")
        self._track_items(aud, *self.audio_tracks())
        aud.addSeparator()
        dev = styled_menu(aud, "Output Device")
        aud.addMenu(dev)
        self._track_items(dev, *self.audio_devices())
        add(aud, None, "Unmute" if self._muted else "Mute", self.toggle_mute, "M")

        sub = submenu(m, "subtitles", "Subtitle")
        self._track_items(sub, *self.subtitle_tracks())
        sub.addSeparator()
        add(sub, None, "Add Subtitle File…", self.add_subtitle_file)
        m.addSeparator()

        more = submenu(m, "settings", "More Settings")
        add(more, None, "Preferences", lambda: self.show_preferences(), "Ctrl + P")
        add(more, None, "Keyboard Shortcuts", self.show_shortcuts)
        add(more, None, "Library Sidebar", self.toggle_library, "L")

        pl = submenu(m, "r_queue", "Playlist")
        if not self.playlist:
            add(pl, None, "Empty", enabled=False)
        for i, p in enumerate(self.playlist[:40]):
            add(pl, "check" if i == self.index else None, self._item_label(p), lambda _=False, i=i: self.play_index(i))
        if self._media_key():
            pl.addSeparator()
            to = styled_menu(pl, "Add current to playlist")
            pl.addMenu(to)
            self.library._fill_playlist_menu(to, [self._media_key()])

        om = submenu(m, "r_open", "Open Media")
        add(om, None, "Open File(s)…", self.open_dialog, "Ctrl + O")
        add(om, None, "Open Folder…", self.open_folder, "Ctrl + F")
        add(om, None, "Open Network Stream…", lambda: self.open_url(), "Ctrl + N")
        add(om, None, "Open Disc", self.open_disc, "Ctrl + D")
        add(om, None, "Open Capture Device", self.open_capture, "Ctrl + C")
        add(m, "r_quit", "Quit VLC", self.close, "Ctrl + Q", A)
        m.exec(pos)

    def _show_playlist_menu(self):
        b = self.controls.playlist_btn
        if not self.playlist:
            self.toast(b, "Playlist is empty. Open a file to fill it")
            return
        m = styled_menu(self)
        for i, p in enumerate(self.playlist[:40]):
            add(m, "check" if i == self.index else None, self._item_label(p), lambda _=False, i=i: self.play_index(i))
        m.exec(b.mapToGlobal(QPoint(b.width() - m.sizeHint().width(), -m.sizeHint().height() - 6)))

    # ---- small dialogs --------------------------------------------------
    def snapshot(self):
        out = Path.home() / "Pictures"
        if self.player.video_take_snapshot(0, str(out), 0, 0) == 0:
            self.toast(self.controls.settings_btn, f"Snapshot saved to {out}")

    def show_shortcuts(self):
        d = QDialog(self)
        d.setWindowTitle("Keyboard Shortcuts")
        d.setStyleSheet(f"QDialog{{background:{T.SHELL};}} QLabel{{font-size:13px;}}")
        grid = QGridLayout(d)
        grid.setContentsMargins(24, 20, 24, 20)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(8)
        for r, (keys, what) in enumerate(SHORTCUTS):
            k = QLabel(keys)
            k.setStyleSheet(f"color:{T.ACCENT}; background:#262626; border-radius:5px; padding:3px 8px;")
            w = QLabel(what)
            w.setStyleSheet("color:#cfcfcf;")
            grid.addWidget(k, r, 0, Qt.AlignLeft)
            grid.addWidget(w, r, 1)
        d.exec()

    def about(self):
        """Credits: the design is Juxtopposed's, the player is VideoLAN's (see credits.py)."""
        AboutDialog(self, _text(vlc.libvlc_get_version())).exec()

    def toast(self, widget, text):
        QToolTip.showText(widget.mapToGlobal(widget.rect().topLeft()) - QPoint(0, 34), text, widget)

    # ---- drag & drop ----------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if not urls:
            return
        if urls[0].isLocalFile():
            p = Path(urls[0].toLocalFile())
            sub_exts = {s.lstrip("*") for s in SUB_EXTS.split()}
            if p.suffix.lower() in sub_exts and self.player.get_media() is not None:
                self._add_sub(urls[0].toString())
            elif p.is_dir():
                self.library.show_folder(p)
                self.library.show()
            else:
                self.open_path(p)
        else:
            self.open_url(urls[0].toString())

    def closeEvent(self, e):
        self._save_position()
        self.resume_prompt.close()
        self.scrub.close()
        self.flash.close()
        self.storyboard.cancel()
        self.timer.stop()
        self.hover_timer.stop()
        self.settings.setValue("prefs_state", json.dumps(self.state))
        self.click_hook.close()
        self.top_overlay.close()
        self.bottom_overlay.close()
        self.player.stop()
        self.player.release()
        self.vlc.release()
        super().closeEvent(e)


def resource(*parts) -> Path:
    """A file shipped with the app (inside the PyInstaller bundle when frozen)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def app_icon() -> QIcon:
    ico = resource("assets", "app.ico")
    return QIcon(str(ico)) if ico.exists() else QIcon(pixmap("vlc", "", 64))


def main():
    if sys.platform == "win32":
        # Its own taskbar identity, so Windows shows the cone instead of grouping it under Python.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VLCReskin.Player")
    app = QApplication(sys.argv)
    app.setApplicationName("VLC Reskin")
    app.setWindowIcon(app_icon())
    if "--selftest" in sys.argv:
        # Used by the build script: start everything, write a report, quit (no window shown).
        out = Path(sys.argv[sys.argv.index("--selftest") + 1])
        w = PlayerWindow()
        report = f"ok libvlc={_text(vlc.libvlc_get_version())} icon={not app_icon().isNull()}"
        out.write_text(report + chr(10), encoding="utf-8")
        w.close()
        return
    f = QFont("Segoe UI")
    f.setPixelSize(13)
    app.setFont(f)
    w = PlayerWindow()
    w.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        w.open_path(Path(sys.argv[1]).resolve())
    elif w.state.get("start_on_home", True):     # Settings > General
        w.enter_library(("home",))   # start on the recent-media start page, like Word
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
