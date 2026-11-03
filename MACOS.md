# XenoPlayer on macOS (Mac Core)

This is the macOS port of XenoPlayer: player, folders/library, playlists,
CBZ/ZIP, collections, story reader, Edge TTS, audio, downloads, and update
checks. It builds a normal `.app` bundle and a `.dmg`.

This build must be produced **on macOS**. PyInstaller cannot cross-compile a
macOS app from Windows.

## What is included

- Main media player (video, audio, images)
- Folder/library browser, recursive load, playlists
- CBZ/ZIP opening and archive browsing
- Collections (routed through the main player on macOS)
- Story reader and Edge Neural TTS
- Online audio and collection downloads
- Git-based update checks
- Registration key gate (native macOS dialogs)

## Deferred from Mac Core

- OCR / translation / manga-OCR
- Voice control
- OnionShare and 7-Zip sharing (the UI remains; the tools are optional)
- Separate PyQt `CollectionViewer`

Those can be added after the core app is verified.

## Requirements

- macOS 12 or newer (Apple Silicon or Intel)
- Python 3.11 or 3.12 from python.org or Homebrew
- Xcode Command Line Tools (`xcode-select --install`)
- Optional: Homebrew

Native tools used at runtime:

```bash
# Needed for formats WKWebView cannot play (WebM, Ogg, MKV, AVI, WMV, ...)
brew install ffmpeg

# Optional: only if you later enable OCR
brew install tesseract
```

The app finds `ffmpeg`/`ffprobe` on `PATH`, in `/opt/homebrew/bin`,
`/usr/local/bin`, or via `ffmpeg_path` in `web_settings.json`.

## Build

```bash
cd /path/to/XenoPlayer
python3 -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-macos.txt
python build_macos.py
```

Outputs:

```text
dist/XenoPlayer.app
dist/XenoPlayer-<version>-macOS.dmg
```

Build options:

```bash
# Build for a specific architecture
XENO_MAC_ARCH=arm64 python build_macos.py
XENO_MAC_ARCH=x86_64 python build_macos.py
XENO_MAC_ARCH=universal2 python build_macos.py   # only if all wheels are universal

# Sign with a Developer ID certificate
XENO_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" python build_macos.py

# Skip DMG creation
XENO_SKIP_DMG=1 python build_macos.py
```

`universal2` requires every native dependency (OpenCV, pyobjc, ffmpeg if
bundled) to ship universal binaries. If it fails, build separate `arm64` and
`x86_64` apps instead.

## App data location

On macOS, writable data is stored in:

```text
~/Library/Application Support/XenoPlayer/
```

That includes `web_settings.json`, `reg_cache.json`, `MAINLIST.json` edits,
`.tts_cache/`, and `.video_cache/`. `XENO_DATA_DIR` still overrides the
location.

The `.app` bundle itself is read-only. Default collection downloads go to
`~/Downloads/XenoPlayer/nhentai`.

## Video playback

WKWebView uses macOS system codecs:

- Native: MP4, M4V, MOV with H.264/HEVC and AAC/MP3 audio
- Converted through ffmpeg: WebM, Ogg, MKV, AVI, WMV, FLV, MPEG, TS

If a native container holds an unsupported codec, the app probes it with
`ffprobe` and converts it to H.264/AAC MP4 in the video cache. Conversion is
cached by path, size, and modification time.

Audio in Ogg, Opus, WebM, or WMA is converted to AAC/M4A in the same cache the
first time it is played. MP3, M4A/AAC, WAV, FLAC, AIFF, and CAF play natively.

## First launch (unsigned build)

An unsigned local build is blocked by Gatekeeper. Either:

- Right-click the app in Finder and choose **Open**, then confirm, or
- Remove the quarantine flag:

```bash
xattr -dr com.apple.quarantine /Applications/XenoPlayer.app
```

For distribution outside your own Mac, sign and notarize.

## Signing and notarization

You need an Apple Developer ID Application certificate.

```bash
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  dist/XenoPlayer.app

xcrun notarytool submit dist/XenoPlayer-<version>-macOS.dmg \
  --keychain-profile "XenoPlayer" --wait

xcrun stapler staple dist/XenoPlayer-<version>-macOS.dmg
```

Create the keychain profile once:

```bash
xcrun notarytool store-credentials "XenoPlayer" \
  --apple-id "you@example.com" \
  --team-id "TEAMID" \
  --password "app-specific-password"
```

Do not notarize an unsigned app.

## Test checklist

Run these on a real Mac before publishing:

1. App launches from `dist/XenoPlayer.app` and from the DMG.
2. Registration key gate appears and accepts a valid key; cancel exits cleanly.
3. Settings survive a restart and live in `~/Library/Application Support/XenoPlayer`.
4. Open a folder and play MP4/H.264/AAC.
5. Play WebM/VP9 and Ogg; confirm ffmpeg conversion appears once, then caches.
6. Play audio (MP3, M4A, FLAC, OGG) and use the top audio bar.
7. Open a CBZ/ZIP; pages and any videos load.
8. Open an image-only collection; it opens in the main player.
9. Story reader loads a story and Edge TTS plays and prefetches.
10. Download an online collection and confirm it lands in `~/Downloads/XenoPlayer/nhentai`.
11. Use **Show in folder** / **Open externally**.
12. Check for updates and confirm the version/commit display.
13. Resize, maximize, and reopen the app; window state persists.
14. Quit while audio/video/ffmpeg conversion is running; no orphan processes remain.

## GitHub Actions

`.github/workflows/build-macos.yml` builds the app on a macOS runner and
uploads the zipped `.app` and `.dmg` as artifacts. The workflow is unsigned by
default. Add signing secrets only when you are ready to notarize.

## Troubleshooting

**`ModuleNotFoundError` at runtime**
Rebuild with the package installed in the active virtualenv. PyInstaller only
bundles what it can import.

**"This video format needs ffmpeg"**
Install ffmpeg (`brew install ffmpeg`) or set `ffmpeg_path` in
`web_settings.json`.

**App opens to a blank window**
Check the Console app for Python/PyInstaller errors. Running the binary directly
shows stdout and stderr:

```bash
dist/XenoPlayer.app/Contents/MacOS/XenoPlayer
```

**Gatekeeper says the app is damaged**
That usually means a broken signature or a partially copied app. Rebuild, or
for a local unsigned build use `xattr -dr com.apple.quarantine`.
