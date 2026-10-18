"""Right-hand preferences sidebar with Playback / Video / Audio / Subtitles tabs,
built from the Figma setting components: collapsible cards, orange sliders
with value boxes, OFF/ON toggles, dropdowns, colour fields and a preset bar."""

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QColorDialog, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

import prefs as P
import theme as T
from icons import pixmap

PANEL_BG = "#191919"
CARD_BG = "#212121"
FIELD_BG = "#111111"
LABEL = "#8f8f8f"
VALUE = "#c8c8c8"

COMBO_QSS = f"""
QComboBox {{ background:{FIELD_BG}; color:{VALUE}; border:1px solid #2a2a2a; border-radius:6px;
             padding:5px 10px; font-size:13px; min-height:20px; }}
QComboBox:hover {{ border-color:#3a3a3a; }}
QComboBox::drop-down {{ border:none; width:22px; }}
QComboBox::down-arrow {{ image:none; }}
QComboBox QAbstractItemView {{ background:#1c1c1c; color:{VALUE}; border:1px solid #2c2c2c;
             selection-background-color:#2a2a2a; selection-color:#eee; outline:0; padding:4px; }}
"""
FIELD_QSS = f"""QLineEdit {{ background:{FIELD_BG}; color:{VALUE}; border:1px solid #2a2a2a; border-radius:6px;
                padding:5px 10px; font-size:13px; }}
                QLineEdit:focus {{ border-color:{T.ACCENT}; }}"""


class PSlider(QWidget):
    """Thick slider in the seek-bar style. Double-click resets to the default."""

    moved = Signal(float)

    def __init__(self, lo, hi, value, step=0.01, default=None, ticks=None, tick_labels=False):
        super().__init__()
        self.lo, self.hi, self.step = lo, hi, step
        self.default = value if default is None else default
        self.ticks = ticks or []
        self.tick_labels = tick_labels
        self._v = value
        self.setFixedHeight(34 if tick_labels else 18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    def value(self):
        return self._v

    def set_value(self, v, emit=False):
        v = min(max(v, self.lo), self.hi)
        if self.step:
            v = round(round((v - self.lo) / self.step) * self.step + self.lo, 6)
        if v != self._v:
            self._v = v
            self.update()
            if emit:
                self.moved.emit(v)

    def _frac(self, v):
        return (v - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0

    def _from_x(self, x):
        f = min(max((x - 4) / max(1, self.width() - 8), 0), 1)
        self.set_value(self.lo + f * (self.hi - self.lo), emit=True)

    def mousePressEvent(self, e):
        self._from_x(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._from_x(e.position().x())

    def mouseDoubleClickEvent(self, e):
        self.set_value(self.default, emit=True)

    def wheelEvent(self, e):
        e.ignore()  # let the sidebar scroll

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(0, 0, self.width(), 18)
        p.setBrush(QColor(T.TRACK))
        p.drawRoundedRect(r, 5, 5)
        inner = r.adjusted(3, 3, -3, -3)
        p.setBrush(QColor("#3a3a3a"))
        for t in self.ticks:
            x = inner.left() + inner.width() * self._frac(t)
            p.drawRect(QRectF(x - 0.5, inner.top() + 3, 1, inner.height() - 6))
        x = inner.left() + inner.width() * self._frac(self._v)
        if x > inner.left() + 1:
            p.setBrush(QColor(T.SEEK_FILL))
            p.drawRoundedRect(QRectF(inner.left(), inner.top(), x - inner.left(), inner.height()), 3, 3)
        p.setBrush(QColor(T.ACCENT))
        p.drawRoundedRect(QRectF(x - 2.5, inner.top() - 1, 5, inner.height() + 2), 2, 2)
        if self.tick_labels:
            p.setPen(QColor("#6a6a6a"))
            f = QFont(self.font())
            f.setPixelSize(10)
            p.setFont(f)
            for t in self.ticks:
                tx = inner.left() + inner.width() * self._frac(t)
                tx = min(max(tx, 20), self.width() - 20)   # keep end labels inside
                p.drawText(QRectF(tx - 20, 20, 40, 14), Qt.AlignCenter, f"{t:g}")


class Toggle(QAbstractButton):
    """OFF / ON pill from the design."""

    def __init__(self, on=False, enabled=True):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(on)
        self.setEnabled(enabled)
        self.setFixedSize(66, 30)
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ForbiddenCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        p.setPen(QColor("#333333"))
        p.setBrush(QColor(FIELD_BG))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.setPen(Qt.NoPen)
        knob = QRectF(36 if on else 4, 4, 26, 22)
        p.setBrush(QColor(T.ACCENT if on else "#4a4a4a") if self.isEnabled() else QColor("#2e2e2e"))
        p.drawRoundedRect(knob, 4, 4)
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor("#d0d0d0" if on else "#7a7a7a") if self.isEnabled() else QColor("#444"))
        p.drawText(QRectF(4 if on else 32, 0, 30, 30), Qt.AlignCenter, "ON" if on else "OFF")


class Card(QFrame):
    """Rounded group. Collapsible cards show "Expand Settings >" when closed."""

    def __init__(self, title="", collapsible=False, expanded=True):
        super().__init__()
        self.setObjectName("card")
        self.collapsible = collapsible
        self.title = title
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(16, 12, 16, 14)
        self.box.setSpacing(8)
        self.head = None
        if title or collapsible:
            self.head = QPushButton()
            self.head.setCursor(Qt.PointingHandCursor if collapsible else Qt.ArrowCursor)
            self.head.setFlat(True)
            self.head.setStyleSheet(f"QPushButton{{background:transparent;border:none;color:{VALUE if not collapsible else LABEL};"
                                    "font-size:14px;text-align:left;padding:2px 0}}")
            self.head.setLayoutDirection(Qt.RightToLeft)
            self.head.setIconSize(QSize(16, 16))
            if collapsible:
                self.head.clicked.connect(lambda: self.set_expanded(not self.expanded))
            self.box.addWidget(self.head)
        self.body = QWidget()
        self.body.setStyleSheet("background:transparent;")
        self.rows = QVBoxLayout(self.body)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(10)
        self.box.addWidget(self.body)
        self.set_expanded(expanded)

    def set_expanded(self, on):
        self.expanded = on
        self.body.setVisible(on)
        dark = self.collapsible and not on
        self.setStyleSheet(f"#card {{ background:{'#0e0e0e' if dark else CARD_BG}; border-radius:8px; }}"
                           "QLabel { background:transparent; }")
        if self.head is not None:
            if self.collapsible:
                label = self.title or ("Collapse Settings" if on else "Expand Settings")
                self.head.setText(label)
                self.head.setIcon(QIcon(pixmap("chevron_right" if not on else "chevron_down", T.ICON, 16)))
            else:
                self.head.setText(self.title)


class PrefsPanel(QFrame):
    """The sidebar. Writes into `state` and emits `changed(key)`; the player
    decides whether a key applies live or needs an engine restart."""

    changed = Signal(str)
    preset_chosen = Signal(str)
    preset_saved = Signal(str)
    advanced = Signal()

    TABS = [("playback", "r_playback", "Playback"), ("video", "video", "Video"),
            ("audio", "eq", "Audio"), ("subtitles", "subtitles", "Subtitles"), ("general", "settings", "General")]

    def __init__(self, state: dict, presets: P.PresetStore, parent=None):
        super().__init__(parent)
        self.state = state
        self.presets = presets
        self.current_preset = ""
        self.tab = "playback"
        self.setFixedWidth(380)
        self.setObjectName("prefs")
        self.setStyleSheet(f"#prefs {{ background:{PANEL_BG}; border-radius:{T.VIDEO_RADIUS}px; }}"
                           "QLabel { background:transparent; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        tabs = QHBoxLayout()
        tabs.setContentsMargins(8, 6, 8, 0)
        tabs.setSpacing(0)
        self.tab_btns = {}
        for key, icon, label in self.TABS:
            b = QPushButton(f" {label}")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(40)
            b.setIconSize(QSize(16, 16))
            b.clicked.connect(lambda _=False, k=key: self.show_tab(k))
            self.tab_btns[key] = (b, icon)
            tabs.addWidget(b)
        lay.addLayout(tabs)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#262626;")
        lay.addWidget(line)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        foot = QVBoxLayout()
        foot.setContentsMargins(12, 8, 12, 10)
        foot.setSpacing(6)
        prow = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.setStyleSheet(COMBO_QSS)
        self.preset_combo.activated.connect(self._preset_picked)
        self.save_btn = QPushButton("Save")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setToolTip("Save these settings as a preset for this show (folder)")
        self.save_btn.setStyleSheet(f"QPushButton{{background:{T.ACCENT};color:#1b1b1b;border:none;border-radius:6px;"
                                    "padding:6px 14px;font-size:13px}} QPushButton:hover{{background:#e58a2a}}")
        self.save_btn.clicked.connect(self._save_preset)
        prow.addWidget(self.preset_combo, 1)
        prow.addWidget(self.save_btn)
        foot.addLayout(prow)
        adv = QPushButton("  Open Advanced Settings")
        adv.setIcon(QIcon(pixmap("settings", LABEL, 16)))
        adv.setCursor(Qt.PointingHandCursor)
        adv.setStyleSheet(f"QPushButton{{background:transparent;border:none;color:{LABEL};font-size:13px;padding:4px}}"
                          "QPushButton:hover{color:#ddd}")
        adv.clicked.connect(self.advanced.emit)
        foot.addWidget(adv)
        lay.addLayout(foot)

        self.rebuild()

    # ---- tabs ----------------------------------------------------------
    def show_tab(self, key):
        self.tab = key
        for k, (b, icon) in self.tab_btns.items():
            on = k == key
            b.setIcon(QIcon(pixmap(icon, T.ACCENT if on else T.ICON, 16)))
            b.setStyleSheet(f"QPushButton{{background:transparent;border:none;border-bottom:2px solid "
                            f"{T.ACCENT if on else 'transparent'};color:{'#e6e6e6' if on else LABEL};font-size:12px;padding:0 2px}}"
                            "QPushButton:hover{color:#e6e6e6}")
        self.stack.setCurrentIndex([k for k, _, _ in self.TABS].index(key))

    def rebuild(self):
        """Recreate every tab from `state` (after a preset loads, for example)."""
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        for build in (self._playback, self._video, self._audio, self._subtitles, self._general):
            self.stack.addWidget(self._scroll(build()))
        self._fill_presets()
        self.show_tab(self.tab)

    def _scroll(self, content):
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        s.setFrameShape(QFrame.NoFrame)
        s.setStyleSheet("QScrollArea{background:transparent;border:none}"
                        "QScrollBar:vertical{width:6px;background:transparent}"
                        "QScrollBar::handle:vertical{background:#333;border-radius:3px}"
                        "QScrollBar::add-line,QScrollBar::sub-line{height:0}"
                        "QScrollBar::add-page,QScrollBar::sub-page{background:none}")
        content.setObjectName("tabbody")
        content.setStyleSheet("#tabbody{background:transparent}")
        s.setWidget(content)
        s.viewport().setStyleSheet("background:transparent;")
        return s

    def _page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        return w, lay

    # ---- row builders ---------------------------------------------------
    def _set(self, key, value):
        self.state[key] = value
        self.changed.emit(key)

    def _label(self, text, tip=""):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{LABEL}; font-size:13px;")
        if tip:
            lbl.setToolTip(tip)
        return lbl

    def slider(self, card, key, label, lo, hi, step, fmt, ticks=None, tick_labels=False, parse=None):
        """Label + value box on one line, slider below (Figma 'Values' rows)."""
        row = QHBoxLayout()
        row.addWidget(self._label(label), 1)
        box = QLineEdit(fmt(self.state[key]))
        box.setFixedWidth(130)
        box.setStyleSheet(FIELD_QSS)
        row.addWidget(box)
        card.rows.addLayout(row)
        s = PSlider(lo, hi, self.state[key], step, P.DEFAULTS.get(key), ticks, tick_labels)
        card.rows.addWidget(s)

        def from_slider(v):
            box.setText(fmt(v))
            self._set(key, v)

        def from_box():
            txt = box.text().strip()
            try:
                v = parse(txt) if parse else float("".join(ch for ch in txt if ch in "-.0123456789") or 0)
            except ValueError:
                box.setText(fmt(self.state[key]))
                return
            s.set_value(v, emit=True)
            box.setText(fmt(s.value()))
        s.moved.connect(from_slider)
        box.editingFinished.connect(from_box)
        return s

    def toggle(self, card, key, label, enabled=True, tip=""):
        row = QHBoxLayout()
        row.addWidget(self._label(label, tip), 1)
        t = Toggle(bool(self.state.get(key, False)), enabled)
        if tip:
            t.setToolTip(tip)
        t.toggled.connect(lambda on: self._set(key, on))
        row.addWidget(t)
        card.rows.addLayout(row)
        return t

    def dropdown(self, card, key, label, options, on_pick=None):
        row = QHBoxLayout()
        row.addWidget(self._label(label), 1)
        c = QComboBox()
        c.setStyleSheet(COMBO_QSS)
        c.setFixedWidth(170)
        c.addItems(options)
        cur = self.state[key]
        if cur in options:
            c.setCurrentIndex(options.index(cur))
        c.currentTextChanged.connect(lambda v: (self._set(key, v), on_pick and on_pick(v)))
        row.addWidget(c)
        card.rows.addLayout(row)
        return c

    def text(self, card, key, label, placeholder=""):
        row = QHBoxLayout()
        row.addWidget(self._label(label), 1)
        e = QLineEdit(self.state[key])
        e.setPlaceholderText(placeholder)
        e.setFixedWidth(170)
        e.setStyleSheet(FIELD_QSS)
        e.editingFinished.connect(lambda: self._set(key, e.text().strip()))
        row.addWidget(e)
        card.rows.addLayout(row)
        return e

    def color(self, card, key, label):
        row = QHBoxLayout()
        row.addWidget(self._label(label), 1)
        e = QLineEdit(self.state[key].upper())
        e.setFixedWidth(130)
        e.setStyleSheet(FIELD_QSS)
        sw = QPushButton()
        sw.setFixedSize(30, 30)
        sw.setCursor(Qt.PointingHandCursor)

        def paint(hexv):
            sw.setStyleSheet(f"QPushButton{{background:{hexv};border:1px solid #444;border-radius:6px}}")

        def commit(hexv):
            c = QColor(hexv)
            if c.isValid():
                hexv = c.name().upper()
                e.setText(hexv)
                paint(hexv)
                self._set(key, hexv)
            else:
                e.setText(self.state[key].upper())

        def pick():
            c = QColorDialog.getColor(QColor(self.state[key]), self, label)
            if c.isValid():
                commit(c.name())
        paint(self.state[key])
        e.editingFinished.connect(lambda: commit(e.text().strip()))
        sw.clicked.connect(pick)
        row.addWidget(e)
        row.addWidget(sw)
        card.rows.addLayout(row)

    def segment(self, card, key, label, options, on_pick=None):
        row = QHBoxLayout()
        row.addWidget(self._label(label), 1)
        wrap = QFrame()
        wrap.setStyleSheet(f"QFrame{{background:{FIELD_BG};border-radius:6px}}")
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(2, 2, 2, 2)
        wl.setSpacing(2)
        btns = []
        for opt in options:
            b = QPushButton(opt)
            b.setCheckable(True)
            b.setChecked(self.state[key] == opt)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{LABEL};border:none;border-radius:5px;padding:5px 12px;font-size:13px}}"
                            f"QPushButton:checked{{background:#3a2208;color:{T.ACCENT};border:1px solid #6b3e0c}}")
            btns.append(b)
            wl.addWidget(b)

        def pick(opt):
            for b in btns:
                b.setChecked(b.text() == opt)
            self._set(key, opt)
            if on_pick:
                on_pick(opt)
        for b in btns:
            b.clicked.connect(lambda _=False, o=b.text(): pick(o))
        row.addWidget(wrap)
        card.rows.addLayout(row)

    def note(self, card, text):
        n = QLabel(text)
        n.setWordWrap(True)
        n.setStyleSheet("color:#5f5f5f; font-size:12px;")
        card.rows.addWidget(n)

    # ---- tabs -----------------------------------------------------------
    def _general(self):
        w, lay = self._page()
        c = Card("Home page")
        self.dropdown(c, "home_style", "Home page style", P.HOME_STYLES)
        self.note(c, "Start screen: a greeting, Continue watching and a list of everything you've played, "
                     "newest first. Classic: the original design with rows of tiles for "
                     "Continue Watching, Listen Again, folders, playlists and artists.")
        self.toggle(c, "start_on_home", "Open the start page when the app starts")
        self.note(c, "Turn this off to open straight into the player. The VLC cone in the top-left corner "
                     "always opens the start page.")
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _playback(self):
        w, lay = self._page()
        c = Card()
        self.toggle(c, "sub_timeline", "Show Subtitle Timeline on Seekbar",
                    tip="Marks where subtitle lines appear, for external .srt / .vtt files")
        self.toggle(c, "waveform", "Show Waveform on Seekbar",
                    tip="Draws the audio waveform in the seek bar; it's worked out in the background")
        self.toggle(c, "reverse", "Reverse", enabled=False, tip="libVLC can't play media backwards")
        self.dropdown(c, "sleep", "Sleep Timer", list(P.SLEEP))
        self.slider(c, "rate", "Speed", 0.25, 2.0, 0.05, lambda v: f"{v:g}x",
                    ticks=[0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2], tick_labels=True)
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _video(self):
        w, lay = self._page()
        c = Card("Essential")
        self.slider(c, "hue", "Hue", -180, 180, 1, lambda v: f"{v:+.0f}°", ticks=[0])
        self.slider(c, "brightness", "Brightness", 0, 2, 0.01, lambda v: f"{v:.2f}", ticks=[1])
        self.slider(c, "contrast", "Contrast", 0, 2, 0.01, lambda v: f"{v:.2f}", ticks=[1])
        self.slider(c, "saturation", "Saturation", 0, 3, 0.01, lambda v: f"{v:.2f}", ticks=[1])
        self.slider(c, "gamma", "Gamma", 0.1, 4, 0.01, lambda v: f"{v:.2f}", ticks=[1])
        lay.addWidget(c)

        g = Card("Geometry")
        self.dropdown(g, "crop", "Crop", P.CROPS)
        self.dropdown(g, "aspect", "Aspect Ratio", P.ASPECTS)
        self.dropdown(g, "zoom", "Zoom", list(P.ZOOMS))
        self.dropdown(g, "transform", "Flip / Rotate", list(P.TRANSFORMS))
        lay.addWidget(g)

        f = Card(collapsible=True, expanded=False)
        self.slider(f, "sharpen", "Sharpen Sigma", 0, 2, 0.05, lambda v: f"{v:.2f}", ticks=[0.5, 1, 1.5])
        self.slider(f, "banding", "Banding Removal Radius", 0, 32, 1, lambda v: "Off" if v == 0 else f"{v:.0f}",
                    ticks=[8, 16, 24])
        self.slider(f, "grain", "Film Grain Variance", 0, 10, 0.1, lambda v: f"{v:.1f}", ticks=[2, 4, 6, 8])
        self.toggle(f, "negate", "Negate Colors")
        self.toggle(f, "posterize", "Posterize")
        self.dropdown(f, "gradient", "Gradient", list(P.GRADIENTS))
        self.toggle(f, "cartoon", "Cartoon", tip="Works together with Gradient")
        self.slider(f, "sepia", "Sepia Intensity", 0, 255, 1, lambda v: "Off" if v == 0 else f"{v:.0f}", ticks=[128])
        self.note(f, "Filters and Flip / Rotate restart playback for a moment to apply.")
        lay.addWidget(self._section("Filters"))
        lay.addWidget(f)
        lay.addStretch(1)
        return w

    def _audio(self):
        w, lay = self._page()
        d = Card("Defaults")
        self.dropdown(d, "audio_default", "Default Audio Track", P.TRACK_DEFAULTS)
        self.text(d, "audio_lang", "Preferred Language", "e.g. English")
        self.note(d, "Applied when the next file starts. \"By language\" matches the track name.")
        lay.addWidget(d)

        s = Card("Synchronization")
        self.slider(s, "audio_delay", "Audio Delay", -5, 5, 0.01, lambda v: f"{v:.3f} s", ticks=[0])
        lay.addWidget(s)

        e = Card("Equalizer")
        names = P.eq_presets()
        opts = names if self.state["eq_preset"] in names else names + [self.state["eq_preset"]]
        self.dropdown(e, "eq_preset", "Preset", opts, on_pick=self._eq_preset)
        lay.addWidget(e)
        bands = Card(collapsible=True, expanded=False)
        db = lambda v: f"{v:.1f} dB"  # noqa: E731
        self.slider(bands, "eq_preamp", "Preamp", -20, 20, 0.1, db, ticks=[0])
        for i, name in enumerate(P.eq_bands()):
            self._band(bands, i, name)
        lay.addWidget(bands)

        fx = Card("Effects")
        self.toggle(fx, "compressor", "Compressor")
        self.toggle(fx, "spatializer", "Spatializer")
        self.toggle(fx, "stereo_widener", "Stereo Widener")
        self.note(fx, "Effects restart playback for a moment to apply.")
        lay.addWidget(fx)
        lay.addStretch(1)
        return w

    def _band(self, card, i, name):
        row = QHBoxLayout()
        row.addWidget(self._label(name), 1)
        box = QLineEdit(f"{self.state['eq_bands'][i]:.1f} dB")
        box.setFixedWidth(130)
        box.setStyleSheet(FIELD_QSS)
        row.addWidget(box)
        card.rows.addLayout(row)
        s = PSlider(-20, 20, self.state["eq_bands"][i], 0.1, 0.0, [0])
        card.rows.addWidget(s)

        def set_band(v):
            bands = list(self.state["eq_bands"])
            bands[i] = v
            self.state["eq_bands"] = bands
            box.setText(f"{v:.1f} dB")
            self.changed.emit("eq_bands")

        def from_box():
            try:
                s.set_value(float(box.text().lower().replace("db", "").strip()), emit=True)
            except ValueError:
                box.setText(f"{self.state['eq_bands'][i]:.1f} dB")
        s.moved.connect(set_band)
        box.editingFinished.connect(from_box)

    def _eq_preset(self, name):
        pre, bands = P.preset_values(name)
        self.state["eq_preamp"] = pre
        self.state["eq_bands"] = bands
        self.changed.emit("eq_bands")
        QTimer.singleShot(0, self.rebuild)   # the combo that fired this gets replaced

    def _subtitles(self):
        w, lay = self._page()
        d = Card("Defaults")
        self.dropdown(d, "sub_default", "Subtitle Track", P.TRACK_DEFAULTS)
        self.text(d, "sub_lang", "Subtitle Language", "e.g. English")
        self.note(d, "Applied when the next file starts, so every episode picks the same track.")
        lay.addWidget(d)

        s = Card("Synchronization")
        self.slider(s, "sub_delay", "Subtitle Track Delay", -10, 10, 0.05, lambda v: f"{v:.3f} s", ticks=[0])
        self.slider(s, "sub_fps", "Subtitle Speed", 0.2, 5, 0.01, lambda v: f"{v:.3f} fps", ticks=[1])
        self.slider(s, "sub_duration", "Subtitle Duration Factor", 0, 10, 0.1, lambda v: f"{v:.3f}", ticks=[1])
        lay.addWidget(s)

        a = Card("Appearance")
        self.toggle(a, "sub_formatting", "Embedded Sub Format", tip="Use bold/italic/colour tags from the subtitle file")
        self.text(a, "sub_font", "Subtitle Font", "Default")
        self.color(a, "sub_color", "Text Color")
        self.color(a, "sub_outline_color", "Outline Color")
        self.slider(a, "sub_offset", "Subtitle Offset", 0, 300, 1, lambda v: f"{v:.0f}px", ticks=[100, 200])
        self.segment(a, "sub_size_mode", "Size Values", ["Relative", "Pixels"], on_pick=lambda _: QTimer.singleShot(0, self.rebuild))
        if self.state["sub_size_mode"] == "Pixels":
            self.slider(a, "sub_px_size", "Font Size", 8, 96, 1, lambda v: f"{v:.0f}px", ticks=[24, 48, 72])
        else:
            self.dropdown(a, "sub_rel_size", "Font Size", list(P.REL_SIZES))
        self.dropdown(a, "sub_outline", "Outline Thickness", list(P.OUTLINES))
        self.slider(a, "sub_bg_opacity", "Background Opacity", 0, 255, 1,
                    lambda v: f"{v / 255 * 100:.0f}%", ticks=[128])
        self.note(a, "Appearance and speed changes restart playback for a moment to apply.")
        lay.addWidget(a)
        lay.addStretch(1)
        return w

    def _section(self, title):
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{VALUE}; font-size:14px; padding:6px 4px 0;")
        return lbl

    # ---- presets --------------------------------------------------------
    def _fill_presets(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("No preset")
        for n in self.presets.names():
            self.preset_combo.addItem(n)
        if self.current_preset and self.current_preset in self.presets.names():
            self.preset_combo.setCurrentText(self.current_preset)
        self.preset_combo.blockSignals(False)

    def _preset_picked(self, idx):
        name = "" if idx == 0 else self.preset_combo.itemText(idx)
        self.preset_chosen.emit(name)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:",
                                        text=self.current_preset or "")
        if ok and name.strip():
            self.preset_saved.emit(name.strip())
