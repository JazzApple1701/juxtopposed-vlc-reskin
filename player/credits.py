"""Who actually made this. VLC Reskin only applies someone else's design to someone
else's player; this is shown in the About box and on the start page."""

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

import theme as T

VIDEO_URL = "https://www.youtube.com/watch?v=ERFeOgqk324"
FIGMA_URL = "https://www.figma.com/community/file/1691465999134370980"
DESIGNER_URL = "https://figma.com/@juxtopposed"
CC_BY_URL = "https://creativecommons.org/licenses/by/4.0/"
VLC_URL = "https://www.videolan.org/vlc/"
DONATE_URL = "https://www.videolan.org/contribute.html#money"
REPO_URL = ""   # filled in once the project is published

_A = f"color:{T.ACCENT};text-decoration:none"


def _a(url, text):
    return f'<a href="{url}" style="{_A}">{text}</a>'


ABOUT_HTML = f"""
<p style="font-size:15px;color:#ececec"><b>VLC Reskin</b>, an unofficial reskin of VLC media player</p>
<p><b>The design is not mine.</b> Every screen here comes from <b>Juxtopposed</b>'s
"VLC Redesign": the video {_a(VIDEO_URL, "I Redesigned VLC After 25 Years")} and the
{_a(FIGMA_URL, "Figma design file")} ({_a(DESIGNER_URL, "@juxtopposed")}), licensed
{_a(CC_BY_URL, "CC BY 4.0")}. This app just applies that design.</p>
<p><b>The player is not mine either.</b> All playback (every format, subtitles, streaming) is
{_a(VLC_URL, "VLC")} by VideoLAN and its volunteers, through libVLC. If you like this,
<b>please {_a(DONATE_URL, "donate to VideoLAN")}</b> to support the real VLC.</p>
<p style="color:#8a8a8a">Not affiliated with or endorsed by VideoLAN or Juxtopposed. VLC and the cone
are trademarks of VideoLAN. Reskin code by Jasim Khan (MIT licence).</p>
"""

FOOTER_HTML = (f'Design by {_a(FIGMA_URL, "Juxtopposed")} ({_a(VIDEO_URL, "video")}), CC BY 4.0 · '
               f'Playback by {_a(VLC_URL, "VLC")} from VideoLAN · '
               f'{_a(DONATE_URL, "Donate to VLC")} · Unofficial reskin')


class AboutDialog(QDialog):
    def __init__(self, parent=None, libvlc_version=""):
        super().__init__(parent)
        self.setWindowTitle("About VLC Reskin")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"QDialog{{background:{T.SHELL}}} QLabel{{color:#cfcfcf;font-size:13px}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)
        text = QLabel(ABOUT_HTML + (f'<p style="color:#6a6a6a">libVLC {libvlc_version}</p>' if libvlc_version else ""))
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setOpenExternalLinks(True)
        lay.addWidget(text)

        row = QHBoxLayout()
        row.setSpacing(8)
        for label, url, primary in (("Donate to VLC", DONATE_URL, True), ("Watch the video", VIDEO_URL, False),
                                    ("Open the design", FIGMA_URL, False)):
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:{T.ACCENT if primary else '#262626'};color:{'#1b1b1b' if primary else '#ddd'};"
                "border:none;border-radius:6px;padding:7px 14px;font-size:13px}"
                f"QPushButton:hover{{background:{'#e58a2a' if primary else '#303030'}}}")
            b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet("QPushButton{background:transparent;color:#aaa;border:1px solid #3a3a3a;"
                            "border-radius:6px;padding:7px 14px}QPushButton:hover{color:#fff}")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)


def footer_label() -> QLabel:
    """One-line credit for the bottom of the start page."""
    lbl = QLabel(FOOTER_HTML)
    lbl.setTextFormat(Qt.RichText)
    lbl.setOpenExternalLinks(True)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color:#6f6f6f;font-size:12px;padding:8px 4px 6px")
    return lbl
