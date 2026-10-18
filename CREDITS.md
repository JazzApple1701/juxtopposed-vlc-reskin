# Credits

VLC Reskin is a reskin. The design and the player both belong to other people.

## Design: Juxtopposed

- **Work:** "VLC Redesign"
- **Author:** Juxtopposed ([figma.com/@juxtopposed](https://figma.com/@juxtopposed), [juxtopposed.com](https://juxtopposed.com))
- **Source:** [Figma community file](https://www.figma.com/community/file/1691465999134370980) and the video [*I Redesigned VLC After 25 Years*](https://www.youtube.com/watch?v=ERFeOgqk324)
- **Licence:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)

Juxtopposed's note on the Figma page: *"Feel free to use the design to contribute to the VLC project directly."* This project is a fan reskin, not a contribution to VLC itself, and isn't endorsed by Juxtopposed.

### Changes made to the design

CC BY asks that changes be indicated. Compared with the Figma file and video:

- Turned the static frames into a working Qt application; where the frames don't show behaviour, interactions were interpreted from the video.
- Icons were redrawn as SVG paths to look like the design's icon set rather than exported from it.
- Added a Word-style "Start screen" Home (recent media table) as the default, with the design's original tile Home available as "Classic" in Settings.
- Added a ✕ to the mini player, pinned folders in the library's left column, short descriptions on library sections, a play/pause flash and a scrub preview on the seek bar.
- The equalizer shows libVLC's real bands (31 Hz-16 kHz) instead of the design's 60 Hz-16 kHz.
- Features the player engine can't do (reverse playback, recording) are shown disabled.
- Not built yet: the full Advanced Settings window, Customize Player, profiles and onboarding.

## Player: VLC by VideoLAN

All playback is [VLC media player](https://www.videolan.org/vlc/) through libVLC, made by VideoLAN and its volunteers since 2001. VLC Reskin uses the copy of VLC installed on your PC.

**Please [donate to VideoLAN](https://www.videolan.org/contribute.html#money)** if you find this useful. They make the part that actually plays your media.

VLC and the VLC cone logo are trademarks of VideoLAN. VLC Reskin isn't affiliated with or endorsed by VideoLAN.

## Reskin code

Jasim Khan, under the [MIT licence](LICENSE). Libraries used are listed in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
