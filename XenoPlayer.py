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
import zipfile
import subprocess
import signal
import uuid
import platform
import urllib.request
import urllib.error
from datetime import datetime
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
    settings = {"favorites": [], "last_video": None, "max_volume": 100, "move_targets": {}, 
"saved_folders": ["", "", "", "", ""], "external_apps": ["", "", "", "", ""], "default_folder": -1, "hotkeys": 
{"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""], 
"pause": ["KeyP", "", "", "", ""], "mute": ["KeyM", "", "", "", ""], 
"split_next_video": ["KeyD", "", "", "", ""], "split_next_image": ["KeyE", "", "", "", ""]}, "saved_volumes": {}, 
"favs_mode": "folder", "collection_sites": [], "audio_sites": [], "online_playlists": {}}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings.update(json.load(f))
        except: pass
    
    online_src_file = os.path.join(app_dir, "MAINLIST.json")
    if not os.path.exists(online_src_file):
        online_src_file = resource_path("MAINLIST.json")
    if os.path.exists(online_src_file):
        try:
            with open(online_src_file, "r", encoding="utf-8") as f:
                online_settings = json.load(f)
                if "collection_sites" in online_settings: settings["collection_sites"] = online_settings["collection_sites"]
                if "audio_sites" in online_settings: settings["audio_sites"] = online_settings["audio_sites"]
                if "story_sites" in online_settings: settings["story_sites"] = online_settings["story_sites"]
        except: pass

    return settings

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
        self.ftp_files = []
        self.ftp_index = -1
        self._current_directory = self.settings.get("last_opened_dir", "")
        self._cbz_temp_dir = None
        self._cbz_root = None
        self._cbz_archive_path = None
        self.onion_proc = None
        self.onion_pack_proc = None
        self.onion_session_dir = None
        self.onion_persistent_file = None
        self.onion_generation = 0
        self.onion_lock = threading.Lock()
        self.encrypt_proc = None
        self.encrypt_generation = 0
        self.encrypt_state = {"state": "idle", "archive_path": None, "error": None}
        self.onion_state = {
            "state": "stopped", "mode": None, "url": None, "key": None,
            "public": False, "error": None, "log": [], "auto_stop_minutes": 0
        }

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
                self._current_directory = def_folder
                try:
                    supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
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
                self.load_selected_directory(def_folder)
                return {"status": "ready"}
                
        last_video = self.settings.get("last_video")
        if last_video and os.path.exists(last_video):
            self.load_directory(last_video, play=False)
        return {"status": "ready"}

    def open_dialog(self):
        last_dir = self.settings.get("last_opened_dir", "")
        if last_dir and not os.path.exists(last_dir): last_dir = ""
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=last_dir, allow_multiple=False, file_types=('Media Files (*.mp4;*.webm;*.ogg;*.mp3;*.wav;*.wave;*.jpg;*.png;*.gif;*.webp;*.cbz)', 'All files (*.*)'))
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

    # --- ONIONSHARE FILE TRANSFER ---

    def _onion_default_receive_dir(self):
        saved = self.settings.get("onion_receive_dir")
        if saved: return saved
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        base = downloads if os.path.isdir(downloads) else os.path.expanduser("~")
        return os.path.join(base, "XenoPlayer Drop")

    def _find_onionshare_cli(self):
        exe = "onionshare-cli.exe" if os.name == "nt" else "onionshare-cli"
        configured = self.settings.get("onionshare_cli_path")
        candidates = []
        if configured: candidates.append(configured)
        candidates.extend([
            os.path.join(app_dir, exe),
            os.path.join(os.path.dirname(sys.executable), exe),
            os.path.join(app_dir, "onionshare", exe),
        ])
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base: candidates.append(os.path.join(base, "OnionShare", exe))
        local = os.environ.get("LOCALAPPDATA")
        if local: candidates.append(os.path.join(local, "Programs", "OnionShare", exe))
        found = shutil.which(exe) or shutil.which("onionshare-cli")
        if found: candidates.append(found)
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return None

    def _find_seven_zip(self):
        names = ("7z.exe", "7za.exe", "7zz.exe") if os.name == "nt" else ("7z", "7zz", "7za")
        configured = self.settings.get("seven_zip_path")
        candidates = []
        if configured: candidates.append(configured)
        for name in names:
            candidates.extend([
                os.path.join(app_dir, name),
                os.path.join(os.path.dirname(sys.executable), name),
            ])
            # Non-system Program Files dirs on any fixed drive (e.g. D:\Program Files)
            for drive in self._windows_drive_roots():
                candidates.append(os.path.join(drive, "Program Files", "7-Zip", name))
                candidates.append(os.path.join(drive, "Program Files (x86)", "7-Zip", name))
            for env in ("ProgramFiles", "ProgramFiles(x86)"):
                base = os.environ.get(env)
                if base: candidates.append(os.path.join(base, "7-Zip", name))
            local = os.environ.get("LOCALAPPDATA")
            if local:
                candidates.append(os.path.join(local, "Programs", "7-Zip", name))
                candidates.append(os.path.join(local, "7-Zip", name))
            program_data = os.environ.get("ProgramData")
            if program_data:
                candidates.append(os.path.join(program_data, "chocolatey", "tools", name))
                candidates.append(os.path.join(program_data, "chocolatey", "bin", name))
            found = shutil.which(name)
            if found: candidates.append(found)
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return None

    @staticmethod
    def _windows_drive_roots():
        if os.name != "nt":
            return []
        import string
        roots = []
        for letter in string.ascii_uppercase:
            root = letter + ":\\"
            try:
                if os.path.isdir(root):
                    roots.append(root)
            except Exception:
                pass
        return roots

    # --- LOCAL ENCRYPTION (7-ZIP) ---

    def _validate_encrypt_paths(self, paths):
        paths = [os.path.abspath(p) for p in (paths or []) if p]
        if not paths:
            return None, "Add at least one file or folder."
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            return None, f"Not found: {missing[0]}"
        if any("\n" in p or "\r" in p for p in paths):
            return None, "File names containing line breaks are not supported."
        norm = [os.path.normcase(p) for p in paths]
        filtered = []
        for path, normalized in zip(paths, norm):
            nested = False
            for other in norm:
                if normalized == other: continue
                if normalized.startswith(other.rstrip("\\/") + os.sep):
                    nested = True
                    break
            if not nested and path not in filtered:
                filtered.append(path)
        names = [os.path.basename(p.rstrip("\\/")).lower() for p in filtered]
        if len(set(names)) != len(names):
            return None, "Selected items have duplicate names. Rename them or select their parent folder."
        return filtered, None

    def _validate_encrypt_password(self, password):
        password = str(password or "")
        if len(password) < 6:
            return None, "Enter an archive password with at least 6 characters."
        if len(password) > 128:
            return None, "Archive password must be 128 characters or fewer."
        if not password.strip():
            return None, "Archive password cannot be only spaces."
        if any(c in password for c in ('"', "\r", "\n", "\x00")):
            return None, "Password cannot contain double quotes or line breaks."
        return password, None

    def get_encrypt_status(self):
        with self.onion_lock:
            state = dict(self.encrypt_state)
        return {"ok": state["state"] != "error", "state": state["state"],
                "archive_path": state["archive_path"], "error": state["error"]}

    def _run_encrypt_files(self, seven_zip, archive_path, paths, password, output_dir, generation):
        list_path = os.path.join(output_dir, f".xeno_list_{uuid.uuid4().hex}.txt")
        try:
            with open(list_path, "w", encoding="utf-8") as f:
                for path in paths:
                    f.write(path + "\n")
        except Exception as e:
            with self.onion_lock:
                if self.encrypt_generation == generation:
                    self.encrypt_state = {"state": "error", "archive_path": None, "error": f"Could not prepare the file list: {e}"}
            return
        cmd = [
            seven_zip, "a", "-t7z", f"-p{password}", "-mhe=on",
            "-mx=1", "-y", "-bd", "-spd", "-scsUTF-8",
            archive_path, f"@{list_path}"
        ]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = None
        try:
            proc = subprocess.Popen(
                cmd, cwd=app_dir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **kwargs
            )
            with self.onion_lock:
                if self.encrypt_generation != generation:
                    self._kill_process_tree(proc)
                    return
                self.encrypt_proc = proc
            output, _ = proc.communicate(timeout=3600)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            self._kill_process_tree(proc)
            try: output, _ = proc.communicate(timeout=5)
            except Exception: pass
            with self.onion_lock:
                if self.encrypt_generation == generation:
                    self.encrypt_state = {"state": "error", "archive_path": None, "error": "Compression timed out after 60 minutes."}
            return
        except Exception as e:
            with self.onion_lock:
                if self.encrypt_generation == generation:
                    self.encrypt_state = {"state": "error", "archive_path": None, "error": f"Could not run 7-Zip: {e}"}
            return
        finally:
            with self.onion_lock:
                if self.encrypt_proc is proc:
                    self.encrypt_proc = None
            try:
                if os.path.exists(list_path): os.remove(list_path)
            except Exception: pass
        if returncode != 0:
            lines = [line for line in (output or "").splitlines() if line.strip()]
            detail = " / ".join(lines[-4:]) if lines else f"7-Zip exited with code {returncode}."
            if password: detail = detail.replace(password, "[hidden]")
            with self.onion_lock:
                if self.encrypt_generation == generation:
                    self.encrypt_state = {"state": "error", "archive_path": None, "error": f"Compression failed: {detail}"}
            return
        if not os.path.isfile(archive_path) or os.path.getsize(archive_path) == 0:
            with self.onion_lock:
                if self.encrypt_generation == generation:
                    self.encrypt_state = {"state": "error", "archive_path": None, "error": "7-Zip did not create the archive."}
            return
        with self.onion_lock:
            if self.encrypt_generation == generation:
                self.encrypt_state = {"state": "done", "archive_path": archive_path, "error": None}

    def encrypt_files(self, paths, password, output_dir=None):
        with self.onion_lock:
            busy = self.encrypt_proc is not None or self.encrypt_state["state"] == "packing"
        if busy:
            return self.get_encrypt_status()
        filtered, error = self._validate_encrypt_paths(paths)
        if error:
            return {"ok": False, "state": "idle", "archive_path": None, "error": error}
        password, error = self._validate_encrypt_password(password)
        if error:
            return {"ok": False, "state": "idle", "archive_path": None, "error": error}
        seven_zip = self._find_seven_zip()
        if not seven_zip:
            return {"ok": False, "state": "idle", "archive_path": None, "error": "7-Zip not found. Install 7-Zip, then click Locate 7z.exe."}
        output_dir = os.path.abspath(output_dir or self.settings.get("onion_receive_dir") or self._onion_default_receive_dir())
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            return {"ok": False, "state": "idle", "archive_path": None, "error": f"Cannot use output folder: {e}"}
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = os.path.join(output_dir, f"XenoShare_{stamp}.7z")
        base, ext = os.path.splitext(archive_path)
        counter = 1
        while os.path.exists(archive_path):
            archive_path = f"{base}_{counter}{ext}"
            counter += 1
        with self.onion_lock:
            self.encrypt_generation += 1
            generation = self.encrypt_generation
            self.encrypt_state = {"state": "packing", "archive_path": archive_path, "error": None}
        threading.Thread(target=self._run_encrypt_files, args=(seven_zip, archive_path, filtered, password, output_dir, generation), daemon=True).start()
        return self.get_encrypt_status()

    def cancel_encrypt(self):
        with self.onion_lock:
            self.encrypt_generation += 1
            proc = self.encrypt_proc
            if self.encrypt_state["state"] == "packing":
                self.encrypt_state = {"state": "idle", "archive_path": None, "error": None}
        self._kill_process_tree(proc)
        with self.onion_lock:
            if self.encrypt_proc is proc:
                self.encrypt_proc = None
        return self.get_encrypt_status()

    def open_encrypt_output(self, archive_path):
        if not archive_path:
            return {"status": "error", "msg": "No archive available."}
        try:
            self.open_folder_location(archive_path)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def browse_encrypt_output(self):
        return self.browse_folder()

    def _onion_payload(self, extra=None):
        cli = self._find_onionshare_cli()
        seven_zip = self._find_seven_zip()
        with self.onion_lock:
            payload = dict(self.onion_state)
            payload["log"] = list(self.onion_state["log"][-12:])
        payload["available"] = bool(cli)
        payload["cli_path"] = cli
        payload["seven_zip_available"] = bool(seven_zip)
        payload["seven_zip_path"] = seven_zip
        payload["receive_dir"] = self._onion_default_receive_dir()
        if extra: payload.update(extra)
        return payload

    def _append_onion_log(self, line, proc=None):
        line = (line or "").strip()
        if not line: return
        line = re.sub(r"\x1b\[[0-9;]*m", "", line)
        with self.onion_lock:
            if proc is not None and self.onion_proc is not proc: return
            log = self.onion_state["log"]
            log.append(re.sub(r"(Private key:\s*)\S+", r"\1[hidden]", line))
            if len(log) > 60: del log[:-60]
            if not self.onion_state["url"] and self.onion_state["state"] in ("starting", "running"):
                match = re.search(r"http://([a-z2-7]{56})\.onion", line)
                if match:
                    self.onion_state["url"] = match.group(0)
                    self.onion_state["state"] = "running"
            match = re.match(r"Private key:\s*(\S+)", line)
            if match:
                self.onion_state["key"] = match.group(1)

    def _refresh_onion_state(self):
        with self.onion_lock:
            path = self.onion_persistent_file
            state = self.onion_state["state"]
        if not path or state not in ("starting", "running") or not os.path.exists(path):
            return
        try:
            if os.name != "nt":
                try: os.chmod(path, 0o600)
                except Exception: pass
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        general = data.get("general") or {}
        onion = data.get("onion") or {}
        service_id = general.get("service_id")
        if service_id: service_id = str(service_id).removesuffix(".onion")
        key = onion.get("client_auth_priv_key")
        public = bool(general.get("public", False))
        if service_id:
            with self.onion_lock:
                if self.onion_state["state"] in ("starting", "running"):
                    self.onion_state["state"] = "running"
                    self.onion_state["url"] = f"http://{service_id}.onion"
                    self.onion_state["public"] = public
                    if key: self.onion_state["key"] = key
                    self.onion_state["error"] = None
        elif key:
            with self.onion_lock:
                self.onion_state["key"] = key

    def _kill_process_tree(self, proc):
        if not proc or proc.poll() is not None: return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try: proc.terminate()
            except Exception: pass
        try: proc.wait(timeout=8)
        except Exception:
            try: proc.kill()
            except Exception: pass

    def _cleanup_onion_session(self, session_dir=None):
        with self.onion_lock:
            if session_dir is None: session_dir = self.onion_session_dir
            if self.onion_session_dir == session_dir:
                self.onion_session_dir = None
                self.onion_persistent_file = None
        if session_dir and os.path.isdir(session_dir):
            shutil.rmtree(session_dir, ignore_errors=True)

    def _abort_onion_start(self, session_dir):
        with self.onion_lock:
            if self.onion_session_dir in (session_dir, None) and self.onion_state["state"] in ("packing", "starting"):
                self.onion_state["state"] = "stopped"
        self._cleanup_onion_session(session_dir)

    def _read_onion_output(self, proc):
        try:
            for line in iter(proc.stdout.readline, ""):
                self._append_onion_log(line, proc)
        except Exception:
            pass
        finally:
            try: proc.stdout.close()
            except Exception: pass

    def _wait_onion_process(self, proc, session_dir, reader):
        returncode = proc.wait()
        try: reader.join(timeout=1.5)
        except Exception: pass
        with self.onion_lock:
            is_current = self.onion_proc is proc
            if is_current:
                self.onion_proc = None
                if self.onion_state["state"] in ("starting", "running"):
                    if returncode == 0:
                        self.onion_state["state"] = "stopped"
                    else:
                        self.onion_state["state"] = "error"
                        details = " / ".join(self.onion_state["log"][-3:])
                        self.onion_state["error"] = details or f"OnionShare exited with code {returncode}."
        self._cleanup_onion_session(session_dir)

    def _pack_share_archive(self, seven_zip, session_dir, archive_path, paths, password, generation):
        with self.onion_lock:
            if (
                self.onion_generation != generation
                or self.onion_session_dir != session_dir
                or self.onion_state["state"] != "packing"
            ):
                return False, "Transfer cancelled."
        list_path = os.path.join(session_dir, "files.txt")
        try:
            with open(list_path, "w", encoding="utf-8") as f:
                for path in paths:
                    f.write(path + "\n")
        except Exception as e:
            return False, f"Could not prepare the file list: {e}"
        cmd = [
            seven_zip, "a", "-t7z", f"-p{password}", "-mhe=on",
            "-mx=1", "-y", "-bd", "-spd", "-scsUTF-8",
            archive_path, f"@{list_path}"
        ]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = None
        output = ""
        try:
            proc = subprocess.Popen(
                cmd, cwd=app_dir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", **kwargs
            )
            with self.onion_lock:
                cancel = (
                    self.onion_generation != generation
                    or self.onion_session_dir != session_dir
                    or self.onion_state["state"] != "packing"
                )
                if not cancel:
                    self.onion_pack_proc = proc
            if cancel:
                self._kill_process_tree(proc)
                return False, "Transfer cancelled."
            output, _ = proc.communicate(timeout=3600)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            self._kill_process_tree(proc)
            try: output, _ = proc.communicate(timeout=5)
            except Exception: pass
            return False, "Compression timed out after 60 minutes."
        except Exception as e:
            return False, f"Could not run 7-Zip: {e}"
        finally:
            with self.onion_lock:
                if self.onion_pack_proc is proc:
                    self.onion_pack_proc = None
        if returncode != 0:
            lines = [line for line in (output or "").splitlines() if line.strip()]
            detail = " / ".join(lines[-4:]) if lines else f"7-Zip exited with code {returncode}."
            if password:
                detail = detail.replace(password, "[hidden]")
            return False, f"Compression failed: {detail}"
        if not os.path.isfile(archive_path) or os.path.getsize(archive_path) == 0:
            return False, "7-Zip did not create the archive."
        return True, None

    def _fail_onion_start(self, session_dir, error):
        with self.onion_lock:
            if self.onion_session_dir == session_dir and self.onion_state["state"] != "stopped":
                self.onion_state["state"] = "error"
                self.onion_state["error"] = error
        self._cleanup_onion_session(session_dir)

    def _run_onion_transfer(self, cli, mode, paths, receive_dir, public, minutes, password, seven_zip, generation, session_dir, persistent_file):
        proc = None
        try:
            expected_state = "packing" if mode == "share" else "starting"
            with self.onion_lock:
                cancelled = (
                    self.onion_generation != generation
                    or self.onion_session_dir != session_dir
                    or self.onion_state["state"] != expected_state
                )
            if cancelled:
                self._abort_onion_start(session_dir)
                return
            if mode == "share":
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                archive_path = os.path.join(session_dir, f"XenoShare_{stamp}.7z")
                ok, error = self._pack_share_archive(seven_zip, session_dir, archive_path, paths, password, generation)
                with self.onion_lock:
                    cancelled = (
                        self.onion_generation != generation
                        or self.onion_session_dir != session_dir
                        or self.onion_state["state"] != "packing"
                    )
                if cancelled:
                    self._abort_onion_start(session_dir)
                    return
                if not ok:
                    self._fail_onion_start(session_dir, error)
                    return
                with self.onion_lock:
                    cancelled = (
                        self.onion_generation != generation
                        or self.onion_session_dir != session_dir
                        or self.onion_state["state"] != "packing"
                    )
                    if not cancelled:
                        self.onion_state["state"] = "starting"
                if cancelled:
                    self._abort_onion_start(session_dir)
                    return
                cmd = [cli, "--persistent", persistent_file, "--title", "XenoPlayer", "--auto-stop-timer", str(minutes * 60)]
                if public: cmd.append("--public")
                cmd.append("--no-autostop-sharing")
                cmd.append(archive_path)
            else:
                cmd = [cli, "--persistent", persistent_file, "--title", "XenoPlayer", "--auto-stop-timer", str(minutes * 60)]
                if public: cmd.append("--public")
                cmd.extend(["--receive", "--disable-text", "--data-dir", receive_dir, "--max-upload-size", "0"])

            with self.onion_lock:
                cancelled = (
                    self.onion_generation != generation
                    or self.onion_session_dir != session_dir
                    or self.onion_state["state"] != "starting"
                )
            if cancelled:
                self._abort_onion_start(session_dir)
                return

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            try:
                proc = subprocess.Popen(
                    cmd, cwd=app_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1, **kwargs
                )
            except Exception as e:
                self._fail_onion_start(session_dir, f"Could not start OnionShare: {e}")
                return

            with self.onion_lock:
                cancelled = (
                    self.onion_generation != generation
                    or self.onion_session_dir != session_dir
                    or self.onion_state["state"] not in ("starting", "running")
                )
                if not cancelled:
                    self.onion_proc = proc
                    self.onion_persistent_file = persistent_file
            if cancelled:
                self._kill_process_tree(proc)
                self._abort_onion_start(session_dir)
                return
            reader = threading.Thread(target=self._read_onion_output, args=(proc,), daemon=True)
            reader.start()
            threading.Thread(target=self._wait_onion_process, args=(proc, session_dir, reader), daemon=True).start()
        except Exception as e:
            if proc:
                self._kill_process_tree(proc)
                with self.onion_lock:
                    if self.onion_proc is proc:
                        self.onion_proc = None
            self._fail_onion_start(session_dir, f"Transfer setup failed: {e}")

    def get_onion_status(self):
        self._refresh_onion_state()
        return self._onion_payload()

    def start_onion_share(self, mode, paths=None, receive_dir=None, public=False, auto_stop_minutes=0, password=None):
        if mode not in ("share", "receive"):
            return self._onion_payload({"ok": False, "error": "Unknown transfer mode."})
        cli = self._find_onionshare_cli()
        if not cli:
            return self._onion_payload({"ok": False, "error": "OnionShare CLI not found. Install OnionShare, then click Locate CLI."})
        with self.onion_lock:
            generation = self.onion_generation
            running = (
                self.onion_proc is not None
                or self.onion_pack_proc is not None
                or self.onion_state["state"] in ("packing", "starting", "running")
            )
        if running:
            return self._onion_payload({"ok": False, "error": "A transfer is already running."})

        with self.onion_lock:
            stale_session = self.onion_session_dir
        if stale_session:
            self._cleanup_onion_session(stale_session)

        if isinstance(paths, str): paths = [paths]
        paths = [os.path.abspath(p) for p in (paths or []) if p]
        if mode == "share":
            if not paths:
                return self._onion_payload({"ok": False, "error": "Add at least one file or folder to send."})
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                return self._onion_payload({"ok": False, "error": f"Not found: {missing[0]}"})
            if any("\n" in p or "\r" in p for p in paths):
                return self._onion_payload({"ok": False, "error": "File names containing line breaks are not supported."})
            norm = [os.path.normcase(p) for p in paths]
            filtered = []
            for path, normalized in zip(paths, norm):
                nested = False
                for other in norm:
                    if normalized == other: continue
                    if normalized.startswith(other.rstrip("\\/") + os.sep):
                        nested = True
                        break
                if not nested and path not in filtered:
                    filtered.append(path)
            paths = filtered
            names = [os.path.basename(p.rstrip("\\/")).lower() for p in paths]
            if len(set(names)) != len(names):
                return self._onion_payload({"ok": False, "error": "Selected items have duplicate names. Rename them or select their parent folder."})
            password = str(password or "")
            if len(password) < 6:
                return self._onion_payload({"ok": False, "error": "Enter an archive password with at least 6 characters."})
            if len(password) > 128:
                return self._onion_payload({"ok": False, "error": "Archive password must be 128 characters or fewer."})
            if not password.strip():
                return self._onion_payload({"ok": False, "error": "Archive password cannot be only spaces."})
            if any(c in password for c in ('"', "\r", "\n", "\x00")):
                return self._onion_payload({"ok": False, "error": "Password cannot contain double quotes or line breaks."})
            seven_zip = self._find_seven_zip()
            if not seven_zip:
                return self._onion_payload({"ok": False, "error": "7-Zip not found. Install 7-Zip, then click Locate 7z.exe."})
        else:
            receive_dir = os.path.abspath(receive_dir or self._onion_default_receive_dir())
            try:
                os.makedirs(receive_dir, exist_ok=True)
            except Exception as e:
                return self._onion_payload({"ok": False, "error": f"Cannot use receive folder: {e}"})
            self.settings["onion_receive_dir"] = receive_dir
            save_settings(self.settings)

        try: minutes = max(0, int(auto_stop_minutes or 0))
        except Exception: minutes = 0

        with self.onion_lock:
            cancelled = self.onion_generation != generation
        if cancelled:
            return self._onion_payload({"ok": False, "error": "Transfer cancelled."})

        session_dir = os.path.join(tempfile.gettempdir(), f"xenoplayer-share-{uuid.uuid4().hex}")
        try:
            os.makedirs(session_dir, mode=0o700, exist_ok=False)
        except Exception as e:
            return self._onion_payload({"ok": False, "error": f"Could not create temporary folder: {e}"})
        persistent_file = os.path.join(session_dir, "session.json")

        if mode == "share":
            for path in paths:
                try:
                    if os.path.commonpath([os.path.abspath(path), session_dir]) == os.path.abspath(path):
                        self._cleanup_onion_session(session_dir)
                        return self._onion_payload({"ok": False, "error": "Selected folder contains XenoPlayer's temporary staging area. Choose a different folder."})
                except ValueError:
                    pass

        with self.onion_lock:
            self.onion_session_dir = session_dir
            self.onion_persistent_file = None
            self.onion_state = {
                "state": "packing" if mode == "share" else "starting",
                "mode": mode, "url": None, "key": None,
                "public": bool(public), "error": None, "log": [],
                "auto_stop_minutes": minutes
            }
            cancelled = self.onion_generation != generation
        if cancelled:
            self._abort_onion_start(session_dir)
            return self._onion_payload({"ok": False, "error": "Transfer cancelled."})

        transfer_args = (
            cli, mode, paths, receive_dir, public, minutes, password,
            seven_zip if mode == "share" else None, generation, session_dir, persistent_file
        )
        try:
            threading.Thread(target=self._run_onion_transfer, args=transfer_args, daemon=True).start()
        except Exception as e:
            self._fail_onion_start(session_dir, f"Could not start transfer thread: {e}")
            return self._onion_payload({"ok": False, "error": f"Could not start transfer thread: {e}"})
        return self._onion_payload({"ok": True})

    def stop_onion_share(self):
        with self.onion_lock:
            self.onion_generation += 1
            proc = self.onion_proc
            pack_proc = self.onion_pack_proc
            session_dir = self.onion_session_dir
            if self.onion_state["state"] in ("packing", "starting", "running"):
                self.onion_state["state"] = "stopped"
        self._kill_process_tree(pack_proc)
        self._kill_process_tree(proc)
        if (proc and proc.poll() is None) or (pack_proc and pack_proc.poll() is None):
            with self.onion_lock:
                self.onion_state["state"] = "error"
                self.onion_state["error"] = "Could not stop the transfer process. Close it manually from Task Manager."
        with self.onion_lock:
            if self.onion_proc is proc: self.onion_proc = None
            if self.onion_pack_proc is pack_proc: self.onion_pack_proc = None
            if self.onion_session_dir == session_dir:
                self.onion_session_dir = None
                self.onion_persistent_file = None
        if session_dir:
            self._cleanup_onion_session(session_dir)
        return self._onion_payload({"ok": True})

    def browse_share_files(self):
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=True, file_types=('All files (*.*)',)
        )
        if not result: return []
        if isinstance(result, str): return [result]
        return list(result)

    def browse_share_folder(self):
        return self.browse_folder()

    def browse_receive_folder(self):
        return self.browse_folder()

    def browse_onionshare_cli(self):
        path = self.browse_exe_dialog()
        if path:
            name = os.path.basename(path).lower()
            if name not in ("onionshare-cli.exe", "onionshare-cli"):
                return self._onion_payload({"ok": False, "error": "Select onionshare-cli.exe, not the OnionShare GUI."})
            self.settings["onionshare_cli_path"] = path
            save_settings(self.settings)
        return self._onion_payload({"ok": True})

    def browse_seven_zip(self):
        path = self.browse_exe_dialog()
        if path:
            name = os.path.basename(path).lower()
            if name not in ("7z.exe", "7za.exe", "7zz.exe", "7z", "7za", "7zz"):
                return self._onion_payload({"ok": False, "error": "Select 7z.exe, not the 7-Zip File Manager."})
            self.settings["seven_zip_path"] = path
            save_settings(self.settings)
        return self._onion_payload({"ok": True})

    def open_receive_folder(self, path=None):
        try:
            path = os.path.abspath(path or self._onion_default_receive_dir())
            os.makedirs(path, exist_ok=True)
            if os.name == "nt": os.startfile(path)
            elif sys.platform == "darwin": subprocess.Popen(["open", path])
            else: subprocess.Popen(["xdg-open", path])
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

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
        if os.path.splitext(filepath)[1].lower() == '.cbz':
            self.open_cbz_archive(filepath)
            return
        directory = os.path.dirname(filepath)
        self._current_directory = directory
        
        supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
        
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
        if not os.path.isdir(directory_path):
            return {"status": "error", "msg": "Folder does not exist."}
        if self._cbz_root:
            try:
                inside_cbz = os.path.commonpath([self._cbz_root, directory_path]) == self._cbz_root
            except ValueError:
                inside_cbz = False
            if not inside_cbz:
                self._cleanup_cbz_archive()
        self._current_directory = directory_path
        
        supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
        
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
        return {"status": "success", "directory": directory_path, "count": len(self.playlist)}

    def _cleanup_cbz_archive(self):
        if self._cbz_temp_dir:
            self._cbz_temp_dir.cleanup()
        self._cbz_temp_dir = None
        self._cbz_root = None
        self._cbz_archive_path = None

    def open_cbz_archive(self, archive_path):
        archive_path = os.path.abspath(archive_path)
        if not os.path.isfile(archive_path) or os.path.splitext(archive_path)[1].lower() != '.cbz':
            return {"status": "error", "msg": "The selected file is not a CBZ archive."}

        self._cleanup_cbz_archive()
        temp_dir = tempfile.TemporaryDirectory(prefix="XenoPlayer_cbz_")
        archive_root = os.path.abspath(temp_dir.name)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    member_path = os.path.abspath(os.path.join(archive_root, member.filename.replace("/", os.sep).replace("\\", os.sep)))
                    if os.path.commonpath([archive_root, member_path]) != archive_root:
                        raise ValueError(f"Unsafe path in CBZ archive: {member.filename}")
                    if member.is_dir():
                        os.makedirs(member_path, exist_ok=True)
                        continue
                    os.makedirs(os.path.dirname(member_path), exist_ok=True)
                    with archive.open(member) as source, open(member_path, "wb") as destination:
                        shutil.copyfileobj(source, destination)
        except Exception as e:
            temp_dir.cleanup()
            return {"status": "error", "msg": f"Could not open CBZ archive: {e}"}

        self._cbz_temp_dir = temp_dir
        self._cbz_root = archive_root
        self._cbz_archive_path = archive_path
        self.load_selected_directory(archive_root)
        return {"status": "success"}

    def close_cbz_archive(self):
        if not self._cbz_archive_path:
            return {"status": "error", "msg": "No CBZ archive is currently open."}
        parent_directory = os.path.dirname(self._cbz_archive_path)
        self._cleanup_cbz_archive()
        self.load_selected_directory(parent_directory)
        return {"status": "success"}

    def refresh_current_directory(self):
        current_path = self.playlist[self.current_index] if (0 <= self.current_index < len(self.playlist)) else None
        if not current_path and self.full_playlist:
            current_path = self.full_playlist[0]
            
        if not current_path:
            default_index = self.settings.get("default_folder", -1)
            folders = self.settings.get("saved_folders", ["", "", "", "", ""])
            if 0 <= default_index < len(folders):
                dir_path = folders[default_index]
            else:
                return {"status": "error", "msg": "No active folder to refresh"}
        else:
            dir_path = os.path.dirname(current_path) if os.path.isfile(current_path) else current_path
            
        if dir_path and os.path.isdir(dir_path):
            self.load_selected_directory(dir_path)
            if current_path in self.playlist:
                self.current_index = self.playlist.index(current_path)
            elif self.playlist:
                self.current_index = 0
            else:
                self.current_index = -1
            self._window.evaluate_js('updatePlaylist()')
            return {"status": "success"}
        return {"status": "error", "msg": "Directory not found"}

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
                playlist_items.append({"path": p, "name": name, "date": 0, "size": 0})
            else:
                try:
                    stat = os.stat(p)
                    date = stat.st_mtime
                    size = stat.st_size
                except:
                    date = 0
                    size = 0
                playlist_items.append({"path": p, "name": os.path.basename(p), "date": date, "size": size})
        return playlist_items

    def play_current(self):
        if not (0 <= self.current_index < len(self.playlist)): return
        path = self.playlist[self.current_index]
        self.settings["last_video"] = path
        save_settings(self.settings)
        self._window.evaluate_js(f'loadMedia({json.dumps(path)}, {self.current_index}); null;')

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
        is_collection = False
        dir_path = ""
        if current_path:
            dir_path = os.path.dirname(current_path)
            if os.path.exists(os.path.join(dir_path, '.collection')):
                is_collection = True
        
        favs_mode = self.settings.get("favs_mode", "folder")
        if favs_mode == "folder":
            filtered_favs = [f for f in self.settings.get("favorites", []) if os.path.dirname(f) == dir_path] if dir_path else []
        else:
            filtered_favs = self.settings.get("favorites", [])
            
        state = {
            "favorites": filtered_favs,
            "move_targets": self.settings.get("move_targets", {}),
            "saved_volumes": self.settings.get("saved_volumes", {}),
            "saved_folders": self.settings.get("saved_folders", ["", "", "", "", ""]),
            "external_apps": self.settings.get("external_apps", ["", "", "", "", ""]),
            "default_folder": self.settings.get("default_folder", -1),
            "hotkeys": self.settings.get("hotkeys", {"next": ["ArrowRight", "Space", "", "", ""], 
"prev": ["ArrowLeft", "", "", "", ""], "pause": ["KeyP", "", "", "", ""], "mute": ["KeyM", "", "", "", ""],
"split_next_video": ["KeyD", "", "", "", ""], "split_next_image": ["KeyE", "", "", "", ""]}),
            "current_path": current_path,
            "is_favorite": current_path in self.settings.get("favorites", []) if current_path else False,
            "is_collection_folder": is_collection,
            "favs_mode": favs_mode,
            "collection_sites": self.settings.get("collection_sites", []),
            "audio_sites": self.settings.get("audio_sites", []),
            "story_sites": self.settings.get("story_sites", []),
            "online_playlists": self.settings.get("online_playlists", {}),
            "favorite_collection_tags": self.settings.get("favorite_collection_tags", {"nhentai": [], "danbooru": [], "hentaiyoga": [], "rule34art": [], "ehentai": []}),
            "recursive_load": self.settings.get("recursive_load", False),
            "type_filter": self.settings.get("type_filter", "all"),
            "playlist_sort": self.settings.get("playlist_sort", "name"),
            "sort_asc": self.settings.get("sort_asc", True),
            "view_mode": self.settings.get("view_mode", "medium"),
            "gemini_api_key": self.settings.get("gemini_api_key", "")
        }

        return state

    def save_playlist_settings(self, type_filter, playlist_sort, sort_asc, view_mode):
        self.settings["type_filter"] = type_filter
        self.settings["playlist_sort"] = playlist_sort
        self.settings["sort_asc"] = sort_asc
        self.settings["view_mode"] = view_mode
        save_settings(self.settings)
        return {"status": "success"}

    def save_online_sources(self, collection_sites, audio_sites, story_sites):
        self.settings["collection_sites"] = collection_sites
        self.settings["audio_sites"] = audio_sites
        self.settings["story_sites"] = story_sites
        save_settings(self.settings)
        try:
            src_path = os.path.join(app_dir, 'MAINLIST.json')
            with open(src_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "collection_sites": collection_sites,
                    "audio_sites": audio_sites,
                    "story_sites": story_sites
                }, f, indent=4)
        except Exception as e:
            print(f"Warning: could not save MAINLIST.json: {e}")
        return self.get_state()

    def export_online_sources(self, collection_sites, audio_sites, story_sites):
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                directory=os.path.expanduser('~'),
                save_filename='MAINLIST.json',
                file_types=('JSON Files (*.json)', 'All files (*.*)')
            )
            if result:
                path = result[0] if isinstance(result, (list, tuple)) else result
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "collection_sites": collection_sites,
                        "audio_sites": audio_sites,
                        "story_sites": story_sites
                    }, f, indent=4)
                return {"status": "ok", "path": path}
        except Exception as e:
            print(f"Export error: {e}")
        return {"status": "cancelled"}

    def import_online_sources(self):
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                directory=os.path.expanduser('~'),
                allow_multiple=False,
                file_types=('JSON Files (*.json)', 'All files (*.*)')
            )
            if result and len(result) > 0:
                with open(result[0], 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return {
                    "status": "ok",
                    "collection_sites": data.get("collection_sites", []),
                    "audio_sites": data.get("audio_sites", []),
                    "story_sites": data.get("story_sites", [])
                }
        except Exception as e:
            print(f"Import error: {e}")
        return {"status": "cancelled"}

    def browse_copyparty(self, url):
        import urllib.request
        try:
            sep = '&' if '?' in url else '?'
            api_url = url.rstrip('/') + '/' + sep + 'ls&dirs=1&files=1'
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Porn Player/1.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode('utf-8'))
            dirs = [{"name": d.get("href","").rstrip('/'), "href": d.get("href",""), "files": d.get("tags",{}).get(".files",0), "sz": d.get("sz",0)} for d in data.get("dirs", [])]
            image_exts = {'.jpg','.jpeg','.png','.webp','.gif','.bmp','.tiff','.avif'}
            video_exts = {'.mp4','.webm','.ogg','.mkv','.avi','.mov','.flv','.wmv','.m4v','.ts'}
            audio_exts = {'.mp3','.wav','.wave','.flac','.aac','.ogg','.m4a','.opus','.wma'}
            archive_exts = {'.zip','.rar','.7z','.tar','.gz','.cbz','.cbr','.cb7'}
            manga_exts = {'.cbz','.cbr','.cb7','.cbt'}
            doc_exts = {'.pdf','.txt','.md','.epub','.mobi'}
            files = []
            for f in data.get("files", []):
                href = f.get("href","")
                ext = ('.' + href.rsplit('.',1)[-1]).lower() if '.' in href else ''
                if ext in manga_exts:
                    ftype = 'manga'
                elif ext in image_exts:
                    ftype = 'image'
                elif ext in video_exts:
                    ftype = 'video'
                elif ext in audio_exts:
                    ftype = 'audio'
                elif ext in archive_exts:
                    ftype = 'archive'
                elif ext in doc_exts:
                    ftype = 'doc'
                else:
                    ftype = 'file'
                files.append({"name": href, "href": href, "sz": f.get("sz",0), "type": ftype, "ext": ext})
            base = url.rstrip('/') + '/'
            return {"status": "ok", "dirs": dirs, "files": files, "base_url": base}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def set_ftp_playlist(self, files, index):
        self.ftp_files = files
        self.ftp_index = index
        return {"status": "success"}

    def get_ftp_playlist(self):
        return {"files": self.ftp_files, "index": self.ftp_index}

    def get_dir_tree(self):
        common_root = self._current_directory
        if not common_root or not os.path.isdir(common_root):
            paths = [p for p in self.full_playlist if not (p.startswith('http://') or p.startswith('https://'))]
            if not paths:
                return {"root": "", "subdirs": [], "cbz_files": []}
            common_root = os.path.dirname(paths[0])
        
        if not common_root or not os.path.isdir(common_root):
            return {"root": "", "subdirs": [], "cbz_files": []}
            
        subdirs = []
        cbz_files = []
        try:
            for root, dirs, files in os.walk(common_root):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for d in dirs:
                    subdirs.append(os.path.normpath(os.path.join(root, d)))
                cbz_files.extend(
                    os.path.normpath(os.path.join(root, name))
                    for name in files
                    if os.path.splitext(name)[1].lower() == '.cbz'
                )
        except:
            pass
            
        return {
            "root": common_root,
            "subdirs": subdirs,
            "cbz_files": cbz_files,
            "cbz_root": self._cbz_root,
            "cbz_archive_path": self._cbz_archive_path
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

    def save_options(self, folders, default_index, external_apps=None, favs_mode="folder", collection_sites=None, audio_sites=None, recursive_load=None, gemini_api_key=None):
        self.settings["saved_folders"] = folders
        self.settings["default_folder"] = default_index
        if external_apps is not None: self.settings["external_apps"] = external_apps
        self.settings["favs_mode"] = favs_mode
        if collection_sites is not None: self.settings["collection_sites"] = collection_sites
        if audio_sites is not None: self.settings["audio_sites"] = audio_sites
        if recursive_load is not None: self.settings["recursive_load"] = recursive_load
        if gemini_api_key is not None: self.settings["gemini_api_key"] = gemini_api_key
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

    def mark_as_collection(self):
        if not self.playlist: return {"status": "error"}
        dir_path = os.path.dirname(self.playlist[0])
        open(os.path.join(dir_path, ".collection"), 'w').close()
        known = self.settings.get("known_collection_folders", [])
        if dir_path not in known:
            known.append(dir_path)
            self.settings["known_collection_folders"] = known
            save_settings(self.settings)
        return self.get_state()

    def unmark_as_collection(self):
        if not self.playlist: return {"status": "error"}
        dir_path = os.path.dirname(self.playlist[0])
        try: os.remove(os.path.join(dir_path, ".collection"))
        except: pass
        known = self.settings.get("known_collection_folders", [])
        if dir_path in known:
            known.remove(dir_path)
            self.settings["known_collection_folders"] = known
            save_settings(self.settings)
        return self.get_state()

    def get_collection_info(self, current_path):
        if not current_path or not os.path.isfile(current_path): return {}
        json_path = os.path.join(os.path.dirname(current_path), "collection_info.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f: return json.load(f).get("translations", {})
            except: pass
        return {}

    def save_collection_info(self, current_path, translations):
        if not current_path or not os.path.isfile(current_path): return {"status": "error"}
        dir_path = os.path.dirname(current_path)
        json_path = os.path.join(dir_path, "collection_info.json")
        data = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f: data = json.load(f)
            except: pass
        data["translations"] = translations
        try:
            with open(json_path, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
            open(os.path.join(dir_path, ".collection"), 'w').close()
            known = self.settings.get("known_collection_folders", [])
            if dir_path not in known:
                known.append(dir_path)
                self.settings["known_collection_folders"] = known
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
            app_dir = os.path.dirname(app_path)
            # If the directory is valid and exists, set it as the working directory
            cwd = app_dir if app_dir and os.path.exists(app_dir) else None
            subprocess.Popen([app_path, os.path.normpath(filepath)], cwd=cwd)
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
                                        self._window.evaluate_js(f'updateAudioDownloadProgress({downloaded_size}, {total_size}, {json.dumps(name)})')
                        self.load_directory(dest_path)
                        self._log_download(name, dest_path, "audio")
                        self._window.evaluate_js(f'downloadCompleteNotify("{safe_title}")')
                        self._window.evaluate_js(f'downloadCompleteNotify({json.dumps(name)})')
                    else:
                        self._window.evaluate_js(f'downloadFailedNotify("{safe_title}", "HTTP {r.status_code}")')
                        self._window.evaluate_js(f'downloadFailedNotify({json.dumps(name)}, "HTTP {r.status_code}")')
                except Exception as ex:
                    safe_ex = str(ex).replace('\\', '\\\\').replace('"', '\\"')
                    self._window.evaluate_js(f'downloadFailedNotify("{safe_title}", "{safe_ex}")')
                    self._window.evaluate_js(f'downloadFailedNotify({json.dumps(name)}, {json.dumps(str(ex))})')
                    
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

    def search_online_stories(self, source_id, query):
        # Find the site config from settings
        try:
            src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MAINLIST.json')
            with open(src_path, 'r', encoding='utf-8') as f:
                sources = json.load(f)
                all_sites = sources.get("story_sites", [])
        except Exception:
            all_sites = []
 
        site_config = next((s for s in all_sites if s.get('id') == source_id), None)
 
        if not site_config:
            return {"status": "error", "msg": f"Could not find configuration for site ID: {source_id}"}
        
        notes = site_config.get('notes', '')
        search_config = {}
        try:
            if notes.strip().startswith('{') and notes.strip().endswith('}'):
                search_config = json.loads(notes)
        except json.JSONDecodeError:
            pass # Not a JSON config, just a note.

        parser_type = search_config.get('parser')

        if parser_type == 'ao3':
            return self._search_ao3(query)
        elif parser_type == 'generic_html':
            return self._search_generic_html(query, search_config)
        
        return {"status": "error", "msg": "Search not configured for this source. Edit its 'notes' in MAINLIST.json."}

    def search_custom_collection(self, source_id, query):
        try:
            all_sites = self.settings.get("collection_sites", [])
            site_config = next((s for s in all_sites if s.get('id') == source_id), None)
            if not site_config:
                return {"status": "error", "msg": f"Could not find configuration for custom site ID: {source_id}"}
            
            notes = site_config.get('notes', '')
            search_config = {}
            if notes.strip().startswith('{') and notes.strip().endswith('}'):
                search_config = json.loads(notes)
            
            res = self._search_generic_html(query, search_config)
            return res
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def _search_generic_html(self, query, config):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            import urllib.parse

            search_url_template = config.get('search_url')
            if not search_url_template:
                return {"status": "error", "msg": "search_url not defined in site configuration."}
            
            search_url = search_url_template.replace('{query}', urllib.parse.quote(query))
            
            scraper = cloudscraper.create_scraper()
            response = scraper.get(search_url, timeout=15)
            if response.status_code != 200:
                return {"status": "error", "msg": f"Site returned HTTP {response.status_code}"}

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            results_selector = config.get('results_selector')
            if not results_selector:
                return {"status": "error", "msg": "results_selector not defined in site configuration."}

            for item in soup.select(results_selector):
                title = item.select_one(config['title_selector']).text.strip() if config.get('title_selector') and item.select_one(config['title_selector']) else ""
                author = item.select_one(config['author_selector']).text.strip() if config.get('author_selector') and item.select_one(config['author_selector']) else ""
                summary = item.select_one(config['summary_selector']).text.strip() if config.get('summary_selector') and item.select_one(config['summary_selector']) else ""
                
                url_el = item.select_one(config['url_selector']) if config.get('url_selector') else item
                url = url_el['href'] if url_el and url_el.has_attr('href') else ""
                
                if not title and url_el: title = url_el.text.strip()

                if not title or not url:
                    continue

                base_url = config.get('base_url', '')
                full_url = urllib.parse.urljoin(base_url if base_url else search_url, url)

                thumb_selector = config.get('thumb_selector')
                thumb_el = item.select_one(thumb_selector) if thumb_selector else item.select_one('img')
                thumb = ""
                if thumb_el:
                    thumb = thumb_el.get('src') or thumb_el.get('data-src') or thumb_el.get('data-original') or ""
                    if thumb:
                        thumb = urllib.parse.urljoin(base_url if base_url else search_url, thumb)

                results.append({"title": title, "author": author, "summary": summary, "url": full_url, "thumb": thumb})
            
            return {"status": "success", "results": results}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def _search_ao3(self, query):
        try:
            import requests
            from bs4 import BeautifulSoup
            import urllib.parse

            search_url = f"https://archiveofourown.org/works/search?work_search[query]={urllib.parse.quote(query)}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            
            response = requests.get(search_url, headers=headers, timeout=15)
            if response.status_code != 200:
                return {"status": "error", "msg": f"AO3 returned HTTP {response.status_code}"}

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for work in soup.select('li.work'):
                title_el = work.select_one('h4.heading a:not([rel="author"])') or work.select_one('h4.heading a')
                author_el = work.select_one('a[rel="author"]')
                summary_el = work.select_one('blockquote.userstuff.summary')
                
                if not title_el: continue
                
                results.append({
                    "title": title_el.text.strip(),
                    "author": author_el.text.strip() if author_el else "Anonymous",
                    "summary": summary_el.text.strip() if summary_el else "",
                    "url": urllib.parse.urljoin("https://archiveofourown.org/", title_el['href'])
                })
            
            return {"status": "success", "results": results}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def guess_story_site_selectors(self, url):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            from collections import Counter
            import urllib.parse
            import re

            scraper = cloudscraper.create_scraper()
            response = scraper.get(url, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')

            parsed_url = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            search_term, search_key = "", ""
            for key, values in query_params.items():
                if len(values) == 1 and len(values[0]) > 2 and re.search(r'[a-zA-Z]{3,}', values[0]):
                    search_term, search_key = values[0], key
                    break
            
            search_url = url.replace(search_term, '{query}') if search_term else url
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # --- New logic to find repeating container elements ---
            signatures = {}
            # We look for elements that could be containers. Good containers have several children.
            for el in soup.find_all(True):
                children = el.find_all(recursive=False)
                if len(children) < 2: continue # Skip elements with 0 or 1 child

                # Create a structural signature from the children's tags
                sig = tuple(sorted([child.name for child in children]))

                if sig not in signatures:
                    signatures[sig] = []
                
                selector = el.name
                if el.has_attr('class'):
                    selector += '.' + el['class'][0] # Use only the first class to keep selector general
                signatures[sig].append(selector)

            best_sig_selectors = []
            for sig, selectors in signatures.items():
                if len(selectors) > len(best_sig_selectors) and len(selectors) > 2: # Must repeat at least 3 times
                    best_sig_selectors = selectors
            
            if not best_sig_selectors:
                return self._guess_selectors_with_ai(url, soup)

            results_selector = Counter(best_sig_selectors).most_common(1)[0][0]
            first_result_item = soup.select_one(results_selector)
            if not first_result_item:
                return self._guess_selectors_with_ai(url, soup)

            def get_selector(element):
                if not element: return ""
                selector = element.name
                if element.has_attr('class'):
                    selector += '.' + '.'.join(element['class'])
                return selector

            title_el = first_result_item.select_one('h1 a, h2 a, h3 a, h4 a')
            title_selector = get_selector(title_el) if title_el else ""
            
            author_selector = ""
            author_el = first_result_item.select_one('[class*="author"], [id*="author"], a[rel="author"]')
            if author_el:
                author_selector = get_selector(author_el)

            summary_selector = ""
            summary_el = first_result_item.select_one('p, div[class*="summary"], div[class*="description"], div[class*="synopsis"], blockquote')
            if summary_el:
                summary_selector = get_selector(summary_el)

            config = {
                "parser": "generic_html", "search_url": search_url, "base_url": base_url,
                "results_selector": results_selector, "title_selector": title_selector,
                "url_selector": title_selector, "author_selector": author_selector,
                "summary_selector": summary_selector
            }

            return {"status": "success", "config": config}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def _get_env_var(self, *names):
        for name in names:
            value = os.environ.get(name)
            if value:
                return value

        for relative_path in [".env", os.path.join("web", ".env")]:
            path = os.path.join(app_dir, relative_path)
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            if "=" in line:
                                k, v = line.split("=", 1)
                                if k.strip() in names:
                                    return v.strip().strip('"').strip("'")
                except: pass
        return ""

    def _guess_selectors_with_ai(self, url, soup):
        account_id = self._get_env_var("CLOUDFLARE_ACCOUNTID", "Cloudflare_Account_ID")
        api_key = self._get_env_var("CF_WORKERSAI_REST_API", "CF_ACCOUNT_API_Token", "Cloudflare_API_Key")
        
        try:
            for tag in soup(["script", "style", "svg", "head", "path", "meta", "link"]):
                tag.decompose()
                
            html_content = str(soup)[:50000]
            
            import requests
            import json
            
            prompt = (
                "You are an expert web scraper helper. I need you to analyze the HTML source code of a search results page "
                f"from URL: {url} and extract the CSS selectors for the repeating items.\n\n"
                "Extract the following:\n"
                "1. 'results_selector': The CSS selector matching each repeating item card/element (e.g. '.result-card', 'li.work', 'div.item').\n"
                "2. 'title_selector': The relative CSS selector (relative to the results_selector element) matching the anchor tag for the item title.\n"
                "3. 'url_selector': The relative CSS selector matching the anchor tag containing the detail URL (usually same as title_selector).\n"
                "4. 'author_selector': Relative CSS selector matching the author link or name element (empty string if not found).\n"
                "5. 'summary_selector': Relative CSS selector matching the description / summary / synopsis text element (empty string if not found).\n"
                "6. 'thumb_selector': Relative CSS selector matching the thumbnail image element (img tag) if present (empty string if not found).\n\n"
                "Return ONLY a valid JSON object matching this structure. Do not output markdown codeblocks, just raw JSON:\n"
                "{\n"
                '  "results_selector": "...",\n'
                '  "title_selector": "...",\n'
                '  "url_selector": "...",\n'
                '  "author_selector": "...",\n'
                '  "summary_selector": "...",\n'
                '  "thumb_selector": "..."\n'
                "}\n\n"
                f"HTML Source Snippet:\n{html_content}"
            )

            # Try Cloudflare Workers AI
            if account_id and api_key:
                try:
                    cf_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/meta/llama-3.1-8b-instruct"
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "messages": [
                            {"role": "user", "content": prompt}
                        ]
                    }
                    r = requests.post(cf_url, json=payload, headers=headers, timeout=20)
                    if r.status_code == 200:
                        resp_data = r.json()
                        response_text = resp_data['result']['response'].strip()
                        if response_text.startswith("```"):
                            lines = response_text.splitlines()
                            if lines[0].startswith("```json"):
                                response_text = "\n".join(lines[1:-1])
                            elif lines[0].startswith("```"):
                                response_text = "\n".join(lines[1:-1])
                        config = json.loads(response_text)
                        return self._build_final_config(url, config)
                except Exception as e:
                    print(f"Cloudflare AI failed: {e}")

            # Fallback to Gemini
            gemini_key = self.settings.get("gemini_api_key", "").strip() or self._get_env_var("GEMINI_API_KEY")
            if gemini_key:
                try:
                    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                    payload = {
                        "contents": [{
                            "parts": [{"text": prompt}]
                        }],
                        "generationConfig": {
                            "responseMimeType": "application/json"
                        }
                    }
                    r = requests.post(api_url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
                    if r.status_code == 200:
                        resp_data = r.json()
                        response_text = resp_data['candidates'][0]['content']['parts'][0]['text'].strip()
                        if response_text.startswith("```"):
                            lines = response_text.splitlines()
                            if lines[0].startswith("```json"):
                                response_text = "\n".join(lines[1:-1])
                            elif lines[0].startswith("```"):
                                response_text = "\n".join(lines[1:-1])
                        config = json.loads(response_text)
                        return self._build_final_config(url, config)
                except Exception as e:
                    print(f"Gemini AI failed: {e}")

            return {"status": "error", "msg": "Heuristic failed, and AI models could not run. Provide a Gemini API key in Options, or set Cloudflare keys in your .env file."}
        except Exception as e:
            return {"status": "error", "msg": f"AI Guess failed: {str(e)}"}

    def scrape_custom_gallery(self, url, source_id=None):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            import urllib.parse
            
            scraper = cloudscraper.create_scraper()
            r = scraper.get(url, timeout=15)
            if r.status_code != 200:
                return {"status": "error", "msg": f"Failed to load gallery page. HTTP {r.status_code}"}
                
            soup = BeautifulSoup(r.text, 'html.parser')
            
            for tag in soup(["script", "style", "svg", "path", "head"]):
                tag.decompose()
                
            media_urls = []
            seen = set()
            
            # Extract large gallery images
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("file-src") or ""
                if src:
                    src_lower = src.lower()
                    if any(x in src_lower for x in ["logo", "avatar", "icon", "theme", "header", "footer", "button", "sprite"]):
                        continue
                    full_url = urllib.parse.urljoin(url, src)
                    if full_url not in seen:
                        seen.add(full_url)
                        media_urls.append(full_url)
            
            # Extract links to media
            for a in soup.find_all("a"):
                href = a.get("href") or ""
                if href:
                    href_lower = href.lower()
                    if any(href_lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm"]):
                        full_url = urllib.parse.urljoin(url, href)
                        if full_url not in seen:
                            seen.add(full_url)
                            media_urls.append(full_url)
                            
            if not media_urls:
                return self._scrape_gallery_with_ai(url, soup)
                
            playlist = []
            for i, mu in enumerate(media_urls):
                filename = mu.split('/')[-1].split('?')[0] or f"item_{i}"
                playlist.append({
                    "name": filename,
                    "type": "image" if not any(mu.lower().endswith(x) for x in [".mp4", ".webm"]) else "video",
                    "url": mu
                })
                
            return {"status": "success", "playlist": playlist}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def _scrape_gallery_with_ai(self, url, soup):
        account_id = self._get_env_var("CLOUDFLARE_ACCOUNTID", "Cloudflare_Account_ID")
        api_key = self._get_env_var("CF_WORKERSAI_REST_API", "CF_ACCOUNT_API_Token", "Cloudflare_API_Key")
        gemini_key = self.settings.get("gemini_api_key", "").strip() or self._get_env_var("GEMINI_API_KEY")
        
        for tag in soup(["script", "style", "svg", "head", "path", "meta", "link"]):
            tag.decompose()
        html_content = str(soup)[:60000]
        
        prompt = (
            "You are an expert web scraper helper. I need you to analyze the HTML source code of a gallery detail page "
            f"from URL: {url} and extract a list of absolute or relative image/video source URLs (the actual images of the comic/gallery).\n\n"
            "Identify the repeating image elements, extract their 'src' or 'href' attribute, and resolve them to absolute URLs if relative.\n\n"
            "Return ONLY a valid JSON object matching this structure. Do not output markdown codeblocks, just raw JSON:\n"
            "{\n"
            '  "media_urls": [\n'
            '    "https://...",\n'
            '    "https://..."\n'
            '  ]\n'
            "}\n\n"
            f"HTML Source Snippet:\n{html_content}"
        )
        
        import requests
        import json

        if account_id and api_key:
            try:
                cf_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/meta/llama-3.1-8b-instruct"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                r = requests.post(cf_url, json={"messages": [{"role": "user", "content": prompt}]}, headers=headers, timeout=20)
                if r.status_code == 200:
                    resp_data = r.json()
                    response_text = resp_data['result']['response'].strip()
                    if response_text.startswith("```"):
                        lines = response_text.splitlines()
                        if lines[0].startswith("```json"): response_text = "\n".join(lines[1:-1])
                        elif lines[0].startswith("```"): response_text = "\n".join(lines[1:-1])
                    config = json.loads(response_text)
                    urls = config.get("media_urls", [])
                    if urls:
                        return self._build_gallery_playlist(url, urls)
            except Exception as e:
                print(f"Cloudflare gallery scraping failed: {e}")
                
        if gemini_key:
            try:
                api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"}
                }
                r = requests.post(api_url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
                if r.status_code == 200:
                    resp_data = r.json()
                    response_text = resp_data['candidates'][0]['content']['parts'][0]['text'].strip()
                    if response_text.startswith("```"):
                        lines = response_text.splitlines()
                        if lines[0].startswith("```json"): response_text = "\n".join(lines[1:-1])
                        elif lines[0].startswith("```"): response_text = "\n".join(lines[1:-1])
                    config = json.loads(response_text)
                    urls = config.get("media_urls", [])
                    if urls:
                        return self._build_gallery_playlist(url, urls)
            except Exception as e:
                print(f"Gemini gallery scraping failed: {e}")
                
        return {"status": "error", "msg": "Could not extract any media elements from this page."}

    def _build_gallery_playlist(self, url, urls):
        import urllib.parse
        playlist = []
        for i, u in enumerate(urls):
            full_url = urllib.parse.urljoin(url, u)
            filename = full_url.split('/')[-1].split('?')[0] or f"item_{i}"
            playlist.append({
                "name": filename,
                "type": "image" if not any(full_url.lower().endswith(x) for x in [".mp4", ".webm"]) else "video",
                "url": full_url
            })
        return {"status": "success", "playlist": playlist}

    def _build_final_config(self, url, config):
        import urllib.parse
        import re
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        search_term = ""
        for key, values in query_params.items():
            if len(values) == 1 and len(values[0]) > 2 and re.search(r'[a-zA-Z]{3,}', values[0]):
                search_term = values[0]
                break
        
        search_url = url.replace(search_term, '{query}') if search_term else url
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        return {
            "status": "success",
            "config": {
                "parser": "generic_html", 
                "search_url": search_url, 
                "base_url": base_url,
                "results_selector": config.get("results_selector", ""),
                "title_selector": config.get("title_selector", ""),
                "url_selector": config.get("url_selector", ""),
                "author_selector": config.get("author_selector", ""),
                "summary_selector": config.get("summary_selector", ""),
                "thumb_selector": config.get("thumb_selector", "")
            }
        }

    def rename_collection(self, path, newName):
        if not path: return {"status": "error"}
        parent = os.path.dirname(path)
        new_path = os.path.join(parent, newName)
        try:
            os.rename(path, new_path)
            known = self.settings.get("known_collection_folders", [])
            if path in known:
                known[known.index(path)] = new_path
            else:
                known.append(new_path)
            self.settings["known_collection_folders"] = known
            
            json_path = os.path.join(new_path, "collection_info.json")
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

    def unmark_folder_as_collection(self, path):
        if not path: return {"status": "error"}
        try:
            collection_file = os.path.join(path, ".collection")
            if os.path.exists(collection_file):
                os.remove(collection_file)
        except: pass
        known = self.settings.get("known_collection_folders", [])
        if path in known:
            known.remove(path)
            self.settings["known_collection_folders"] = known
            save_settings(self.settings)
        return {"status": "success"}

    def open_collection_viewer(self, path):
        if not path: return
        directory = os.path.dirname(path) if os.path.isfile(path) else path
        import subprocess
        env = os.environ.copy()
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "CollectionViewer", directory], env=env)
        else:
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CollectionViewer.py")
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
            headers = {'User-Agent': 'PornPlayer/1.0 (contact@xenohead.com)'}
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
            headers = {'User-Agent': 'Porn Player/1.0 (contact@xenohead.com)'}
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
            "doujinshi", "collection", "artist cg", "western", "game cg",
            "swimsuit", "exhibitionism", "public use", "impregnation",
            "harem", "netorare", "femdom", "futanari", "yaoi", "yuri"
        ]
        if query:
            filtered = [t for t in popular_tags if query.lower() in t.lower()]
            return {"status": "success", "tags": filtered}
        return {"status": "success", "tags": popular_tags}

    def save_favorite_collection_tags(self, tags):
        self.settings["favorite_collection_tags"] = tags
        save_settings(self.settings)
        return self.get_state()

    def get_collection_details(self, url, source):
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
                img_els = soup.select('img[src*="/collection/"]')
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

    def choose_collection_download_dir(self):
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if result and len(result) > 0:
            self.settings["collection_download_dir"] = result[0]
            save_settings(self.settings)
            return {"status": "success", "dir": result[0]}
        return {"status": "canceled"}

    def get_collection_download_dir(self):
        d = self.settings.get("collection_download_dir", "")
        if not d:
            base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            d = os.path.join(base, "Downloads", "nhentai")
        return {"dir": d}

    def _log_download(self, title, path, media_type="collection", status="success"):
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
        download_dir = os.path.join(self.get_collection_download_dir()["dir"], folder_name)
        
        def run_download():
            self.cancel_flags[title] = False
            safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
            try:
                os.makedirs(download_dir, exist_ok=True)
                open(os.path.join(download_dir, ".collection"), 'w').close()
                import subprocess, time
                cmd = [sys.executable, "gallery_dl_module", "-d", download_dir, url] if getattr(sys, 'frozen', False) else [sys.executable, "-m", "gallery_dl", "-d", download_dir, url]
                process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                while process.poll() is None:
                    if self.cancel_flags.get(title):
                        process.terminate()
                        raise Exception("Cancelled by user")
                    time.sleep(0.5)
                if process.returncode != 0 and not self.cancel_flags.get(title):
                    # Fallback to custom scraper for unsupported urls (e.g. multporn.net)
                    scraped = self.scrape_custom_gallery(url)
                    if scraped.get("status") == "success" and scraped.get("playlist"):
                        import urllib.request
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        for index, item in enumerate(scraped["playlist"]):
                            item_url = item["url"]
                            ext = "." + item_url.split('.')[-1].split('?')[0] if '.' in item_url.split('/')[-1] else ".jpg"
                            if ext.lower() not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm"]:
                                ext = ".jpg"
                            local_path = os.path.join(download_dir, f"{index:04d}{ext}")
                            try:
                                req = urllib.request.Request(item_url, headers=headers)
                                with urllib.request.urlopen(req, timeout=10) as response, open(local_path, 'wb') as out_file:
                                    out_file.write(response.read())
                            except Exception as e:
                                print(f"Scrape download failed for item {index}: {e}")
                    else:
                        raise Exception(f"gallery-dl failed (code {process.returncode}) and scraper fallback failed: {scraped.get('msg')}")
                
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
                
                self._log_download(title, download_dir, "collection")
                self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
                self._window.evaluate_js(f'downloadComplete({json.dumps(download_dir)}, {json.dumps(title)})')
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                self._window.evaluate_js(f'downloadFailed({json.dumps(str(e))}, {json.dumps(title)})')
                
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
            
        download_dir = os.path.join(self.get_collection_download_dir()["dir"], folder_name)
        
        def run_download():
            self.cancel_flags[title] = False
            safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
            try:
                import requests
                headers = {'User-Agent': 'Porn Player/1.0 (contact@xenohead.com)'}
                
                os.makedirs(download_dir, exist_ok=True)
                open(os.path.join(download_dir, ".collection"), 'w').close()
                
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
                                    self._window.evaluate_js(f'updateDownloadProgress({downloaded_size}, {total_size}, {json.dumps(title)})')
                    
                    self._log_download(title, download_dir, "collection")
                    self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
                    self._window.evaluate_js(f'downloadComplete({json.dumps(download_dir)}, {json.dumps(title)})')
                else:
                    raise Exception(f"Failed to fetch image: HTTP {img_r.status_code}")
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                self._window.evaluate_js(f'downloadFailed({json.dumps(str(e))}, {json.dumps(title)})')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}

    def download_hentai_yoga(self, url, title, media_type="all"):
        import string
        import threading
        import os
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        download_dir = os.path.join(self.get_collection_download_dir()["dir"], folder_name)
        
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
                open(os.path.join(download_dir, ".collection"), 'w').close()

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
                                            self._window.evaluate_js(f'updateDownloadProgress({downloaded_size}, {total_size}, {json.dumps(video_title)})')
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
                                found = self._download_collection_soup_images(chap_soup, chap_url, download_dir, headers, prefix=f"c{idx+1}_", title=chap_title, scraper=scraper)
                                if found: img_downloaded = True
                    else:
                        found = self._download_collection_soup_images(soup, url, download_dir, headers, title=title, scraper=scraper)
                        if found: img_downloaded = True
                        
                    if media_type == "img" and not img_downloaded:
                        raise Exception("Could not find any images on this page.")

                if not vid_downloaded and not img_downloaded:
                    raise Exception("No matching media found for the selected type.")
                    
                self._log_download(title, download_dir, "collection")
                self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
                self._window.evaluate_js(f'downloadComplete({json.dumps(download_dir)}, {json.dumps(title)})')
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                self._window.evaluate_js(f'downloadFailed({json.dumps(str(e))}, {json.dumps(title)})')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}

    def _download_collection_soup_images(self, soup, page_url, download_dir, headers, prefix="", title="", scraper=None):
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
                if "cdn.hentai.yoga/collection/" in full_src or "cdn2.hentai.yoga/collection/" in full_src or re.search(r'chapter-\d+-\d+\.(jpg|jpeg|png|webp)', full_src):
                    if full_src not in images:
                        images.append(full_src)
                        
        if not images:
            found_imgs = re.findall(r'https?://cdn\d*\.hentai\.yoga/collection/[^\s"\']+\.(?:jpg|jpeg|png|webp)', str(soup))
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
                self._window.evaluate_js(f'updateDownloadProgress({idx+1}, {total_images}, {json.dumps(title)})')
        return successful_downloads > 0

    def download_rule34art_comic(self, url, title):
        import string
        import threading
        import os
        valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
        folder_name = ''.join(c for c in title if c in valid_chars)[:50].strip()
        if not folder_name:
            folder_name = "Rule34Art_Comic"
            
        download_dir = os.path.join(self.get_collection_download_dir()["dir"], folder_name)
        
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
                open(os.path.join(download_dir, ".collection"), 'w').close()
                
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
                        self._window.evaluate_js(f'updateDownloadProgress({current}, {total_images}, {json.dumps(title)})')
                        
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    executor.map(download_image, enumerate(images))
                        
                if self.cancel_flags.get(title):
                    raise Exception("Cancelled by user")
 
                if successful_downloads == 0:
                    raise Exception("Failed to fetch images. Access denied by server/Cloudflare.")
                    
                self._log_download(title, download_dir, "collection")
                self._window.evaluate_js(f'downloadComplete("{download_dir.replace("\\", "\\\\")}", "{safe_title}")')
                self._window.evaluate_js(f'downloadComplete({json.dumps(download_dir)}, {json.dumps(title)})')
            except Exception as e:
                self._window.evaluate_js(f'downloadFailed("{str(e).replace("\\", "\\\\")}", "{safe_title}")')
                self._window.evaluate_js(f'downloadFailed({json.dumps(str(e))}, {json.dumps(title)})')
                
        threading.Thread(target=run_download, daemon=True).start()
        return {"status": "started"}


    def get_collection_library(self):
        known = self.settings.get("known_collection_folders", [])
        library = []
        dl_dir = self.get_collection_download_dir()["dir"]
        
        # Auto-scan Download Locations Safely
        for parent in [dl_dir] + self.settings.get("saved_folders", []):
            if parent and os.path.exists(parent) and os.path.isdir(parent):
                try:
                    for sub in os.listdir(parent):
                        fp = os.path.join(parent, sub)
                        if os.path.isdir(fp) and fp not in known:
                            if os.path.exists(os.path.join(fp, ".collection")) or os.path.exists(os.path.join(fp, "collection_info.json")):
                                known.append(fp)
                except: pass

        valid_known = []
        for d in known:
            if os.path.exists(d) and os.path.isdir(d):
                valid_known.append(d)
                name = os.path.basename(d)
                json_path = os.path.join(d, "collection_info.json")
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
                
        self.settings["known_collection_folders"] = valid_known
        save_settings(self.settings)
        return {"status": "success", "library": library}

    def delete_collection_folder(self, path):
        if not path: return {"status": "error"}
        known = self.settings.get("known_collection_folders", [])
        if path in known: known.remove(path)
        self.settings["known_collection_folders"] = known
        save_settings(self.settings)
        if os.path.exists(path) and os.path.isdir(path):
            try:
                import send2trash
                send2trash.send2trash(path)
            except: shutil.rmtree(path)
        return {"status": "success"}

    # --- SUBPROCESS SEGREGATED TRANSLATE PIPELINE ---

    def translate_rect(self, path, x, y, w, h, ocr_mode, disp_w, disp_h, target_lang='English (en)', ocr_source_lang='auto'):
        if not path or not os.path.isfile(path): return {"status": "error"}
        from PIL import Image
        import pytesseract
        if os.name == 'nt' and not shutil.which('tesseract'):
            for p_path in [r'C:\Program Files\Tesseract-OCR\tesseract.exe', r'D:\Programs\Tesseract-OCR\tesseract.exe']:
                if os.path.exists(p_path):
                    pytesseract.pytesseract.tesseract_cmd = p_path
                    break
        try:
            img = Image.open(path)
            ratio_w, ratio_h = img.width / disp_w, img.height / disp_h
            orig_x, orig_y, orig_w, orig_h = int(x * ratio_w), int(y * ratio_h), int(w * ratio_w), int(h * ratio_h)
            cropped = img.crop((orig_x, orig_y, orig_x + orig_w, orig_y + orig_h))
            
            detected_lang = None
            if ocr_mode == "Japanese (Manga OCR)":
                import subprocess
                temp_img_path = os.path.join(tempfile.gettempdir(), "player_ocr_crop.png")
                cropped.save(temp_img_path)
                
                if getattr(sys, 'frozen', False):
                    # In a COLLECT/onedir build, ocr_worker.exe sits in ocr_worker/ or next to Porn layer.exe
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
                detected_lang = 'ja'
            else:
                if ocr_source_lang == 'auto':
                    try:
                        installed = pytesseract.get_languages(config='')
                        tess_lang = "+".join(installed) if installed else "eng"
                    except:
                        tess_lang = "eng"
                else:
                    tess_lang = ocr_source_lang
                
                extracted_text = pytesseract.image_to_string(cropped, lang=tess_lang).strip()
            
            # Clean up noise characters from OCR
            cleaned_extracted = re.sub(r'[@#$*%&]+', '', extracted_text).strip()
            if not cleaned_extracted or not any(c.isalnum() or '\u3040' <= c <= '\u9fff' or '\u0400' <= c <= '\u04ff' for c in cleaned_extracted):
                return {"status": "error", "msg": "No valid text found."}
            
            # Auto-detect language code if needed
            if not detected_lang:
                if ocr_source_lang == 'auto':
                    # Heuristic detection
                    if any('\u3040' <= c <= '\u30ff' for c in cleaned_extracted):
                        detected_lang = 'ja'
                    elif any('\u0400' <= c <= '\u04ff' for c in cleaned_extracted):
                        detected_lang = 'ru'
                    elif any('\u4e00' <= c <= '\u9fff' for c in cleaned_extracted):
                        detected_lang = 'zh'
                    else:
                        # Latin-script heuristic for Spanish and French
                        text_lower = cleaned_extracted.lower()
                        spa_indicators = ['ñ', '¿', '¡', 'á', 'é', 'í', 'ó', 'ú', 'ü']
                        spa_words = {'el', 'la', 'los', 'las', 'un', 'una', 'y', 'en', 'de', 'que', 'es', 'con', 'para', 'como', 'hola'}
                        fra_indicators = ['ç', 'à', 'è', 'ù', 'â', 'ê', 'î', 'ô', 'û', 'ë', 'ï']
                        fra_words = {'le', 'la', 'les', 'un', 'une', 'et', 'en', 'dans', 'pour', 'est', 'avec', 'mais'}
                        
                        words = set(re.findall(r'\b\w+\b', text_lower))
                        spa_score = sum(1 for char in spa_indicators if char in text_lower) + sum(3 for w in words if w in spa_words)
                        fra_score = sum(1 for char in fra_indicators if char in text_lower) + sum(3 for w in words if w in fra_words)
                        
                        if spa_score > fra_score and spa_score > 0:
                            detected_lang = 'es'
                        elif fra_score > spa_score and fra_score > 0:
                            detected_lang = 'fr'
                        else:
                            detected_lang = 'en'
                else:
                    # Map standard Tesseract 3-letter codes to standard 2-letter codes for Argos
                    lang_map_argos = {
                        "rus": "ru", "chi_sim": "zh", "chi_tra": "zh", 
                        "eng": "en", "jpn": "ja", "spa": "es", "fra": "fr",
                        "deu": "de", "ita": "it", "por": "pt", "kor": "ko"
                    }
                    detected_lang = lang_map_argos.get(ocr_source_lang, "en")
            
            # Dynamic destination fallback
            lang_code = target_lang.split("(")[-1].replace(")", "").strip()
            if "-" in lang_code: 
                lang_code = lang_code.split("-")[0] # Normalize 'zh-CN' to 'zh' style for Argos
            
            if detected_lang == lang_code:
                translated_text = cleaned_extracted
            else:
                translated_text = None
                try:
                    import argostranslate.translate
                    translated_text = argostranslate.translate.translate(cleaned_extracted, detected_lang, lang_code)
                    
                    # Check for repetition loops in argostranslate output
                    is_loop = False
                    if translated_text:
                        for length in range(4, 15):
                            for i in range(len(translated_text) - length * 3):
                                sub = translated_text[i:i+length]
                                if translated_text.count(sub) > 5:
                                    is_loop = True
                                    break
                            if is_loop:
                                break
                    
                    if is_loop or not translated_text:
                        raise Exception("Local model repetition loop or empty result")
                except Exception as e:
                    # Fallback to deep-translator (GoogleTranslator)
                    try:
                        from deep_translator import GoogleTranslator
                        translated_text = GoogleTranslator(source=detected_lang, target=lang_code).translate(cleaned_extracted)
                    except Exception as ex:
                        if translated_text:
                            # If offline and we had a loop, return sanitized loop text
                            # Sanitize word repetition loops
                            words = translated_text.split()
                            if len(words) > 10:
                                from collections import Counter
                                most_common, count = Counter(words).most_common(1)[0]
                                if count / len(words) > 0.4:
                                    translated_text = f"{most_common} ..."
                            
                            # Sanitize character-level repetition loops
                            cleaned_loop = False
                            for length in range(4, 15):
                                if cleaned_loop:
                                    break
                                for i in range(len(translated_text) - length * 3):
                                    sub = translated_text[i:i+length]
                                    if translated_text.count(sub) > 5:
                                        translated_text = sub + " ..."
                                        cleaned_loop = True
                                        break
                        else:
                            translated_text = f"{cleaned_extracted} (Translation model {detected_lang}->{lang_code} not installed)"
            
            return {"status": "success", "orig": cleaned_extracted, "text": translated_text, "rect": [orig_x, orig_y, orig_w, orig_h]}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def download_translation_model(self, from_code, to_code):
        try:
            import argostranslate.package
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            pack = next(filter(lambda x: x.from_code == from_code and x.to_code == to_code, available), None)
            if pack:
                argostranslate.package.install_from_path(pack.download())
                return {"status": "success"}
            return {"status": "error", "msg": f"No package found for {from_code} -> {to_code}"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def get_available_languages(self):
        try:
            import argostranslate.package
            try:
                argostranslate.package.update_package_index()
            except:
                pass
            available = argostranslate.package.get_available_packages()
            langs = {}
            for p in available:
                langs[p.from_code] = p.from_name
                langs[p.to_code] = p.to_name
            sorted_langs = [{"code": k, "name": v} for k, v in sorted(langs.items(), key=lambda item: item[1])]
            return {"status": "success", "languages": sorted_langs}
        except Exception as e:
            fallback = [
                {"code": "ja", "name": "Japanese"},
                {"code": "en", "name": "English"},
                {"code": "zh", "name": "Chinese"},
                {"code": "es", "name": "Spanish"},
                {"code": "fr", "name": "French"},
                {"code": "de", "name": "German"},
                {"code": "ru", "name": "Russian"}
            ]
            return {"status": "success", "languages": fallback, "error": str(e)}

    def get_tesseract_languages(self):
        try:
            import pytesseract
            if os.name == 'nt' and not shutil.which('tesseract'):
                for p_path in [r'C:\Program Files\Tesseract-OCR\tesseract.exe', r'D:\Programs\Tesseract-OCR\tesseract.exe']:
                    if os.path.exists(p_path):
                        pytesseract.pytesseract.tesseract_cmd = p_path
                        break
            langs = pytesseract.get_languages(config='')
            mapping = {
                "eng": "English", "jpn": "Japanese", "chi_sim": "Chinese (Simplified)", 
                "chi_tra": "Chinese (Traditional)", "rus": "Russian", "spa": "Spanish", 
                "fra": "French", "deu": "German", "ita": "Italian", "por": "Portuguese", 
                "kor": "Korean"
            }
            res = []
            for l in langs:
                res.append({"code": l, "name": mapping.get(l, l.upper())})
            return {"status": "success", "languages": res}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

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

    def clean_collection_directory(self):
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
                    if not contents or (len(contents) == 1 and contents[0] == ".collection"):
                        try:
                            if contents and contents[0] == ".collection":
                                os.remove(os.path.join(root, ".collection"))
                            os.rmdir(root)
                            deleted_folders_count += 1
                        except:
                            pass
                            
            state = {
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
            
        supported = {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.wave', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
        
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

    def save_window_state(self):
        try:
            settings = load_settings()
            if self._window and self._window.width > 100 and self._window.height > 100:
                settings["window_x"] = int(self._window.x)
                settings["window_y"] = int(self._window.y)
                settings["window_width"] = int(self._window.width)
                settings["window_height"] = int(self._window.height)
                save_settings(settings)
        except:
            pass

    def exit_app(self):
        self.cancel_encrypt()
        self.stop_onion_share()
        self.save_window_state()
        self._window.destroy()

api = Api()

# --- FLASK STREAMING INFRASTRUCTURE ---

@app.route('/media')
def stream_media():
    path = request.args.get('path')
    if not path or not os.path.exists(path) or os.path.isdir(path): return "Not found", 404
    
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
    if not path or not os.path.exists(path) or os.path.isdir(path): return "Not found", 404
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

@app.route('/ftp_player')
def ftp_player_page():
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>FTP Player</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {
            margin: 0;
            background: #09090e;
            color: #cdd6f4;
            font-family: system-ui, -apple-system, sans-serif;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            justify-content: center;
            align-items: center;
            user-select: none;
        }
        #viewer-container {
            flex: 1;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
            background: #000;
        }
        img, video {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        #controls {
            background: #11111b;
            width: 100%;
            padding: 15px;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 20px;
            box-sizing: border-box;
        }
        button {
            background: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: background 0.15s, border-color 0.15s;
        }
        button:hover {
            background: #45475a;
            border-color: #a6e3a1;
        }
        #title-display {
            font-size: 13px;
            color: #a6e3a1;
            text-align: center;
            max-width: 50%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        /* Floating Prev/Next arrows on hover */
        .nav-arrow {
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(0,0,0,0.5);
            color: #fff;
            border: none;
            width: 50px;
            height: 50px;
            border-radius: 25px;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 24px;
            cursor: pointer;
            opacity: 0;
            transition: opacity 0.2s, background 0.15s;
            z-index: 10;
        }
        #viewer-container:hover .nav-arrow {
            opacity: 0.7;
        }
        .nav-arrow:hover {
            opacity: 1 !important;
            background: rgba(166, 227, 161, 0.8);
            color: #11111b;
        }
        #prev-arrow { left: 20px; }
        #next-arrow { right: 20px; }
    </style>
</head>
<body>
    <div id="viewer-container">
        <button id="prev-arrow" class="nav-arrow" onclick="playPrev()"><i class="fa-solid fa-chevron-left"></i></button>
        <div id="media-slot" style="width:100%; height:100%; display:flex; justify-content:center; align-items:center;"></div>
        <button id="next-arrow" class="nav-arrow" onclick="playNext()"><i class="fa-solid fa-chevron-right"></i></button>
    </div>
    <div id="controls">
        <button onclick="playPrev()"><i class="fa-solid fa-backward"></i> Prev</button>
        <div id="title-display">Loading...</div>
        <button onclick="playNext()">Next <i class="fa-solid fa-forward"></i></button>
    </div>

    <script>
        let playlist = [];
        let currentIndex = -1;

        document.addEventListener('DOMContentLoaded', () => {
            window.addEventListener('pywebviewready', () => {
                loadPlaylist();
            });
            if (window.pywebview && window.pywebview.api) {
                loadPlaylist();
            }
        });

        function loadPlaylist() {
            pywebview.api.get_ftp_playlist().then(res => {
                playlist = res.files || [];
                currentIndex = res.index;
                playCurrent();
            });
        }

        function playCurrent() {
            if (currentIndex < 0 || currentIndex >= playlist.length) return;
            const item = playlist[currentIndex];
            const name = decodeURIComponent(item.name);
            document.getElementById('title-display').textContent = `(${currentIndex + 1}/${playlist.length}) ${name}`;
            document.title = name;

            const slot = document.getElementById('media-slot');
            slot.innerHTML = '';

            if (item.type === 'image') {
                const img = document.createElement('img');
                img.src = item.url;
                slot.appendChild(img);
            } else if (item.type === 'video') {
                const vid = document.createElement('video');
                vid.src = item.url;
                vid.autoplay = true;
                vid.controls = true;
                vid.style.width = '100%';
                vid.style.height = '100%';
                slot.appendChild(vid);
            } else if (item.type === 'audio') {
                const aud = document.createElement('audio');
                aud.src = item.url;
                aud.autoplay = true;
                aud.controls = true;
                slot.appendChild(aud);
            } else {
                slot.innerHTML = `<div style="text-align:center;color:#888;"><i class="fa-solid fa-file" style="font-size:64px;margin-bottom:15px;"></i><br>Unsupported preview format: ${name}</div>`;
            }
        }

        function playNext() {
            if (playlist.length === 0) return;
            currentIndex = (currentIndex + 1) % playlist.length;
            playCurrent();
        }

        function playPrev() {
            if (playlist.length === 0) return;
            currentIndex = (currentIndex - 1 + playlist.length) % playlist.length;
            playCurrent();
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight' || e.key === ' ') {
                e.preventDefault();
                playNext();
            } else if (e.key === 'ArrowLeft') {
                e.preventDefault();
                playPrev();
            }
        });
    </script>
</body>
</html>"""

def run_server():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(port=5050, debug=False, use_reloader=False)

# --- REGISTRATION KEY SECURITY (Cloudflare-backed) ---

REG_KEY_CACHE_FILE = os.path.join(app_dir, "reg_cache.json")
REG_KEY_TTL_DAYS = 30


def _sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def machine_fingerprint():
    parts = []
    try:
        parts.append(str(uuid.getnode()))
    except Exception:
        pass
    parts.append(platform.node())
    parts.append(platform.machine())
    parts.append(platform.processor())
    parts.append(platform.system())
    parts.append(platform.release())
    return _sha256_hex("|".join(parts))


def reg_key_validate_url():
    return os.environ.get("REG_KEY_VALIDATE_URL", "").strip()


def load_reg_cache():
    try:
        if os.path.exists(REG_KEY_CACHE_FILE):
            with open(REG_KEY_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_reg_cache(data):
    try:
        with open(REG_KEY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


def is_reg_unlocked():
    cache = load_reg_cache()
    if not cache:
        return False
    if cache.get("machine_id") != machine_fingerprint():
        return False
    validated_at = cache.get("validated_at")
    if not validated_at:
        return False
    try:
        v = datetime.fromisoformat(validated_at)
    except Exception:
        return False
    return (datetime.now() - v).days <= REG_KEY_TTL_DAYS


def validate_reg_key_online(key):
    url = reg_key_validate_url()
    if not url:
        return False, "Reg key validation URL not configured. Set REG_KEY_VALIDATE_URL in .env."
    key = key.strip()
    if not key:
        return False, "Please enter a registration key."
    key_hash = _sha256_hex(key)
    payload = json.dumps({
        "key": key,
        "key_hash": key_hash,
        "machine_id": machine_fingerprint(),
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            if resp.status == 200:
                data = json.loads(body)
                if data.get("ok"):
                    return True, None
                return False, data.get("error", "Invalid registration key.")
            return False, f"Validation failed (HTTP {resp.status})."
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8"))
            return False, data.get("error", f"Validation failed (HTTP {e.code}).")
        except Exception:
            return False, f"Validation failed (HTTP {e.code})."
    except Exception as e:
        return False, f"Could not reach validation server: {e}"


class RegKeyDialog:
    def __init__(self):
        self.result = None

    def run(self):
        import tkinter as tk
        from tkinter import simpledialog, messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        try:
            while self.result is None:
                key = simpledialog.askstring(
                    "XenoPlayer - Registration",
                    "Enter your registration key to unlock XenoPlayer:",
                    parent=root,
                )
                if key is None:
                    self.result = False
                    break
                key = key.strip()
                if not key:
                    messagebox.showwarning(
                        "XenoPlayer - Registration",
                        "Please enter a registration key.",
                        parent=root,
                    )
                    continue
                ok, msg = validate_reg_key_online(key)
                if ok:
                    save_reg_cache({
                        "key_hash": _sha256_hex(key),
                        "machine_id": machine_fingerprint(),
                        "validated_at": datetime.now().isoformat(),
                        "ttl_days": REG_KEY_TTL_DAYS,
                    })
                    messagebox.showinfo(
                        "XenoPlayer - Registration",
                        "Registration key accepted. Welcome to XenoPlayer.",
                        parent=root,
                    )
                    self.result = True
                else:
                    messagebox.showerror(
                        "XenoPlayer - Registration",
                        f"Invalid key: {msg}",
                        parent=root,
                    )
        finally:
            try:
                root.destroy()
            except Exception:
                pass
        return self.result


if __name__ == '__main__':
    # --- Registration key gate (keys stored/validated on Cloudflare) ---
    if not is_reg_unlocked():
        _dialog = RegKeyDialog()
        if not _dialog.run():
            sys.exit(1)

    threading.Thread(target=run_server, daemon=True).start()
    html_path = resource_path(os.path.join('web', 'index.html'))
    
    settings = load_settings()
    w_x = settings.get("window_x", None)
    w_y = settings.get("window_y", None)
    w_width = settings.get("window_width", 1000)
    w_height = settings.get("window_height", 700)
    
    if w_x is not None and w_y is not None:
        window = webview.create_window('XenoPlayer', html_path, js_api=api, x=w_x, y=w_y, width=w_width, height=w_height)
    else:
        window = webview.create_window('XenoPlayer', html_path, js_api=api, width=w_width, height=w_height)
        
    api._window = window
    window.events.closing += api.save_window_state
    window.events.closing += api.stop_onion_share
    webview.start(debug=False)