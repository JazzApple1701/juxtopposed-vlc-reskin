# Third-party notices

VLC Reskin is built on the following. Their licences apply to them, not the MIT licence of the reskin code.

| Component | Used for | Licence | Shipped in the release? |
|---|---|---|---|
| [VLC media player / libVLC](https://www.videolan.org/vlc/) (VideoLAN) | All playback | [LGPL-2.1-or-later](https://code.videolan.org/videolan/vlc/-/blob/master/COPYING.LIB) (libVLC), GPL-2.0-or-later (parts of VLC) | **No.** The app uses the VLC already installed on your PC. |
| [python-vlc](https://pypi.org/project/python-vlc/) | Python bindings for libVLC | [LGPL-2.1-or-later](https://github.com/oaubert/python-vlc/blob/master/COPYING) | Yes |
| [Qt 6](https://www.qt.io/) via [PySide6](https://pypi.org/project/PySide6/) (The Qt Company) | The user interface | [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html) | Yes, as separate DLLs in `_internal\` |
| [Python](https://www.python.org/) | Runtime | [PSF License](https://docs.python.org/3/license.html) | Yes |
| [PyInstaller](https://pyinstaller.org/) bootloader | Packaging the exe | [GPL-2.0 with bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) (allows distributing the result under any licence) | Yes (the bootloader) |
| "VLC Redesign" design by [Juxtopposed](https://figma.com/@juxtopposed) | The look and layout | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Yes (as the app's UI); see [CREDITS.md](CREDITS.md) |

## LGPL components (Qt / PySide6, python-vlc)

These libraries are used unmodified. In the release they are separate files inside the `_internal` folder next to `VLC Reskin.exe`, so you can replace them with your own builds of the same versions. Their source code is available from the links above (Qt: https://download.qt.io/, PySide6: https://code.qt.io/pyside/pyside-setup.git, python-vlc: https://github.com/oaubert/python-vlc).

## Trademarks

VLC and the VLC cone logo are trademarks of VideoLAN. VLC Reskin is an unofficial fan project and isn't affiliated with or endorsed by VideoLAN.
