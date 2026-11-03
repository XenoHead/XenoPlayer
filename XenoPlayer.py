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
import time
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

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def _macos_app_support_dir():
    """Writable per-user location for a macOS application bundle."""
    return os.path.join(
        os.path.expanduser("~"), "Library", "Application Support", "XenoPlayer"
    )


def _pick_app_pwd():
    """Pick the directory used for read/write application data.

    On macOS a .app bundle is read-only and its launch directory is unreliable,
    so data lives in ~/Library/Application Support/XenoPlayer by default.
    Windows keeps the historical behavior: the directory the app was launched
    from, falling back to the executable/script folder. Set XENO_DATA_DIR to
    override both.
    """
    candidates = []
    override = os.environ.get("XENO_DATA_DIR")
    if override:
        override = os.path.abspath(os.path.expanduser(override))
        try:
            os.makedirs(override, exist_ok=True)
        except OSError:
            pass
        candidates.append(override)
    if IS_MACOS:
        mac_dir = _macos_app_support_dir()
        try:
            os.makedirs(mac_dir, exist_ok=True)
        except OSError:
            pass
        candidates.append(mac_dir)
    candidates.extend([os.getcwd(), app_dir])
    seen = set()
    for candidate in candidates:
        candidate = os.path.abspath(os.path.expanduser(candidate))
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            with tempfile.TemporaryFile(dir=candidate):
                pass
            return candidate
        except OSError:
            continue
    return os.path.abspath(os.getcwd())

APP_PWD = _pick_app_pwd()


def subprocess_creationflags():
    """Hide console windows on Windows; harmless everywhere else."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0


def subprocess_group_kwargs(show_window=False):
    """Start a subprocess in its own group so the whole tree can be killed."""
    if IS_WINDOWS:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if not show_window:
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def open_with_system(path):
    """Open a file or folder with the platform's default handler."""
    if IS_WINDOWS:
        os.startfile(path)
    elif IS_MACOS:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_with_system(path):
    """Reveal a file in the platform file manager."""
    path = os.path.abspath(path)
    if IS_WINDOWS:
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
    elif IS_MACOS:
        subprocess.Popen(["open", "-R", path])
    else:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        subprocess.Popen(["xdg-open", folder])


def helper_binary_path(name):
    """Locate a bundled helper executable inside a onefile/onedir or .app build.

    PyInstaller places a macOS .app's main executable in Contents/MacOS and
    extracted onefile data in sys._MEIPASS. Helpers may sit beside either one.
    """
    filenames = [name]
    if IS_WINDOWS and not name.lower().endswith(".exe"):
        filenames.insert(0, name + ".exe")

    search_dirs = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if meipass:
            search_dirs.append(meipass)
        search_dirs.append(exe_dir)
        if IS_MACOS:
            contents = os.path.dirname(exe_dir)
            search_dirs.extend([
                os.path.join(contents, "Frameworks"),
                os.path.join(contents, "Resources"),
                os.path.join(contents, "MacOS"),
            ])
    search_dirs.extend([app_dir])

    for directory in search_dirs:
        for filename in filenames:
            candidate = os.path.join(directory, filename)
            if os.path.isfile(candidate):
                return candidate
    return ""


def app_data_read_paths(filename):
    """Where to look for an existing data file, newest location first."""
    paths = [os.path.join(APP_PWD, filename)]
    for candidate in (os.path.join(app_dir, filename), resource_path(filename)):
        if candidate not in paths:
            paths.append(candidate)
    return paths

def find_app_data_file(filename):
    for path in app_data_read_paths(filename):
        if os.path.exists(path):
            return path
    return None

SETTINGS_FILE = os.path.join(APP_PWD, "web_settings.json")

def load_settings():
    settings = {"favorites": [], "last_video": None, "max_volume": 100, "move_targets": {}, 
"saved_folders": ["", "", "", "", ""], "external_apps": ["", "", "", "", ""], "default_folder": -1, "hotkeys": 
{"next": ["ArrowRight", "Space", "", "", ""], "prev": ["ArrowLeft", "", "", "", ""], 
"pause": ["KeyP", "", "", "", ""], "mute": ["KeyM", "", "", "", ""], 
"split_next_video": ["KeyD", "", "", "", ""], "split_next_image": ["KeyE", "", "", "", ""]}, "saved_volumes": {}, 
"favs_mode": "folder", "collection_sites": [], "audio_sites": [], "online_playlists": {},
"ffmpeg_path": "", "ffprobe_path": "", "video_cache_dir": "", "video_cache_max_gb": 5,
"github_token": "", "story_tts_engine": "edge",
"story_tts_voice": "en-US-AriaNeural", "story_tts_rate": 1.0}
    settings_file = find_app_data_file("web_settings.json")
    if settings_file:
        try:
            with open(settings_file, "r") as f:
                settings.update(json.load(f))
        except: pass
    
    online_src_file = find_app_data_file("MAINLIST.json")
    if online_src_file:
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

def natural_sort_path_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', os.path.normpath(s))]

# Formats the embedded webview can play directly. On Windows that is the
# Chromium/WebView2 set. WKWebView on macOS relies on the system codecs, so
# WebM/Ogg are converted through ffmpeg instead of opening to a black element.
VIDEO_BUNDLE_EXTS = {'.mp4', '.webm', '.ogg'}
IMAGE_BUNDLE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
AUDIO_BUNDLE_EXTS = {
    '.mp3', '.m4a', '.m4b', '.wav', '.ogg', '.oga', '.opus',
    '.flac', '.aac', '.webm', '.mp4',
}
if IS_MACOS:
    NATIVE_VIDEO_EXTS = {'.mp4', '.m4v', '.mov'}
    CONVERTIBLE_VIDEO_EXTS = {
        '.mp4', '.m4v', '.mov', '.webm', '.ogg', '.avi', '.wmv', '.mkv',
        '.flv', '.mpg', '.mpeg', '.ts', '.mts', '.m2ts', '.3gp', '.ogv',
    }
    # Codecs WKWebView handles reliably on supported macOS releases.
    NATIVE_VIDEO_CODECS = {"h264", "hevc", "vp8", "vp9", "av1"}
    NATIVE_AUDIO_CODECS = {
        "", "aac", "mp3", "opus", "vorbis", "flac", "alac",
        "pcm_s16le", "pcm_s16be", "pcm_s24le", "pcm_s24be",
    }
    NATIVE_AUDIO_EXTS = {
        ".mp3", ".m4a", ".m4b", ".aac", ".wav", ".wave", ".flac",
        ".aif", ".aiff", ".caf",
    }
    AUDIO_CONVERT_EXTS = {
        ".ogg", ".oga", ".opus", ".webm", ".wma", ".ape", ".wv",
    }
else:
    NATIVE_VIDEO_EXTS = {'.mp4', '.webm', '.ogg'}
    CONVERTIBLE_VIDEO_EXTS = {
        '.avi', '.wmv', '.mkv', '.mov', '.flv', '.mpg', '.mpeg', '.m4v', '.ts',
    }
    NATIVE_VIDEO_CODECS = set()
    NATIVE_AUDIO_CODECS = set()
    NATIVE_AUDIO_EXTS = set()
    AUDIO_CONVERT_EXTS = set()
GITHUB_REPO = "XenoHead/XenoPlayer"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}"

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
        self._video_conversion_lock = threading.Lock()
        self._video_conversion_token = 0
        self._video_conversion_cancel = None
        self._video_conversion_process = None
        self._video_conversion_source = ""
        try:
            self._prune_video_cache()
        except Exception:
            pass

    def get_startup_info(self):
        art_path = resource_path('XenoHead_art.png')
        platform_name = "macos" if IS_MACOS else ("windows" if IS_WINDOWS else "linux")
        info = {
            "art_path": art_path if os.path.exists(art_path) else None,
            "platform": platform_name,
            "native_video_exts": sorted(ext.lstrip(".") for ext in NATIVE_VIDEO_EXTS),
            "convertible_video_exts": sorted(
                ext.lstrip(".") for ext in CONVERTIBLE_VIDEO_EXTS
                if ext not in NATIVE_VIDEO_EXTS
            ),
            "audio_convert_exts": sorted(ext.lstrip(".") for ext in AUDIO_CONVERT_EXTS),
        }
        return info

    def _git_run(self, args, cwd, timeout=20):
        git = shutil.which("git")
        if not git:
            return None
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "never"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
        try:
            return subprocess.run(
                [git, "-C", cwd] + args,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, env=env,
                creationflags=creationflags,
            )
        except Exception:
            return None

    def _local_version_info(self):
        info = {}
        for filename in ("version.json", "build_info.json"):
            path = find_app_data_file(filename) or resource_path(filename)
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if value not in (None, ""):
                            info[key] = value
            except Exception:
                pass

        repo_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.isdir(os.path.join(repo_dir, ".git")):
            commit = self._git_run(["rev-parse", "HEAD"], repo_dir, timeout=5)
            if commit and commit.returncode == 0:
                info["commit"] = commit.stdout.strip()
            date = self._git_run(["log", "-1", "--format=%cI"], repo_dir, timeout=5)
            if date and date.returncode == 0:
                info["commit_date"] = date.stdout.strip()
            subject = self._git_run(["log", "-1", "--format=%s"], repo_dir, timeout=5)
            if subject and subject.returncode == 0:
                info["commit_subject"] = subject.stdout.strip()
        return info

    def _github_api(self, path):
        import requests
        token = (
            os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
            or self._get_env_var("GITHUB_TOKEN", "GH_TOKEN")
            or (self.settings.get("github_token") or "").strip()
        )
        headers = {
            "User-Agent": "XenoPlayer-UpdateCheck",
            "Accept": "application/vnd.github+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}{path}",
                headers=headers, timeout=15,
            )
        except Exception as e:
            return None, f"Could not reach GitHub: {e}"
        if response.status_code == 200:
            try:
                return response.json(), None
            except Exception as e:
                return None, f"GitHub returned invalid JSON: {e}"
        if response.status_code in (401, 403, 404):
            return None, "Repository not found or private (GitHub token required)."
        return None, f"GitHub returned HTTP {response.status_code}."

    @staticmethod
    def _version_tuple(value):
        import re
        parts = re.findall(r"\d+", value or "")
        return tuple(int(part) for part in parts[:4]) if parts else ()

    def check_for_updates(self):
        local = self._local_version_info()
        local_version = str(local.get("version") or "0.0.0").strip()
        local_commit = str(local.get("commit") or "").strip()
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        has_git_checkout = (
            os.path.isdir(os.path.join(repo_dir, ".git"))
            and bool(shutil.which("git"))
        )

        if has_git_checkout:
            fetch = self._git_run(
                ["fetch", "--quiet", "origin", "main"], repo_dir, timeout=30
            )
            if fetch is not None and fetch.returncode == 0:
                counts = self._git_run(
                    ["rev-list", "--left-right", "--count", "HEAD...origin/main"],
                    repo_dir, timeout=10,
                )
                if counts is not None and counts.returncode == 0:
                    try:
                        ahead, behind = (int(part) for part in counts.stdout.split()[:2])
                    except Exception:
                        ahead = behind = 0

                    remote_sha_result = self._git_run(
                        ["rev-parse", "origin/main"], repo_dir, timeout=5
                    )
                    remote_sha = (
                        remote_sha_result.stdout.strip()
                        if remote_sha_result and remote_sha_result.returncode == 0
                        else ""
                    )
                    subject_result = self._git_run(
                        ["log", "-1", "--format=%s", "origin/main"], repo_dir, timeout=5
                    )
                    remote_subject = (
                        subject_result.stdout.strip()
                        if subject_result and subject_result.returncode == 0
                        else ""
                    )
                    date_result = self._git_run(
                        ["log", "-1", "--format=%cI", "origin/main"], repo_dir, timeout=5
                    )
                    remote_date = (
                        date_result.stdout.strip()
                        if date_result and date_result.returncode == 0
                        else ""
                    )

                    if behind > 0:
                        compare_url = (
                            f"{GITHUB_REPO_URL}/compare/{local_commit}...{remote_sha}"
                            if local_commit and remote_sha
                            else f"{GITHUB_REPO_URL}/commits/main"
                        )
                        return {
                            "status": "update_available",
                            "version": remote_sha[:7] or "new commit",
                            "commit": remote_sha,
                            "current": local_commit[:7] or local_version,
                            "latest": remote_sha[:7],
                            "date": remote_date,
                            "notes": remote_subject,
                            "ahead": ahead,
                            "behind": behind,
                            "url": compare_url,
                        }

                    return {
                        "status": "up_to_date",
                        "version": local_version,
                        "commit": local_commit[:7],
                        "latest": remote_sha[:7],
                        "date": remote_date,
                        "ahead": ahead,
                        "behind": behind,
                    }

        # Packaged build: compare the live remote main SHA against the SHA
        # recorded when the app was built.
        build_remote = str(local.get("remote_main") or "").strip()
        if not has_git_checkout and build_remote and shutil.which("git"):
            ls_remote = self._git_run(
                ["ls-remote", GITHUB_REPO_URL, "refs/heads/main"],
                os.getcwd(), timeout=20,
            )
            if ls_remote is not None and ls_remote.returncode == 0:
                parts = ls_remote.stdout.split()
                remote_sha = parts[0] if parts else ""
                if remote_sha:
                    if remote_sha.lower() == build_remote.lower():
                        return {
                            "status": "up_to_date",
                            "version": local_version,
                            "commit": local_commit[:7],
                            "latest": remote_sha[:7],
                        }
                    return {
                        "status": "update_available",
                        "version": remote_sha[:7],
                        "commit": remote_sha,
                        "current": local_commit[:7] or local_version,
                        "latest": remote_sha[:7],
                        "url": (
                            f"{GITHUB_REPO_URL}/compare/{local_commit}...{remote_sha}"
                            if local_commit
                            else f"{GITHUB_REPO_URL}/commits/main"
                        ),
                    }

        # Fallback for packaged builds or machines without a usable Git checkout.
        release, release_error = self._github_api("/releases/latest")
        if release:
            tag = str(release.get("tag_name") or "").strip()
            latest_version = tag.lstrip("vV") or local_version
            if self._version_tuple(latest_version) > self._version_tuple(local_version):
                return {
                    "status": "update_available",
                    "version": latest_version,
                    "current": local_version,
                    "date": release.get("published_at", ""),
                    "notes": (release.get("name") or release.get("body") or "")[:500],
                    "url": release.get("html_url") or f"{GITHUB_REPO_URL}/releases",
                }
            return {
                "status": "up_to_date",
                "version": local_version,
                "latest": latest_version,
            }

        commit, commit_error = self._github_api("/commits/main")
        if commit:
            sha = str(commit.get("sha") or "")
            commit_info = commit.get("commit") or {}
            author = commit_info.get("author") or {}
            remote_date = str(author.get("date") or "")
            message = str(commit_info.get("message") or "").splitlines()[0]
            if local_commit and sha:
                if sha.lower() == local_commit.lower():
                    return {
                        "status": "up_to_date",
                        "version": local_version,
                        "commit": local_commit[:7],
                        "latest": sha[:7],
                    }
                return {
                    "status": "update_available",
                    "version": sha[:7],
                    "commit": sha,
                    "current": local_commit[:7],
                    "latest": sha[:7],
                    "date": remote_date,
                    "notes": message,
                    "url": f"{GITHUB_REPO_URL}/compare/{local_commit}...{sha}",
                }

            local_date = str(
                local.get("build_date")
                or local.get("commit_date")
                or local.get("last_updated")
                or ""
            )
            if remote_date and local_date and remote_date > local_date:
                return {
                    "status": "update_available",
                    "version": sha[:7],
                    "commit": sha,
                    "current": local_version,
                    "latest": sha[:7],
                    "date": remote_date,
                    "notes": message,
                    "url": f"{GITHUB_REPO_URL}/commits/main",
                }
            return {
                "status": "up_to_date",
                "version": local_version,
                "latest": sha[:7],
                "date": remote_date,
            }

        detail = release_error or commit_error or "Git is not available."
        return {
            "status": "error",
            "msg": (
                "Could not check Git for updates. Run XenoPlayer from a Git checkout "
                "with credentials, or add GITHUB_TOKEN to .env for a private "
                f"repository. ({detail})"
            ),
        }

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
                    supported = {'.mp4', '.webm', '.ogg', '.avi', '.wmv', '.mkv', '.mov', '.flv', '.mpg', '.mpeg', '.m4v', '.ts', '.zip', '.cbz', '.mp3', '.wav', '.wave', '.m4a', '.m4b', '.aac', '.flac', '.oga', '.opus', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
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
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=last_dir, allow_multiple=False, file_types=('Media Files (*.mp4;*.webm;*.ogg;*.avi;*.wmv;*.mkv;*.mov;*.flv;*.mpg;*.mpeg;*.m4v;*.ts;*.mp3;*.wav;*.wave;*.m4a;*.m4b;*.aac;*.flac;*.oga;*.opus;*.jpg;*.png;*.gif;*.webp;*.cbz;*.zip)', 'All files (*.*)'))
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
        if IS_MACOS:
            file_types = ('Applications (*.app)', 'All files (*.*)')
        else:
            file_types = ('Executables (*.exe)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, directory=last_dir, allow_multiple=False, file_types=file_types)
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
        exe = "onionshare-cli.exe" if IS_WINDOWS else "onionshare-cli"
        configured = self.settings.get("onionshare_cli_path")
        candidates = []
        if configured: candidates.append(configured)
        candidates.extend([
            os.path.join(app_dir, exe),
            os.path.join(os.path.dirname(sys.executable), exe),
            os.path.join(app_dir, "onionshare", exe),
        ])
        if IS_MACOS:
            candidates.extend([
                "/Applications/OnionShare.app/Contents/MacOS/onionshare-cli",
                os.path.expanduser("~/Applications/OnionShare.app/Contents/MacOS/onionshare-cli"),
                "/opt/homebrew/bin/onionshare-cli",
                "/usr/local/bin/onionshare-cli",
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
        names = ("7z.exe", "7za.exe", "7zz.exe") if IS_WINDOWS else ("7z", "7zz", "7za")
        configured = self.settings.get("seven_zip_path")
        candidates = []
        if configured: candidates.append(configured)
        for name in names:
            candidates.extend([
                os.path.join(app_dir, name),
                os.path.join(os.path.dirname(sys.executable), name),
            ])
            if IS_MACOS:
                candidates.extend([
                    f"/opt/homebrew/bin/{name}",
                    f"/usr/local/bin/{name}",
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
        if not IS_WINDOWS:
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
                return self._onion_payload({"ok": False, "error": "Select onionshare-cli, not the OnionShare GUI."})
            self.settings["onionshare_cli_path"] = path
            save_settings(self.settings)
        return self._onion_payload({"ok": True})

    def browse_seven_zip(self):
        path = self.browse_exe_dialog()
        if path:
            name = os.path.basename(path).lower()
            if name not in ("7z.exe", "7za.exe", "7zz.exe", "7z", "7za", "7zz"):
                return self._onion_payload({"ok": False, "error": "Select the 7-Zip command-line tool, not the File Manager."})
            self.settings["seven_zip_path"] = path
            save_settings(self.settings)
        return self._onion_payload({"ok": True})

    def open_receive_folder(self, path=None):
        try:
            path = os.path.abspath(path or self._onion_default_receive_dir())
            os.makedirs(path, exist_ok=True)
            open_with_system(path)
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
        if os.path.splitext(filepath)[1].lower() in ('.cbz', '.zip'):
            self.open_cbz_archive(filepath)
            return
        directory = os.path.dirname(filepath)
        self._current_directory = directory
        
        supported = {'.mp4', '.webm', '.ogg', '.avi', '.wmv', '.mkv', '.mov', '.flv', '.mpg', '.mpeg', '.m4v', '.ts', '.zip', '.cbz', '.mp3', '.wav', '.wave', '.m4a', '.m4b', '.aac', '.flac', '.oga', '.opus', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
        
        if self.settings.get("recursive_load", False):
            full_playlist = []
            for root, dirs, files in os.walk(directory):
                for f in files:
                    if f.lower() == "collection_info.json":
                        continue
                    if os.path.splitext(f)[1].lower() in supported:
                        full_playlist.append(os.path.join(root, f))
            self.full_playlist = full_playlist
        else:
            try:
                files = os.listdir(directory)
            except: return
            self.full_playlist = [os.path.join(directory, f) for f in files if f.lower() != "collection_info.json" and os.path.splitext(f)[1].lower() in supported]
            
        self.full_playlist.sort(key=natural_sort_key)
        
        self.filter_mode = "all"
        self.apply_filter(filepath)
            
        self.settings["last_video"] = filepath
        save_settings(self.settings)
        self._window.evaluate_js('updatePlaylist()')
        if play:
            self.play_current()

    def load_selected_directory(self, directory_path, recursive=None):
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
        
        supported = {'.mp4', '.webm', '.ogg', '.avi', '.wmv', '.mkv', '.mov', '.flv', '.mpg', '.mpeg', '.m4v', '.ts', '.zip', '.cbz', '.mp3', '.wav', '.wave', '.m4a', '.m4b', '.aac', '.flac', '.oga', '.opus', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
        
        if recursive is None:
            recursive = self.settings.get("recursive_load", False)
        if recursive:
            full_playlist = []
            for root, dirs, files in os.walk(directory_path):
                for f in files:
                    if f.lower() == "collection_info.json":
                        continue
                    if os.path.splitext(f)[1].lower() in supported:
                        full_playlist.append(os.path.join(root, f))
            self.full_playlist = full_playlist
        else:
            try:
                files = os.listdir(directory_path)
            except: return
            self.full_playlist = [os.path.join(directory_path, f) for f in files if f.lower() != "collection_info.json" and os.path.splitext(f)[1].lower() in supported]
            
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
            try:
                self._cbz_temp_dir.cleanup()
            except Exception:
                # WebView2 can briefly hold the currently playing video open.
                # Let TemporaryDirectory retry when the object is collected.
                pass
        self._cbz_temp_dir = None
        self._cbz_root = None
        self._cbz_archive_path = None

    def _video_js(self, script):
        try:
            if self._window:
                self._window.evaluate_js(script)
        except Exception:
            pass

    def _find_ffmpeg(self):
        override = (self.settings.get("ffmpeg_path") or "").strip()
        exe = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
        candidates = []
        if override:
            candidates.append(override)
            if os.path.isdir(override):
                candidates.append(os.path.join(override, exe))
        candidates.extend([
            os.path.join(app_dir, exe),
            os.path.join(app_dir, "bin", exe),
            os.path.join(app_dir, "ffmpeg", "bin", exe),
        ])
        if IS_MACOS:
            candidates.extend([
                os.path.join(app_dir, "ffmpeg", exe),
                "/opt/homebrew/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "/opt/local/bin/ffmpeg",
            ])
        which = shutil.which("ffmpeg")
        if which:
            candidates.append(which)
        if IS_WINDOWS:
            candidates.extend([
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "ffmpeg", "bin", exe),
                os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin", exe),
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"D:\Tools\ffmpeg\bin\ffmpeg.exe",
            ])
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return ""

    def _find_ffprobe(self):
        override = (self.settings.get("ffprobe_path") or "").strip()
        if override and os.path.isfile(override):
            return override
        ffmpeg = self._find_ffmpeg()
        if ffmpeg:
            exe = "ffprobe.exe" if IS_WINDOWS else "ffprobe"
            candidate = os.path.join(os.path.dirname(ffmpeg), exe)
            if os.path.isfile(candidate):
                return candidate
        if IS_MACOS:
            for candidate in ("/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"):
                if os.path.isfile(candidate):
                    return candidate
        return shutil.which("ffprobe") or ""

    def _video_cache_dir(self):
        configured = (self.settings.get("video_cache_dir") or "").strip()
        cache = os.path.abspath(configured) if configured else os.path.join(APP_PWD, ".video_cache")
        try:
            os.makedirs(cache, exist_ok=True)
            return cache
        except OSError:
            fallback = os.path.join(tempfile.gettempdir(), "XenoPlayer_video_cache")
            os.makedirs(fallback, exist_ok=True)
            return fallback

    def _media_cache_path(self, path, extension):
        stat = os.stat(path)
        key = hashlib.sha256(
            f"{os.path.abspath(path)}|{stat.st_mtime_ns}|{stat.st_size}|v1".encode("utf-8")
        ).hexdigest()[:32]
        return os.path.join(self._video_cache_dir(), f"{key}{extension}")

    def _video_cache_path(self, path):
        return self._media_cache_path(path, ".mp4")

    def _prune_video_cache(self, keep_path=None):
        cache = self._video_cache_dir()
        try:
            max_gb = float(self.settings.get("video_cache_max_gb", 5) or 5)
        except (TypeError, ValueError):
            max_gb = 5
        max_bytes = max(0.5, max_gb) * 1024 ** 3
        now = time.time()
        entries = []
        total = 0
        try:
            names = os.listdir(cache)
        except OSError:
            return
        for name in names:
            path = os.path.join(cache, name)
            if not os.path.isfile(path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            if name.endswith(".part"):
                if now - stat.st_mtime > 3600:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                continue
            if not name.lower().endswith((".mp4", ".m4a")):
                continue
            if now - stat.st_mtime > 30 * 86400:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            entries.append((stat.st_mtime, path))
            total += stat.st_size

        if total <= max_bytes:
            return
        entries.sort(key=lambda row: row[0])
        for _mtime, path in entries:
            if total <= max_bytes:
                break
            if keep_path and os.path.normpath(path) == os.path.normpath(keep_path):
                continue
            try:
                size = os.path.getsize(path)
                os.remove(path)
                total -= size
            except OSError:
                pass

    def _probe_video(self, ffprobe, path):
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
            result = subprocess.run(
                [
                    ffprobe, "-v", "error", "-print_format", "json",
                    "-show_streams", "-show_format", path,
                ],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, creationflags=creationflags,
            )
            data = json.loads(result.stdout or "{}")
            streams = data.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
            duration = data.get("format", {}).get("duration") or video.get("duration") or 0
            try:
                duration = float(duration)
            except (TypeError, ValueError):
                duration = 0.0
            return {
                "video_codec": (video.get("codec_name") or "").lower(),
                "audio_codec": (audio.get("codec_name") or "").lower(),
                "duration": duration,
            }
        except Exception:
            return {}

    def _native_video_is_playable(self, path):
        """Return False when a native container holds a codec WKWebView can't decode."""
        if not IS_MACOS:
            return True
        ffprobe = self._find_ffprobe()
        if not ffprobe:
            # Without a probe, let WebKit make the first attempt.
            return True
        info = self._probe_video(ffprobe, path)
        video_codec = info.get("video_codec")
        audio_codec = info.get("audio_codec")
        if video_codec and video_codec not in NATIVE_VIDEO_CODECS:
            return False
        if audio_codec and audio_codec not in NATIVE_AUDIO_CODECS:
            return False
        return True

    def prepare_audio_for_playback(self, path):
        """Convert Ogg/Opus/WMA audio to AAC/M4A for WKWebView on macOS."""
        temp_path = ""
        try:
            if not path:
                return {"status": "error", "msg": "No audio file provided."}
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                return {"status": "error", "msg": "Audio file not found."}
            if not IS_MACOS:
                return {"status": "native", "path": path}

            ext = os.path.splitext(path)[1].lower()
            if ext in NATIVE_AUDIO_EXTS:
                return {"status": "native", "path": path}
            if ext not in AUDIO_CONVERT_EXTS:
                return {
                    "status": "error",
                    "msg": f"{ext or 'This file'} is not an audio format XenoPlayer can open.",
                }

            cache_path = self._media_cache_path(path, ".m4a")
            if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 1024:
                return {"status": "ready", "path": cache_path, "source": path, "cached": True}

            ffmpeg = self._find_ffmpeg()
            if not ffmpeg:
                return {
                    "status": "no_ffmpeg",
                    "source": path,
                    "msg": (
                        "This audio format needs ffmpeg for playback. Install ffmpeg "
                        "with `brew install ffmpeg`, or set ffmpeg_path in web_settings.json."
                    ),
                }

            cache_dir = self._video_cache_dir()
            temp_path = os.path.join(
                cache_dir, f".audio_{int(time.time() * 1000)}.m4a"
            )
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", path, "-vn", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", temp_path,
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=1800, creationflags=subprocess_creationflags(),
            )
            if (
                result.returncode != 0
                or not os.path.exists(temp_path)
                or os.path.getsize(temp_path) < 1024
            ):
                message = (result.stderr or "").strip().splitlines()
                message = message[-1] if message else f"ffmpeg failed (exit code {result.returncode})."
                return {"status": "error", "msg": message}
            os.replace(temp_path, cache_path)
            self._prune_video_cache(keep_path=cache_path)
            return {"status": "ready", "path": cache_path, "source": path, "cached": False}
        except Exception as error:
            return {"status": "error", "msg": str(error)}
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def prepare_video_for_playback(self, path):
        try:
            if not path:
                return {"status": "error", "msg": "No video file provided."}
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                return {"status": "error", "msg": "Video file not found."}

            ext = os.path.splitext(path)[1].lower()
            if ext in NATIVE_VIDEO_EXTS and self._native_video_is_playable(path):
                return {"status": "native", "path": path}
            if ext not in CONVERTIBLE_VIDEO_EXTS:
                return {
                    "status": "error",
                    "msg": f"{ext or 'This file'} is not a video format XenoPlayer can open.",
                }

            cache_path = self._video_cache_path(path)
            if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 1024:
                return {
                    "status": "ready", "path": cache_path,
                    "source": path, "cached": True,
                }

            if not self._find_ffmpeg():
                return {
                    "status": "no_ffmpeg",
                    "source": path,
                    "msg": (
                        "This video format needs ffmpeg for playback. Install ffmpeg "
                        "and make sure it is on PATH"
                        + (" (for example: brew install ffmpeg)" if IS_MACOS else "")
                        + ", or set ffmpeg_path in web_settings.json."
                    ),
                }

            with self._video_conversion_lock:
                self._video_conversion_token += 1
                token = self._video_conversion_token
                old_cancel = self._video_conversion_cancel
                cancel_event = threading.Event()
                self._video_conversion_cancel = cancel_event
                self._video_conversion_source = path
            if old_cancel is not None:
                old_cancel.set()
            process = self._video_conversion_process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass

            threading.Thread(
                target=self._convert_video_worker,
                args=(path, cache_path, token, cancel_event),
                daemon=True,
            ).start()
            return {
                "status": "converting",
                "token": token,
                "source": path,
                "name": os.path.basename(path),
            }
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def cancel_video_conversion(self):
        with self._video_conversion_lock:
            event = self._video_conversion_cancel
            process = self._video_conversion_process
            if event is not None:
                event.set()
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
        return {"status": "ok"}

    def _convert_video_worker(self, source, cache_path, token, cancel_event):
        process = None
        temp_path = ""
        try:
            ffmpeg = self._find_ffmpeg()
            ffprobe = self._find_ffprobe()
            info = self._probe_video(ffprobe, source) if ffprobe else {}
            duration = info.get("duration", 0.0)
            video_codec = info.get("video_codec", "")
            audio_codec = info.get("audio_codec", "")
            remux = video_codec == "h264" and (
                not audio_codec or audio_codec in ("aac", "mp3")
            )

            cache_dir = self._video_cache_dir()
            temp_path = os.path.join(
                cache_dir, f".{token}_{int(time.time() * 1000)}.part"
            )
            command = [
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-progress", "pipe:1", "-nostats", "-i", source,
            ]
            if remux:
                command += [
                    "-map", "0:v:0", "-map", "0:a:0?",
                    "-c", "copy", "-movflags", "+faststart",
                ]
            else:
                command += [
                    "-map", "0:v:0", "-map", "0:a:0?",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart",
                ]
            command += ["-f", "mp4", temp_path]

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            self._video_conversion_process = process
            last_error = ""
            for line in process.stdout:
                if cancel_event.is_set():
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    break
                line = line.strip()
                if line.startswith(("out_time_us=", "out_time_ms=")):
                    try:
                        microseconds = int(line.split("=", 1)[1])
                        seconds = microseconds / 1_000_000.0
                        percent = int(min(99, max(0, seconds / duration * 100))) if duration > 0 else -1
                        self._video_js(
                            "updateVideoConvertProgress("
                            f"{percent}, {json.dumps(os.path.basename(source))})"
                        )
                    except Exception:
                        pass
                elif line and "=" not in line:
                    last_error = line
            process.wait()
            self._video_conversion_process = None

            if cancel_event.is_set():
                self._video_js(
                    f"videoConvertFailed({json.dumps(token)}, {json.dumps('Cancelled')})"
                )
                return
            if (
                process.returncode != 0
                or not os.path.exists(temp_path)
                or os.path.getsize(temp_path) < 1024
            ):
                message = last_error or f"ffmpeg failed (exit code {process.returncode})."
                self._video_js(
                    f"videoConvertFailed({json.dumps(token)}, {json.dumps(message)})"
                )
                return

            os.replace(temp_path, cache_path)
            self._prune_video_cache(keep_path=cache_path)
            self._video_js(
                "videoConvertFinished("
                f"{json.dumps(token)}, {json.dumps(cache_path)}, {json.dumps(source)})"
            )
        except Exception as error:
            self._video_js(
                f"videoConvertFailed({json.dumps(token)}, {json.dumps(str(error))})"
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            if process is not None:
                try:
                    if process.poll() is None:
                        process.kill()
                except Exception:
                    pass
            self._video_conversion_process = None

    def open_path_external(self, path):
        try:
            if not path or not os.path.exists(path):
                return {"status": "error", "msg": "File not found."}
            open_with_system(path)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def open_cbz_archive(self, archive_path):
        archive_path = os.path.abspath(archive_path)
        ext = os.path.splitext(archive_path)[1].lower()
        if not os.path.isfile(archive_path) or ext not in ('.cbz', '.zip'):
            return {"status": "error", "msg": "The selected file is not a CBZ or ZIP archive."}

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

    def _collect_bundle_media(self, folder, extensions):
        media = []
        if self.settings.get("recursive_load", False):
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for name in files:
                    if name.startswith('.'):
                        continue
                    if os.path.splitext(name)[1].lower() in extensions:
                        media.append(os.path.join(root, name))
        else:
            try:
                names = os.listdir(folder)
            except OSError:
                return []
            for name in names:
                path = os.path.join(folder, name)
                if name.startswith('.') or not os.path.isfile(path):
                    continue
                if os.path.splitext(name)[1].lower() in extensions:
                    media.append(path)
        media.sort(key=lambda path: natural_sort_path_key(os.path.relpath(path, folder)))
        return media

    def _write_media_cbz(self, media_files, archive_path, compress):
        # Flatten nested files into the archive root so they play even when
        # recursive loading is disabled. Number every entry so chapter folders
        # and duplicate page names keep their exact collected order.
        entries = []
        width = max(4, len(str(len(media_files))))
        for index, media_file in enumerate(media_files, start=1):
            name = os.path.basename(media_file)
            arcname = f"{index:0{width}d}_{name}"
            entries.append((media_file, arcname))

        compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
        temp_path = f"{archive_path}.part"
        try:
            with zipfile.ZipFile(
                temp_path, "w", compression=compression, allowZip64=True
            ) as archive:
                for media_file, arcname in entries:
                    archive.write(media_file, arcname=arcname)
            os.replace(temp_path, archive_path)
        except Exception:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise
        return len(entries)

    def _create_media_cbz(self, kind):
        if kind == "image":
            extensions = IMAGE_BUNDLE_EXTS
            bundle_label = "Image"
            default_name = "ImageBundle"
            empty_msg = ("No supported image files were found in that folder.\n\n"
                         "Image CBZ bundles support JPG, JPEG, PNG, WebP, and GIF.")
            compress = True
        else:
            extensions = VIDEO_BUNDLE_EXTS
            bundle_label = "Video"
            default_name = "VideoBundle"
            empty_msg = ("No playable video files were found in that folder.\n\n"
                         "Video CBZ bundles support MP4, WebM, and OGG clips.")
            compress = False

        last_dir = self.settings.get("last_opened_dir") or self._current_directory
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = os.path.expanduser("~")

        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=last_dir)
        if not result:
            return {"status": "cancelled"}
        folder = result[0] if isinstance(result, (list, tuple)) else result
        folder = os.path.abspath(folder)

        media_files = self._collect_bundle_media(folder, extensions)
        if not media_files:
            return {"status": "error", "msg": empty_msg}

        bundle_name = os.path.basename(os.path.normpath(folder)) or default_name
        save_result = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=folder,
            save_filename=f"{bundle_name}.cbz",
            file_types=('Comic Book Archive (*.cbz)', 'All files (*.*)')
        )
        if not save_result:
            return {"status": "cancelled"}
        archive_path = save_result[0] if isinstance(save_result, (list, tuple)) else save_result
        archive_path = os.path.abspath(archive_path)
        if not archive_path.lower().endswith('.cbz'):
            archive_path += '.cbz'

        try:
            count = self._write_media_cbz(media_files, archive_path, compress)
        except Exception as e:
            return {"status": "error", "msg": f"Could not create the CBZ: {e}"}

        self.settings["last_opened_dir"] = folder
        save_settings(self.settings)
        return {
            "status": "success",
            "path": archive_path,
            "count": count,
            "folder": folder,
            "kind": kind,
            "label": bundle_label
        }

    def create_image_cbz(self):
        return self._create_media_cbz("image")

    def create_video_cbz(self):
        return self._create_media_cbz("video")

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

        is_collection_archive = False
        collection_name = ""
        collection_target = self._collection_target(current_path) if current_path else None
        if collection_target:
            if collection_target["kind"] == "archive":
                archive = collection_target["archive"]
                sidecar = self._collection_sidecar_path(archive)
                meta = self._read_collection_meta(sidecar)
                is_collection_archive = os.path.exists(sidecar)
                collection_name = (meta.get("name") or "").strip() or os.path.splitext(os.path.basename(archive))[0]
            else:
                meta = self._read_collection_meta(os.path.join(collection_target["dir"], "collection_info.json"))
                collection_name = (meta.get("name") or "").strip() or os.path.basename(collection_target["dir"])
        
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
            "is_collection_archive": is_collection_archive,
            "collection_name": collection_name,
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
            "gemini_api_key": self.settings.get("gemini_api_key", ""),
            "story_tts_engine": self.settings.get("story_tts_engine", "edge"),
            "story_tts_voice": self.settings.get("story_tts_voice", "en-US-AriaNeural"),
            "story_tts_rate": self.settings.get("story_tts_rate", 1.0)
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
            src_path = os.path.join(APP_PWD, 'MAINLIST.json')
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
                directory=APP_PWD,
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
                directory=APP_PWD,
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
            audio_exts = {'.mp3','.wav','.wave','.flac','.aac','.ogg','.oga','.m4a','.m4b','.opus','.wma'}
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
                    if os.path.splitext(name)[1].lower() in ('.cbz', '.zip')
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

    COLLECTION_ARCHIVE_EXTS = ('.cbz', '.cbr', '.cb7', '.cbt')

    def _collection_sidecar_path(self, archive_path):
        stem, _ = os.path.splitext(archive_path)
        return stem + ".collection.json"

    def _read_collection_meta(self, json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_collection_meta(self, json_path, data):
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _sanitize_collection_name(self, name, fallback=""):
        cleaned = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in str(name or ""))
        cleaned = cleaned.strip().strip(".").strip()
        return cleaned or fallback

    def _unique_file_path(self, path):
        if not os.path.exists(path):
            return path
        stem, ext = os.path.splitext(path)
        for index in range(2, 1000):
            candidate = "{} ({}){}".format(stem, index, ext)
            if not os.path.exists(candidate):
                return candidate
        return path

    def _replace_path_references(self, old_path, new_path):
        favorites = [new_path if fav == old_path else fav for fav in self.settings.get("favorites", [])]
        self.settings["favorites"] = favorites
        if self.settings.get("last_video") == old_path:
            self.settings["last_video"] = new_path
        save_settings(self.settings)

    def _collection_target(self, path=None):
        """Resolve what 'Make Collection' should act on.

        An open CBZ archive always wins, otherwise the given path (or the first
        playlist entry) decides between a folder and a comic archive.
        """
        if self._cbz_archive_path:
            archive = self._cbz_archive_path
            return {"kind": "archive", "dir": os.path.dirname(archive), "archive": archive}
        if not path:
            path = self.playlist[0] if self.playlist else None
        if not path:
            return None
        ext = os.path.splitext(path)[1].lower()
        if ext in self.COLLECTION_ARCHIVE_EXTS and os.path.isfile(path):
            return {"kind": "archive", "dir": os.path.dirname(path), "archive": path}
        dir_path = path if os.path.isdir(path) else os.path.dirname(path)
        if not dir_path or not os.path.isdir(dir_path):
            return None
        return {"kind": "folder", "dir": dir_path, "archive": None}

    def get_collection_prompt(self, path=None):
        """Details used by the 'Make Collection' naming dialog."""
        target = self._collection_target(path)
        if not target:
            return {"status": "error", "msg": "Right-click a folder or comic file first."}
        if target["kind"] == "archive":
            archive = target["archive"]
            stem, ext = os.path.splitext(os.path.basename(archive))
            sidecar = self._collection_sidecar_path(archive)
            meta = self._read_collection_meta(sidecar)
            return {
                "status": "success",
                "kind": "archive",
                "path": archive,
                "name": (meta.get("name") or "").strip() or stem,
                "file_name": stem,
                "extension": ext,
                "is_collection": os.path.exists(sidecar),
            }
        dir_path = target["dir"]
        meta = self._read_collection_meta(os.path.join(dir_path, "collection_info.json"))
        return {
            "status": "success",
            "kind": "folder",
            "path": dir_path,
            "name": (meta.get("name") or "").strip() or os.path.basename(dir_path),
            "file_name": "",
            "extension": "",
            "is_collection": os.path.exists(os.path.join(dir_path, ".collection")),
        }

    def mark_as_collection(self, path=None, name=None, archive_name=None):
        target = self._collection_target(path)
        if not target:
            return {"status": "error", "msg": "No folder or comic file is selected."}
        if target["kind"] == "archive":
            return self._mark_archive_collection(target["archive"], name, archive_name)
        dir_path = target["dir"]
        collection_name = self._sanitize_collection_name(name, os.path.basename(dir_path))
        try:
            open(os.path.join(dir_path, ".collection"), "w").close()
            json_path = os.path.join(dir_path, "collection_info.json")
            data = self._read_collection_meta(json_path)
            data["name"] = collection_name
            self._write_collection_meta(json_path, data)
        except Exception as e:
            return {"status": "error", "msg": str(e)}
        known = self.settings.get("known_collection_folders", [])
        if dir_path not in known:
            known.append(dir_path)
            self.settings["known_collection_folders"] = known
            save_settings(self.settings)
        return self.get_state()

    def _mark_archive_collection(self, archive, name, archive_name=None):
        old_stem, ext = os.path.splitext(os.path.basename(archive))
        collection_name = self._sanitize_collection_name(name, old_stem)
        desired_stem = self._sanitize_collection_name(archive_name, old_stem)
        final_path = archive
        if desired_stem and desired_stem != old_stem:
            candidate = self._unique_file_path(os.path.join(os.path.dirname(archive), desired_stem + ext))
            try:
                os.rename(archive, candidate)
            except OSError as e:
                return {"status": "error", "msg": "Could not rename the comic file: {}".format(e)}
            final_path = candidate
            if self._cbz_archive_path == archive:
                self._cbz_archive_path = final_path
            self._replace_path_references(archive, final_path)
        old_sidecar = self._collection_sidecar_path(archive)
        sidecar = self._collection_sidecar_path(final_path)
        if old_sidecar != sidecar and os.path.exists(old_sidecar):
            try:
                os.remove(old_sidecar)
            except Exception:
                pass
        try:
            meta = self._read_collection_meta(sidecar)
            meta["name"] = collection_name
            meta["file"] = os.path.basename(final_path)
            meta["updated_at"] = datetime.now().isoformat()
            self._write_collection_meta(sidecar, meta)
        except Exception as e:
            return {"status": "error", "msg": str(e)}
        try:
            archive_dirs = self.settings.get("known_collection_archive_dirs", [])
            parent_dir = os.path.dirname(final_path)
            if parent_dir and parent_dir not in archive_dirs:
                archive_dirs.append(parent_dir)
                self.settings["known_collection_archive_dirs"] = archive_dirs
                save_settings(self.settings)
        except Exception:
            pass
        return self.get_state()

    def unmark_as_collection(self, path=None):
        target = self._collection_target(path)
        if not target:
            return {"status": "error"}
        if target["kind"] == "archive":
            sidecar = self._collection_sidecar_path(target["archive"])
            try:
                if os.path.exists(sidecar):
                    os.remove(sidecar)
            except Exception as e:
                return {"status": "error", "msg": str(e)}
            return self.get_state()
        dir_path = target["dir"]
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
        try:
            reveal_with_system(path)
            return {"status": "ok"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def open_with(self, filepath, app_path):
        import subprocess
        try:
            filepath = os.path.normpath(filepath)
            if IS_MACOS and app_path.lower().rstrip("/\\").endswith(".app"):
                subprocess.Popen(["open", "-a", app_path, filepath])
                return {"status": "ok"}
            app_dir = os.path.dirname(app_path)
            # If the directory is valid and exists, set it as the working directory
            cwd = app_dir if app_dir and os.path.exists(app_dir) else None
            subprocess.Popen([app_path, filepath], cwd=cwd)
            return {"status": "ok"}
        except Exception as e: return {"status": "error", "msg": str(e)}

    def play_online_playlist(self, tracks, start_index=0):
        # Online audio URLs often have no file extension (for example
        # /media/12345), so the main media player cannot tell they are audio.
        # Use the dedicated top audio bar instead of guessing from extensions.
        try:
            safe_tracks = [
                {
                    "name": track.get("name") or "Audio track",
                    "url": track.get("url") or "",
                }
                for track in (tracks or [])
                if track.get("url")
            ]
            if not safe_tracks:
                return {"status": "error", "msg": "This playlist has no playable tracks."}
            start_index = max(0, min(int(start_index or 0), len(safe_tracks) - 1))
            self._window.evaluate_js(
                f"playTopAudio({json.dumps(safe_tracks)}, {start_index}); null;"
            )
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def save_online_playlists(self, playlists):
        self.settings["online_playlists"] = playlists
        save_settings(self.settings)
        return self.get_state()

    def _audio_filename_from_response(self, response, url, name):
        """Choose a safe filename using Content-Disposition, URL, or MIME type."""
        import re
        import urllib.parse

        disposition = response.headers.get("content-disposition", "") or ""
        match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", disposition, re.I)
        source_name = urllib.parse.unquote(match.group(1).strip()) if match else ""
        if not source_name:
            source_name = os.path.basename(urllib.parse.urlsplit(url).path)

        _, ext = os.path.splitext(os.path.basename(source_name))
        if not ext:
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            ext = {
                "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/mpeg": ".mp3",
                "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav",
                "audio/webm": ".webm", "audio/flac": ".flac", "audio/aac": ".aac",
                "audio/opus": ".opus", "video/mp4": ".mp4",
            }.get(content_type, ".mp3")

        # Prefer the readable track title over the server's internal filename.
        stem = clean_filename(name)[:150].strip()
        if not stem or stem.lower() in ("audio", "audio track", "track", "unknown"):
            disposition_stem = os.path.splitext(os.path.basename(source_name))[0]
            stem = clean_filename(disposition_stem)[:150].strip() or "audio"
        return f"{stem}{ext.lower()}"

    def download_online_track(self, url, name, download_url=None):
        try:
            import requests
            import urllib.parse

            if not url:
                return {"status": "error", "msg": "No track URL provided."}
            download_url = (download_url or url).strip()
            name = (name or "audio").strip() or "audio"

            # Prefer the folder containing the current local media. Otherwise
            # use the remembered audio download folder, or ask once.
            active_dir = ""
            if self.playlist and 0 <= self.current_index < len(self.playlist):
                active_path = self.playlist[self.current_index]
                if not active_path.startswith(("http://", "https://")):
                    candidate = os.path.dirname(active_path)
                    if os.path.isdir(candidate):
                        active_dir = candidate
            dir_path = active_dir or self.settings.get("audio_download_dir", "")
            if not dir_path or not os.path.isdir(dir_path):
                last_dir = self.settings.get("last_opened_dir") or APP_PWD
                if not os.path.isdir(last_dir):
                    last_dir = APP_PWD
                result = self._window.create_file_dialog(
                    webview.FileDialog.FOLDER, directory=last_dir
                )
                if not result:
                    return {"status": "cancelled"}
                dir_path = result[0] if isinstance(result, (list, tuple)) else result
                dir_path = os.path.abspath(dir_path)
                self.settings["audio_download_dir"] = dir_path
                save_settings(self.settings)

            def run_download():
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "*/*",
                }
                parsed = urllib.parse.urlsplit(download_url)
                if parsed.scheme and parsed.netloc:
                    headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

                temp_path = ""
                try:
                    self.cancel_flags[name] = False
                    with requests.get(
                        download_url, headers=headers, stream=True,
                        timeout=30, allow_redirects=True,
                    ) as response:
                        if response.status_code != 200:
                            raise Exception(f"HTTP {response.status_code}")

                        content_type = (
                            response.headers.get("content-type") or ""
                        ).split(";")[0].strip().lower()
                        if content_type in ("text/html", "application/json"):
                            raise Exception(
                                "The site returned a web page instead of an audio file"
                            )

                        filename = self._audio_filename_from_response(
                            response, download_url, name
                        )
                        destination = os.path.join(dir_path, filename)
                        stem, ext = os.path.splitext(destination)
                        counter = 2
                        while os.path.exists(destination):
                            destination = f"{stem} ({counter}){ext}"
                            counter += 1
                        temp_path = destination + ".part"

                        total_size = int(response.headers.get("content-length", 0) or 0)
                        downloaded_size = 0
                        last_reported = 0
                        with open(temp_path, "wb") as out_file:
                            for chunk in response.iter_content(chunk_size=65536):
                                if self.cancel_flags.get(name):
                                    raise Exception("Cancelled by user")
                                if not chunk:
                                    continue
                                out_file.write(chunk)
                                downloaded_size += len(chunk)
                                if downloaded_size - last_reported > 250 * 1024:
                                    last_reported = downloaded_size
                                    self._window.evaluate_js(
                                        "updateAudioDownloadProgress("
                                        f"{downloaded_size}, {total_size}, "
                                        f"{json.dumps(name)})"
                                    )

                    if not temp_path or not os.path.exists(temp_path):
                        raise Exception("Download produced no file")
                    os.replace(temp_path, destination)
                    try:
                        self._log_download(name, destination, "audio")
                    except Exception:
                        pass
                    self._window.evaluate_js(
                        f"downloadCompleteNotify({json.dumps(name)})"
                    )
                    try:
                        self.load_directory(destination)
                    except Exception:
                        pass
                except Exception as error:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
                    try:
                        self._window.evaluate_js(
                            f"downloadFailedNotify({json.dumps(name)}, "
                            f"{json.dumps(str(error))})"
                        )
                    except Exception:
                        pass

            threading.Thread(target=run_download, daemon=True).start()
            return {"status": "started"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def _audio_track_title(self, soup, page_url, fallback):
        import re

        def clean(text):
            text = re.sub(r"\s+", " ", (text or "")).strip()
            text = re.sub(r"^Post\s*#\d+\s*[·\-]\s*", "", text, flags=re.I)
            text = re.sub(r"\s*[-·]\s*Liltsome\s*$", "", text, flags=re.I)
            return text.strip()

        for selector in (
            "h1.audio-player-title", "h1.post-title", "article h1",
            "main h1", "h1",
        ):
            element = soup.select_one(selector)
            if element is None:
                continue
            text = clean(element.get_text(" ", strip=True))
            if text and not re.fullmatch(r"Post\s*#\d+", text, flags=re.I):
                return text

        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            text = clean(meta["content"])
            if text:
                return text
        if soup.title and soup.title.string:
            text = clean(soup.title.string)
            if text:
                return text
        return clean(fallback) or "Audio track"

    def _audio_track_artist(self, soup):
        for selector in (
            ".audio-tile-artist", "[class*='artist']", "[rel='author']",
            "meta[name='author']",
        ):
            element = soup.select_one(selector)
            if element is None:
                continue
            value = element.get("content") if element.name == "meta" else element.get_text(" ", strip=True)
            value = re.sub(r"^(?:by|artist)\s*[:\-]?\s*", "", (value or "").strip(), flags=re.I)
            value = value.strip()
            if value and len(value) <= 120:
                return value
        return ""

    def _audio_tracks_from_page(self, soup, page_url, fallback_name):
        import re
        import urllib.parse

        media_urls = []
        labels = {}

        def add_media(source, label=""):
            if not source:
                return
            source = source.strip()
            if source.startswith(("data:", "blob:", "javascript:", "#")):
                return
            abs_url = urllib.parse.urljoin(page_url, source)
            media_urls.append(abs_url)
            label = (label or "").strip()
            if label:
                labels.setdefault(abs_url, label)

        for audio in soup.find_all("audio"):
            label = audio.get("title") or audio.get("aria-label") or ""
            label = re.sub(r"^Play\s+", "", label, flags=re.I).strip()
            if label.lower() in ("play", "audio", "audio player"):
                label = ""
            if audio.get("src"):
                add_media(audio["src"], label)
            for source in audio.find_all("source", src=True):
                add_media(source["src"], label)
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            if prop in ("og:audio", "og:audio:url", "twitter:player:stream"):
                add_media(meta.get("content"))
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            ext = os.path.splitext(urllib.parse.urlsplit(href).path)[1].lower()
            if ext in AUDIO_BUNDLE_EXTS:
                label = anchor.get_text(" ", strip=True)
                if not label:
                    label = urllib.parse.unquote(
                        os.path.basename(urllib.parse.urlsplit(href).path)
                    )
                add_media(href, label)

        download_url = ""
        for anchor in soup.find_all("a", href=True):
            text = anchor.get_text(" ", strip=True).lower()
            href = anchor["href"]
            if href.lower().startswith(("javascript:", "#")):
                continue
            if "download" in text or re.search(r"/download(?:[/?#]|$)", href, re.I):
                download_url = urllib.parse.urljoin(page_url, href)
                break

        title = self._audio_track_title(soup, page_url, fallback_name)
        artist = self._audio_track_artist(soup)
        tracks = []
        seen = set()
        for index, media_url in enumerate(media_urls):
            if media_url in seen:
                continue
            seen.add(media_url)
            specific_label = labels.get(media_url, "")
            if specific_label:
                name = specific_label
            else:
                name = title
                if len(media_urls) > 1:
                    name = f"{title} ({index + 1})"
            if artist and artist.lower() not in name.lower():
                name = f"{artist} - {name}"
            tracks.append({
                "name": name,
                "url": media_url,
                "download_url": download_url or media_url,
                "source_url": page_url,
                "artist": artist,
            })
        return tracks

    def _audio_detail_links(self, soup, base_url, limit=30):
        import urllib.parse

        base_host = urllib.parse.urlsplit(base_url).netloc.lower()
        links = []
        seen = set()

        def add(href):
            if not href or href.startswith(("javascript:", "#", "mailto:")):
                return False
            abs_url = urllib.parse.urljoin(base_url, href)
            parts = urllib.parse.urlsplit(abs_url)
            if parts.scheme not in ("http", "https"):
                return False
            if parts.netloc.lower() != base_host:
                return False
            path = parts.path.lower()
            if any(path.startswith(prefix) for prefix in (
                "/login", "/register", "/tags", "/users", "/preferences",
                "/news", "/support", "/search-help", "/filters", "/blacklist",
            )):
                return False
            normalized = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, parts.path, parts.query, "")
            )
            if normalized in seen:
                return False
            seen.add(normalized)
            links.append(abs_url)
            return True

        selectors = (
            "a.post-card-link[href]",
            "a[href*='/post/']",
            "a[href*='/posts/']",
            "a[href*='/track/']",
            "a[href*='/audio/']",
            "a[href*='/episode/']",
            "a[href*='/view/']",
        )
        for selector in selectors:
            for anchor in soup.select(selector):
                add(anchor.get("href"))
                if len(links) >= limit:
                    return links[:limit]

        if len(links) < limit:
            for anchor in soup.find_all("a", href=True):
                classes = " ".join(anchor.get("class") or []).lower()
                if any(token in classes for token in (
                    "post-card-link", "card-link", "title-link", "thumb-link",
                )):
                    add(anchor.get("href"))
                    if len(links) >= limit:
                        break
        return links[:limit]

    def scrape_audio_links(self, url):
        try:
            import requests
            from bs4 import BeautifulSoup
            import urllib.parse

            url = (url or "").strip()
            if not url:
                return {"status": "error", "msg": "No audio site URL provided."}
            if "://" not in url:
                url = "https://" + url

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            response = None
            try:
                import cloudscraper
                response = cloudscraper.create_scraper().get(
                    url, headers=headers, timeout=20
                )
            except Exception:
                response = None
            if response is None or response.status_code != 200:
                try:
                    response = requests.get(url, headers=headers, timeout=20)
                except Exception as error:
                    return {"status": "error", "msg": f"Could not load audio site: {error}"}
            if response.status_code != 200:
                return {
                    "status": "error",
                    "msg": f"Failed to load page: HTTP {response.status_code}",
                }

            soup = BeautifulSoup(response.text, "html.parser")
            tracks = self._audio_tracks_from_page(soup, url, "Audio track")

            # Directory-style audio sites often put the actual player on a
            # detail/post page rather than the listing page.
            if not tracks:
                detail_links = self._audio_detail_links(soup, url)
                if detail_links:
                    from concurrent.futures import ThreadPoolExecutor

                    def fetch_detail(link):
                        try:
                            detail = requests.get(
                                link, headers=headers, timeout=15,
                                allow_redirects=True,
                            )
                            if detail.status_code == 200:
                                return link, BeautifulSoup(detail.text, "html.parser")
                        except Exception:
                            pass
                        return link, None

                    with ThreadPoolExecutor(max_workers=8) as pool:
                        for link, detail_soup in pool.map(fetch_detail, detail_links):
                            if detail_soup is None:
                                continue
                            fallback = urllib.parse.unquote(
                                os.path.basename(urllib.parse.urlsplit(link).path)
                            ) or "Audio track"
                            tracks.extend(
                                self._audio_tracks_from_page(
                                    detail_soup, link, fallback
                                )
                            )

            seen = set()
            unique_tracks = []
            for track in tracks:
                media_url = track.get("url")
                if not media_url or media_url in seen:
                    continue
                seen.add(media_url)
                unique_tracks.append(track)
            return {"status": "success", "tracks": unique_tracks}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    @staticmethod
    def _audio_search_url(url, query):
        import urllib.parse

        parts = urllib.parse.urlsplit(url)
        pairs = [
            (key, value) for key, value in
            urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in ("q", "query", "search", "keywords", "term")
        ]
        pairs.append(("q", query))
        return urllib.parse.urlunsplit((
            parts.scheme, parts.netloc, parts.path,
            urllib.parse.urlencode(pairs), parts.fragment,
        ))

    def search_audio_site(self, url, query):
        try:
            import urllib.parse

            query = (query or "").strip()
            if not query:
                return self.scrape_audio_links(url)

            base = (url or "").strip()
            if not base:
                return {"status": "error", "msg": "No audio site URL provided."}
            if "://" not in base:
                base = "https://" + base
            parsed_base = urllib.parse.urlsplit(base)

            configured_search = ""
            for site in self.settings.get("audio_sites", []) or []:
                domain = (site.get("domain") or "").strip()
                if not domain:
                    continue
                if "://" not in domain:
                    domain = "https://" + domain
                if urllib.parse.urlsplit(domain).netloc.lower() != parsed_base.netloc.lower():
                    continue
                notes = (site.get("notes") or "").strip()
                if notes.startswith("{") and notes.endswith("}"):
                    try:
                        config = json.loads(notes)
                        configured_search = (config.get("search_url") or "").strip()
                    except Exception:
                        pass
                break

            if configured_search:
                if "{query}" in configured_search:
                    search_url = configured_search.replace(
                        "{query}", urllib.parse.quote(query, safe="")
                    )
                else:
                    search_url = self._audio_search_url(configured_search, query)
            else:
                search_url = self._audio_search_url(base, query)

            result = self.scrape_audio_links(search_url)
            if isinstance(result, dict):
                result["search_url"] = search_url
                result["query"] = query
            return result
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

    def _search_nifty(self, query, config):
        try:
            import re
            import requests
            import urllib.parse
            from bs4 import BeautifulSoup

            listing_url = (
                config.get("search_url") or "https://www.nifty.org/nifty/"
            ).strip()
            if "nifty.org" not in listing_url:
                listing_url = "https://www.nifty.org/nifty/"
            if not listing_url.endswith("/"):
                listing_url += "/"

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            response = None
            try:
                import cloudscraper
                response = cloudscraper.create_scraper().get(
                    listing_url, headers=headers, timeout=20
                )
            except Exception:
                response = None
            if response is None or response.status_code != 200:
                response = requests.get(listing_url, headers=headers, timeout=20)
            if response.status_code != 200:
                return {
                    "status": "error",
                    "msg": f"Nifty returned HTTP {response.status_code}.",
                }

            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table")
            if table is None:
                return {
                    "status": "error",
                    "msg": "Could not find the Nifty story listing.",
                }

            results = []
            seen = set()
            for row in table.find_all("tr")[1:]:
                anchor = row.find("a", href=True)
                if anchor is None:
                    continue
                href = anchor["href"].strip()
                label = anchor.get_text(" ", strip=True).strip()
                if not href or href.startswith(("#", "mailto:", "javascript:")):
                    continue
                if label.endswith("/") or href.split("?")[0].endswith("/"):
                    continue
                cells = [
                    cell.get_text(" ", strip=True) for cell in row.find_all("td")
                ]
                if cells and cells[0].lower() == "dir":
                    continue
                full_url = urllib.parse.urljoin(listing_url, href)
                if full_url in seen:
                    continue
                seen.add(full_url)

                display = urllib.parse.unquote(label)
                display = display.replace("-", " ").replace("_", " ").strip()
                display = re.sub(r"\s+", " ", display)
                display = " ".join(word.capitalize() for word in display.split())
                if not display:
                    display = os.path.basename(
                        urllib.parse.urlsplit(full_url).path
                    ) or "Nifty story"
                summary = f"{cells[0]} · {cells[1]}" if len(cells) >= 3 else ""
                results.append({
                    "title": display,
                    "author": "",
                    "summary": summary,
                    "url": full_url,
                })

            query_norm = (query or "").strip().lower()
            if query_norm:
                matches = [
                    item for item in results
                    if all(
                        token in item["title"].lower()
                        for token in query_norm.split()
                    )
                ]
                if matches:
                    results = matches
            return {"status": "success", "results": results[:100]}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def search_online_stories(self, source_id, query):
        # Find the site config from settings. save_online_sources() updates both
        # settings and MAINLIST.json, but in a frozen build __file__ points at
        # the bundled copy, so settings is the reliable source at runtime.
        all_sites = self.settings.get("story_sites") or []
        if not all_sites:
            try:
                src_path = find_app_data_file('MAINLIST.json')
                if src_path:
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

        site_id = (site_config.get('id') or '').lower()
        site_domain = (site_config.get('domain') or '').lower()
        site_name = (site_config.get('name') or '').lower()
        if site_id == 'nifty' or 'nifty.org' in site_domain or 'nifty' in site_name:
            return self._search_nifty(query, search_config)

        if parser_type == 'ao3':
            return self._search_ao3(query)
        elif parser_type == 'generic_html':
            return self._search_generic_html(query, search_config)
        
        return {"status": "error", "msg": "Search not configured for this source. Edit its 'notes' in MAINLIST.json."}

    def _story_page_title(self, soup):
        import re

        def clean(text):
            text = re.sub(r"\s+", " ", (text or "")).strip()
            text = re.sub(r"\s*\|\s*Archive of Our Own\s*$", "", text, flags=re.I)
            return text

        def acceptable(text):
            low = text.lower().strip()
            if len(low) < 2:
                return False
            if low in ("stories", "story", "online stories", "home", "index"):
                return False
            if re.fullmatch(r"[a-z0-9.-]+\.(com|org|net|info|us|co\.uk|io)", low):
                return False
            return True

        for selector in (
            'meta[property="og:title"]',
            "h1.story-title", "h1.title", "h2.story-title", "h2.title",
            ".story-title", "h1", "h2",
        ):
            element = soup.select_one(selector)
            if element is None:
                continue
            text = element.get("content") if element.name == "meta" else element.get_text(" ", strip=True)
            text = clean(text)
            if acceptable(text):
                return text
        return ""

    def _story_page_author(self, soup):
        import re

        for selector in (
            'meta[name="author"]',
            'a[rel="author"]',
            "h3.byline a", "h3.byline", ".byline a", ".byline",
            '[class*="author"]',
        ):
            element = soup.select_one(selector)
            if element is None:
                continue
            text = element.get("content") if element.name == "meta" else element.get_text(" ", strip=True)
            text = re.sub(r"^(?:by|author)\s*[:\-]?\s*", "", (text or "").strip(), flags=re.I)
            text = re.sub(r"\s+", " ", text).strip()
            if text and len(text) <= 120:
                return text
        return ""

    def _extract_story_paragraphs(self, soup):
        import re

        selectors = (
            "#chapters .userstuff", "div.chapter .userstuff", ".userstuff",
            ".story_center_panel", ".block_panel", ".storytext", "#storytext",
            ".story-text", ".story-body", ".storybody", ".chapter-content",
            ".chapterText", ".entry-content", ".post-content",
            ".reading-content", ".text-content", "article", "main",
            "#content", ".content", "pre",
        )
        candidates = []
        seen_nodes = set()
        for selector in selectors:
            for node in soup.select(selector):
                if id(node) in seen_nodes:
                    continue
                seen_nodes.add(id(node))
                candidates.append(node)
        if not candidates and soup.body:
            candidates.append(soup.body)
        if not candidates:
            return []

        def score(node):
            text = node.get_text(" ", strip=True)
            classes = (
                " ".join(node.get("class") or []) + " " + (node.get("id") or "")
            ).lower()
            bonus = 0
            if any(word in classes for word in ("story", "chapter", "text", "read", "content")):
                bonus += 600
            for bad in (
                "nav", "menu", "comment", "footer", "sidebar", "header",
                "share", "related", "breadcrumb",
            ):
                if bad in classes:
                    bonus -= 2000
            return len(text) + len(node.find_all("p")) * 80 + bonus

        best = max(candidates, key=score)
        if score(best) <= 0 and soup.body:
            best = soup.body

        chapter_nodes = soup.select("#chapters .userstuff, div.chapter .userstuff")
        nodes = chapter_nodes if len(chapter_nodes) > 1 else [best]

        paragraphs = []
        seen_text = set()
        total_chars = 0

        def add(kind, text):
            nonlocal total_chars
            text = re.sub(r"[ \t]+", " ", (text or "")).strip()
            if len(text) < 2 or text in seen_text:
                return
            seen_text.add(text)
            paragraphs.append({"type": kind, "text": text})
            total_chars += len(text)

        for node in nodes:
            blocks = node.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre"])
            if blocks:
                for block in blocks:
                    if block.name == "pre":
                        text = block.get_text("\n", strip=True)
                    else:
                        text = block.get_text(" ", strip=True)
                    if not text:
                        continue
                    if block.name in ("h1", "h2", "h3", "h4"):
                        add(block.name, text)
                    elif block.name == "li":
                        add("li", "• " + text)
                    elif block.name == "blockquote":
                        add("blockquote", text)
                    else:
                        add("p", text)
                    if total_chars > 400000:
                        break
            else:
                raw = node.get_text("\n", strip=True)
                for chunk in re.split(r"\n+", raw):
                    add("p", chunk)
                    if total_chars > 400000:
                        break
            if total_chars > 400000:
                break

        if len(paragraphs) == 1 and len(paragraphs[0]["text"]) > 1200:
            raw = paragraphs[0]["text"]
            paragraphs = []
            seen_text.clear()
            total_chars = 0
            for chunk in re.split(r"(?<=[.!?])\s+", raw):
                add("p", chunk)

        # Strip rating/vote/comment/footer boilerplate that some story sites
        # place inside the same container as the story text.
        stop_pattern = re.compile(
            r"^(?:vote list|please login or register|rated$|\d+\s*votes?$|"
            r"times\s*\|$|copyright|back to|do you write|submit a text|"
            r"contact us|bookmark|set us as your homepage|visit xnxx)", re.I
        )
        cut_at = len(paragraphs)
        for index, paragraph in enumerate(paragraphs):
            text = paragraph["text"].strip()
            if stop_pattern.match(text):
                cut_at = index
                break
            if re.fullmatch(r"\d{2,}", text):
                nearby = " ".join(
                    item["text"] for item in paragraphs[index:index + 4]
                ).lower()
                if "times" in nearby or "rated" in nearby or "votes" in nearby:
                    cut_at = index
                    break
        paragraphs = paragraphs[:cut_at]

        leading_noise = re.compile(
            r"^(?:all chars are 18|do you write|back to|visit xnxx|bookmark|"
            r"set us as your homepage|submit a text|contact us|copyright)", re.I
        )
        while paragraphs and leading_noise.match(paragraphs[0]["text"].strip()):
            paragraphs.pop(0)
        trailing_noise = re.compile(
            r"^(?:read|next|previous|prev|back|home|comments?|share|report|"
            r"favorite|favourite|rate|vote)$", re.I
        )
        while paragraphs and trailing_noise.match(paragraphs[-1]["text"].strip()):
            paragraphs.pop()
        while paragraphs and re.fullmatch(r"[\d\s|%]+", paragraphs[-1]["text"].strip()):
            paragraphs.pop()
        return paragraphs

    def _parse_plain_story(self, text, url):
        import re

        raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = raw.split("\n")

        subject = ""
        body_start = 0
        for index, line in enumerate(lines[:40]):
            stripped = line.strip()
            if not stripped:
                body_start = index + 1
                break
            match = re.match(r"^Subject:\s*(.+)$", stripped, re.I)
            if match:
                subject = match.group(1).strip()

        body_lines = lines[body_start:]
        title = ""
        if subject:
            title = re.sub(r"\s*\([^)]*\)\s*$", "", subject).strip()

        author = ""
        title_index = None
        author_index = None
        if title:
            for index, line in enumerate(body_lines):
                if line.strip().lower() == title.lower():
                    title_index = index
                    break
        for index, line in enumerate(body_lines):
            match = re.match(r"^\s*By\s+(.+?)\s*$", line, re.I)
            if match and (title_index is None or index >= title_index):
                author = match.group(1).strip()
                author_index = index
                break

        if title_index is not None:
            start = title_index + 1
            if author_index is not None and author_index >= start:
                start = author_index + 1
            while start < len(body_lines) and not body_lines[start].strip():
                start += 1
            if start < len(body_lines):
                match = re.match(r"^\s*By\s+(.+?)\s*$", body_lines[start], re.I)
                if match:
                    author = match.group(1).strip()
                    start += 1
        elif author_index is not None:
            start = author_index + 1
        else:
            start = 0
            noise_start = re.compile(
                r"^(?:date|from|subject|this story is a work of fiction|"
                r"if this type of content|note:|remember to donate|"
                r"please donate|donate\.nifty\.org|https?://|nifty\.org)",
                re.I,
            )
            while start < len(body_lines):
                stripped = body_lines[start].strip()
                if not stripped or noise_start.match(stripped):
                    start += 1
                    continue
                break

        content = "\n".join(body_lines[start:])
        noise = re.compile(
            r"donate\.nifty\.org|Remember to donate|"
            r"This story is a work of fiction|"
            r"If this type of content offends|Please donate|Nifty\.org",
            re.I,
        )
        paragraphs = []
        for block in re.split(r"\n\s*\n", content):
            paragraph = " ".join(
                line.strip() for line in block.splitlines() if line.strip()
            )
            paragraph = re.sub(r"\s+", " ", paragraph).strip()
            if not paragraph or noise.search(paragraph):
                continue
            paragraphs.append({"type": "p", "text": paragraph})

        if len(paragraphs) <= 1 and content.strip():
            paragraphs = []
            for line in content.splitlines():
                paragraph = line.strip()
                if paragraph and not noise.search(paragraph):
                    paragraphs.append({"type": "p", "text": paragraph})

        if not title:
            title = "Nifty Story"
        return {
            "title": title,
            "author": author,
            "paragraphs": paragraphs,
            "text": "\n\n".join(p["text"] for p in paragraphs)[:400000],
            "word_count": sum(len(p["text"].split()) for p in paragraphs),
        }

    def fetch_story_content(self, url):
        try:
            import re
            import requests
            import urllib.parse
            from bs4 import BeautifulSoup

            url = (url or "").strip()
            if not url:
                return {"status": "error", "msg": "No story URL provided."}
            if "://" not in url:
                url = "https://" + url

            fetch_url = url
            if "archiveofourown.org/works/" in url and "view_full_work" not in url:
                fetch_url = url + ("&" if "?" in url else "?") + "view_full_work=true"

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            response = None
            try:
                import cloudscraper
                response = cloudscraper.create_scraper().get(
                    fetch_url, headers=headers, timeout=20
                )
            except Exception:
                response = None
            if response is None or response.status_code != 200:
                try:
                    response = requests.get(fetch_url, headers=headers, timeout=20)
                except Exception as error:
                    return {
                        "status": "error",
                        "msg": f"Could not load the story: {error}",
                    }
            if response.status_code != 200:
                return {
                    "status": "error",
                    "msg": f"The story site returned HTTP {response.status_code}.",
                }

            content_type = (response.headers.get("content-type") or "").lower()
            raw_text = response.text or ""
            if content_type.startswith("text/plain") or raw_text.lstrip().startswith(
                ("Date:", "From:", "Subject:")
            ):
                plain = self._parse_plain_story(raw_text, url)
                if plain and plain.get("paragraphs"):
                    return {
                        "status": "success",
                        "url": url,
                        "fetch_url": fetch_url,
                        **plain,
                    }

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup([
                "script", "style", "noscript", "svg", "nav", "header",
                "footer", "aside", "form", "iframe", "button", "input",
                "select", "textarea",
            ]):
                tag.decompose()

            title = self._story_page_title(soup)
            author = self._story_page_author(soup)
            if title and not author and "sexstories.com" in url:
                match = re.match(r"^(.*?)\s+by\s+(.+)$", title, flags=re.I)
                if match:
                    title = match.group(1).strip()
                    author = match.group(2).strip()

            paragraphs = self._extract_story_paragraphs(soup)
            if not paragraphs:
                return {
                    "status": "error",
                    "msg": (
                        "Could not find readable story text on that page. "
                        "Open it in your browser instead."
                    ),
                }

            text = "\n\n".join(paragraph["text"] for paragraph in paragraphs)
            return {
                "status": "success",
                "url": url,
                "fetch_url": fetch_url,
                "title": title,
                "author": author,
                "paragraphs": paragraphs,
                "text": text[:400000],
                "word_count": len(text.split()),
            }
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def _tts_cache_dir(self):
        cache = os.path.join(APP_PWD, ".tts_cache")
        try:
            os.makedirs(cache, exist_ok=True)
            return cache
        except OSError:
            fallback = os.path.join(tempfile.gettempdir(), "XenoPlayer_tts_cache")
            os.makedirs(fallback, exist_ok=True)
            return fallback

    def _prune_tts_cache(self, keep_path=None):
        cache = self._tts_cache_dir()
        max_bytes = 300 * 1024 ** 2
        now = time.time()
        entries = []
        total = 0
        try:
            names = os.listdir(cache)
        except OSError:
            return
        for name in names:
            path = os.path.join(cache, name)
            if not os.path.isfile(path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            if name.endswith(".part"):
                if now - stat.st_mtime > 3600:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                continue
            if not name.lower().endswith(".mp3"):
                continue
            if now - stat.st_mtime > 30 * 86400:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            entries.append((stat.st_mtime, path))
            total += stat.st_size
        if total <= max_bytes:
            return
        entries.sort(key=lambda row: row[0])
        for _mtime, path in entries:
            if total <= max_bytes:
                break
            if keep_path and os.path.normpath(path) == os.path.normpath(keep_path):
                continue
            try:
                size = os.path.getsize(path)
                os.remove(path)
                total -= size
            except OSError:
                pass

    def edge_tts_voices(self):
        try:
            import edge_tts  # noqa: F401
        except Exception:
            return {
                "status": "unavailable",
                "voices": [],
                "msg": (
                    "edge-tts is not installed. Install it with: "
                    "pip install edge-tts"
                ),
            }
        voices = [
            {"id": "en-US-AriaNeural", "name": "Aria — US female"},
            {"id": "en-US-JennyNeural", "name": "Jenny — US female"},
            {"id": "en-US-MichelleNeural", "name": "Michelle — US female"},
            {"id": "en-US-GuyNeural", "name": "Guy — US male"},
            {"id": "en-US-AndrewNeural", "name": "Andrew — US male"},
            {"id": "en-US-BrianNeural", "name": "Brian — US male"},
            {"id": "en-US-ChristopherNeural", "name": "Christopher — US male"},
            {"id": "en-GB-SoniaNeural", "name": "Sonia — UK female"},
            {"id": "en-GB-RyanNeural", "name": "Ryan — UK male"},
            {"id": "en-AU-NatashaNeural", "name": "Natasha — AU female"},
            {"id": "en-AU-WilliamMultilingualNeural", "name": "William — AU male"},
            {"id": "en-CA-ClaraNeural", "name": "Clara — CA female"},
            {"id": "en-CA-LiamNeural", "name": "Liam — CA male"},
            {"id": "en-IE-EmilyNeural", "name": "Emily — IE female"},
            {"id": "en-IE-ConnorNeural", "name": "Connor — IE male"},
            {"id": "en-IN-NeerjaNeural", "name": "Neerja — IN female"},
            {"id": "en-IN-PrabhatNeural", "name": "Prabhat — IN male"},
            {"id": "en-NZ-MollyNeural", "name": "Molly — NZ female"},
            {"id": "en-NZ-MitchellNeural", "name": "Mitchell — NZ male"},
        ]
        return {"status": "success", "voices": voices, "default": "en-US-AriaNeural"}

    def edge_tts_generate(self, text, voice="en-US-AriaNeural", rate=1.0):
        try:
            import asyncio
            import hashlib

            text = (text or "").strip()
            if not text:
                return {"status": "error", "msg": "No text to speak."}
            if len(text) > 6000:
                text = text[:6000]
            try:
                import edge_tts
            except Exception:
                return {
                    "status": "unavailable",
                    "msg": (
                        "edge-tts is not installed. Install it with: "
                        "pip install edge-tts"
                    ),
                }
            voice = (voice or "en-US-AriaNeural").strip()
            try:
                rate_value = float(rate)
            except (TypeError, ValueError):
                rate_value = 1.0
            rate_value = max(0.5, min(2.0, rate_value))
            rate_percent = max(
                -50, min(100, int(round((rate_value - 1.0) * 100)))
            )
            rate_text = f"{rate_percent:+d}%"

            cache_dir = self._tts_cache_dir()
            key = hashlib.sha256(
                f"{voice}|{rate_text}|{text}".encode("utf-8")
            ).hexdigest()[:32]
            cache_path = os.path.join(cache_dir, f"{key}.mp3")
            if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 1000:
                return {
                    "status": "success",
                    "path": cache_path,
                    "voice": voice,
                    "rate": rate_text,
                    "cached": True,
                }

            temp_path = cache_path + ".part"

            async def generate():
                communicate = edge_tts.Communicate(text, voice, rate=rate_text)
                await communicate.save(temp_path)

            try:
                try:
                    asyncio.run(generate())
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(generate())
                    finally:
                        loop.close()
                if not os.path.exists(temp_path) or os.path.getsize(temp_path) < 1000:
                    raise RuntimeError("Edge TTS returned no audio.")
                os.replace(temp_path, cache_path)
                self._prune_tts_cache(keep_path=cache_path)
                return {
                    "status": "success",
                    "path": cache_path,
                    "voice": voice,
                    "rate": rate_text,
                }
            except Exception as error:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                return {"status": "error", "msg": f"Edge TTS failed: {error}"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def save_story_tts_settings(self, engine, voice, rate):
        self.settings["story_tts_engine"] = (
            "edge" if (engine or "").lower() == "edge" else "system"
        )
        self.settings["story_tts_voice"] = (
            voice or "en-US-AriaNeural"
        ).strip()
        try:
            self.settings["story_tts_rate"] = max(0.5, min(2.0, float(rate)))
        except (TypeError, ValueError):
            self.settings["story_tts_rate"] = 1.0
        save_settings(self.settings)
        return {
            "status": "success",
            "engine": self.settings["story_tts_engine"],
            "voice": self.settings["story_tts_voice"],
            "rate": self.settings["story_tts_rate"],
        }

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
            
            search_url = search_url_template.replace('{query}', urllib.parse.quote(query, safe=''))
            
            scraper = cloudscraper.create_scraper()
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
            response = scraper.get(search_url, timeout=20, headers=headers)
            if response.status_code == 202:
                return {
                    "status": "error",
                    "msg": (
                        "That site returned a bot-check page (HTTP 202) instead of "
                        "results. Try again later, or open this source in your browser."
                    ),
                }
            if response.status_code != 200:
                return {"status": "error", "msg": f"Site returned HTTP {response.status_code}."}

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            results_selector = config.get('results_selector')
            if not results_selector:
                return {"status": "error", "msg": "results_selector not defined in site configuration."}
            try:
                candidate_items = soup.select(results_selector)
            except Exception as selector_error:
                return {
                    "status": "error",
                    "msg": f"Invalid results selector '{results_selector}': {selector_error}",
                }

            def pick(item, selector):
                if not selector:
                    return None
                try:
                    return item.select_one(selector)
                except Exception:
                    return None

            for item in candidate_items:
                title_el = pick(item, config.get('title_selector'))
                title = title_el.get_text(" ", strip=True) if title_el else ""
                if not title and title_el is not None:
                    title = (title_el.get("aria-label") or "").strip()
                    if not title:
                        image = title_el.find("img")
                        if image is not None:
                            title = (image.get("alt") or "").strip()
                author_el = pick(item, config.get('author_selector'))
                author = author_el.get_text(" ", strip=True) if author_el else ""
                summary_el = pick(item, config.get('summary_selector'))
                summary = summary_el.get_text(" ", strip=True) if summary_el else ""

                url_el = pick(item, config.get('url_selector')) or item
                url = url_el['href'] if url_el and url_el.has_attr('href') else ""

                if not title and url_el:
                    title = url_el.get_text(" ", strip=True)

                if not title or not url:
                    continue

                base_url = config.get('base_url', '')
                full_url = urllib.parse.urljoin(search_url, url)

                thumb_el = pick(item, config.get('thumb_selector')) or item.find("img")
                thumb = ""
                if thumb_el:
                    thumb = thumb_el.get('src') or thumb_el.get('data-src') or thumb_el.get('data-original') or ""
                    if thumb:
                        thumb = urllib.parse.urljoin(search_url, thumb)

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

    # --- Site config guessing -------------------------------------------------
    # The guesser looks for a group of sibling cards that each contain a link.
    # That is far more reliable than grouping by child-tag signatures, which
    # happily selects SVG <defs> blocks or navigation wrappers.

    _GUESS_BAD_TAGS = {
        "script", "style", "noscript", "svg", "head", "meta", "link",
        "template", "iframe", "canvas", "object", "embed",
    }
    _GUESS_BAD_CONTEXT = {"nav", "header", "footer", "aside", "form"}
    _GUESS_RESULT_WORDS = (
        "result", "search", "item", "card", "entry", "post", "work", "book",
        "story", "gallery", "manga", "comic", "album", "track", "song", "video",
        "product", "listing", "grid", "thumb", "media", "chapter", "title",
    )
    _GUESS_BAD_WORDS = (
        "nav", "menu", "breadcrumb", "pagination", "pager", "sidebar", "footer",
        "header", "advert", "promo", "banner", "filter", "sort", "tab", "modal",
        "tag", "genre", "toolbar", "cookie",
    )
    _GUESS_SEARCH_KEYS = (
        "q", "query", "query_string", "search", "search_query", "searchquery",
        "search_term", "searchterm", "keyword", "keywords", "k", "term", "terms",
        "text", "f_search", "quicksearch", "title", "name",
    )
    _GUESS_AI_CHALLENGE_MARKERS = (
        "cf-browser-verification", "cf-chl", "challenge-platform",
        "just a moment...", "checking your browser before accessing",
        "attention required! | cloudflare", "ddos protection by",
        "px-captcha", "captcha-delivery", "please turn javascript on",
    )

    @staticmethod
    def _guess_is_within(element, ancestor):
        node = element
        while node is not None:
            if node is ancestor:
                return True
            node = node.parent
        return False

    @classmethod
    def _guess_has_bad_ancestor(cls, element):
        node = element.parent
        while node is not None and getattr(node, "name", None):
            if node.name in cls._GUESS_BAD_CONTEXT:
                return True
            node = node.parent
        return False

    @classmethod
    def _guess_class_token(cls, element):
        """Pick the most descriptive, CSS-safe class on an element."""
        import re
        classes = [
            name for name in (element.get("class") or [])
            if re.fullmatch(r"[A-Za-z_][\w-]*", name)
        ]
        if not classes:
            return ""
        ranked = []
        good_words = {
            "title", "name", "cover", "caption", "author", "artist", "summary",
            "desc", "thumb", "image", "result", "item", "card", "track",
            "album", "story", "book", "work", "entry", "post", "song", "video",
        }
        for index, name in enumerate(classes):
            low = name.lower()
            score = 0.0
            if good_words & set(re.split(r"[-_]+", low)):
                score += 20
            score += min(len(name), 24) / 10.0
            if re.fullmatch(r"[a-f0-9]{6,}", low) or re.search(r"\d{4,}", low):
                score -= 30
            if low.startswith(("svelte-", "css-", "sc-", "jsx-")):
                score -= 30
            ranked.append((score, -index, name))
        ranked.sort(reverse=True)
        return ranked[0][2]

    @classmethod
    def _guess_step_selector(cls, element):
        from soupsieve import escape
        token = cls._guess_class_token(element)
        if token:
            return f"{element.name}.{escape(token)}"
        parent = element.parent
        if parent is not None:
            siblings = [
                child for child in parent.find_all(recursive=False)
                if getattr(child, "name", None) == element.name
            ]
            if element in siblings:
                return f"{element.name}:nth-of-type({siblings.index(element) + 1})"
        return element.name

    @classmethod
    def _guess_selector_within(cls, element, item):
        """Build a selector for `element` that is relative to `item`."""
        if element is None or item is None:
            return ""
        from soupsieve import escape
        parts = []
        node = element
        guard = 0
        while node is not None and node is not item and getattr(node, "name", None) and guard < 10:
            parts.append(cls._guess_step_selector(node))
            node = node.parent
            guard += 1
        if node is not item:
            return ""
        selector = " > ".join(reversed(parts))
        try:
            if item.select_one(selector) is element:
                return selector
        except Exception:
            pass
        token = cls._guess_class_token(element)
        candidates = ([f"{element.name}.{escape(token)}"] if token else []) + [element.name]
        for candidate in candidates:
            try:
                if item.select_one(candidate) is element:
                    return candidate
            except Exception:
                continue
        return ""

    @classmethod
    def _score_guess_group(cls, items, kind):
        count = len(items)
        links = 0
        images = 0
        good_text = 0
        total_text = 0
        unique_hrefs = set()
        for item in items:
            anchors = [
                anchor for anchor in item.find_all("a", href=True)
                if anchor.get("href") and not anchor["href"].startswith(("javascript:", "#", "mailto:"))
            ]
            if anchors:
                links += 1
                unique_hrefs.add(anchors[0]["href"])
            if item.find("img"):
                images += 1
            text = item.get_text(" ", strip=True)
            length = len(text)
            if 8 <= length <= 1200:
                good_text += 1
            total_text += min(length, 400)
        if links < count * 0.6 or len(unique_hrefs) < 2:
            return None

        # Reject link farms that point at taxonomy pages (genres, tags,
        # categories) rather than individual result items.
        import urllib.parse
        taxonomy_prefixes = (
            "/genre", "/genres", "/tag", "/tags", "/category", "/categories",
            "/browse", "/search", "/login", "/signup", "/register", "/about",
            "/help", "/privacy", "/terms", "/settings", "/account",
        )
        sampled = 0
        taxonomy_links = 0
        for item in items:
            anchor = item.find("a", href=True)
            if not anchor or not anchor.get("href"):
                continue
            sampled += 1
            path = urllib.parse.urlsplit(anchor["href"]).path.lower()
            if path.startswith(taxonomy_prefixes):
                taxonomy_links += 1
        if sampled and taxonomy_links / sampled >= 0.7:
            return None

        attrs = " ".join(
            " ".join(item.get("class") or []) for item in items[:3]
        ).lower()
        attrs += " " + (items[0].get("id") or "").lower()
        bonus = 0
        if any(word in attrs for word in cls._GUESS_RESULT_WORDS):
            bonus += 6
        if any(word in attrs for word in cls._GUESS_BAD_WORDS):
            bonus -= 14

        score = (
            count * 2
            + links * 2
            + images * 1.5
            + good_text * 2
            + min(total_text / 20.0, 80)
            + bonus
        )
        average_text = total_text / max(1, count)
        if average_text > 600:
            score -= (average_text - 600) / 10.0
        if kind == "collection":
            score += images * 1.5
        elif kind == "audio":
            score += sum(1 for item in items if item.find(["audio", "video"])) * 3
        else:
            score += good_text * 1.5
        return score

    @classmethod
    def _guess_results_selector(cls, soup, parent, items, token):
        from soupsieve import escape

        candidates = []
        if token:
            candidates.append(f"{items[0].name}.{escape(token)}")
        parent_step = cls._guess_step_selector(parent)
        candidates.append(f"{parent_step} > {items[0].name}")
        candidates.append(items[0].name)

        threshold = max(3, int(len(items) * 0.6))
        best = None
        for selector in candidates:
            try:
                matched = soup.select(selector)
            except Exception:
                continue
            if len(matched) < threshold:
                continue
            distance = abs(len(matched) - len(items))
            if best is None or distance < best[0]:
                best = (distance, selector)
        if best:
            return best[1]
        return candidates[0]

    @classmethod
    def _guess_title_element(cls, item):
        anchors = [
            anchor for anchor in item.find_all("a", href=True)
            if anchor.get("href") and not anchor["href"].startswith(("javascript:", "#", "mailto:"))
        ]
        if not anchors:
            return None

        def score(anchor):
            text = anchor.get_text(" ", strip=True)
            value = min(len(text), 120)
            attrs_parts = list(anchor.get("class") or [])
            attrs_parts.append(anchor.get("id") or "")
            for ancestor in list(anchor.parents)[:2]:
                attrs_parts.extend(ancestor.get("class") or [])
                attrs_parts.append(ancestor.get("id") or "")
            attrs = " ".join(attrs_parts).lower()
            if anchor.find_parent(["h1", "h2", "h3", "h4", "h5", "h6"]):
                value += 40
            if any(word in attrs for word in (
                "title", "name", "heading", "track", "book", "story", "caption",
                "cover", "work", "entry", "post",
            )):
                value += 25
            if any(word in attrs for word in (
                "tag", "genre", "author", "artist", "user", "avatar", "button",
                "play", "icon", "thumb", "subdued", "series", "secondary",
                "meta", "muted", "stats", "edition", "rating", "review",
                "publication", "format",
            )):
                value -= 30
            if text:
                value += 10
            else:
                value -= 45
            if anchor.get("aria-label"):
                value += 20
            if anchor.find("img") and not text:
                value -= 20
            return value

        return max(anchors, key=score)

    @classmethod
    def _guess_author_element(cls, item, title_element):
        tokens = (
            "author", "byline", "writer", "creator", "artist", "username",
            "uploader", "poster",
        )
        candidates = []
        for element in item.find_all(True):
            if element is title_element:
                continue
            if (cls._guess_is_within(title_element, element)
                    or cls._guess_is_within(element, title_element)):
                continue
            attrs = (
                " ".join(element.get("class") or [])
                + " " + (element.get("id") or "")
                + " " + " ".join(element.get("rel") or [])
            ).lower()
            if not any(token in attrs for token in tokens):
                continue
            text = element.get_text(" ", strip=True)
            if not text or len(text) > 120:
                continue
            candidates.append((1 if element.name == "a" else 0, -len(text), element))
        if not candidates:
            return None
        candidates.sort(reverse=True, key=lambda row: (row[0], row[1]))
        return candidates[0][2]

    @classmethod
    def _guess_summary_element(cls, item, title_element):
        tokens = (
            "summary", "description", "desc", "synopsis", "excerpt", "snippet",
            "caption", "blurb", "abstract",
        )
        for element in item.find_all(["p", "div", "span"]):
            if element is title_element:
                continue
            if (cls._guess_is_within(title_element, element)
                    or cls._guess_is_within(element, title_element)):
                continue
            attrs = (
                " ".join(element.get("class") or [])
                + " " + (element.get("id") or "")
            ).lower()
            text = element.get_text(" ", strip=True)
            if any(token in attrs for token in tokens) and 8 <= len(text) <= 600:
                return element
        paragraph = item.find("p")
        if paragraph is not None:
            text = paragraph.get_text(" ", strip=True)
            if 20 <= len(text) <= 600:
                return paragraph
        return None

    @classmethod
    def _guess_search_url(cls, url):
        """Turn a search-results URL into a template containing {query}."""
        import re
        import urllib.parse

        parsed = urllib.parse.urlsplit(url)
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if pairs:
            chosen_key = None
            lowered = [(key, key.lower().strip("[]")) for key, _ in pairs]
            for key, low in lowered:
                if low in cls._GUESS_SEARCH_KEYS:
                    chosen_key = key
                    break
            if chosen_key is None:
                for key, low in lowered:
                    if any(token in low for token in ("query", "search", "keyword", "term")):
                        chosen_key = key
                        break
            if chosen_key is None:
                ignored = {
                    "page", "p", "sort", "order", "sortby", "orderby", "type",
                    "ready", "limit", "offset", "per_page", "lang", "language",
                }
                for key, value in pairs:
                    if key.lower() in ignored:
                        continue
                    if len(value) >= 2 and re.search(r"[A-Za-z]{2,}", value):
                        chosen_key = key
                        break
            if chosen_key is not None:
                rebuilt = []
                paging_keys = {"page", "p", "offset", "start", "pg", "paged"}
                for key, value in pairs:
                    if key == chosen_key:
                        value = "{query}"
                    elif key.lower() in paging_keys:
                        # Don't pin the guessed page number into every search.
                        continue
                    rebuilt.append(
                        f"{urllib.parse.quote(key, safe='')}="
                        f"{urllib.parse.quote(value, safe='{}')}"
                    )
                query = "&".join(rebuilt)
                template = urllib.parse.urlunsplit(
                    (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
                )
                return template, True

        segments = parsed.path.split("/")
        for index, segment in enumerate(segments):
            if segment.lower() in ("search", "query", "results") and index + 1 < len(segments):
                if segments[index + 1]:
                    new_segments = segments[:]
                    new_segments[index + 1] = "{query}"
                    template = urllib.parse.urlunsplit(
                        (parsed.scheme, parsed.netloc, "/".join(new_segments),
                         parsed.query, parsed.fragment)
                    )
                    return template, True
        return url, False

    @classmethod
    def _guess_site_config_from_soup(cls, url, soup, kind="story"):
        import urllib.parse
        from collections import defaultdict
        from bs4 import Tag

        # React streaming pages (Goodreads and others) leave real card markup
        # inside <template> tags. Unwrap them so it can be inspected normally.
        for template in soup.find_all("template"):
            template.unwrap()
        for tag in soup.find_all(cls._GUESS_BAD_TAGS):
            tag.decompose()

        groups = []
        for parent in soup.find_all(True):
            if parent.name in cls._GUESS_BAD_TAGS or cls._guess_has_bad_ancestor(parent):
                continue
            children = [
                child for child in parent.find_all(recursive=False)
                if isinstance(child, Tag) and child.name not in cls._GUESS_BAD_TAGS
            ]
            if len(children) < 3:
                continue
            buckets = defaultdict(list)
            for child in children:
                token = cls._guess_class_token(child)
                buckets[(child.name, token)].append(child)
            for (tag, token), items in buckets.items():
                if len(items) < 3:
                    continue
                score = cls._score_guess_group(items, kind)
                if score is None:
                    continue
                groups.append((score, parent, items, token))

        groups.sort(key=lambda row: row[0], reverse=True)
        for _score, parent, items, token in groups[:30]:
            result = cls._guess_config_from_group(
                url, soup, parent, items, token, kind
            )
            if result:
                return result
        return None

    @classmethod
    def _guess_config_from_group(cls, url, soup, parent, items, token, kind):
        import urllib.parse

        # The first sibling is often a header or a differently shaped promo row.
        # Try several representatives and keep the title selector that covers
        # the most cards.
        best = None
        tried = set()
        for representative in items[:12]:
            title_element = cls._guess_title_element(representative)
            if title_element is None:
                continue
            title_selector = cls._guess_selector_within(title_element, representative)
            if not title_selector or title_selector in tried:
                continue
            tried.add(title_selector)
            covered = 0
            for item in items:
                try:
                    element = item.select_one(title_selector)
                except Exception:
                    element = None
                if element is None or not element.has_attr("href") or not element.get("href"):
                    continue
                label = element.get_text(" ", strip=True)
                if not label:
                    label = (element.get("aria-label") or "").strip()
                if not label:
                    image = element.find("img")
                    if image is not None:
                        label = (image.get("alt") or "").strip()
                if label:
                    covered += 1
            if best is None or covered > best[0]:
                best = (covered, title_element, title_selector, representative)

        if best is None:
            return None
        covered, title_element, title_selector, representative = best
        required = max(3, int(len(items) * 0.6))
        if covered < required:
            return None

        author_element = cls._guess_author_element(representative, title_element)
        summary_element = cls._guess_summary_element(representative, title_element)
        thumb_element = representative.find("img")

        results_selector = cls._guess_results_selector(soup, parent, items, token)
        search_url, has_query = cls._guess_search_url(url)
        parsed = urllib.parse.urlsplit(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        config = {
            "parser": "generic_html",
            "search_url": search_url,
            "base_url": base_url,
            "results_selector": results_selector,
            "title_selector": title_selector,
            "url_selector": title_selector,
            "author_selector": cls._guess_selector_within(author_element, representative),
            "summary_selector": cls._guess_selector_within(summary_element, representative),
            "thumb_selector": cls._guess_selector_within(thumb_element, representative),
        }
        warning = ""
        if not has_query:
            warning = (
                "This URL had no obvious search parameter, so it was saved as a "
                "static listing URL. Every search will show that same page; edit "
                "the search_url in Notes to add {query} for real searching."
            )
        return {
            "status": "success",
            "config": config,
            "url": url,
            "kind": kind,
            "item_count": covered,
            "warning": warning,
        }

    def guess_site_selectors(self, url, kind="story"):
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            import urllib.parse

            kind = (kind or "story").lower()
            url = (url or "").strip()
            if not url:
                return {"status": "error", "msg": "Please paste a URL to guess from."}
            if "://" not in url:
                url = "https://" + url

            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return {"status": "error", "msg": "That does not look like a valid http(s) URL."}

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }

            response = None
            first_error = None
            try:
                response = cloudscraper.create_scraper().get(
                    url, timeout=20, headers=headers
                )
            except Exception as error:
                first_error = error
                try:
                    import requests
                    response = requests.get(url, timeout=20, headers=headers)
                except Exception:
                    return {
                        "status": "error",
                        "msg": f"Could not reach that URL: {first_error}",
                    }

            status = getattr(response, "status_code", 0)
            if status >= 400:
                if status in (401, 403, 418, 429, 503):
                    return {
                        "status": "error",
                        "msg": (
                            f"That site refused the automated request (HTTP {status}). "
                            "It blocks scrapers, so Guess cannot read its results. "
                            "Open the page in your browser and paste its address in a "
                            "normal browser tab, or add a JSON config to Notes manually."
                        ),
                    }
                return {"status": "error", "msg": f"That page returned HTTP {status}."}

            text = response.text or ""
            if len(text.strip()) < 200:
                return {
                    "status": "error",
                    "msg": "That page returned almost no HTML. It may need a login or JavaScript.",
                }

            soup = BeautifulSoup(text, "html.parser")
            lowered = text.lower()
            has_challenge_marker = any(
                marker in lowered for marker in self._GUESS_AI_CHALLENGE_MARKERS
            )
            if has_challenge_marker:
                visible_text = soup.get_text(" ", strip=True)
                meaningful_links = soup.find_all("a", href=True)
                # Many normal pages mention a challenge script but still ship
                # real results. Only treat it as a block when there is almost
                # no usable content.
                if len(visible_text) < 400 or len(meaningful_links) < 5:
                    return {
                        "status": "error",
                        "msg": (
                            "That page is showing a bot/JavaScript challenge instead of "
                            "search results. Open the results in a normal browser tab and "
                            "paste that URL, or configure the source manually."
                        ),
                    }

            result = self._guess_site_config_from_soup(url, soup, kind)
            if result:
                return result
            return self._guess_selectors_with_ai(url, soup, kind)
        except Exception as error:
            return {"status": "error", "msg": f"Guess failed: {error}"}

    def guess_story_site_selectors(self, url):
        return self.guess_site_selectors(url, "story")

    def guess_collection_site_selectors(self, url):
        return self.guess_site_selectors(url, "collection")

    def guess_audio_site_selectors(self, url):
        return self.guess_site_selectors(url, "audio")

    def _get_env_var(self, *names):
        for name in names:
            value = os.environ.get(name)
            if value:
                return value

        bases = []
        for base in (APP_PWD, app_dir, os.getcwd()):
            base = os.path.abspath(base)
            if base not in bases:
                bases.append(base)
        for base in bases:
            for relative_path in [".env", os.path.join("web", ".env")]:
                path = os.path.join(base, relative_path)
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

    @staticmethod
    def _parse_ai_config(response_text):
        import json
        import re
        text = (response_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            config = json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}
            try:
                config = json.loads(match.group(0))
            except Exception:
                return {}
        return config if isinstance(config, dict) else {}

    def _guess_selectors_with_ai(self, url, soup, kind="story"):
        account_id = self._get_env_var("CLOUDFLARE_ACCOUNTID", "Cloudflare_Account_ID")
        api_key = self._get_env_var("CF_WORKERSAI_REST_API", "CF_ACCOUNT_API_Token", "Cloudflare_API_Key")
        
        try:
            for tag in soup(["script", "style", "svg", "head", "path", "meta", "link"]):
                tag.decompose()
                
            html_content = str(soup)[:50000]
            
            import requests
            
            prompt = (
                "You are an expert web scraper helper. I need you to analyze the HTML source code of a search results page "
                f"from URL: {url} and extract the CSS selectors for the repeating items. "
                f"The user is configuring a {kind} source.\n\n"
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
                        config = self._parse_ai_config(response_text)
                        if config.get("results_selector"):
                            return self._build_final_config(url, config, kind)
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
                        config = self._parse_ai_config(response_text)
                        if config.get("results_selector"):
                            return self._build_final_config(url, config, kind)
                except Exception as e:
                    print(f"Gemini AI failed: {e}")

            return {
                "status": "error",
                "msg": (
                    "XenoPlayer could not find a repeating result list on that page. "
                    "Some sites build their results with JavaScript or refuse automated "
                    "requests. Try a server-rendered search results page, add a Gemini "
                    "API key in Options, or paste a JSON config into the Notes field."
                ),
            }
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

    def _build_final_config(self, url, config, kind="story"):
        import urllib.parse
        search_url, has_query = self._guess_search_url(url)
        parsed_url = urllib.parse.urlsplit(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        warning = ""
        if not has_query:
            warning = (
                "This URL had no obvious search parameter, so it was saved as a "
                "static listing URL. Every search will show that same page; edit "
                "the search_url in Notes to add {query} for real searching."
            )
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
            },
            "url": url,
            "kind": kind,
            "warning": warning,
        }

    def rename_collection(self, path, newName):
        if not path: return {"status": "error"}
        if os.path.isfile(path):
            return self._rename_collection_archive(path, newName)
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

    def _rename_collection_archive(self, archive, new_name):
        old_stem, ext = os.path.splitext(os.path.basename(archive))
        desired = self._sanitize_collection_name(new_name, old_stem)
        final_path = archive
        if desired != old_stem:
            candidate = self._unique_file_path(os.path.join(os.path.dirname(archive), desired + ext))
            try:
                os.rename(archive, candidate)
            except OSError as e:
                return {"status": "error", "msg": str(e)}
            final_path = candidate
            if self._cbz_archive_path == archive:
                self._cbz_archive_path = final_path
            self._replace_path_references(archive, final_path)
        old_sidecar = self._collection_sidecar_path(archive)
        sidecar = self._collection_sidecar_path(final_path)
        was_collection = os.path.exists(old_sidecar) or os.path.exists(sidecar)
        meta = self._read_collection_meta(old_sidecar) if os.path.exists(old_sidecar) else self._read_collection_meta(sidecar)
        if old_sidecar != sidecar and os.path.exists(old_sidecar):
            try: os.remove(old_sidecar)
            except Exception: pass
        if was_collection:
            meta["name"] = desired
            meta["file"] = os.path.basename(final_path)
            try: self._write_collection_meta(sidecar, meta)
            except Exception: pass
        return {"status": "success", "path": final_path, "name": desired}

    def unmark_folder_as_collection(self, path):
        if not path: return {"status": "error"}
        if os.path.isfile(path):
            sidecar = self._collection_sidecar_path(path)
            try:
                if os.path.exists(sidecar):
                    os.remove(sidecar)
            except Exception as e:
                return {"status": "error", "msg": str(e)}
            return {"status": "success"}
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
        if not path:
            return {"status": "error", "msg": "No collection selected."}
        if os.path.isfile(path) and os.path.splitext(path)[1].lower() in self.COLLECTION_ARCHIVE_EXTS:
            return self.open_cbz_archive(path)
        directory = os.path.dirname(path) if os.path.isfile(path) else path
        if not os.path.isdir(directory):
            return {"status": "error", "msg": "Collection folder does not exist."}

        image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif'}
        video_exts = {
            '.mp4', '.webm', '.ogg', '.mkv', '.avi', '.mov', '.m4v',
            '.wmv', '.flv', '.mpg', '.mpeg', '.ts',
        }
        has_video = False
        has_image = False
        for root_dir, dirs, files in os.walk(directory):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in video_exts:
                    has_video = True
                elif ext in image_exts:
                    has_image = True
            if has_video:
                break

        if not has_video and not has_image:
            return {
                "status": "error",
                "msg": "This collection has no images or videos to open.",
            }

        root_has_image = False
        try:
            root_has_image = any(
                os.path.splitext(f)[1].lower() in image_exts
                for f in os.listdir(directory)
                if os.path.isfile(os.path.join(directory, f))
            )
        except OSError:
            pass

        # CollectionViewer is an image-page reader. If the collection contains
        # videos, or only has images inside subfolders, use the main player so
        # every supported media type is available. The separate PyQt helper is
        # not shipped in the macOS core build, so macOS always uses the player.
        if IS_MACOS or has_video or (has_image and not root_has_image):
            return self.load_selected_directory(directory, recursive=True)

        import subprocess
        env = os.environ.copy()
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "CollectionViewer", directory], env=env)
        else:
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CollectionViewer.py")
            subprocess.Popen([sys.executable, script, directory], env=env)
        return {"status": "success", "viewer": "collection_viewer"}

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
            if IS_MACOS:
                base = os.path.join(os.path.expanduser("~"), "Downloads", "XenoPlayer")
            else:
                base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                base = os.path.join(base, "Downloads")
            d = os.path.join(base, "nhentai")
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
                returncode = 0
                if getattr(sys, 'frozen', False) and IS_MACOS:
                    # A frozen .app cannot run `python -m gallery_dl` in a child
                    # process, so drive the library in this worker thread.
                    try:
                        import gallery_dl.config
                        import gallery_dl.job
                        gallery_dl.config.set(("extractor",), "base-directory", download_dir)
                        job = gallery_dl.job.DownloadJob(url)
                        job.run()
                    except Exception:
                        returncode = 1
                    if self.cancel_flags.get(title):
                        raise Exception("Cancelled by user")
                else:
                    cmd = [sys.executable, "gallery_dl_module", "-d", download_dir, url] if getattr(sys, 'frozen', False) else [sys.executable, "-m", "gallery_dl", "-d", download_dir, url]
                    process = subprocess.Popen(cmd, creationflags=subprocess_creationflags())
                    while process.poll() is None:
                        if self.cancel_flags.get(title):
                            process.terminate()
                            raise Exception("Cancelled by user")
                        time.sleep(0.5)
                    returncode = process.returncode
                if returncode != 0 and not self.cancel_flags.get(title):
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
                        raise Exception(f"gallery-dl failed (code {returncode}) and scraper fallback failed: {scraped.get('msg')}")
                
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
        parents = [dl_dir] + self.settings.get("saved_folders", [])
        archive_parents = list(parents)
        for parent in self.settings.get("known_collection_archive_dirs", []) or []:
            if parent and parent not in archive_parents:
                archive_parents.append(parent)
        
        # Auto-scan Download Locations Safely
        for parent in parents:
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
                
                image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif'}
                video_exts = {
                    '.mp4', '.webm', '.ogg', '.mkv', '.avi', '.mov', '.m4v',
                    '.wmv', '.flv', '.mpg', '.mpeg', '.ts',
                }
                thumb_exts = {'.mp4', '.webm', '.ogg'}
                first_image = None
                first_video = None
                page_count = 0
                video_count = 0
                try:
                    files = os.listdir(d)
                    image_files = sorted(
                        [f for f in files if os.path.splitext(f)[1].lower() in image_exts],
                        key=natural_sort_key,
                    )
                    video_files = sorted(
                        [f for f in files if os.path.splitext(f)[1].lower() in video_exts],
                        key=natural_sort_key,
                    )
                    page_count = len(image_files)
                    video_count = len(video_files)
                    if image_files:
                        first_image = os.path.join(d, image_files[0])
                    if video_files:
                        preferred = [
                            f for f in video_files
                            if os.path.splitext(f)[1].lower() in thumb_exts
                        ]
                        first_video = os.path.join(d, (preferred or video_files)[0])
                except: pass

                # Collections with media only inside subfolders still deserve a
                # thumbnail in the library grid.
                if not first_image and not first_video:
                    try:
                        for root_dir, dirs, files in os.walk(d):
                            dirs.sort(key=natural_sort_key)
                            for f in sorted(files, key=natural_sort_key):
                                ext = os.path.splitext(f)[1].lower()
                                if ext in image_exts:
                                    first_image = os.path.join(root_dir, f)
                                    break
                                if ext in video_exts and not first_video:
                                    first_video = os.path.join(root_dir, f)
                            if first_image or first_video:
                                break
                    except: pass

                thumb = first_image or first_video
                
                try: mtime = os.path.getctime(d)
                except: mtime = 0
                
                library.append({
                    "path": d, "name": name, "thumb": thumb, "mtime": mtime,
                    "page_count": page_count, "video_count": video_count,
                    "kind": "folder",
                })

        # Comic archives marked as collections (sidecar <name>.collection.json next to the file)
        seen_archives = set()
        for parent in archive_parents:
            if not parent or not os.path.isdir(parent):
                continue
            try:
                entries = os.listdir(parent)
            except Exception:
                continue
            for entry in entries:
                if not entry.lower().endswith(".collection.json"):
                    continue
                sidecar = os.path.join(parent, entry)
                meta = self._read_collection_meta(sidecar)
                archive_name = (meta.get("file") or "").strip()
                if not archive_name:
                    base = entry[: -len(".collection.json")]
                    for ext in self.COLLECTION_ARCHIVE_EXTS:
                        if os.path.exists(os.path.join(parent, base + ext)):
                            archive_name = base + ext
                            break
                if not archive_name:
                    continue
                archive = os.path.normpath(os.path.join(parent, archive_name))
                if archive in seen_archives or not os.path.isfile(archive):
                    continue
                seen_archives.add(archive)
                name = (meta.get("name") or "").strip() or os.path.splitext(archive_name)[0]
                try: mtime = os.path.getmtime(archive)
                except: mtime = 0
                library.append({"path": archive, "name": name, "thumb": None, "mtime": mtime, "page_count": 0, "video_count": 0, "kind": "archive"})

        self.settings["known_collection_folders"] = valid_known
        save_settings(self.settings)
        return {"status": "success", "library": library}

    def delete_collection_folder(self, path):
        if not path: return {"status": "error"}
        if os.path.isfile(path):
            sidecar = self._collection_sidecar_path(path)
            try:
                import send2trash
                send2trash.send2trash(path)
            except Exception:
                try:
                    os.remove(path)
                except Exception as e:
                    return {"status": "error", "msg": str(e)}
            try:
                if os.path.exists(sidecar):
                    os.remove(sidecar)
            except Exception:
                pass
            if self._cbz_archive_path == path:
                self._cleanup_cbz_archive()
            return {"status": "success"}
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
        try:
            import pytesseract
        except ImportError:
            return {
                "status": "error",
                "msg": "OCR is not included in this build. Install Tesseract and the Python OCR packages to enable it.",
            }
        if not shutil.which('tesseract'):
            if IS_WINDOWS:
                tess_candidates = [r'C:\Program Files\Tesseract-OCR\tesseract.exe', r'D:\Programs\Tesseract-OCR\tesseract.exe']
            elif IS_MACOS:
                tess_candidates = ['/opt/homebrew/bin/tesseract', '/usr/local/bin/tesseract']
            else:
                tess_candidates = ['/usr/bin/tesseract']
            for p_path in tess_candidates:
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
                    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
                    worker_exe = helper_binary_path("ocr_worker")
                    if not worker_exe:
                        try: os.remove(temp_img_path)
                        except Exception: pass
                        return {
                            "status": "error",
                            "msg": "Japanese Manga OCR is not included in the macOS core build yet.",
                        }
                    cmd = [worker_exe, temp_img_path]
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    worker_script = os.path.join(base_dir, "ocr_worker.py")
                    if not os.path.exists(worker_script):
                        try: os.remove(temp_img_path)
                        except Exception: pass
                        return {"status": "error", "msg": "OCR worker script not found."}
                    cmd = [sys.executable, worker_script, temp_img_path]

                model_path = os.path.normpath(os.path.join(base_dir, 'manga_ocr_model'))
                if not os.path.exists(os.path.join(model_path, "config.json")):
                    model_path = os.path.normpath(os.path.join(base_dir, '..', 'manga_ocr_model'))
                cmd.append(model_path)

                # Set PYTHONIOENCODING as belt-and-suspenders for the child process
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                        env=env,
                                        creationflags=subprocess_creationflags())
                
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
            if not shutil.which('tesseract'):
                if IS_WINDOWS:
                    tess_candidates = [r'C:\Program Files\Tesseract-OCR\tesseract.exe', r'D:\Programs\Tesseract-OCR\tesseract.exe']
                elif IS_MACOS:
                    tess_candidates = ['/opt/homebrew/bin/tesseract', '/usr/local/bin/tesseract']
                else:
                    tess_candidates = ['/usr/bin/tesseract']
                for p_path in tess_candidates:
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
            
        supported = {'.mp4', '.webm', '.ogg', '.avi', '.wmv', '.mkv', '.mov', '.flv', '.mpg', '.mpeg', '.m4v', '.ts', '.zip', '.cbz', '.mp3', '.wav', '.wave', '.m4a', '.m4b', '.aac', '.flac', '.oga', '.opus', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.txt', '.md', '.json', '.csv'}
        
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
    if ext not in {
        '.mp4', '.webm', '.ogg', '.mkv', '.avi', '.mov', '.m4v',
        '.wmv', '.flv', '.mpg', '.mpeg', '.ts',
    }:
        return "Not video", 404
    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
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

REG_KEY_CACHE_FILE = os.path.join(APP_PWD, "reg_cache.json")
REG_KEY_TTL_DAYS = 30
DEFAULT_REG_KEY_VALIDATE_URL = (
    "https://xenoplayer-regkeys.skotxeno.workers.dev/api/reg-key/validate"
)


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


def _dotenv_lookup(*names):
    """Return the first value found in the process environment, then in .env files."""
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    bases = []
    for base in (APP_PWD, app_dir, os.getcwd()):
        base = os.path.abspath(base)
        if base not in bases:
            bases.append(base)
    for base in bases:
        for relative_path in (".env", os.path.join("web", ".env")):
            path = os.path.join(base, relative_path)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        if k.strip() in names:
                            return v.strip().strip('"').strip("'")
            except Exception:
                pass
    return ""


def reg_key_validate_url():
    return _dotenv_lookup("REG_KEY_VALIDATE_URL") or DEFAULT_REG_KEY_VALIDATE_URL


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
    headers = {
        "Content-Type": "application/json",
        # A browser-like agent avoids Cloudflare's bot/browser-integrity block
        # ("error code: 1010", HTTP 403) that targets non-browser clients.
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    access_id = os.environ.get("CF_ACCESS_CLIENT_ID", "").strip()
    access_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET", "").strip()
    if access_id and access_secret:
        headers["CF-Access-Client-Id"] = access_id
        headers["CF-Access-Client-Secret"] = access_secret
    req = urllib.request.Request(
        url, data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", "replace")
            lowered = body.lower()
            if "<html" in lowered and "cloudflare access" in lowered:
                return False, (
                    "The validation endpoint is protected by Cloudflare Access. "
                    "Remove Access protection from /api/reg-key/validate, or set "
                    "CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET in .env."
                )
            if resp.status == 200:
                data = json.loads(body)
                if data.get("ok"):
                    return True, None
                return False, data.get("error", "Invalid registration key.")
            return False, f"Validation failed (HTTP {resp.status})."
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = None
        if isinstance(data, dict) and data.get("error"):
            return False, data["error"]
        lowered = (raw or "").lower()
        location = str(e.headers.get("Location", "") if e.headers else "").lower()
        if "cloudflareaccess" in location or "cloudflare-access" in lowered or "error code: 1010" in lowered:
            return False, (
                f"The validation endpoint is protected by Cloudflare Access (HTTP {e.code}). "
                "Remove Access protection for /api/reg-key/validate or point "
                "REG_KEY_VALIDATE_URL at an unprotected endpoint."
            )
        return False, f"Validation failed (HTTP {e.code})."
    except Exception as e:
        return False, f"Could not reach validation server: {e}"


class RegKeyDialog:
    def __init__(self):
        self.result = None

    @staticmethod
    def _applescript_string(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ") + '"'

    def _mac_ask(self, prompt, title):
        script = (
            f"display dialog {self._applescript_string(prompt)} default answer \"\" "
            f"with title {self._applescript_string(title)} "
            'buttons {"Cancel", "Continue"} default button "Continue"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return None
        output = (result.stdout or "").strip()
        if "text returned:" in output:
            return output.split("text returned:", 1)[1]
        return ""

    def _mac_alert(self, message, title, critical=False):
        script = (
            f"display alert {self._applescript_string(title)} "
            f"message {self._applescript_string(message)} as "
            f"{'critical' if critical else 'informational'}"
        )
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=60)
        except Exception:
            pass

    def _run_macos(self):
        """Registration prompt using native dialogs, so Tk is not required."""
        while self.result is None:
            key = self._mac_ask(
                "Enter your registration key to unlock XenoPlayer:",
                "XenoPlayer - Registration",
            )
            if key is None:
                self.result = False
                break
            key = key.strip()
            if not key:
                self._mac_alert("Please enter a registration key.", "XenoPlayer - Registration")
                continue
            ok, msg = validate_reg_key_online(key)
            if ok:
                save_reg_cache({
                    "key_hash": _sha256_hex(key),
                    "machine_id": machine_fingerprint(),
                    "validated_at": datetime.now().isoformat(),
                    "ttl_days": REG_KEY_TTL_DAYS,
                })
                self._mac_alert(
                    "Registration key accepted. Welcome to XenoPlayer.",
                    "XenoPlayer - Registration",
                )
                self.result = True
            else:
                self._mac_alert(f"Invalid key: {msg}", "XenoPlayer - Registration", critical=True)
        return self.result

    def run(self):
        if IS_MACOS:
            return self._run_macos()

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