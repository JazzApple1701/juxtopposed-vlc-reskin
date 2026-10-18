"""Line icons drawn to match the Figma icon set (24x24, 1.5px strokes).

`{c}` in each SVG is replaced with the requested color, so one icon can be
rendered in its normal and hover states.
"""

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_S = 'fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"'

SVG = {
    "vlc": """
        <path d="M9.2 4h5.6l1.1 4H8.1z" fill="#f08a1c"/>
        <path d="M7.6 10h8.8l1.1 4.2H6.5z" fill="#f08a1c"/>
        <path d="M8.6 8h6.8l.5 2H8.1zM6.9 14.2h10.2l.7 2.3H6.2z" fill="#f5f5f5"/>
        <path d="M4 17.5h16l-.8 2.5H4.8z" fill="#f08a1c"/>""",
    "more": """
        <circle cx="6" cy="12" r="1.3" fill="{c}"/><circle cx="12" cy="12" r="1.3" fill="{c}"/>
        <circle cx="18" cy="12" r="1.3" fill="{c}"/>""",
    "sidebar": f'<rect x="4" y="4.5" width="16" height="15" rx="2" {_S}/><path d="M9.5 4.5v15" {_S}/>',
    "folder": f'<path d="M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4l2 2.2h8a1.5 1.5 0 0 1 1.5 1.5V17a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 17z" {_S}/>',
    "minimize": f'<path d="M6 12h12" {_S}/>',
    "maximize": f'<rect x="6" y="6" width="12" height="12" rx="1" {_S}/>',
    "restore": f'<rect x="6" y="8.5" width="9.5" height="9.5" rx="1" {_S}/><path d="M8.5 6h8.5a1 1 0 0 1 1 1v8.5" {_S}/>',
    "fullscreen": f'<path d="M5 9V6a1 1 0 0 1 1-1h3M15 5h3a1 1 0 0 1 1 1v3M19 15v3a1 1 0 0 1-1 1h-3M9 19H6a1 1 0 0 1-1-1v-3" {_S}/>',
    "fullscreen_exit": f'<path d="M9 5v3a1 1 0 0 1-1 1H5M19 9h-3a1 1 0 0 1-1-1V5M15 19v-3a1 1 0 0 1 1-1h3M5 15h3a1 1 0 0 1 1 1v3" {_S}/>',
    "close": f'<path d="M6.5 6.5l11 11M17.5 6.5l-11 11" {_S}/>',
    "previous": '<path d="M7 6.5v11" stroke="{c}" stroke-width="2" stroke-linecap="round"/><path d="M17.5 6.8v10.4a.6.6 0 0 1-.9.5L9.4 12.5a.6.6 0 0 1 0-1l7.2-5.2a.6.6 0 0 1 .9.5z" fill="{c}"/>',
    "next": '<path d="M17 6.5v11" stroke="{c}" stroke-width="2" stroke-linecap="round"/><path d="M6.5 6.8v10.4a.6.6 0 0 0 .9.5l7.2-5.2a.6.6 0 0 0 0-1L7.4 6.3a.6.6 0 0 0-.9.5z" fill="{c}"/>',
    # Centred on its bounding box (measured), so it sits in the middle of round / pill buttons.
    "play": '<path d="M6.4 5.8v12.4a.8.8 0 0 0 1.2.7l9.6-6.2a.8.8 0 0 0 0-1.4L7.6 5.1A.8.8 0 0 0 6.4 5.8z" fill="{c}"/>',
    "pause": '<rect x="7" y="5.5" width="3.4" height="13" rx="1" fill="{c}"/><rect x="13.6" y="5.5" width="3.4" height="13" rx="1" fill="{c}"/>',
    "back15": f'<path d="M5.5 12a6.5 6.5 0 1 0 2-4.7" {_S}/><path d="M5.5 4.5v3.3h3.3" {_S}/>'
              '<text x="12.3" y="15.2" font-size="6.5" font-family="Segoe UI" fill="{c}" text-anchor="middle">15</text>',
    "fwd15": f'<path d="M18.5 12a6.5 6.5 0 1 1-2-4.7" {_S}/><path d="M18.5 4.5v3.3h-3.3" {_S}/>'
             '<text x="11.7" y="15.2" font-size="6.5" font-family="Segoe UI" fill="{c}" text-anchor="middle">15</text>',
    "volume": f'<path d="M4.5 9.5h3l4-3.5v12l-4-3.5h-3z" {_S}/><path d="M15 9.5v5M18 8v8" {_S}/>',
    "volume_low": f'<path d="M4.5 9.5h3l4-3.5v12l-4-3.5h-3z" {_S}/><path d="M15 10.5v3" {_S}/>',
    "volume_mute": f'<path d="M4.5 9.5h3l4-3.5v12l-4-3.5h-3z" {_S}/><path d="M15 9.5l5 5M20 9.5l-5 5" {_S}/>',
    "eq": f'<path d="M4 11v2M7.2 8v8M10.4 5v14M13.6 8.5v7M16.8 6.5v11M20 10.5v3" {_S}/>',
    "subtitles": f'<rect x="3.5" y="5.5" width="17" height="13" rx="2" {_S}/><path d="M7 14.5h4M13.5 14.5H17M7 11.5h7" {_S}/>',
    "settings": f'<path d="M12 3.8l2 1.2 2.3-.2 1.1 2 2 1.2-.2 2.3 1.1 1.7-1.1 1.7.2 2.3-2 1.2-1.1 2-2.3-.2-2 1.2-2-1.2-2.3.2-1.1-2-2-1.2.2-2.3L3.7 12l1.1-1.7-.2-2.3 2-1.2 1.1-2 2.3.2z" {_S}/><circle cx="12" cy="12" r="2.8" {_S}/>',
    "playlist": f'<path d="M9 7h11M9 12h11M9 17h11" {_S}/><circle cx="4.8" cy="7" r=".9" fill="{{c}}"/><circle cx="4.8" cy="12" r=".9" fill="{{c}}"/><circle cx="4.8" cy="17" r=".9" fill="{{c}}"/>',
    "chevron_left": f'<path d="M14.5 6l-6 6 6 6" {_S}/>',
    "chevron_right": f'<path d="M9.5 6l6 6-6 6" {_S}/>',
    "chevron_down": f'<path d="M6 9.5l6 6 6-6" {_S}/>',
    "search": f'<circle cx="11" cy="11" r="6" {_S}/><path d="M15.5 15.5L20 20" {_S}/>',
    "sort": f'<path d="M8 5v14M8 19l-3-3M8 19l3-3M16 19V5M16 5l-3 3M16 5l3 3" {_S}/>',
    "popout": f'<path d="M13 4.5h6.5V11M19.5 4.5L12 12M10 5.5H6A1.5 1.5 0 0 0 4.5 7v11A1.5 1.5 0 0 0 6 19.5h11a1.5 1.5 0 0 0 1.5-1.5v-4" {_S}/>',
    "refresh": f'<path d="M19 12a7 7 0 1 1-2-4.9M19 4.5v3.3h-3.3" {_S}/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="{a}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "home": f'<path d="M4.5 10.5L12 4.5l7.5 6V19a1 1 0 0 1-1 1h-4v-5.5h-5V20h-4a1 1 0 0 1-1-1z" {_S}/>',
    "music": f'<path d="M9 17.5V6l10-2v11.5" {_S}/><circle cx="6.8" cy="17.5" r="2.3" {_S}/><circle cx="16.8" cy="15.5" r="2.3" {_S}/>',
    "video": f'<rect x="3.5" y="6" width="12.5" height="12" rx="2" {_S}/><path d="M16 10.5l4.5-2.5v8L16 13.5" {_S}/>',
    "add": f'<path d="M12 5v14M5 12h14" {_S}/>',
    "grid": f'<rect x="4.5" y="4.5" width="6" height="6" rx="1.2" {_S}/><rect x="13.5" y="4.5" width="6" height="6" rx="1.2" {_S}/>'
            f'<rect x="4.5" y="13.5" width="6" height="6" rx="1.2" {_S}/><rect x="13.5" y="13.5" width="6" height="6" rx="1.2" {_S}/>',
    "list_view": f'<path d="M10 7h10M10 12h10M10 17h10" {_S}/><rect x="4" y="5.5" width="3" height="3" rx=".6" {_S}/>'
                 f'<rect x="4" y="10.5" width="3" height="3" rx=".6" {_S}/><rect x="4" y="15.5" width="3" height="3" rx=".6" {_S}/>',
    # Menu icons: grey outlines with an orange accent ({a}), as in the Figma menus.
    "m_file": f'<rect x="5" y="3.5" width="14" height="17" rx="2.5" {_S}/><rect x="7.5" y="6" width="3.6" height="3.6" rx="1" fill="{{a}}"/>',
    "m_folder": f'<path d="M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4l2 2.2h8a1.5 1.5 0 0 1 1.5 1.5V17a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 17z" {_S}/>',
    "m_network": '<circle cx="12" cy="12" r="2" fill="{a}"/>'
                 f'<path d="M8.6 8.6a4.8 4.8 0 0 0 0 6.8M15.4 8.6a4.8 4.8 0 0 1 0 6.8M5.8 5.8a8.8 8.8 0 0 0 0 12.4M18.2 5.8a8.8 8.8 0 0 1 0 12.4" {_S.replace("{c}", "{a}")}/>',
    "m_disc": f'<circle cx="12" cy="12" r="8.5" {_S}/><circle cx="12" cy="12" r="2.4" fill="none" stroke="{{a}}" stroke-width="1.5"/><path d="M7.5 9.5a5 5 0 0 1 2.5-2.8" stroke="{{a}}" stroke-width="1.5" fill="none" stroke-linecap="round"/>',
    "m_capture": f'<path d="M5 4h14v12H5zM9 16v4h6v-4" {_S}/><path d="M10.5 8v4.5l3.5-2.2z" fill="{{a}}"/>',
    "m_convert": f'<path d="M5 8h13M15 5l3 3-3 3" {_S}/><path d="M19 16H6M9 13l-3 3 3 3" {_S.replace("{c}", "{a}")}/>',
    "m_recent": f'<path d="M5 12a7 7 0 1 0 2.1-5M5 4.5v3.3h3.3" {_S}/><circle cx="12" cy="12" r="1.8" fill="{{a}}"/>',
    "m_profile": f'<circle cx="12" cy="8.5" r="3.5" {_S.replace("{c}", "{a}")}/><path d="M5 20a7 7 0 0 1 14 0" {_S.replace("{c}", "{a}")}/>',
    "m_keyboard": f'<rect x="3" y="6.5" width="18" height="11" rx="2" {_S}/><path d="M6.5 10h.01M9.5 10h.01M12.5 10h.01M15.5 10h.01M8.5 14h7" stroke="{{a}}" stroke-width="1.8" stroke-linecap="round"/>',
    "m_brush": f'<path d="M19.5 4.5l-8 8" {_S}/><path d="M11 13c-3 0-4 2-4 3.5S5.5 19.5 4.5 19.5c3.5 1.5 8 0 8-4.5z" {_S.replace("{c}", "{a}")}/>',
    "m_info": f'<circle cx="12" cy="12" r="8.5" {_S}/><path d="M12 11v5.5" {_S}/><circle cx="12" cy="7.8" r="1" fill="{{c}}"/>',
    # Right-click menu icons (orange outlines).
    "r_play": f'<path d="M7.5 5.5v13l10.5-6.5z" {_S}/>',
    "r_stop": f'<rect x="6.5" y="6.5" width="11" height="11" rx="1" {_S}/>',
    "r_prev": f'<path d="M6.5 6v12M17.5 6.5v11L9.5 12z" {_S}/>',
    "r_next": f'<path d="M17.5 6v12M6.5 6.5v11l8-5.5z" {_S}/>',
    "r_record": f'<circle cx="12" cy="12" r="8" {_S}/><circle cx="12" cy="12" r="3.5" fill="{{c}}"/>',
    "r_hide": f'<rect x="4.5" y="4.5" width="15" height="15" rx="2" {_S}/><path d="M8 8l8 8" {_S}/>',
    "r_playback": f'<path d="M8 5.2a1.5 1.5 0 0 1 2.2-1.3l9 6.8a1.6 1.6 0 0 1 0 2.6l-9 6.8A1.5 1.5 0 0 1 8 18.8z" {_S}/><path d="M11 9.5v5l3.5-2.5z" fill="{{c}}"/>',
    "r_video": f'<rect x="4" y="8" width="16" height="11.5" rx="1.5" {_S}/><path d="M4 8l1.5-3.5h13L20 8M8.5 4.5L7 8M13 4.5L11.5 8M17.5 4.5L16 8" {_S}/>',
    "r_open": f'<rect x="5" y="3.5" width="14" height="17" rx="2.5" {_S}/><rect x="7.5" y="6" width="3.6" height="3.6" rx="1" fill="{{c}}"/>',
    "r_quit": f'<path d="M10 4.5H6a1.5 1.5 0 0 0-1.5 1.5v12A1.5 1.5 0 0 0 6 19.5h4M14 8l4 4-4 4M18 12H9" {_S}/>',
    "r_queue": f'<path d="M4 7h12M4 12h9M4 17h7" {_S}/><path d="M15 14v6l5-3z" fill="{{c}}"/>',
}


def pixmap(name: str, color: str, size: int = 20, scale: float = 2.0, accent: str = "#d37918") -> QPixmap:
    body = SVG[name].replace("{c}", color).replace("{a}", accent)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">' + body + "</svg>"
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    px = QPixmap(int(size * scale), int(size * scale))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, px.width(), px.height()))
    p.end()
    px.setDevicePixelRatio(scale)
    return px


def icon(name: str, color: str, hover: str | None = None, size: int = 20) -> QIcon:
    ic = QIcon(pixmap(name, color, size))
    if hover:
        ic.addPixmap(pixmap(name, hover, size), QIcon.Active)
    return ic
