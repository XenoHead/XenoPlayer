# Simple Media Player

A lightweight, folder-based media player built with Python and PyQt6. It seamlessly handles both video files and images (including animated GIFs), automatically loading all supported media within the same directory as the opened file.

## Features

* **Folder-based Playback:** Open a single file and instantly access a playlist of all media in that folder.
* **Mixed Media Support:** Seamlessly transitions between playing videos and viewing images/GIFs.
* **Favorites System:** Keep track of your favorite files. Play exclusively your favorites or filter them out to watch only unfavorited content.
* **Live Manga Translation:** Draw a box over Japanese text in the Manga Viewer to automatically OCR and translate it to English subtitles.
* **Live Thumbnails:** Bottom playlist bar generates thumbnails for videos and images on the fly (powered by OpenCV).
* **File Management:** Rename, move, delete, or quickly find and remove duplicate files directly from the player. Configure standard "Move Target" folders for easily sorting media on the fly via dropdown. Mass renaming is also supported.
* **Sorting & Looping:** Sort your playlist by Name, Date, or Size. Loop individual files a specific number of times or infinitely.

## Supported Formats

* **Video:** `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.mpg`, `.mpeg`
* **Image:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`

## Requirements

To run this application from the source code, you will need Python installed along with the following packages:

```bash
pip install PyQt6 opencv-python numpy pytesseract Pillow deep-translator
```

## Keyboard & Mouse Shortcuts

* **Space:** Play / Pause
* **Left / Right Arrow:** Previous / Next media
* **Mouse Wheel Up / Down:** Previous / Next media
* **+ / -:** Increase / Decrease video playback speed
* **Home / End:** Jump to the start / end of the playlist
* **F2:** Rename current or selected file(s)
* **F3:** Move current or selected file(s) to a folder
* **Delete:** Delete current or selected file(s)
* **Escape:** Close application
* **Double-Click Video/Image:** Toggle fullscreen
