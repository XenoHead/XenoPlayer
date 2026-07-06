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
    return {"favorites": [], "last_video": None, "max_volume": 100, "move_targets": {}, "saved_folders": ["", "", "", "", ""], "external_apps": ["", "", "", "", ""], "default_folder": -1, "hotkeys": {"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""]}, "saved_volumes": {}, "favs_mode": "folder", "manga_sites": [], "audio_sites": [], "online_playlists": {}}

def save_settings(s):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=4)

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', os.path.basename(s))]

def clean_filename(name):
    import string
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleaned = ''.join(c for c in name if c in valid_chars or c.isalnum())
    return cleaned.strip()

# --- CORE FRONTEND INTEGRATED API HANDLERS ---

class Api:
    def __init__(self):
        self.settings = load_settings()
        self.playlist = []
        self.full_playlist = []
        self.filter_mode = "all" # "all", "favorites", "unfavorites"
        self.current_index = -1
        self._window = None
        self.cancel_flags = {}

    def get_startup_info(self):
        art_path = resource_path('XenoHead_art.png')
        if os.path.exists(art_path):
            return {"art_path": art_path}
        return {"art_path": None}

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
                    supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
                    if self.settings.get("recursive_load", False):
                        first_file = None
                        for root, dirs, files in os.walk(def_folder):
                            first_file = next((os.path.join(root, f) for f in files if os.path.splitext(f)[1].lower() in supported), None)
                            if first_file:
                                break
                        if first_file:
                            self.load_directory(first_file, play=False)
                            return {"status": "ready"}
                    else:
                        first_file = next((f for f in os.listdir(def_folder) if os.path.isfile(os.path.join(def_folder, f)) and os.path.splitext(f)[1].lower() in supported), None)
                        if first_file:
                            self.load_directory(os.path.join(def_folder, first_file), play=False)
                            return {"status": "ready"}
                except Exception: pass
                
        last_video = self.settings.get("last_video")
        if last_video and os.path.exists(last_video):
            self.load_directory(last_video, play=False)
        return {"status": "ready"}

    def open_dialog(self):
        last_dir = self.settings.get("last_opened_dir", "")
        if last_dir and not os.path.exists(last_dir): last_dir = ""
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=last_dir, allow_multiple=False, file_types=('Media Files (*.mp4;*.webm;*.ogg;*.mp3;*.wav;*.wave;*.jpg;*.png;*.gif;*.webp)', 'All files (*.*)'))
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

    def apply_filter(self, current_filepath=None):
        if not current_filepath and 0 <= self.current_index < len(self.playlist):
            current_filepath = self.playlist[self.current_index]
        elif not current_filepath and self.full_playlist:
            current_filepath = self.full_playlist[0]

        favs = self.settings.get("favorites", [])
        favs_mode = self.settings.get("favs_mode", "folder")

        if self.filter_mode == "favorites":
            if favs_mode == "global":
                self.playlist = [p for p in favs if os.path.exists(p)]
            else:
                self.playlist = [p for p in self.full_playlist if p in favs]
        elif self.filter_mode == "unfavorites":
            self.playlist = [p for p in self.full_playlist if p not in favs]
        else:
            self.playlist = list(self.full_playlist)

        if current_filepath:
            try:
                self.current_index = self.playlist.index(current_filepath)
            except ValueError:
                self.current_index = 0 if self.playlist else -1
        else:
            self.current_index = 0 if self.playlist else -1

    def load_directory(self, filepath, play=True):
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath): return
        directory = os.path.dirname(filepath)
        
        supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
        
        if self.settings.get("recursive_load", False):
            full_playlist = []
            for root, dirs, files in os.walk(directory):
                for f in files:
                    if os.path.splitext(f)[1].lower() in supported:
                        full_playlist.append(os.path.join(root, f))
            self.full_playlist = full_playlist
        else:
            try:
                files = os.listdir(directory)
            except: return
            self.full_playlist = [os.path.join(directory, f) for f in files if os.path.splitext(f)[1].lower() in supported]
            
        self.full_playlist.sort(key=natural_sort_key)
        
        self.filter_mode = "all"
        self.apply_filter(filepath)
            
        self.settings["last_video"] = filepath
        save_settings(self.settings)
        self._window.evaluate_js('updatePlaylist()')
        if play:
            self.play_current()

    def load_selected_directory(self, directory_path):
        directory_path = os.path.abspath(directory_path)
        if not os.path.isdir(directory_path): return
        
        supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
        
        if self.settings.get("recursive_load", False):
            full_playlist = []
            for root, dirs, files in os.walk(directory_path):
                for f in files:
                    if os.path.splitext(f)[1].lower() in supported:
                        full_playlist.append(os.path.join(root, f))
            self.full_playlist = full_playlist
        else:
            try:
                files = os.listdir(directory_path)
            except: return
            self.full_playlist = [os.path.join(directory_path, f) for f in files if os.path.splitext(f)[1].lower() in supported]
            
        self.full_playlist.sort(key=natural_sort_key)
        
        self.filter_mode = "all"
        filepath = self.full_playlist[0] if self.full_playlist else None
        self.apply_filter(filepath)
            
        if filepath:
            self.settings["last_video"] = filepath
            save_settings(self.settings)
            
        self._window.evaluate_js('updatePlaylist()')
        if filepath:
            self.play_current()

    def play_favorites(self):
        self.filter_mode = "favorites"
        self.apply_filter()
        if 0 <= self.current_index < len(self.playlist):
            self.settings["last_video"] = self.playlist[self.current_index]
            save_settings(self.settings)
        self._window.evaluate_js('updatePlaylist()')
        self.play_current()
        return {"status": "ok"}

    def play_unfavorites(self):
        self.filter_mode = "unfavorites"
        self.apply_filter()
        if 0 <= self.current_index < len(self.playlist):
            self.settings["last_video"] = self.playlist[self.current_index]
            save_settings(self.settings)
        self._window.evaluate_js('updatePlaylist()')
        self.play_current()
        return {"status": "ok"}

    def get_playlist(self):
        playlist_items = []
        for p in self.playlist:
            if p.startswith('http://') or p.startswith('https://'):
                name = p.split('/')[-1]
                if hasattr(self, 'online_names') and p in self.online_names:
                    name = self.online_names[p]
                playlist_items.append({"path": p, "name": name})
            else:
                playlist_items.append({"path": p, "name": os.path.basename(p)})
        return playlist_items

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
            if os.path.exists(os.path.join(dir_path, '.manga')):
                is_manga = True
        
        favs_mode = self.settings.get("favs_mode", "folder")
        if favs_mode == "folder":
            filtered_favs = [f for f in self.settings.get("favorites", []) if os.path.dirname(f) == dir_path] if dir_path else []
        else:
            filtered_favs = self.settings.get("favorites", [])
            
        return {
            "favorites": filtered_favs,
            "move_targets": self.settings.get("move_targets", {}),
            "saved_volumes": self.settings.get("saved_volumes", {}),
            "saved_folders": self.settings.get("saved_folders", ["", "", "", "", ""]),
            "external_apps": self.settings.get("external_apps", ["", "", "", "", ""]),
            "default_folder": self.settings.get("default_folder", -1),
            "hotkeys": self.settings.get("hotkeys", {"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""]}),
            "current_path": current_path,
            "is_favorite": current_path in self.settings.get("favorites", []) if current_path else False,
            "is_manga_folder": is_manga,
            "favs_mode": favs_mode,
            "manga_sites": self.settings.get("manga_sites", []),
            "audio_sites": self.settings.get("audio_sites", []),
            "online_playlists": self.settings.get("online_playlists", {}),
            "favorite_manga_tags": self.settings.get("favorite_manga_tags", {"nhentai": [], "danbooru": [], "hentaiyoga": [], "rule34art": [], "ehentai": []}),
            "recursive_load": self.settings.get("recursive_load", False)
        }

    def get_dir_tree(self):
        if not self.full_playlist:
            return {"root": "", "subdirs": []}
        
        paths = [p for p in self.full_playlist if not (p.startswith('http://') or p.startswith('https://'))]
        if not paths:
            return {"root": "", "subdirs": []}
            
        try:
            dirs = [os.path.dirname(p) for p in paths]
            common_root = os.path.commonpath(dirs)
        except Exception:
            common_root = os.path.dirname(paths[0])
        
        if not common_root or not os.path.isdir(common_root):
            return {"root": "", "subdirs": []}
            
        subdirs = []
        try:
            for root, dirs, files in os.walk(common_root):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for d in dirs:
                    subdirs.append(os.path.normpath(os.path.join(root, d)))
        except:
            pass
            
        return {
            "root": common_root,
            "subdirs": subdirs
        }

    def toggle_favorite(self):
        if not (0 <= self.current_index < len(self.playlist)): return {"status": "error"}
        path = self.playlist[self.current_index]
        favs = self.settings.get("favorites", [])
        if path in favs: favs.remove(path)
        else: favs.append(path)
        self.settings["favorites"] = favs
        save_settings(self.settings)
        
        if self.filter_mode != "all":
            self.apply_filter(path)
            self._window.evaluate_js('updatePlaylist()')
            self.play_current()
            
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
        
        if self.filter_mode != "all":
            self.apply_filter()
            self._window.evaluate_js('updatePlaylist()')
            self.play_current()
            
        return self.get_state()

    def save_options(self, folders, default_index, external_apps=None, favs_mode="folder", manga_sites=None, audio_sites=None, recursive_load=None):
        self.settings["saved_folders"] = folders
        self.settings["default_folder"] = default_index
        if external_apps is not None: self.settings["external_apps"] = external_apps
        self.settings["favs_mode"] = favs_mode
        if manga_sites is not None: self.settings["manga_sites"] = manga_sites
        if audio_sites is not None: self.settings["audio_sites"] = audio_sites
        if recursive_load is not None: self.settings["recursive_load"] = recursive_load
        save_settings(self.settings)
        return self.get_state()

    def save_recursive_load(self, enabled):
        self.settings["recursive_load"] = enabled
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

    def play_online_playlist(self, tracks, start_index=0):
        # tracks is a list of {"name": name, "url": url}
        self.playlist = [t["url"] for t in tracks]
        self.online_names = {t["url"]: t["name"] for t in tracks}
        self.current_index = start_index
        self.filter_mode = "all"
        self._window.evaluate_js('updatePlaylist()')
        self.play_current()
        return {"status": "ok"}

    def save_online_playlists(self, playlists):
        self.settings["online_playlists"] = playlists
        save_settings(self.settings)
        return self.get_state()

    def download_online_track(self, url, name):
        try:
            import requests
            import string
            
            # Find the active folder directory
            if self.playlist and 0 <= self.current_index < len(self.playlist):
                active_path = self.playlist[self.current_index]
                if active_path.startswith('http://') or active_path.startswith('https://'):
                    dir_path = self.settings.get("last_opened_dir", "")
                else:
                    dir_path = os.path.dirname(active_path)
            else:
                dir_path = self.settings.get("last_opened_dir", "")
                
            if not dir_path or not os.path.exists(dir_path):
                return {"status": "error", "msg": "No active folder loaded. Load a folder first."}
                
            parsed_url = urllib.parse.urlparse(url)
            ext = os.path.splitext(parsed_url.path)[1].lower()
            if not ext:
                ext = ".mp3"
                
            cleaned_name = clean_filename(name)
            filename = f"{cleaned_name}{ext}"
            dest_path = os.path.join(dir_path, filename)
            
            def run_download():
                self.cancel_flags[name] = False
                safe_title = name.replace('\\', '\\\\').replace('"', '\\"')
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    r = requests.get(url, headers=headers, stream=True, timeout=30)
                    if r.status_code == 200:
                        total_size = int(r.headers.get('content-length', 0))
                        downloaded_size = 0
                        last_reported = 0
                        with open(dest_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if self.cancel_flags.get(name):
                                    raise Exception("Cancelled by user")
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    if downloaded_size - last_reported > 1024 * 250:
                                        last_reported = downloaded_size
                                        self._window.evaluate_js(f'updateAudioDownloadProgress({downloaded_size}, {total_size}, "{safe_title}")')
                        self.load_directory(dest_path)
                        self._log_download(name, dest_path, "audio")
                        self._window.evaluate_js(f'downloadCompleteNotify("{safe_title}")')
                    else:
                        self._window.evaluate_js(f'downloadFailedNotify("{safe_title}", "HTTP {r.status_code}")')
                except Exception as ex:
                    safe_ex = str(ex).replace('\\', '\\\\').replace('"', '\\"')
                    self._window.evaluate_js(f'downloadFailedNotify("{safe_title}", "{safe_ex}")')
                    
            threading.Thread(target=run_download, daemon=True).start()
            return {"status": "started"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def scrape_audio_links(self, url):
        try:
            import requests
            from bs4 import BeautifulSoup
            import urllib.parse
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            
            # Special JSON scraper for Liltsome
            if "liltsome.yerf.org" in url:
                json_url = urllib.parse.urljoin(url, "/data/library.json")
                try:
                    r = requests.get(json_url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        tracks = []
                        for artist in data.get("artists", []):
                            artist_name = artist.get("name", "Unknown Artist")
                            audio_files = artist.get("files", {}).get("audio", [])
                            for file in audio_files:
                                file_path = file.get("path", "")
                                if file_path:
                                    # Encode path components but keep directory separators
                                    encoded_path = urllib.parse.quote(file_path).replace('%2F', '/')
                                    track_url = urllib.parse.urljoin(url, f"audio_files/{encoded_path}")
                                    track_title = file.get("title", file.get("filename", "Unknown"))
                                    tracks.append({
                                        "name": f"{artist_name} - {track_title}",
                                        "url": track_url
                                    })
                        if tracks:
                            return {"status": "success", "tracks": tracks}
                except Exception as ex:
                    pass

            try:
                import cloudscraper
                scraper = cloudscraper.create_scraper()
                response = scraper.get(url, headers=headers, timeout=10)
            except:
                response = requests.get(url, headers=headers, timeout=10)
                
            if response.status_code != 200:
                return {"status": "error", "msg": f"Failed to load page: HTTP {response.status_code}"}
                
            soup = BeautifulSoup(response.text, 'html.parser')
            tracks = []
            supported_exts = {'.mp3', '.wav', '.ogg', '.m4a', '.mp4', '.webm'}
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                parsed_href = urllib.parse.urlparse(href)
                path = parsed_href.path
                ext = os.path.splitext(path)[1].lower()
                
                if ext in supported_exts:
                    abs_url = urllib.parse.urljoin(url, href)
                    text = a.text.strip()
                    if not text:
                        text = urllib.parse.unquote(os.path.basename(path))
                    tracks.append({"name": text, "url": abs_url})
            
            if not tracks:
                for audio in soup.find_all(['audio', 'video']):
                    src = audio.get('src')
                    if src:
                        abs_url = urllib.parse.urljoin(url, src)
                        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(abs_url).path))
                        tracks.append({"name": name, "url": abs_url})
                    for source in audio.find_all('source', src=True):
                        src = source['src']
                        abs_url = urllib.parse.urljoin(url, src)
                        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(abs_url).path))
                        tracks.append({"name": name, "url": abs_url})
            
            seen = set()
            unique_tracks = []
            for t in tracks:
                if t["url"] not in seen:
                    seen.add(t["url"])
                    unique_tracks.append(t)
                    
            return {"status": "success", "tracks": unique_tracks}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def open_external_url(self, url):
        import webbrowser
        try:
            webbrowser.open(url)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def open_in_app_browser(self, url, title="Browser"):
        try:
            webview.create_window(title, url, width=1000, height=700)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def rename_manga(self, path, newName):
        if not path: return {"status": "error"}
        parent = os.path.dirname(path)
        new_path = os.path.join(parent, newName)
        try:
            os.rename(path, new_path)
            known = self.settings.get("known_manga_folders", [])
            if path in known:
                known[known.index(path)] = new_path
            else:
                known.append(new_path)
            self.settings["known_manga_folders"] = known
            
            json_path = os.path.join(new_path, "manga_info.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["name"] = newName
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                except: pass
            save_settings(self.settings)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def unmark_folder_as_manga(self, path):
        if not path: return {"status": "error"}
        try:
            manga_file = os.path.join(path, ".manga")
            if os.path.exists(manga_file):
                os.remove(manga_file)
        except: pass
        known = self.settings.get("known_manga_folders", [])
        if path in known:
            known.remove(path)
            self.settings["known_manga_folders"] = known
            save_settings(self.settings)
        return {"status": "success"}

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
            return {"status": "success", "tags": [t for t in tags if not (t in seen or seen.add(t))][:100]}
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

    # --- DANBOORU AUTOMATION ENGINE ROUTING ---

    def get_danbooru_tags(self, query=None):
        try:
            import requests
            headers = {'User-Agent': 'XenoPlayer/1.0 (contact@xenohead.com)'}
            url = 'https://danbooru.donmai.us/tags.json?search[order]=count&limit=100'
            if query:
                url += f'&search[name_matches]=*{urllib.parse.quote(query)}*'
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                tags = [t['name'] for t in r.json() if 'name' in t]
                return {"status": "success", "tags": tags}
            return {"status": "error", "msg": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def search_danbooru(self, query):
        try:
            import requests
            headers = {'User-Agent': 'XenoPlayer/1.0 (contact@xenohead.com)'}
            url = f"https://danbooru.donmai.us/posts.json?tags={urllib.parse.quote(query)}&limit=20"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                results = []
                for post in r.json():
                    post_id = post.get('id')
                    if not post_id: continue
                    thumb = post.get('preview_file_url') or post.get('large_file_url') or post.get('file_url') or ""
                    
                    if not thumb:
                        media_asset = post.get('media_asset') or {}
                        variants = media_asset.get('variants') or []
                        for v in variants:
                            if v.get('type') == 'preview': thumb = v.get('url', '')
                        if not thumb and variants: thumb = variants[0].get('url', '')
                    if not thumb: thumb = post.get('source', '')
                    
                    post_url = f"https://danbooru.donmai.us/posts/{post_id}"
                    tag_string = post.get('tag_string_character') or post.get('tag_string_artist') or post.get('tag_string') or ""
                    title = f"Danbooru {post_id} - " + (tag_string[:40].strip() if tag_string else "Image")
                    results.append({
                        "title": title,
                        "thumb": thumb,
                        "url": post_url
                    })
                return {"status": "success", "results": results}
            return {"status": "error", "msg": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def search_hentai_yoga(self, query):
        try:
            import requests
            from bs4 import BeautifulSoup
            import urllib.parse
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            url = f"https://hentai.yoga/search?s={urllib.parse.quote(query)}"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                return {"status": "error", "msg": f"HTTP {r.status_code}"}
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            
            for card in soup.select('.video-card, .episode-card, .chapter-card, [itemtype*="VideoObject"]'):
                name_meta = card.find('meta', itemprop='name')
                url_meta = card.find('meta', itemprop='url') or card.find('meta', itemprop='contentUrl')
                thumb_meta = card.find('meta', itemprop='thumbnailUrl')
                
                title = name_meta.get('content') if name_meta else None
                link = url_meta.get('content') if url_meta else None
                thumb = thumb_meta.get('content') if thumb_meta else None
                
                if not title:
                    title_el = card.select_one('.video-title, .episode-card-title-mini, .chapter-card-title-mini, .episode-title')
                    if title_el: title = title_el.text.strip()
                if not link:
                    link_el = card.select_one('a')
                    if link_el: link = urllib.parse.urljoin(url, link_el.get('href'))
                if not thumb:
                    img_el = card.find('img')
                    if img_el: thumb = img_el.get('src') or img_el.get('data-src') or img_el.get('data-lazy-src')
                    
                if title and link:
                    if not any(res['url'] == link for res in results):
                        if thumb and thumb.startswith('//'): thumb = 'https:' + thumb
                        results.append({
                            "title": title.strip(),
                            "thumb": thumb or "",
                            "url": urllib.parse.urljoin(url, link)
                        })
            return {"status": "success", "results": results}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def get_hentai_yoga_tags(self, query=None):
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            url = 'https://hentai.yoga/tags'
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                tags = []
                for pill in soup.select('.tag-pill'):
                    name_el = pill.select_one('.tag-name')
                    if name_el:
                        name = name_el.text.strip()
                        if query:
                            if query.lower() in name.lower():
                                tags.append(name)
                        else:
                            tags.append(name)
                # Fallback to footer tag links if tag-pills are empty
                if not tags:
                    for tag_link in soup.select('.footer-tag-link'):
                        name = tag_link.text.replace(' hentai porn', '').replace(' hentai', '').strip()
                        if query:
                            if query.lower() in name.lower():
                                tags.append(name)
                        else:
                            tags.append(name)
                seen = set()
                return {"status": "success", "tags": [t for t in tags if not (t in seen or seen.add(t))][:100]}
            return {"status": "error", "msg": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def search_rule34art(self, query):
        try:
            import requests
            from bs4 import BeautifulSoup
            import urllib.parse
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            url = f"https://rule34.art/search?search={urllib.parse.quote(query)}"
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return {"status": "error", "msg": f"HTTP {r.status_code}"}
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            for row in soup.select('.masonry-item.views-row, div.views-row'):
                link_el = row.select_one('.afterclear a, .views-field-title a')
                img_el = row.select_one('img.img-responsive, img')
                if not link_el:
                    continue
                title = link_el.text.strip()
                href = link_el.get('href', '')
                link = urllib.parse.urljoin('https://rule34.art', href)
                thumb = ''
                if img_el:
                    src = img_el.get('src') or img_el.get('data-src') or ''
                    if src:
                        thumb = urllib.parse.urljoin('https://rule34.art', src)
                if title and link and not any(r['url'] == link for r in results):
                    results.append({"title": title, "thumb": thumb, "url": link})
            return {"status": "success", "results": results[:30]}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def get_rule34art_tags(self, query=None):
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            r = requests.get('https://rule34.art/comics/category', headers=headers, timeout=12)
            if r.status_code != 200:
                return {"status": "error", "msg": f"HTTP {r.status_code}"}
            soup = BeautifulSoup(r.text, 'html.parser')
            tags = []
            seen = set()
            for a in soup.select('.views-field-name a, .field-content a'):
                name = a.text.strip()
                if not name or name in seen:
                    continue
                if query and query.lower() not in name.lower():
                    continue
                seen.add(name)
                tags.append(name)
            return {"status": "success", "tags": tags[:100]}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def search_ehentai(self, query):
        try:
            import requests
            from bs4 import BeautifulSoup
            import urllib.parse
            
            try:
                import cloudscraper
                scraper = cloudscraper.create_scraper()
            except:
                scraper = requests
                
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            url = f"https://e-hentai.org/?f_search={urllib.parse.quote(query)}"
            r = scraper.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                return {"status": "error", "msg": f"HTTP {r.status_code}"}
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            
            # E-Hentai has several layout formats (Minimal, Compact, Extended, Thumbnail).
            # We select containers from any known layout to ensure we always capture results.
            for container in soup.select('table.itg tr, .itg .gl1t, .itg .gl3t, .gl1e'):
                a_els = container.select('a[href*="e-hentai.org/g/"]')
                if not a_els:
                    continue
                a_el = a_els[0]
                href = a_el.get('href', '')
                
                # Extract Title
                title_el = container.select_one('.glink')
                title = title_el.text.strip() if title_el else ""
                img_el = container.select_one('img')
                
                if not title and img_el:
                    title = img_el.get('title') or img_el.get('alt') or ""
                if not title:
                    title = a_el.get('title') or a_el.text.strip() or "Gallery"
                    
                # Extract Thumbnail
                thumb = ""
                if img_el:
                    thumb = img_el.get('data-src') or img_el.get('src') or ""
                    
                if href and not any(res['url'] == href for res in results):
                    results.append({"title": title, "thumb": thumb, "url": href})

            return {"status": "success", "results": results[:30]}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def get_ehentai_tags(self, query=None):
        # E-hentai doesn't have a public tag listing API, so return a curated popular tag list
        popular_tags = [
            "lolicon", "shotacon", "incest", "full color", "schoolgirl uniform",
            "stockings", "blowjob", "ahegao", "group", "paizuri", "milf",
            "anal", "big breasts", "small breasts", "ponytail", "maid",
            "vanilla", "rape", "mind break", "mosaic censorship", "uncensored",
            "sister", "oppai loli", "flat chest", "twintails", "catgirl",
            "doujinshi", "manga", "artist cg", "western", "game cg",
            "swimsuit", "exhibitionism", "public use", "impregnation",
            "harem", "netorare", "femdom", "futanari", "yaoi", "yuri"
        ]
        if query:
            filtered = [t for t in popular_tags if query.lower() in t.lower()]
            return {"status": "success", "tags": filtered}
        return {"status": "success", "tags": popular_tags}

    def save_favorite_manga_tags(self, tags):
        self.settings["favorite_manga_tags"] = tags
        save_settings(self.settings)
        return self.get_state()

    def get_manga_details(self, url, source):
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            
            # nhentai requires cloudscraper occasionally
            if "nhentai.net" in url:
                try:
                    import cloudscraper
                    scraper = cloudscraper.create_scraper()
                    r = scraper.get(url, timeout=15)
                except:
                    r = requests.get(url, headers=headers, timeout=15)
            else:
                r = requests.get(url, headers=headers, timeout=15)
                
            if r.status_code != 200:
                return {"status": "error", "msg": f"HTTP {r.status_code}"}
                
            soup = BeautifulSoup(r.text, 'html.parser')
            tags = []
            image_count = "Unknown"
            
            if source == "nhentai" or "nhentai.net" in url:
                for a in soup.select('.tag-container .tags a.tag'):
                    name_el = a.select_one('.name')
                    if name_el:
                        tags.append(name_el.text.strip())
                # Try to find page count
                for s in soup.select('.tag-container.field-name .name'):
                    if s.text.strip().isdigit():
                        image_count = s.text.strip()
                        break
                if image_count == "Unknown":
                    # alternative way
                    for div in soup.find_all('div'):
                        if 'pages' in div.text.lower() and len(div.text) < 15:
                            image_count = ''.join(filter(str.isdigit, div.text))
                            if image_count: break
            
            elif source == "danbooru" or "danbooru" in url:
                for a in soup.select('.search-tag'):
                    tags.append(a.text.strip())
                image_count = "1"
                
            elif source == "hentaiyoga" or "hentai.yoga" in url:
                for pill in soup.select('.tag-pill .tag-name, .video-tags a, .footer-tag-link'):
                    tags.append(pill.text.strip())
                img_els = soup.select('img[src*="/manga/"]')
                if img_els:
                    image_count = str(len(img_els))
                else:
                    chap_els = soup.select('a[href*="/chapter/"]')
                    if chap_els:
                        image_count = f"Chapters: {len(chap_els)}"
                
            elif source == "rule34art" or "rule34.art" in url:
                for a in soup.select('.field-name-field-tags a, .tag-type-general a'):
                    tags.append(a.text.strip())
                image_count = "1+"
                
            elif source == "ehentai" or "e-hentai.org" in url:
                for a in soup.select('#taglist td a'):
                    tags.append(a.text.strip())
                for td in soup.select('.gdt2'):
                    if 'pages' in td.text.lower():
                        image_count = td.text.lower().replace('pages', '').strip()
                        
            # generic fallback
            if not tags:
                for a in soup.select('a[href*="/tag/"], a[href*="/tags/"], a[href*="?tags="]'):
                    t = a.text.strip()
                    if t and t not in tags and len(t) < 40:
                        tags.append(t)
                        
            seen = set()
            unique_tags = []
            for t in tags:
                if t and t not in seen:
                    seen.add(t)
                    unique_tags.append(t)
                    
            return {"status": "success", "tags": unique_tags[:50], "image_count": image_count}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

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

    def _log_download(self, title, path, media_type="manga", status="success"):
        import time
        history = self.settings.get("download_history", [])
        history.insert(0, {
            "title": title,
            "path": path,
            "type": media_type,
            "status": status,
            "timestamp": time.time()
        })
        self.settings["download_history"] = history[:100] # Keep only the last 100 entries
        save_settings(self.settings)

    def get_download_history(self):
        
        return self.settings.get("download_history", [])

    def clear_download_history(self):
        self.settings["download_history"] = []
        save_settings(self.settings)
        return {"status": "success"}

    def download_nhentai(self, url, title, media_type="all"):
        if "hentai.yoga" in url:
            return self.download_hentai_yoga(url, title, media_type)
        if "rule34.art" in url:
            return self.download_rule34art_comic(url, title)
        if "danbooru.donmai.us" in url:
            return self.download_danbooru(url, title)
            
        import string
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        download_dir = os.path.join(self.get_manga_download_dir()["dir"], folder_name)
        
        def run_download():
            self.cancel_flags[title] = False
            safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
            try:
                os.makedirs(download_dir, exist_ok=True)
                open(os.path.join(download_dir, ".manga"), 'w').close()
                import subprocess, time
                cmd = [sys.executable, "gallery_dl_module", "-d", download_dir, url] if getattr(sys, 'frozen', False) else [sys.executable, "-m", "gallery_dl", "-d", download_dir, url]
                process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                while process.poll() is None:
                    if self.cancel_flags.get(title):
                        process.terminate()
                        raise Exception("Cancelled by user")
                    time.sleep(0.5)
                if process.returncode != 0 and not self.cancel_flags.get(title):
                    raise Exception(f"gallery-dl failed with return code {process.returncode}")
                
                # Flatten any nested subdirectories created by gallery-dl
                import shutil
                for root, dirs, files in os.walk(download_dir, topdown=False):
                    if root != download_dir:
                        for f in files:
                            try:
                                shutil.move(os.path.join(root, f), os.path.join(download_dir, f))
                            except: pass
                        try:
                            os.rmdir(root)
                        except: pass
                
                self._log_download(title, download_dir, "manga")
                self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}

    def download_danbooru(self, url, title):
        import string
        import threading
        import os
        import urllib.parse
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        if not folder_name:
            folder_name = "Danbooru_Post"
            
        download_dir = os.path.join(self.get_manga_download_dir()["dir"], folder_name)
        
        def run_download():
            self.cancel_flags[title] = False
            safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
            try:
                import requests
                headers = {'User-Agent': 'XenoPlayer/1.0 (contact@xenohead.com)'}
                
                os.makedirs(download_dir, exist_ok=True)
                open(os.path.join(download_dir, ".manga"), 'w').close()
                
                api_url = url + ".json" if not url.endswith(".json") else url
                r = requests.get(api_url, headers=headers, timeout=15)
                if r.status_code != 200: raise Exception(f"HTTP {r.status_code}")
                
                post = r.json()
                img_url = post.get('file_url') or post.get('large_file_url')
                if not img_url:
                    media_asset = post.get('media_asset') or {}
                    variants = media_asset.get('variants') or []
                    if variants: img_url = variants[-1].get('url')
                
                if not img_url: raise Exception("No high-res image URL found in post.")
                
                img_r = requests.get(img_url, headers=headers, stream=True, timeout=30)
                if img_r.status_code == 200:
                    ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1]
                    if not ext: ext = ".jpg"
                    img_name = f"danbooru_{post.get('id', 'image')}{ext}"
                    dest = os.path.join(download_dir, img_name)
                    
                    total_size = int(img_r.headers.get('content-length', 0))
                    downloaded_size = 0
                    last_reported = 0
                    
                    with open(dest, 'wb') as f:
                        for chunk in img_r.iter_content(chunk_size=8192):
                            if self.cancel_flags.get(title):
                                raise Exception("Cancelled by user")
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                                if downloaded_size - last_reported > 1024 * 500:
                                    last_reported = downloaded_size
                                    self._window.evaluate_js(f'updateDownloadProgress({downloaded_size}, {total_size}, "{safe_title}")')
                    
                    self._log_download(title, download_dir, "manga")
                    self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
                else:
                    raise Exception(f"Failed to fetch image: HTTP {img_r.status_code}")
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}

    def download_hentai_yoga(self, url, title, media_type="all"):
        import string
        import threading
        import os
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        download_dir = os.path.join(self.get_manga_download_dir()["dir"], folder_name)
        
        def run_download():
            self.cancel_flags[title] = False
            video_title = f"{title} (Video)"
            self.cancel_flags[video_title] = False
            safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
            safe_video_title = video_title.replace('\\', '\\\\').replace('"', '\\"')
            try:
                import requests
                from bs4 import BeautifulSoup
                import urllib.parse
                import re
                import json

                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                
                os.makedirs(download_dir, exist_ok=True)
                open(os.path.join(download_dir, ".manga"), 'w').close()

                try:
                    import cloudscraper
                    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
                except:
                    scraper = requests

                r = scraper.get(url, headers=headers, timeout=15)
                if r.status_code != 200:
                    raise Exception(f"Failed to fetch page: HTTP {r.status_code}")
                
                soup = BeautifulSoup(r.text, 'html.parser')
                
                vid_downloaded = False
                img_downloaded = False
                
                if media_type in ["all", "vid"]:
                    mp4_url = None
                    for script in soup.find_all('script', type='application/ld+json'):
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, dict):
                                if data.get('@type') == 'VideoObject' and data.get('contentUrl'):
                                    mp4_url = data['contentUrl']
                                    break
                                elif '@graph' in data:
                                    for item in data['@graph']:
                                        if item.get('@type') == 'VideoObject' and item.get('contentUrl'):
                                            mp4_url = item['contentUrl']
                                            break
                        except:
                            pass
                    
                    if not mp4_url:
                        meta_embed = soup.find('meta', itemprop='embedUrl') or soup.find('meta', itemprop='contentUrl')
                        if meta_embed:
                            embed_val = meta_embed.get('content')
                            if embed_val and embed_val.endswith('.mp4'):
                                mp4_url = embed_val
                    
                    if not mp4_url:
                        m = re.search(r'https://cdn\.hentai\.yoga/videos/[^\s"\']+\.mp4', r.text)
                        if m:
                            mp4_url = m.group(0)
                    
                    if mp4_url:
                        thumb_url = None
                        meta_thumb = soup.find('meta', itemprop='thumbnailUrl') or soup.find('meta', property='og:image')
                        if meta_thumb:
                            thumb_url = meta_thumb.get('content')
                            
                        video_filename = f"{folder_name}.mp4"
                        video_dest = os.path.join(download_dir, video_filename)
                        
                        resp = scraper.get(mp4_url, headers=headers, stream=True, timeout=30)
                        ctype = resp.headers.get('Content-Type', '').lower()
                        if resp.status_code == 200 and 'text/html' not in ctype:
                            total_size = int(resp.headers.get('content-length', 0))
                            downloaded_size = 0
                            last_reported = 0
                            with open(video_dest, 'wb') as f:
                                for chunk in resp.iter_content(chunk_size=8192):
                                    if self.cancel_flags.get(video_title) or self.cancel_flags.get(title):
                                        raise Exception("Cancelled by user")
                                    if chunk:
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        if downloaded_size - last_reported > 1024 * 500:
                                            last_reported = downloaded_size
                                            self._window.evaluate_js(f'updateDownloadProgress({downloaded_size}, {total_size}, "{safe_video_title}")')
                            vid_downloaded = True
                        else:
                            raise Exception(f"Failed to download video stream: HTTP {resp.status_code} - Content-Type: {ctype}")
                            
                        if thumb_url:
                            try:
                                thumb_resp = scraper.get(thumb_url, headers=headers, timeout=15)
                                if thumb_resp.status_code == 200:
                                    with open(os.path.join(download_dir, "cover.jpg"), 'wb') as f:
                                        f.write(thumb_resp.content)
                            except:
                                pass
                    elif media_type == "vid":
                        raise Exception("Could not find a video stream URL on this page.")
                                 
                if media_type in ["all", "img"]:
                    chapter_urls = []
                    if "/chapter/" not in url:
                        for a_tag in soup.find_all('a'):
                            href = a_tag.get('href')
                            if href:
                                full_href = urllib.parse.urljoin(url, href)
                                if "/chapter/" in full_href and full_href not in chapter_urls:
                                    chapter_urls.append(full_href)
                                    
                    if chapter_urls:
                        for idx, chap_url in enumerate(chapter_urls):
                            if self.cancel_flags.get(title):
                                raise Exception("Cancelled by user")
                            chap_r = scraper.get(chap_url, headers=headers, timeout=15)
                            if chap_r.status_code == 200:
                                chap_soup = BeautifulSoup(chap_r.text, 'html.parser')
                                chap_title = f"{title} - Ch {idx+1}"
                                self.cancel_flags[chap_title] = False
                                found = self._download_manga_soup_images(chap_soup, chap_url, download_dir, headers, prefix=f"c{idx+1}_", title=chap_title, scraper=scraper)
                                if found: img_downloaded = True
                    else:
                        found = self._download_manga_soup_images(soup, url, download_dir, headers, title=title, scraper=scraper)
                        if found: img_downloaded = True
                        
                    if media_type == "img" and not img_downloaded:
                        raise Exception("Could not find any images on this page.")

                if not vid_downloaded and not img_downloaded:
                    raise Exception("No matching media found for the selected type.")
                    
                self._log_download(title, download_dir, "manga")
                self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}

    def _download_manga_soup_images(self, soup, page_url, download_dir, headers, prefix="", title="", scraper=None):
        self.cancel_flags[title] = False
        if not scraper:
            try:
                import cloudscraper
                scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
            except:
                import requests
                scraper = requests
                
        import urllib.parse
        import re
        import os
        
        images = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                full_src = urllib.parse.urljoin(page_url, src)
                if "cdn.hentai.yoga/manga/" in full_src or "cdn2.hentai.yoga/manga/" in full_src or re.search(r'chapter-\d+-\d+\.(jpg|jpeg|png|webp)', full_src):
                    if full_src not in images:
                        images.append(full_src)
                        
        if not images:
            found_imgs = re.findall(r'https?://cdn\d*\.hentai\.yoga/manga/[^\s"\']+\.(?:jpg|jpeg|png|webp)', str(soup))
            for img in found_imgs:
                if img not in images:
                    images.append(img)
                    
        total_images = len(images)
        if total_images == 0:
            return False
            
        successful_downloads = 0
        for idx, img_url in enumerate(images):
            if self.cancel_flags.get(title):
                raise Exception("Cancelled by user")
            try:
                img_resp = scraper.get(img_url, headers=headers, timeout=15)
                if img_resp.status_code == 200:
                    ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1]
                    if not ext: ext = ".jpg"
                    img_name = f"{prefix}{idx+1:03d}{ext}"
                    with open(os.path.join(download_dir, img_name), 'wb') as f:
                        f.write(img_resp.content)
                    successful_downloads += 1
            except:
                pass
            finally:
                safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
                self._window.evaluate_js(f'updateDownloadProgress({idx+1}, {total_images}, "{safe_title}")')
        return successful_downloads > 0

    def download_rule34art_comic(self, url, title):
        import string
        import threading
        import os
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        if not folder_name:
            folder_name = "Rule34Art_Comic"
            
        download_dir = os.path.join(self.get_manga_download_dir()["dir"], folder_name)
        
        def run_download():
            self.cancel_flags[title] = False
            safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
            try:
                import requests
                from bs4 import BeautifulSoup
                import urllib.parse
                import re
                import concurrent.futures
                
                try:
                    import cloudscraper
                    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
                except:
                    scraper = requests
                    
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                os.makedirs(download_dir, exist_ok=True)
                open(os.path.join(download_dir, ".manga"), 'w').close()
                
                current_url = url
                images = []
                visited_pages = set()
                
                def is_img_url(u):
                    p = urllib.parse.urlparse(u).path.lower()
                    return p.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))
                
                while current_url and current_url not in visited_pages:
                    if self.cancel_flags.get(title):
                        raise Exception("Cancelled by user")
                    visited_pages.add(current_url)
                    r = scraper.get(current_url, headers=headers, timeout=15)
                    if r.status_code != 200: 
                        if not images: raise Exception(f"Failed to load page: HTTP {r.status_code}")
                        break
                    
                    soup = BeautifulSoup(r.text, 'html.parser')
                    
                    found_on_page = False
                    for a in soup.select('a.colorbox, .field-items a, .views-field-field-gallery a, .views-field-php a'):
                        href = a.get('href')
                        if href and is_img_url(href):
                            full_url = urllib.parse.urljoin(current_url, href)
                            if not any(x[0] == full_url for x in images):
                                images.append((full_url, full_url))
                                found_on_page = True
                                
                    for img in soup.select('.view-content img, .field-items img, article img'):
                        src = img.get('src') or img.get('data-src') or ''
                        if not src: continue
                        clean_src = re.sub(r'/styles/[^/]+/public/', '/public/', src)
                        full_url = urllib.parse.urljoin(current_url, clean_src)
                        original_url = urllib.parse.urljoin(current_url, src)
                        if any(x in full_url.lower() for x in ['avatar', 'logo', 'icon', 'profile', 'button']):
                            continue
                        if is_img_url(full_url):
                            if not any(x[0] == full_url for x in images):
                                images.append((full_url, original_url))
                                found_on_page = True
                                
                    if not found_on_page:
                        node_links = []
                        parsed_base = urllib.parse.urlparse(url).path.rstrip('/')
                        for a in soup.find_all('a', href=True):
                            href = a.get('href')
                            parsed_href = urllib.parse.urlparse(urllib.parse.urljoin(current_url, href)).path.rstrip('/')
                            if parsed_href.startswith(parsed_base) and parsed_href != parsed_base:
                                full_link = urllib.parse.urljoin(current_url, href)
                                if full_link not in node_links:
                                    node_links.append(full_link)
                                    
                        for node_link in node_links:
                            if node_link in visited_pages: continue
                            visited_pages.add(node_link)
                            nr = scraper.get(node_link, headers=headers, timeout=15)
                            if nr.status_code == 200:
                                nsoup = BeautifulSoup(nr.text, 'html.parser')
                                for img in nsoup.select('.field-name-field-image img, .field-items img, #main-content img'):
                                    src = img.get('src') or img.get('data-src') or ''
                                    if not src: continue
                                    clean_src = re.sub(r'/styles/[^/]+/public/', '/public/', src)
                                    full_url = urllib.parse.urljoin(node_link, clean_src)
                                    original_url = urllib.parse.urljoin(node_link, src)
                                    if any(x in full_url.lower() for x in ['avatar', 'logo', 'icon']): continue
                                    if is_img_url(full_url):
                                        if not any(x[0] == full_url for x in images):
                                            images.append((full_url, original_url))
                                            
                    next_link = soup.select_one('li.pager-next a, .pager__item--next a, a[title="Go to next page"]')
                    if next_link and next_link.get('href'):
                        current_url = urllib.parse.urljoin(current_url, next_link['href'])
                    else:
                        current_url = None
                        
                if not images:
                    raise Exception("Could not find any comic images on this page.")
                    
                total_images = len(images)
                downloaded_count = 0
                successful_downloads = 0
                lock = threading.Lock()
                
                def download_image(item):
                    if self.cancel_flags.get(title): return
                    nonlocal downloaded_count, successful_downloads
                    idx, urls = item
                    clean_url, original_url = urls
                    try:
                        import requests
                        req_headers = headers.copy()
                        req_headers['Referer'] = 'https://rule34.art/'
                        req_headers['Accept'] = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
                        
                        img_r = requests.get(clean_url, headers=req_headers, timeout=20)
                        if img_r.status_code != 200 or 'text/html' in img_r.headers.get('Content-Type', '').lower():
                            img_r = requests.get(original_url, headers=req_headers, timeout=20)
                            
                        if img_r.status_code != 200 or 'text/html' in img_r.headers.get('Content-Type', '').lower():
                            import cloudscraper
                            iso_scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
                            img_r = iso_scraper.get(clean_url, headers=req_headers, timeout=20)
                            
                        if img_r.status_code != 200 or 'text/html' in img_r.headers.get('Content-Type', '').lower():
                            import cloudscraper
                            iso_scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
                            img_r = iso_scraper.get(original_url, headers=req_headers, timeout=20)
                            
                        if img_r.status_code == 200 and 'text/html' not in img_r.headers.get('Content-Type', '').lower():
                            ext = os.path.splitext(urllib.parse.urlparse(original_url).path)[1]
                            if not ext: ext = ".jpg"
                            img_name = f"{idx+1:03d}{ext}"
                            with open(os.path.join(download_dir, img_name), 'wb') as f:
                                f.write(img_r.content)
                            with lock:
                                successful_downloads += 1
                    except Exception:
                        pass
                    finally:
                        with lock:
                            downloaded_count += 1
                            current = downloaded_count
                        self._window.evaluate_js(f'updateDownloadProgress({current}, {total_images}, "{safe_title}")')
                        
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    executor.map(download_image, enumerate(images))
                        
                if self.cancel_flags.get(title):
                    raise Exception("Cancelled by user")
 
                if successful_downloads == 0:
                    raise Exception("Failed to fetch images. Access denied by server/Cloudflare.")
                    
                self._log_download(title, download_dir, "manga")
                self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                
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
                    # In a COLLECT/onedir build, ocr_worker.exe sits in ocr_worker/ or next to XenoPlayer.exe
                    exe_dir = os.path.dirname(sys.executable)
                    worker_exe = os.path.join(exe_dir, "ocr_worker", "ocr_worker.exe")
                    if not os.path.exists(worker_exe):
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
            if path in self.full_playlist:
                self.full_playlist.remove(path)
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
        self.full_playlist = [p for p in self.full_playlist if p not in paths]
        if self.current_index >= len(self.playlist): self.current_index = max(-1, len(self.playlist) - 1)
        return {"status": "success"}

    def rename_file(self, old_path, new_name):
        np = os.path.join(os.path.dirname(old_path), new_name + os.path.splitext(old_path)[1])
        try:
            os.rename(old_path, np)
            if old_path in self.playlist: self.playlist[self.playlist.index(old_path)] = np
            if old_path in self.full_playlist: self.full_playlist[self.full_playlist.index(old_path)] = np
            return {"status": "success"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def move_files(self, paths, target_name):
        td = self.settings.get("move_targets", {}).get(target_name, os.path.join(os.path.dirname(paths[0]), target_name))
        try:
            os.makedirs(td, exist_ok=True)
            for p in paths: shutil.move(p, td)
            self.playlist = [p for p in self.playlist if p not in paths]
            self.full_playlist = [p for p in self.full_playlist if p not in paths]
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
                        if fp in self.full_playlist:
                            self.full_playlist.remove(fp)
                        deleted += 1
                    else: hashes[h] = True
                except: pass
        if deleted > 0:
            self.current_index = 0 if self.playlist else -1
            self._window.evaluate_js('updatePlaylist()')
            if self.playlist: self.play_current()
        return {"status": "success", "msg": f"Deleted {deleted} duplicates."}

    def clean_manga_directory(self):
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not result or len(result) == 0:
            return {"status": "canceled"}
        target_dir = result[0]
            
        if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
            return {"status": "error", "msg": "Directory does not exist."}
            
        flattened_count = 0
        deleted_folders_count = 0
        
        try:
            # 1. Move nested media files up to immediate children of target_dir
            for item in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item)
                if os.path.isdir(item_path):
                    for root, dirs, files in os.walk(item_path, topdown=False):
                        if root != item_path:
                            for f in files:
                                src_file = os.path.join(root, f)
                                dst_file = os.path.join(item_path, f)
                                if not os.path.exists(dst_file):
                                    shutil.move(src_file, dst_file)
                                    flattened_count += 1
                                else:
                                    base, ext = os.path.splitext(f)
                                    counter = 1
                                    while os.path.exists(os.path.join(item_path, f"{base}_{counter}{ext}")):
                                        counter += 1
                                    shutil.move(src_file, os.path.join(item_path, f"{base}_{counter}{ext}"))
                                    flattened_count += 1
                                    
            # 2. Delete empty folders recursively in target_dir
            for root, dirs, files in os.walk(target_dir, topdown=False):
                if root != target_dir:
                    contents = os.listdir(root)
                    if not contents or (len(contents) == 1 and contents[0] == ".manga"):
                        try:
                            if contents and contents[0] == ".manga":
                                os.remove(os.path.join(root, ".manga"))
                            os.rmdir(root)
                            deleted_folders_count += 1
                        except:
                            pass
                            
            return {
                "status": "success", 
                "msg": f"Cleaned successfully!\n\nMoved {flattened_count} files up and deleted {deleted_folders_count} empty folders."
            }
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def get_directory_files(self, filepath):
        filepath = os.path.abspath(filepath)
        if os.path.isdir(filepath):
            directory = filepath
        else:
            directory = os.path.dirname(filepath)
            
        supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif'}
        
        if self.settings.get("recursive_load", False):
            full_paths = []
            for root, dirs, files in os.walk(directory):
                for f in files:
                    if os.path.splitext(f)[1].lower() in supported:
                        full_paths.append(os.path.normpath(os.path.join(root, f)))
        else:
            try:
                files = os.listdir(directory)
            except:
                return []
            full_paths = [os.path.normpath(os.path.join(directory, f)) for f in files if os.path.splitext(f)[1].lower() in supported]
            
        full_paths.sort(key=natural_sort_key)
        return [{"path": p, "name": os.path.basename(p)} for p in full_paths]

    def exit_app(self): self._window.destroy()

api = Api()

# --- FLASK STREAMING INFRASTRUCTURE ---

@app.route('/media')
def stream_media():
    path = request.args.get('path')
    if not path or not os.path.exists(path): return "Not found", 404
    
    import mimetypes
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = 'application/octet-stream'
        
    range_header = request.headers.get('Range', None)
    if not range_header: return send_file(path, mimetype=mime)
    
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
    rv = Response(generate(), 206, mimetype=mime)
    rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    return rv

@app.route('/thumbnail')
def get_thumbnail():
    path = request.args.get('path')
    if not path or not os.path.exists(path): return "Not found", 404
    ext = os.path.splitext(path)[1].lower()
    if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}: return send_file(path)
    if ext not in {'.mp4', '.webm', '.ogg'}: return "Not video", 404
    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            _, buf = cv2.imencode(".jpg", cv2.resize(frame, (160, 90)))
            return Response(buf.tobytes(), mimetype='image/jpeg')
    return "Error", 500

@app.route('/imgproxy')
def img_proxy():
    img_url = request.args.get('url', '')
    referer = request.args.get('ref', '')
    if not img_url or not img_url.startswith('http'):
        return "Bad request", 400
    try:
        import requests as req
        import urllib.parse
        # Derive referer from the URL if not provided
        if not referer:
            parsed = urllib.parse.urlparse(img_url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': referer,
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        }
        r = req.get(img_url, headers=headers, timeout=10, stream=True)
        if r.status_code != 200:
            return f"Upstream {r.status_code}", r.status_code
        content_type = r.headers.get('Content-Type', 'image/jpeg')
        return Response(r.content, mimetype=content_type)
    except Exception as e:
        return str(e), 500

def run_server():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(port=5050, debug=False, use_reloader=False)

if __name__ == '__main__':
    threading.Thread(target=run_server, daemon=True).start()
    html_path = resource_path(os.path.join('web', 'index.html'))
    window = webview.create_window('XenoPlayer', html_path, js_api=api, width=1000, height=700, maximized=True)
    api._window = window
    webview.start(debug=True)