import os
import sys

# Force local offline execution for machine learning assets
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import threading
import json
import re
import cv2
import webview
import tempfile
import shutil
import hashlib
import urllib.parse
from flask import Flask, request, send_file, Response

class DummyWriter:
    encoding = 'utf-8'
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False
if sys.stdout is None: sys.stdout = DummyWriter()
if sys.stderr is None: sys.stderr = DummyWriter()

app = Flask(__name__)
    
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(app_dir, "web_settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {"favorites": [], "last_video": None, "max_volume": 100, "move_targets": {}, "saved_folders": ["", "", "", "", ""], "external_apps": ["", "", "", "", ""], "default_folder": -1, "hotkeys": {"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""]}, "saved_volumes": {}}

def save_settings(s):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=4)

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', os.path.basename(s))]

# --- CORE FRONTEND INTEGRATED API HANDLERS ---

class Api:
    def __init__(self):
        self.settings = load_settings()
        self.playlist = []
        self.current_index = -1
        self._window = None

    def init(self):
        if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
            self.load_directory(sys.argv[1])
            return {"status": "ready"}
            
        default_index = self.settings.get("default_folder", -1)
        folders = self.settings.get("saved_folders", ["", "", "", "", ""])
        
        if 0 <= default_index < len(folders):
            def_folder = folders[default_index]
            if def_folder and os.path.isdir(def_folder):
                try:
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
        if last_dir and not os.path.exists(last_dir): last_dir = ""
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=last_dir, allow_multiple=False, file_types=('Media Files (*.mp4;*.webm;*.ogg;*.jpg;*.png;*.gif;*.webp)', 'All files (*.*)'))
        if result and len(result) > 0:
            self.settings["last_opened_dir"] = os.path.dirname(result[0])
            save_settings(self.settings)
            self.load_directory(result[0])

    def browse_folder(self):
        last_dir = self.settings.get("last_opened_dir", "")
        if last_dir and not os.path.exists(last_dir): last_dir = ""
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=last_dir)
        if result and len(result) > 0:
            self.settings["last_opened_dir"] = result[0]
            save_settings(self.settings)
            return result[0]
        return None

    def browse_exe_dialog(self):
        last_dir = self.settings.get("last_opened_dir", "")
        if last_dir and not os.path.exists(last_dir): last_dir = ""
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=last_dir, allow_multiple=False, file_types=('Executables (*.exe)', 'All files (*.*)'))
        if result and len(result) > 0: return result[0]
        return None

    def load_directory(self, filepath):
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath): return
        directory = os.path.dirname(filepath)
        try:
            files = os.listdir(directory)
        except: return
            
        supported = {'.mp4', '.webm', '.ogg', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
        self.playlist = [os.path.join(directory, f) for f in files if os.path.splitext(f)[1].lower() in supported]
        self.playlist.sort(key=natural_sort_key)
        
        try: self.current_index = self.playlist.index(filepath)
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
        if not (0 <= self.current_index < len(self.playlist)): return
        path = self.playlist[self.current_index]
        self.settings["last_video"] = path
        save_settings(self.settings)
        self._window.evaluate_js(f'loadMedia({json.dumps(path)}, {self.current_index})')

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
        is_manga = False
        dir_path = ""
        if current_path:
            dir_path = os.path.dirname(current_path)
            if os.path.exists(os.path.join(dir_path, '.manga')) or os.path.exists(os.path.join(dir_path, 'manga_info.json')):
                is_manga = True
        return {
            "favorites": [f for f in self.settings.get("favorites", []) if os.path.dirname(f) == dir_path] if dir_path else [],
            "move_targets": self.settings.get("move_targets", {}),
            "saved_volumes": self.settings.get("saved_volumes", {}),
            "saved_folders": self.settings.get("saved_folders", ["", "", "", "", ""]),
            "external_apps": self.settings.get("external_apps", ["", "", "", "", ""]),
            "default_folder": self.settings.get("default_folder", -1),
            "hotkeys": self.settings.get("hotkeys", {"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""]}),
            "current_path": current_path,
            "is_favorite": current_path in self.settings.get("favorites", []) if current_path else False,
            "is_manga_folder": is_manga
        }

    def toggle_favorite(self):
        if not (0 <= self.current_index < len(self.playlist)): return {"status": "error"}
        path = self.playlist[self.current_index]
        favs = self.settings.get("favorites", [])
        if path in favs: favs.remove(path)
        else: favs.append(path)
        self.settings["favorites"] = favs
        save_settings(self.settings)
        return self.get_state()

    def save_volume(self, path, volume):
        vols = self.settings.get("saved_volumes", {})
        vols[path] = volume
        self.settings["saved_volumes"] = vols
        save_settings(self.settings)
        return {"status": "ok"}

    def save_favorites(self, favs):
        if not self.playlist: return self.get_state()
        dir_path = os.path.dirname(self.playlist[0])
        all_favs = [f for f in self.settings.get("favorites", []) if os.path.dirname(f) != dir_path]
        all_favs.extend(favs)
        self.settings["favorites"] = all_favs
        save_settings(self.settings)
        return self.get_state()

    def save_options(self, folders, default_index, external_apps=None):
        self.settings["saved_folders"] = folders
        self.settings["default_folder"] = default_index
        if external_apps is not None: self.settings["external_apps"] = external_apps
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

    def mark_as_manga(self):
        if not self.playlist: return {"status": "error"}
        dir_path = os.path.dirname(self.playlist[0])
        open(os.path.join(dir_path, ".manga"), 'w').close()
        known = self.settings.get("known_manga_folders", [])
        if dir_path not in known:
            known.append(dir_path)
            self.settings["known_manga_folders"] = known
            save_settings(self.settings)
        return self.get_state()

    def unmark_as_manga(self):
        if not self.playlist: return {"status": "error"}
        dir_path = os.path.dirname(self.playlist[0])
        try: os.remove(os.path.join(dir_path, ".manga"))
        except: pass
        known = self.settings.get("known_manga_folders", [])
        if dir_path in known:
            known.remove(dir_path)
            self.settings["known_manga_folders"] = known
            save_settings(self.settings)
        return self.get_state()

    def get_manga_info(self, current_path):
        if not current_path or not os.path.isfile(current_path): return {}
        json_path = os.path.join(os.path.dirname(current_path), "manga_info.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f: return json.load(f).get("translations", {})
            except: pass
        return {}

    def save_manga_info(self, current_path, translations):
        if not current_path or not os.path.isfile(current_path): return {"status": "error"}
        dir_path = os.path.dirname(current_path)
        json_path = os.path.join(dir_path, "manga_info.json")
        data = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f: data = json.load(f)
            except: pass
        data["translations"] = translations
        try:
            with open(json_path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
            open(os.path.join(dir_path, ".manga"), 'w').close()
            known = self.settings.get("known_manga_folders", [])
            if dir_path not in known:
                known.append(dir_path)
                self.settings["known_manga_folders"] = known
                save_settings(self.settings)
            return {"status": "success"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def open_folder_location(self, path):
        import subprocess
        try:
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            return {"status": "ok"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def open_with(self, filepath, app_path):
        import subprocess
        try:
            subprocess.Popen([app_path, os.path.normpath(filepath)])
            return {"status": "ok"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def open_manga_viewer(self, path):
        if not path: return
        directory = os.path.dirname(path) if os.path.isfile(path) else path
        import subprocess
        env = os.environ.copy()
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "MangaViewer", directory], env=env)
        else:
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MangaViewer.py")
            subprocess.Popen([sys.executable, script, directory], env=env)
        return {"status": "success"}

    # --- NHENTAI AUTOMATION ENGINE ROUTING ---

    def get_nhentai_tags(self):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            scraper = cloudscraper.create_scraper()
            html = scraper.get('https://nhentai.net/tags?sort=popular').text
            soup = BeautifulSoup(html, 'html.parser')
            tags = []
            for a in soup.select('a'):
                if '/tag/' in a.get('href', ''):
                    name_el = a.select_one('.name')
                    if name_el: tags.append(name_el.text.strip())
            seen = set()
            return {"status": "success", "tags": [t for t in tags if not (t in seen or seen.add(t))][:50]}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def search_nhentai(self, query):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
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
                    thumb = img_el.get('data-src') or img_el.get('src') or ""
                    if thumb.startswith('//'): thumb = 'https:' + thumb
                    results.append({"title": title_el.text.strip(), "thumb": thumb, "url": "https://nhentai.net" + link_el.get('href', '')})
            return {"status": "success", "results": results[:20]}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def choose_manga_download_dir(self):
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if result and len(result) > 0:
            self.settings["manga_download_dir"] = result[0]
            save_settings(self.settings)
            return {"status": "success", "dir": result[0]}
        return {"status": "canceled"}

    def get_manga_download_dir(self):
        d = self.settings.get("manga_download_dir", "")
        if not d:
            base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            d = os.path.join(base, "Downloads", "nhentai")
        return {"dir": d}

    def download_nhentai(self, url, title):
        import string
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        download_dir = os.path.join(self.get_manga_download_dir()["dir"], folder_name)
        
        def run_download():
            try:
                os.makedirs(download_dir, exist_ok=True)
                open(os.path.join(download_dir, ".manga"), 'w').close()
                import subprocess
                cmd = [sys.executable, "gallery_dl_module", "-d", download_dir, url] if getattr(sys, 'frozen', False) else [sys.executable, "-m", "gallery_dl", "-d", download_dir, url]
                subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}")')
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}")')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}

    def get_manga_library(self):
        known = self.settings.get("known_manga_folders", [])
        library = []
        dl_dir = self.get_manga_download_dir()["dir"]
        
        # Auto-scan Download Locations Safely
        for parent in [dl_dir] + self.settings.get("saved_folders", []):
            if parent and os.path.exists(parent) and os.path.isdir(parent):
                try:
                    for sub in os.listdir(parent):
                        fp = os.path.join(parent, sub)
                        if os.path.isdir(fp) and fp not in known:
                            if os.path.exists(os.path.join(fp, ".manga")) or os.path.exists(os.path.join(fp, "manga_info.json")):
                                known.append(fp)
                except: pass

        valid_known = []
        for d in known:
            if os.path.exists(d) and os.path.isdir(d):
                valid_known.append(d)
                name = os.path.basename(d)
                json_path = os.path.join(d, "manga_info.json")
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            n = json.load(f).get("name", "").strip()
                            if n: name = n
                    except: pass
                
                first_image = None
                page_count = 0
                try:
                    supported = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
                    image_files = sorted([f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in supported], key=natural_sort_key)
                    page_count = len(image_files)
                    if image_files: first_image = os.path.join(d, image_files[0])
                except: pass
                
                try: mtime = os.path.getctime(d)
                except: mtime = 0
                
                library.append({"path": d, "name": name, "thumb": first_image, "mtime": mtime, "page_count": page_count})
                
        self.settings["known_manga_folders"] = valid_known
        save_settings(self.settings)
        return {"status": "success", "library": library}

    def delete_manga_folder(self, path):
        if not path: return {"status": "error"}
        known = self.settings.get("known_manga_folders", [])
        if path in known: known.remove(path)
        self.settings["known_manga_folders"] = known
        save_settings(self.settings)
        if os.path.exists(path) and os.path.isdir(path):
            try:
                import send2trash
                send2trash.send2trash(path)
            except: shutil.rmtree(path)
        return {"status": "success"}

    # --- SUBPROCESS SEGREGATED TRANSLATE PIPELINE ---

    def translate_rect(self, path, x, y, w, h, ocr_mode, disp_w, disp_h):
        if not path or not os.path.isfile(path): return {"status": "error"}
        from PIL import Image
        try:
            img = Image.open(path)
            ratio_w, ratio_h = img.width / disp_w, img.height / disp_h
            orig_x, orig_y, orig_w, orig_h = int(x * ratio_w), int(y * ratio_h), int(w * ratio_w), int(h * ratio_h)
            cropped = img.crop((orig_x, orig_y, orig_x + orig_w, orig_y + orig_h))
            
            if ocr_mode == "Japanese (Manga OCR)":
                import subprocess
                temp_img_path = os.path.join(tempfile.gettempdir(), "player_ocr_crop.png")
                cropped.save(temp_img_path)
                
                if getattr(sys, 'frozen', False):
                    # In a COLLECT/onedir build, ocr_worker.exe sits next to XenoPlayer.exe
                    exe_dir = os.path.dirname(sys.executable)
                    worker_exe = os.path.join(exe_dir, "ocr_worker.exe")
                    # manga_ocr_model is bundled inside _MEIPASS (the _internal extraction dir)
                    base_dir = sys._MEIPASS
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    worker_exe = sys.executable
                
                model_path = os.path.normpath(os.path.join(base_dir, 'manga_ocr_model'))
                if not os.path.exists(os.path.join(model_path, "config.json")):
                    model_path = os.path.normpath(os.path.join(base_dir, '..', 'manga_ocr_model'))
                
                if getattr(sys, 'frozen', False):
                    cmd = [worker_exe, temp_img_path, model_path]
                else:
                    cmd = [worker_exe, os.path.join(base_dir, "ocr_worker.py"), temp_img_path, model_path]
                
                # Set PYTHONIOENCODING as belt-and-suspenders for the child process
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                        env=env,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                
                try: os.remove(temp_img_path)
                except: pass
                extracted_text = result.stdout.strip()
                if result.returncode != 0 or extracted_text.startswith("ERROR:"): return {"status": "error", "msg": extracted_text}
            else:
                import pytesseract
                lang_map = {"Russian": "rus", "Chinese (Simplified)": "chi_sim", "Chinese (Traditional)": "chi_tra", "English": "eng", "Japanese (Tesseract)": "jpn"}
                extracted_text = pytesseract.image_to_string(cropped, lang=lang_map.get(ocr_mode, "eng")).strip()
            
            if not extracted_text: return {"status": "error", "msg": "No text found."}
            from deep_translator import GoogleTranslator
            return {"status": "success", "orig": extracted_text, "text": GoogleTranslator(source='auto', target='en').translate(extracted_text), "rect": [orig_x, orig_y, orig_w, orig_h]}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def move_file_to(self, target_name):
        if not (0 <= self.current_index < len(self.playlist)): return {"status": "error"}
        path = self.playlist[self.current_index]
        target_dir = self.settings.get("move_targets", {}).get(target_name)
        if not target_dir: return {"status": "error"}
        os.makedirs(target_dir, exist_ok=True)
        try:
            shutil.move(path, os.path.join(target_dir, os.path.basename(path)))
            self.playlist.pop(self.current_index)
            if self.current_index >= len(self.playlist): self.current_index = len(self.playlist) - 1
            self._window.evaluate_js('updatePlaylist()')
            if self.current_index >= 0: self.play_current()
            return {"status": "success"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def delete_files(self, paths):
        for p in paths:
            try:
                import send2trash
                send2trash.send2trash(p)
            except: os.remove(p)
        self.playlist = [p for p in self.playlist if p not in paths]
        if self.current_index >= len(self.playlist): self.current_index = max(-1, len(self.playlist) - 1)
        return {"status": "success"}

    def rename_file(self, old_path, new_name):
        np = os.path.join(os.path.dirname(old_path), new_name + os.path.splitext(old_path)[1])
        try:
            os.rename(old_path, np)
            if old_path in self.playlist: self.playlist[self.playlist.index(old_path)] = np
            return {"status": "success"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def move_files(self, paths, target_name):
        td = self.settings.get("move_targets", {}).get(target_name, os.path.join(os.path.dirname(paths[0]), target_name))
        try:
            os.makedirs(td, exist_ok=True)
            for p in paths: shutil.move(p, td)
            self.playlist = [p for p in self.playlist if p not in paths]
            if self.current_index >= len(self.playlist): self.current_index = max(-1, len(self.playlist) - 1)
            return {"status": "success"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def delete_dupes(self):
        if not self.playlist: return {"status": "error"}
        hashes, deleted = {}, 0
        for fp in list(self.playlist):
            if os.path.isfile(fp):
                try:
                    h = hashlib.md5(open(fp,'rb').read()).hexdigest()
                    if h in hashes:
                        os.remove(fp)
                        self.playlist.remove(fp)
                        deleted += 1
                    else: hashes[h] = True
                except: pass
        if deleted > 0:
            self.current_index = 0 if self.playlist else -1
            self._window.evaluate_js('updatePlaylist()')
            if self.playlist: self.play_current()
        return {"status": "success", "msg": f"Deleted {deleted} duplicates."}

    def exit_app(self): self._window.destroy()

api = Api()

# --- FLASK STREAMING INFRASTRUCTURE ---

@app.route('/media')
def stream_media():
    path = request.args.get('path')
    if not path or not os.path.exists(path): return "Not found", 404
    range_header = request.headers.get('Range', None)
    if not range_header: return send_file(path)
    
    size = os.path.getsize(path)
    byte1, byte2 = 0, size - 1
    m = re.search(r'bytes=(\d+)-(\d*)', range_header)
    if m:
        g = m.groups()
        if g[0]: byte1 = int(g[0])
        if g[1]: byte2 = int(g[1])
        
    length = byte2 - byte1 + 1
    def generate():
        with open(path, 'rb') as f:
            f.seek(byte1)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1024*1024, remaining))
                if not chunk: break
                remaining -= len(chunk)
                yield chunk
    rv = Response(generate(), 206, mimetype='video/mp4')
    rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    return rv

@app.route('/thumbnail')
def get_thumbnail():
    path = request.args.get('path')
    if not path or not os.path.exists(path): return "Not found", 404
    if os.path.splitext(path)[1].lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}: return send_file(path)
    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            _, buf = cv2.imencode(".jpg", cv2.resize(frame, (160, 90)))
            return Response(buf.tobytes(), mimetype='image/jpeg')
    return "Error", 500

def run_server():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(port=5050, debug=False, use_reloader=False)

if __name__ == '__main__':
    threading.Thread(target=run_server, daemon=True).start()
    html_path = resource_path(os.path.join('web', 'index.html'))
    window = webview.create_window('XenoPlayer', html_path, js_api=api, width=1000, height=700)
    api._window = window
    webview.start(debug=False)