"""What the library remembers: play history with resume positions, library
folders, saved network streams, playlists and a tag index for music.

Everything lives in one JSON file. The music indexer reads tags in a
background thread with its own headless libVLC instance."""

import json
import os
import re
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import vlc
from PySide6.QtCore import QObject, Signal

DEFAULT_FILE = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "vlc-redesign" / "library.json"
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg", ".ts", ".3gp"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS
MAX_INDEX = 5000   # music files to tag-index per scan


def is_url(s: str) -> bool:
    return "://" in s and not s.lower().startswith("file:")


class LibraryStore(QObject):
    changed = Signal()

    def __init__(self, path: Path = DEFAULT_FILE):
        super().__init__()
        self.path = Path(path)
        self.d = {"history": {}, "video_roots": [], "music_roots": [], "streams": [],
                  "playlists": {}, "playlist_plays": {}, "music_index": {}, "pinned": []}
        try:
            self.d.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            for name, key in (("Videos", "video_roots"), ("Music", "music_roots")):
                p = Path.home() / name
                if p.is_dir():
                    self.d[key].append(str(p))
        self._lock = threading.Lock()

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d), encoding="utf-8")
            tmp.replace(self.path)

    # ---- history ----------------------------------------------------------
    def record_play(self, item: str, kind: str, title: str = "", artist: str = ""):
        h = self.d["history"].setdefault(item, {"plays": 0, "pos": 0, "length": 0})
        h.update(kind=kind, title=title or h.get("title", ""), artist=artist or h.get("artist", ""),
                 last=time.time())
        h["plays"] += 1
        self.save()
        self.changed.emit()

    def set_meta(self, item: str, title: str = "", artist: str = ""):
        h = self.d["history"].get(item)
        if h and (title, artist) != (h.get("title"), h.get("artist")):
            h["title"], h["artist"] = title or h.get("title", ""), artist or h.get("artist", "")
            self.save()

    def record_position(self, item: str, pos_ms: int, length_ms: int, save=True):
        h = self.d["history"].get(item)
        if h is None or length_ms <= 0:
            return
        h["pos"], h["length"] = int(pos_ms), int(length_ms)
        if save:
            self.save()

    def resume_point(self, item: str) -> int:
        """Where to continue from, or 0 when the file is new, nearly done or short."""
        h = self.d["history"].get(item)
        if not h or h.get("length", 0) < 60_000:
            return 0
        frac = h["pos"] / h["length"]
        return h["pos"] if 0.03 < frac < 0.95 else 0

    def progress(self, item: str) -> float | None:
        h = self.d["history"].get(item)
        if not h or not h.get("length"):
            return None
        return min(1.0, h["pos"] / h["length"])

    def watched(self, item: str) -> bool:
        p = self.progress(item)
        return p is not None and p >= 0.95

    def _existing(self, items):
        return [(k, v) for k, v in items if is_url(k) or Path(k).exists()]

    def continue_watching(self, n=20):
        items = [(k, v) for k, v in self.d["history"].items()
                 if v.get("kind") == "video" and self.resume_point(k)]
        return self._existing(sorted(items, key=lambda kv: -kv[1].get("last", 0)))[:n]

    def listen_again(self, n=20):
        items = [(k, v) for k, v in self.d["history"].items() if v.get("kind") == "audio"]
        return self._existing(sorted(items, key=lambda kv: -kv[1].get("last", 0)))[:n]

    def recent(self, n=50):
        return self._existing(sorted(self.d["history"].items(), key=lambda kv: -kv[1].get("last", 0)))[:n]

    def frequent_folders(self, n=10):
        counts = {}
        for k, v in self.d["history"].items():
            if not is_url(k):
                f = str(Path(k).parent)
                counts[f] = counts.get(f, 0) + v.get("plays", 1)
        return [f for f, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if Path(f).is_dir()][:n]

    def frequent_artists(self, n=10):
        counts = {}
        for k, v in self.d["history"].items():
            a = v.get("artist") or self.d["music_index"].get(k, {}).get("artist")
            if v.get("kind") == "audio" and a:
                counts[a] = counts.get(a, 0) + v.get("plays", 1)
        return [a for a, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:n]

    def forget(self, item: str):
        self.d["history"].pop(item, None)
        self.save()
        self.changed.emit()

    # ---- roots ------------------------------------------------------------
    def add_root(self, kind: str, folder: Path):
        key = f"{kind}_roots"
        if str(folder) not in self.d[key]:
            self.d[key].append(str(folder))
            self.save()
            self.changed.emit()

    def remove_root(self, kind: str, folder: str):
        key = f"{kind}_roots"
        if folder in self.d[key]:
            self.d[key].remove(folder)
            self.d["pinned"] = [p for p in self.d["pinned"] if p["path"] != folder]
            self.save()
            self.changed.emit()

    # ---- pinned folders (shown in the full library's left column) ----------
    def pinned(self):
        return [p for p in self.d.setdefault("pinned", []) if Path(p["path"]).is_dir()]

    def pin(self, folder: Path, kind: str):
        pins = self.d.setdefault("pinned", [])
        if not any(p["path"] == str(folder) for p in pins):
            pins.append({"path": str(folder), "kind": kind})
            self.save()
            self.changed.emit()

    def unpin(self, folder: str):
        self.d["pinned"] = [p for p in self.d.setdefault("pinned", []) if p["path"] != folder]
        self.save()
        self.changed.emit()


    # ---- network streams ------------------------------------------------
    def add_stream(self, name: str, url: str, channels=None):
        self.d["streams"] = [s for s in self.d["streams"] if s["url"] != url]
        entry = {"name": name, "url": url}
        if channels:
            entry["channels"] = channels
        self.d["streams"].append(entry)
        self.save()
        self.changed.emit()

    def remove_stream(self, url: str):
        self.d["streams"] = [s for s in self.d["streams"] if s["url"] != url]
        self.save()
        self.changed.emit()

    # ---- playlists ------------------------------------------------------
    def playlists(self):
        return self.d["playlists"]

    def create_playlist(self, name: str, items=()):
        self.d["playlists"].setdefault(name, [])
        for i in items:
            if i not in self.d["playlists"][name]:
                self.d["playlists"][name].append(i)
        self.save()
        self.changed.emit()

    def add_to_playlist(self, name: str, items):
        self.create_playlist(name, items)

    def remove_from_playlist(self, name: str, item: str):
        if item in self.d["playlists"].get(name, []):
            self.d["playlists"][name].remove(item)
            self.save()
            self.changed.emit()

    def delete_playlist(self, name: str):
        self.d["playlists"].pop(name, None)
        self.d["playlist_plays"].pop(name, None)
        self.save()
        self.changed.emit()

    def record_playlist_play(self, name: str):
        self.d["playlist_plays"][name] = self.d["playlist_plays"].get(name, 0) + 1
        self.save()

    def frequent_playlists(self, n=10):
        plays = self.d["playlist_plays"]
        names = [p for p in self.d["playlists"] if plays.get(p)]
        return sorted(names, key=lambda p: -plays[p])[:n]

    # ---- music index ----------------------------------------------------
    def music_files(self):
        return {k: v for k, v in self.d["music_index"].items() if Path(k).exists()}

    def group_music(self, field: str):
        groups = {}
        for path, tags in self.music_files().items():
            key = tags.get(field) or f"Unknown {field.title()}"
            groups.setdefault(key, []).append(path)
        return dict(sorted(groups.items(), key=lambda kv: kv[0].lower()))


class MusicIndexer(QObject):
    """Reads title / artist / album / genre for music under the music roots."""

    done = Signal(int)

    def __init__(self, store: LibraryStore):
        super().__init__()
        self.store = store
        self._running = False

    def scan(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        added = 0
        try:
            index = self.store.d["music_index"]
            files = []
            for root in list(self.store.d["music_roots"]):
                for dirpath, _, names in os.walk(root):
                    files += [Path(dirpath) / n for n in names if Path(n).suffix.lower() in AUDIO_EXTS]
                    if len(files) >= MAX_INDEX:
                        break
            todo = []
            for f in files[:MAX_INDEX]:
                try:
                    mtime = int(f.stat().st_mtime)
                except OSError:
                    continue
                if index.get(str(f), {}).get("mtime") != mtime:
                    todo.append((f, mtime))
            if todo:
                inst = vlc.Instance(["--quiet", "--intf=dummy", "--no-video"])
                for f, mtime in todo:
                    m = inst.media_new(str(f))
                    m.parse_with_options(vlc.MediaParseFlag.local, 3000)
                    t = time.time()
                    while m.get_parsed_status() == 0 and time.time() - t < 3.5:
                        time.sleep(0.01)
                    title = m.get_meta(vlc.Meta.Title) or f.stem
                    if title == f.name:
                        title = f.stem
                    index[str(f)] = {"mtime": mtime, "title": title,
                                     "artist": m.get_meta(vlc.Meta.Artist) or "",
                                     "album": m.get_meta(vlc.Meta.Album) or "",
                                     "genre": m.get_meta(vlc.Meta.Genre) or "",
                                     "length": m.get_duration()}
                    m.release()
                    added += 1
                inst.release()
                self.store.save()
        finally:
            self._running = False
            self.done.emit(added)


# ---- m3u playlists from the web ------------------------------------------
_EXTINF = re.compile(r'#EXTINF:[^,]*,(.*)')


def fetch_m3u(url: str, limit=5000):
    """Channel list [(name, url)] of an .m3u / .m3u8 playlist, or [] when the URL
    isn't a playlist (a plain stream)."""
    req = urllib.request.Request(url, headers={"User-Agent": "VLC-Redesign/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        head = r.read(2_000_000).decode("utf-8", "replace")
    if "#EXTM3U" not in head[:200] and "#EXTINF" not in head:
        return []
    out, name = [], None
    for line in head.splitlines():
        line = line.strip()
        m = _EXTINF.match(line)
        if m:
            name = m.group(1).strip()
        elif line and not line.startswith("#"):
            out.append({"name": name or line.rsplit("/", 1)[-1], "url": line})
            name = None
            if len(out) >= limit:
                break
    # A master HLS playlist (variants of one stream) isn't a channel list.
    if head.count("#EXT-X-STREAM-INF") and not head.count("#EXTINF"):
        return []
    return out


def guess_folder_kind(folder: Path, limit=400) -> str:
    """"music" when a folder holds mostly audio files, otherwise "video"."""
    audio = video = 0
    for dirpath, _, names in os.walk(folder):
        for n in names:
            ext = Path(n).suffix.lower()
            audio += ext in AUDIO_EXTS
            video += ext in VIDEO_EXTS
        if audio + video >= limit:
            break
    return "music" if audio > video else "video"
