import os
import sys
import threading
import json
import re
import cv2
import webview
import shutil
import hashlib
import urllib.parse
from flask import Flask, request, send_file, Response

app = Flask(__name__)

# Settings
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_settings.json")
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {"favorites": [], "last_video": None, "max_volume": 100, "move_targets": {}, "saved_folders": ["", "", "", "", ""], "default_folder": -1, "hotkeys": {"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""]}}

def save_settings(s):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=4)

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', os.path.basename(s))]

manga_ocr_model = None

# Global API object
class Api:
    def __init__(self):
        self.settings = load_settings()
        self.playlist = []
        self.current_index = -1
        self._window = None

    def init(self):
        default_index = self.settings.get("default_folder", -1)
        folders = self.settings.get("saved_folders", ["", "", "", "", ""])
        
        # Priority: Default Folder -> Last Video
        if 0 <= default_index < len(folders):
            def_folder = folders[default_index]
            if def_folder and os.path.isdir(def_folder):
                try:
                    # Pick the first supported file to load the directory
                    supported = {'.mp4', '.webm', '.ogg', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
                    first_file = next((f for f in os.listdir(def_folder) if os.path.isfile(os.path.join(def_folder, f)) and os.path.splitext(f)[1].lower() in supported), None)
                    if first_file:
                        self.load_directory(os.path.join(def_folder, first_file))
                        return {"status": "ready"}
                except Exception: pass
                
        last_video = self.settings.get("last_video")
        if last_video and os.path.exists(last_video):
            self.load_directory(last_video)
        return {"status": "ready"}

    def open_dialog(self):
        last_dir = self.settings.get("last_opened_dir", "")
        if last_dir and not os.path.exists(last_dir):
            last_dir = ""
            
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, directory=last_dir, allow_multiple=False, file_types=('Media Files (*.mp4;*.webm;*.ogg;*.jpg;*.png;*.gif;*.webp)', 'All files (*.*)'))
        if result and len(result) > 0:
            filepath = result[0]
            self.settings["last_opened_dir"] = os.path.dirname(filepath)
            save_settings(self.settings)
            self.load_directory(filepath)

    def browse_folder(self):
        last_dir = self.settings.get("last_opened_dir", "")
        if last_dir and not os.path.exists(last_dir):
            last_dir = ""
            
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG, directory=last_dir)
        if result and len(result) > 0:
            folderpath = result[0]
            self.settings["last_opened_dir"] = folderpath
            save_settings(self.settings)
            return folderpath
        return None

    def load_directory(self, filepath):
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath):
            return
        
        directory = os.path.dirname(filepath)
        try:
            files = os.listdir(directory)
        except Exception as e:
            print(f"Error reading directory: {e}")
            return
            
        supported = {'.mp4', '.webm', '.ogg', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
        self.playlist = []
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in supported:
                self.playlist.append(os.path.join(directory, f))
                
        self.playlist.sort(key=natural_sort_key)
        
        try:
            self.current_index = self.playlist.index(filepath)
        except ValueError:
            self.playlist.append(filepath)
            self.current_index = len(self.playlist) - 1
            
        self.settings["last_video"] = filepath
        save_settings(self.settings)
        
        self._window.evaluate_js('updatePlaylist()')
        self.play_current()

    def get_playlist(self):
        return [{"path": p, "name": os.path.basename(p)} for p in self.playlist]

    def play_current(self):
        if not (0 <= self.current_index < len(self.playlist)):
            return
            
        path = self.playlist[self.current_index]
        self.settings["last_video"] = path
        save_settings(self.settings)
        
        safe_path = json.dumps(path)
        self._window.evaluate_js(f'loadMedia({safe_path}, {self.current_index})')

    def play_index(self, index):
        if 0 <= index < len(self.playlist):
            self.current_index = index
            self.play_current()

    def next_media(self):
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            self.play_current()

    def prev_media(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.play_current()

    def get_state(self):
        current_path = self.playlist[self.current_index] if (0 <= self.current_index < len(self.playlist)) else None
        return {
            "favorites": self.settings.get("favorites", []),
            "move_targets": self.settings.get("move_targets", {}),
            "saved_folders": self.settings.get("saved_folders", ["", "", "", "", ""]),
            "default_folder": self.settings.get("default_folder", -1),
            "hotkeys": self.settings.get("hotkeys", {"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""]}),
            "current_path": current_path,
            "is_favorite": current_path in self.settings.get("favorites", []) if current_path else False
        }

    def toggle_favorite(self):
        if not (0 <= self.current_index < len(self.playlist)): return {"status": "error"}
        path = self.playlist[self.current_index]
        favs = self.settings.get("favorites", [])
        if path in favs:
            favs.remove(path)
        else:
            favs.append(path)
        self.settings["favorites"] = favs
        save_settings(self.settings)
        return self.get_state()

    def play_favorites(self):
        favs = [f for f in self.settings.get("favorites", []) if os.path.exists(f)]
        if not favs: return
        self.playlist = favs
        self.current_index = 0
        self._window.evaluate_js('updatePlaylist()')
        self.play_current()

    def play_unfavorites(self):
        if not self.playlist: return
        dir_path = os.path.dirname(self.playlist[0])
        favs = set(self.settings.get("favorites", []))
        supported = {'.mp4', '.webm', '.ogg', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
        self.playlist = []
        for f in os.listdir(dir_path):
            fp = os.path.join(dir_path, f)
            if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in supported:
                if fp not in favs:
                    self.playlist.append(fp)
        self.playlist.sort(key=natural_sort_key)
        if self.playlist:
            self.current_index = 0
            self._window.evaluate_js('updatePlaylist()')
            self.play_current()

    def save_options(self, folders, default_index):
        self.settings["saved_folders"] = folders
        self.settings["default_folder"] = default_index
        save_settings(self.settings)
        return self.get_state()

    def save_move_targets(self, targets):
        self.settings["move_targets"] = targets
        save_settings(self.settings)
        return self.get_state()

    def save_hotkeys(self, hotkeys):
        self.settings["hotkeys"] = hotkeys
        save_settings(self.settings)
        return self.get_state()

    def get_manga_info(self, current_path):
        if not current_path or not os.path.isfile(current_path): return {}
        dir_path = os.path.dirname(current_path)
        json_path = os.path.join(dir_path, "manga_info.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("translations", {})
            except: pass
        return {}

    def save_manga_info(self, current_path, translations):
        if not current_path or not os.path.isfile(current_path): return {"status": "error"}
        dir_path = os.path.dirname(current_path)
        json_path = os.path.join(dir_path, "manga_info.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"translations": translations}, f, indent=4)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def translate_rect(self, path, x, y, w, h, ocr_mode, disp_w, disp_h):
        if not path or not os.path.isfile(path): return {"status": "error"}
        from PIL import Image
        global manga_ocr_model
        
        try:
            img = Image.open(path)
            # Map display rect to actual image rect
            ratio_w = img.width / disp_w
            ratio_h = img.height / disp_h
            
            orig_x = int(x * ratio_w)
            orig_y = int(y * ratio_h)
            orig_w = int(w * ratio_w)
            orig_h = int(h * ratio_h)
            
            cropped = img.crop((orig_x, orig_y, orig_x + orig_w, orig_y + orig_h))
            
            extracted_text = ""
            if ocr_mode == "Japanese (Manga OCR)":
                if manga_ocr_model is None:
                    from manga_ocr import MangaOcr
                    manga_ocr_model = MangaOcr()
                extracted_text = manga_ocr_model(cropped).strip()
            else:
                import pytesseract
                lang_map = {
                    "Russian": "rus",
                    "Chinese (Simplified)": "chi_sim",
                    "Chinese (Traditional)": "chi_tra",
                    "English": "eng",
                    "Japanese (Tesseract)": "jpn"
                }
                tess_lang = lang_map.get(ocr_mode, "eng")
                extracted_text = pytesseract.image_to_string(cropped, lang=tess_lang).strip()
            
            if not extracted_text:
                return {"status": "error", "msg": "No text recognized."}
                
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source='auto', target='en').translate(extracted_text)
            
            return {
                "status": "success",
                "orig": extracted_text,
                "text": translated,
                "rect": [orig_x, orig_y, orig_w, orig_h]
            }
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def open_manga_viewer(self, path):
        if not path: return
        directory = os.path.dirname(path) if os.path.isfile(path) else path
        import subprocess
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MangaViewer.py")
        subprocess.Popen([sys.executable, script, directory])
        return {"status": "success"}

    def get_nhentai_tags(self):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            scraper = cloudscraper.create_scraper()
            html = scraper.get('https://nhentai.net/tags?sort=popular').text
            soup = BeautifulSoup(html, 'html.parser')
            # Extract tags
            tags = [a.text.strip().split('(')[0].strip() for a in soup.select('a') if '/tag/' in a.get('href', '') and a.text.strip()]
            seen = set()
            clean_tags = []
            for t in tags:
                if t and t not in seen:
                    seen.add(t)
                    clean_tags.append(t)
            return {"status": "success", "tags": clean_tags[:50]}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def search_nhentai(self, query):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            import urllib.parse
            scraper = cloudscraper.create_scraper()
            url = f"https://nhentai.net/search/?q={urllib.parse.quote(query)}"
            html = scraper.get(url).text
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            for g in soup.select('.gallery'):
                title_el = g.select_one('.caption')
                img_el = g.select_one('img')
                link_el = g.select_one('a')
                if title_el and img_el and link_el:
                    title = title_el.text.strip()
                    thumb = img_el.get('data-src') or img_el.get('src')
                    if thumb and thumb.startswith('//'):
                        thumb = 'https:' + thumb
                    gallery_url = "https://nhentai.net" + link_el.get('href', '')
                    results.append({"title": title, "thumb": thumb, "url": gallery_url})
            return {"status": "success", "results": results[:20]} # Limit to 20 results for now
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def choose_manga_download_dir(self):
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            folderpath = result[0]
            self.settings["manga_download_dir"] = folderpath
            save_settings(self.settings)
            return {"status": "success", "dir": folderpath}
        return {"status": "canceled"}

    def get_manga_download_dir(self):
        d = self.settings.get("manga_download_dir", "")
        if not d:
            d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Downloads", "nhentai")
        return {"dir": d}

    def download_nhentai(self, url, title):
        import subprocess
        import string
        import threading
        import json
        import sys
        import os
        
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        base_dir = self.get_manga_download_dir()["dir"]
        download_dir = os.path.join(base_dir, folder_name)
        
        def run_download():
            try:
                os.makedirs(download_dir, exist_ok=True)
                subprocess.run([sys.executable, "-m", "gallery_dl", "-d", download_dir, url], check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                # Escape for JS evaluation
                safe_dir = download_dir.replace('\\', '\\\\')
                self._window.evaluate_js(f'downloadComplete("{safe_dir}")')
            except Exception as e:
                safe_err = str(e).replace('"', '\\"').replace('\\', '\\\\')
                self._window.evaluate_js(f'downloadFailed("{safe_err}")')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}

    def move_file_to(self, target_name):
        if not (0 <= self.current_index < len(self.playlist)): return {"status": "error", "msg": "No file selected"}
        path = self.playlist[self.current_index]
        targets = self.settings.get("move_targets", {})
        if target_name not in targets: return {"status": "error", "msg": "Target not found"}
        
        target_dir = targets[target_name]
        if not os.path.exists(target_dir):
            try: os.makedirs(target_dir)
            except: return {"status": "error", "msg": "Cannot create target dir"}
        
        dest = os.path.join(target_dir, os.path.basename(path))
        try:
            shutil.move(path, dest)
            self.playlist.pop(self.current_index)
            if self.current_index >= len(self.playlist):
                self.current_index = len(self.playlist) - 1
            self._window.evaluate_js('updatePlaylist()')
            if self.current_index >= 0:
                self.play_current()
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def delete_dupes(self):
        if not self.playlist: return {"status": "error", "msg": "No directory loaded"}
        dir_path = os.path.dirname(self.playlist[0])
        hashes = {}
        deleted = 0
        for f in os.listdir(dir_path):
            fp = os.path.join(dir_path, f)
            if os.path.isfile(fp):
                try:
                    h = hashlib.md5(open(fp,'rb').read()).hexdigest()
                    if h in hashes:
                        os.remove(fp)
                        deleted += 1
                        if fp in self.playlist:
                            self.playlist.remove(fp)
                    else:
                        hashes[h] = True
                except: pass
        if deleted > 0:
            if self.current_index >= len(self.playlist):
                self.current_index = 0
            self._window.evaluate_js('updatePlaylist()')
            if self.playlist: self.play_current()
        return {"status": "success", "msg": f"Deleted {deleted} duplicates."}

    def exit_app(self):
        self._window.destroy()

api = Api()

# FLASK ROUTES
@app.route('/media')
def stream_media():
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return "Not found", 404

    # Support byte range requests for video seeking
    range_header = request.headers.get('Range', None)
    if not range_header:
        return send_file(path)
    
    size = os.path.getsize(path)
    byte1, byte2 = 0, None
    m = re.search(r'bytes=(\d+)-(\d*)', range_header)
    g = m.groups()
    byte1 = int(g[0])
    if g[1]:
        byte2 = int(g[1])
    else:
        byte2 = size - 1

    length = byte2 - byte1 + 1
    
    def generate(remaining_length):
        with open(path, 'rb') as f:
            f.seek(byte1)
            chunk_size = 1024 * 1024 # 1MB chunks
            while remaining_length > 0:
                data = f.read(min(chunk_size, remaining_length))
                if not data:
                    break
                remaining_length -= len(data)
                yield data

    # HTML5 video requires 206 Partial Content
    rv = Response(generate(length), 206, mimetype='video/mp4')
    rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    return rv

import functools

@functools.lru_cache(maxsize=1000)
def _generate_video_thumbnail(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
    ret, frame = cap.read()
    if not ret:
        cap.release()
        cap = cv2.VideoCapture(path)
        ret, frame = cap.read()
    cap.release()
    
    if ret and frame is not None:
        frame = cv2.resize(frame, (160, 90))
        is_success, buffer = cv2.imencode(".jpg", frame)
        if is_success:
            return buffer.tobytes()
    return None

@app.route('/thumbnail')
def get_thumbnail():
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return "Not found", 404
        
    ext = os.path.splitext(path)[1].lower()
    if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        return send_file(path)
        
    # Generate video thumbnail on the fly
    img_bytes = _generate_video_thumbnail(path)
    if img_bytes:
        return Response(img_bytes, mimetype='image/jpeg')
            
    return "Error", 500

def run_server():
    # Disable flask request logging for cleaner output
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(port=5050, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Start the backend media server
    threading.Thread(target=run_server, daemon=True).start()
    
    # Start the Webview
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'index.html')
    window = webview.create_window('XenoPlayer', html_path, js_api=api, width=1000, height=700)
    api._window = window
    webview.start(debug=False)
