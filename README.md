# XenoPlayer

XenoPlayer is a versatile, all-in-one media player and manga reader. It effortlessly handles both video files and images (including animated GIFs), automatically loading all supported media within the same directory as the opened file.

Beyond standard playback, XenoPlayer is packed with advanced features including AI-powered live manga translation, built-in online manga downloading, voice-controlled reading, and extensive file management tools. Everything is packaged into a single, easy-to-use application!

## ✨ Key Features

* **Folder-based Playback:** Open a single file and instantly access a playlist of all media in that folder. Seamlessly transitions between playing videos and viewing images/GIFs.
* **Image & Video CBZ Bundles:** Use **File → Create Image CBZ...** to pack a folder of JPG/PNG/WebP/GIF pages into a comic-style `.cbz`, or **File → Create Video CBZ...** to pack MP4/WebM/OGG clips into one playable archive. Files are numbered in natural-sort order (including nested chapter folders), so the sequence is preserved. XenoPlayer opens either bundle like a comic archive and steps through it — one portable file, no loose folders.
* **Manga Reading & Live Translation:**
  * Draw a box over foreign text in the Manga Viewer to automatically recognize and translate it to English (or other languages) using built-in AI.
  * **Burn Translations:** Optionally burn translated text directly into the image file using ImageMagick.
  * **Interactive Translations:** Move, resize, edit, or delete saved translations directly on the page.
* **Online Manga Integration:** Browse popular tags, search, and download galleries directly from your favorite online sources using the built-in downloader.
* **Online Story Reader & TTS:** Click a story result to read it in a fitted in-app reader. TTS uses Microsoft Edge Neural voices by default (requires `edge-tts` and internet) with system voices as a fallback, plus voice selection, speed control, pause/stop, and paragraph highlighting.
* **Collections:** Mark folders or comic archives as collections. Image-only collections open in the page reader, while collections containing videos open in the main player. The Collection Library shows image and video counts plus a thumbnail (including a video frame).
* **Online Audio:** Browse audio sites, filter the loaded tracks, or search the source site for new tracks. Tracks stream in the built-in pop-up player and download to the active folder (or a folder you choose on first download).
* **Advanced File Management:**
  * Instantly move files to pre-configured "Move Target" folders.
  * Smart duplicate deletion—automatically finds and removes identical files to save space.
  * Mass rename files or rename them individually.
* **Audio Normalization:** Built-in dynamic range compression to automatically boost quiet dialogue and lower loud sounds in videos.
* **Video Enhancement:** **Tools → Enhance Video...** cleans up or enlarges a video using ffmpeg filters (denoise, deband, sharpen, and Lanczos upscaling) with no AI models. It can remove noise and restore edge contrast, but it cannot invent real detail. Requires ffmpeg.
* **Favorites System:** Keep track of your favorite files. Play exclusively your favorites or filter them out to watch only unfavorited content.
* **Live Thumbnails:** The playlist dynamically generates previews for your videos and images on the fly.
* **Sharing Hub:** Share your library with friends over your network. Friends connect with their own email address — only `@xenohead.com` addresses are accepted.
* **Direct File Transfer:** Send files or folders to friends, or receive uploads, over Tor using OnionShare. Sends are packed into a password-protected 7z archive (7-Zip required); recipients open the address in Tor Browser. Use **Encrypt for Upload** to make a password-protected 7z locally before uploading to a friend's receive page.

## 🎬 Supported Formats

* **Video:** `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.mpg`, `.mpeg`, `.ogg`
* **Image:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`
* **Archives:** `.cbz` comic archives and `.zip` archives containing images or playable video clips. Both are listed in the playlist and can be filtered with the ZIP/CBZ options. Image CBZ creation uses `.jpg`, `.jpeg`, `.png`, `.webp`, and `.gif`; video CBZ creation uses `.mp4`, `.webm`, and `.ogg`.
  * Playback requires codecs the embedded webview can decode. On Windows that is typically H.264/AAC MP4, VP8/VP9 WebM, and Theora/Vorbis OGG. On macOS, MP4/M4V/MOV play natively; WebM, Ogg, MKV, AVI and other containers are converted to H.264/AAC MP4 with ffmpeg.

## 📁 Application Data

By default on Windows, XenoPlayer reads and writes its data files (`web_settings.json`, `MAINLIST.json`, `reg_cache.json`, and `.env`) in the application's current working directory — the folder the app is launched from. If that folder is not writable, it falls back to the program folder. Existing files in the program folder are still read so settings aren't lost; the first save creates a copy in the working directory. Set the `XENO_DATA_DIR` environment variable to force a specific data folder.

On macOS, a `.app` bundle is read-only, so data is stored in `~/Library/Application Support/XenoPlayer/` instead. See [MACOS.md](MACOS.md) for the Mac build and test steps.

## 🔄 Update Checks

**Check for Updates** compares your local build against `origin/main` on GitHub. When running from a Git checkout, it uses `git fetch` and your existing Git credentials. Packaged builds bundle `build_info.json` with their version and commit. For a private repository outside a Git checkout, add `GITHUB_TOKEN` (or `GH_TOKEN`) to `.env` so the GitHub API can be queried.

## 🚀 Installation & Usage

1. **Download:** Grab the latest `XenoPlayer.exe` (or installer) from the Releases page.
2. **Run:** Double-click the executable to launch the app. No complex setup or dependencies required!
3. **Play:** Drag and drop a file, or click "Load Folder/File" to start watching or reading.
*(Note: The AI translation model may download a small, one-time update on its very first run).*

For **Direct File Transfer**, install [OnionShare](https://onionshare.org) (the Windows installer includes both `onionshare-cli.exe` and Tor) and [7-Zip](https://www.7-zip.org/), then open **Share Files** in XenoPlayer. If either tool is not detected automatically, use **Locate CLI** / **Locate 7z.exe**. Sends are encrypted into a password-protected `.7z` archive; the archive password is set in the Share Files window and must be sent to the recipient separately.

## Keyboard & Mouse Shortcuts

### Main Player

* **Space / ArrowRight:** Next media (Customizable in Options)
* **ArrowLeft:** Previous media (Customizable in Options)
* **Ctrl + Left-Click (Playlist):** Select multiple files
* **Shift + Left-Click (Playlist):** Select a range of files
* **Right-Click (Playlist):** Open context menu (Rename, Delete, Move, Open With...)

### Manga Viewer

* **Left / Right Arrow:** Previous / Next page
* **Right-Click / Forward/Back Mouse Buttons:** Navigate pages or clear selection boxes
* **Left-Click & Drag:** Draw translation box
* **Right-Click (on translation box):** Delete saved translation
* **Ctrl + Right-Click (on translation box):** Edit saved translation text
* **Ctrl + Left-Click & Drag (on translation box):** Move or resize saved translation
* **Escape:** Close Manga Viewer
