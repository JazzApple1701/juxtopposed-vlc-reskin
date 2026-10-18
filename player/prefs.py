"""Preferences model for the sidebar: defaults, which settings apply live, and
how the rest turn into libVLC engine options.

libVLC 3 only lets some things change during playback (speed, picture adjust,
crop, delays, equalizer). Filters and subtitle styling are engine options, so
changing them restarts the engine; the player keeps the position."""

import json
import re
from pathlib import Path

import vlc

DEFAULTS = {
    # Playback
    "rate": 1.0,
    "sleep": "Off",
    "sub_timeline": False,
    "waveform": True,
    # General (whole app, never part of a per-show preset)
    "home_style": "Start screen",
    "start_on_home": True,
    # Video: live
    "hue": 0.0, "brightness": 1.0, "contrast": 1.0, "saturation": 1.0, "gamma": 1.0,
    "crop": "Default", "aspect": "Default", "zoom": "Fit",
    # Video: engine
    "transform": "None", "sharpen": 0.0, "grain": 0.0, "banding": 0,
    "negate": False, "posterize": False, "sepia": 0, "gradient": "Off", "cartoon": False,
    # Audio
    "audio_delay": 0.0, "audio_default": "Auto", "audio_lang": "",
    "eq_preset": "None", "eq_preamp": 0.0, "eq_bands": [0.0] * 10,
    "compressor": False, "spatializer": False, "stereo_widener": False,
    # Subtitles: live
    "sub_delay": 0.0,
    # Subtitles: on the next file
    "sub_default": "Auto", "sub_lang": "",
    # Subtitles: engine
    "sub_fps": 1.0, "sub_duration": 0.0, "sub_formatting": True,
    "sub_font": "", "sub_color": "#FFFFFF", "sub_outline_color": "#000000", "sub_offset": 0,
    "sub_size_mode": "Relative", "sub_rel_size": "Auto", "sub_px_size": 24,
    "sub_outline": "Normal", "sub_bg_opacity": 0,
}

APP_KEYS = {"home_style", "start_on_home"}
HOME_STYLES = ["Start screen", "Classic"]

ENGINE_KEYS = {
    "transform", "sharpen", "grain", "banding", "negate", "posterize", "sepia", "gradient", "cartoon",
    "compressor", "spatializer", "stereo_widener",
    "sub_fps", "sub_duration", "sub_formatting", "sub_font", "sub_color", "sub_outline_color",
    "sub_offset", "sub_size_mode", "sub_rel_size", "sub_px_size", "sub_outline", "sub_bg_opacity",
}

CROPS = ["Default", "16:9", "4:3", "1.85:1", "2.39:1", "5:4", "1:1"]
ASPECTS = ["Default", "16:9", "4:3", "16:10", "1:1", "2.21:1", "2.35:1", "5:4"]
ZOOMS = {"Fit": 0.0, "50%": 0.5, "100%": 1.0, "200%": 2.0}
TRANSFORMS = {"None": None, "Flip horizontally": "hflip", "Flip vertically": "vflip",
              "Rotate 90°": "90", "Rotate 180°": "180", "Rotate 270°": "270"}
GRADIENTS = {"Off": None, "Gradient": "gradient", "Edge": "edge", "Hough": "hough"}
REL_SIZES = {"Auto": 0, "Smaller": 20, "Small": 18, "Normal": 16, "Large": 12, "Larger": 6}
OUTLINES = {"None": 0, "Thin": 2, "Normal": 4, "Thick": 6}
SLEEP = {"Off": 0, "15 min": 15, "30 min": 30, "45 min": 45, "60 min": 60, "End of file": -1}
TRACK_DEFAULTS = ["Auto", "Off", "Track 1", "Track 2", "Track 3", "By language"]


def _rgb_int(hex_color: str) -> int:
    try:
        return int(hex_color.lstrip("#")[:6], 16)
    except ValueError:
        return 0xFFFFFF


def engine_args(s: dict) -> list[str]:
    """libVLC instance options for everything in ENGINE_KEYS."""
    args = []
    vf = []
    if TRANSFORMS.get(s["transform"]):
        vf.append("transform")
        args.append(f"--transform-type={TRANSFORMS[s['transform']]}")
    if s["sharpen"] > 0:
        vf.append("sharpen")
        args.append(f"--sharpen-sigma={s['sharpen']:.2f}")
    if s["grain"] > 0:
        vf.append("grain")
        args.append(f"--grain-variance={s['grain']:.2f}")
    if s["banding"] > 0:
        vf.append("gradfun")
        args.append(f"--gradfun-radius={int(s['banding'])}")
    if s["negate"]:
        vf.append("invert")
    if s["posterize"]:
        vf.append("posterize")
    if s["sepia"] > 0:
        vf.append("sepia")
        args.append(f"--sepia-intensity={int(s['sepia'])}")
    if GRADIENTS.get(s["gradient"]):
        vf.append("gradient")
        args.append(f"--gradient-mode={GRADIENTS[s['gradient']]}")
        args.append("--gradient-cartoon" if s["cartoon"] else "--no-gradient-cartoon")
    if vf:
        args.append("--video-filter=" + ":".join(vf))

    af = [name for key, name in (("compressor", "compressor"), ("spatializer", "spatializer"),
                                 ("stereo_widener", "stereo_widen")) if s[key]]
    if af:
        args.append("--audio-filter=" + ",".join(af))

    if abs(s["sub_fps"] - 1.0) > 1e-3:
        args.append(f"--sub-fps={s['sub_fps']:.3f}")
    if s["sub_duration"] > 0:
        args += ["--sub-source=subsdelay", "--subsdelay-mode=1", f"--subsdelay-factor={s['sub_duration']:.2f}"]
    if not s["sub_formatting"]:
        args.append("--no-subsdec-formatting")
    if s["sub_font"].strip():
        args.append(f"--freetype-font={s['sub_font'].strip()}")
    if s["sub_color"].upper() != "#FFFFFF":
        args.append(f"--freetype-color={_rgb_int(s['sub_color'])}")
    if s["sub_outline_color"].upper() != "#000000":
        args.append(f"--freetype-outline-color={_rgb_int(s['sub_outline_color'])}")
    if s["sub_offset"]:
        args.append(f"--sub-margin={int(s['sub_offset'])}")
    if s["sub_size_mode"] == "Pixels":
        args.append(f"--freetype-fontsize={int(s['sub_px_size'])}")
    elif REL_SIZES.get(s["sub_rel_size"]):
        args.append(f"--freetype-rel-fontsize={REL_SIZES[s['sub_rel_size']]}")
    if s["sub_outline"] != "Normal":
        args.append(f"--freetype-outline-thickness={OUTLINES[s['sub_outline']]}")
    if s["sub_bg_opacity"] > 0:
        args.append(f"--freetype-background-opacity={int(s['sub_bg_opacity'])}")
    return args


# ---- live settings ---------------------------------------------------------
def eq_presets() -> list[str]:
    n = vlc.libvlc_audio_equalizer_get_preset_count()
    names = [vlc.libvlc_audio_equalizer_get_preset_name(i) for i in range(n)]
    return ["None"] + [x.decode() if isinstance(x, bytes) else str(x) for x in names]


def eq_bands() -> list[str]:
    out = []
    for i in range(vlc.libvlc_audio_equalizer_get_band_count()):
        f = vlc.libvlc_audio_equalizer_get_band_frequency(i)
        out.append(f"{f / 1000:g} KHz" if f >= 1000 else f"{f:g} Hz")
    return out


def preset_values(name: str):
    """(preamp, bands) of a built-in equalizer preset."""
    names = eq_presets()
    if name not in names or name == "None":
        return 0.0, [0.0] * 10
    eq = vlc.libvlc_audio_equalizer_new_from_preset(names.index(name) - 1)
    pre = vlc.libvlc_audio_equalizer_get_preamp(eq)
    bands = [vlc.libvlc_audio_equalizer_get_amp_at_index(eq, i) for i in range(10)]
    vlc.libvlc_audio_equalizer_release(eq)
    return round(pre, 1), [round(b, 1) for b in bands]


def apply_live(player, s: dict, key: str | None = None):
    """Apply live settings to `player` (all of them when key is None)."""
    def want(*keys):
        return key is None or key in keys

    if want("rate"):
        player.set_rate(float(s["rate"]))
    if want("hue", "brightness", "contrast", "saturation", "gamma"):
        changed = any(abs(s[k] - DEFAULTS[k]) > 1e-3 for k in ("hue", "brightness", "contrast", "saturation", "gamma"))
        player.video_set_adjust_int(vlc.VideoAdjustOption.Enable, 1 if changed else 0)
        if changed:
            player.video_set_adjust_float(vlc.VideoAdjustOption.Hue, float(s["hue"]))
            player.video_set_adjust_float(vlc.VideoAdjustOption.Brightness, float(s["brightness"]))
            player.video_set_adjust_float(vlc.VideoAdjustOption.Contrast, float(s["contrast"]))
            player.video_set_adjust_float(vlc.VideoAdjustOption.Saturation, float(s["saturation"]))
            player.video_set_adjust_float(vlc.VideoAdjustOption.Gamma, float(s["gamma"]))
    if want("crop"):
        player.video_set_crop_geometry(None if s["crop"] == "Default" else s["crop"])
    if want("aspect"):
        player.video_set_aspect_ratio(None if s["aspect"] == "Default" else s["aspect"])
    if want("zoom"):
        player.video_set_scale(ZOOMS.get(s["zoom"], 0.0))
    if want("audio_delay"):
        player.audio_set_delay(int(s["audio_delay"] * 1_000_000))
    if want("sub_delay"):
        player.video_set_spu_delay(int(s["sub_delay"] * 1_000_000))
    if want("eq_preset", "eq_preamp", "eq_bands"):
        if s["eq_preset"] == "None" and not any(s["eq_bands"]) and not s["eq_preamp"]:
            player.set_equalizer(None)
        else:
            eq = vlc.AudioEqualizer()
            eq.set_preamp(float(s["eq_preamp"]))
            for i, amp in enumerate(s["eq_bands"]):
                eq.set_amp_at_index(float(amp), i)
            player.set_equalizer(eq)


def pick_default_track(items, mode: str, lang: str):
    """Track id to select for a new file, or None to leave libVLC's choice."""
    real = [(i, n) for i, n in items if i != -1]
    if mode == "Off":
        return -1
    if mode.startswith("Track "):
        k = int(mode.split()[1]) - 1
        return real[k][0] if k < len(real) else None
    if mode == "By language" and lang.strip():
        want = lang.strip().lower()
        for i, n in real:
            if want in n.lower():
                return i
    return None


# ---- presets ---------------------------------------------------------------
class PresetStore:
    """Named presets kept in QSettings as JSON, plus which folder ("show") uses
    which preset so it comes back automatically for the next episode."""

    def __init__(self, qsettings):
        self.q = qsettings

    def names(self) -> list[str]:
        return sorted(json.loads(self.q.value("presets", "{}") or "{}").keys())

    def get(self, name):
        return json.loads(self.q.value("presets", "{}") or "{}").get(name)

    def save(self, name, state: dict, folder: Path | None):
        all_ = json.loads(self.q.value("presets", "{}") or "{}")
        all_[name] = state
        self.q.setValue("presets", json.dumps(all_))
        if folder:
            self.bind(folder, name)

    def delete(self, name):
        all_ = json.loads(self.q.value("presets", "{}") or "{}")
        all_.pop(name, None)
        self.q.setValue("presets", json.dumps(all_))
        binds = {k: v for k, v in self._binds().items() if v != name}
        self.q.setValue("preset_folders", json.dumps(binds))

    def _binds(self):
        return json.loads(self.q.value("preset_folders", "{}") or "{}")

    def bind(self, folder: Path, name: str | None):
        binds = self._binds()
        if name:
            binds[str(folder)] = name
        else:
            binds.pop(str(folder), None)
        self.q.setValue("preset_folders", json.dumps(binds))

    def for_folder(self, folder: Path | None):
        return self._binds().get(str(folder)) if folder else None


# ---- subtitle timeline ----------------------------------------------------
_TS = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d{1,3})")


def subtitle_cues(path: Path) -> list[tuple[float, float]]:
    """(start, end) seconds of each cue in an .srt or .vtt file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    cues = []
    for m in _TS.finditer(text):
        h1, m1, s1, f1, h2, m2, s2, f2 = m.groups()
        a = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(f1.ljust(3, "0")) / 1000
        b = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(f2.ljust(3, "0")) / 1000
        cues.append((a, b))
    return cues
