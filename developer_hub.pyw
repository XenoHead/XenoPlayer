import os
import sys
import json
import threading
import subprocess
import shutil
import re
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
import requests

# Determine directories
current_dir = os.path.dirname(os.path.abspath(__file__))
version_file = os.path.join(current_dir, "version.json")
build_bat = os.path.join(current_dir, "build.bat")

# Determine settings file path dynamically (portable mode check)
use_portable = False
try:
    test_file = os.path.join(current_dir, ".write_test")
    with open(test_file, "w") as f:
        pass
    os.remove(test_file)
    use_portable = True
except (IOError, OSError, PermissionError):
    use_portable = False

if use_portable:
    settings_file = os.path.join(current_dir, "settings.json")
else:
    settings_file = os.path.join(os.path.expanduser("~"), "Documents", "ReelScript", "Backups", "settings.json")

class DeveloperHubApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ReelScript - Developer & Update Hub")
        self.root.geometry("750x850") # Slightly taller to accommodate token field
        self.root.configure(bg="#12181f")
        
        # Styling parameters
        self.colors = {
            "bg_dark": "#12181f",
            "card_bg": "#1a232c",
            "accent_blue": "#1b8adb",
            "accent_green": "#10b981",
            "accent_amber": "#f59e0b",
            "text_light": "#ffffff",
            "text_muted": "#abb2bf",
            "border": "#25313e",
            "terminal_bg": "#0b0f19",
            "terminal_fg": "#3b82f6"
        }
        
        # Load version data
        self.load_version_data()
        
        # Load Git info
        self.load_git_info()
        
        # Load GitHub Token
        self.github_token = self.load_github_token()
        
        # Build widgets
        self.create_widgets()
        self.log("🚀 Developer Hub initialized successfully.\nReady to build and deploy.")

    def load_version_data(self):
        self.version_data = {"version": "2.5", "last_updated": "2026-05-31", "changelog": []}
        if os.path.exists(version_file):
            try:
                with open(version_file, "r", encoding="utf-8") as f:
                    self.version_data = json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load version.json: {str(e)}")
        else:
            self.save_version_data()

    def save_version_data(self):
        try:
            with open(version_file, "w", encoding="utf-8") as f:
                json.dump(self.version_data, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save version.json: {str(e)}")

    def get_installed_version(self):
        installed_version = "Not Installed"
        install_path = None
        try:
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\XenoHead\ReelScript", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            except OSError:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\XenoHead\ReelScript", 0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
            
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
        except Exception:
            # Fallback to default paths
            for p in [r"C:\Program Files\ReelScript", r"C:\Program Files (x86)\ReelScript", r"C:\ReelScript"]:
                if os.path.exists(os.path.join(p, "ReelScript.exe")) or os.path.exists(os.path.join(p, "reelscript.exe")):
                    install_path = p
                    break
        
        if install_path and os.path.exists(os.path.join(install_path, "version.json")):
            try:
                with open(os.path.join(install_path, "version.json"), "r", encoding="utf-8") as f:
                    vdata = json.load(f)
                    installed_version = f"v{vdata.get('version', 'Unknown')} ({install_path})"
            except Exception:
                installed_version = f"Error reading version.json at {install_path}"
        elif install_path:
            installed_version = f"Unknown Version ({install_path})"
            
        return installed_version

    def load_github_token(self):
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r") as f:
                    settings = json.load(f)
                    return settings.get("githubToken", "")
            except:
                pass
        return ""

    def save_github_token(self, token):
        try:
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            settings = {}
            if os.path.exists(settings_file):
                with open(settings_file, "r") as f:
                    settings = json.load(f)
            settings["githubToken"] = token
            with open(settings_file, "w") as f:
                json.dump(settings, f, indent=4)
            self.github_token = token
        except Exception as e:
            self.log(f"Warning: Failed to save GitHub token to settings.json: {str(e)}")

    def load_git_info(self):
        self.git_repo = "Unknown Repository"
        self.git_branch = "Unknown Branch"
        try:
            creationflags = 0
            if os.name == 'nt':
                creationflags = 0x08000000  # CREATE_NO_WINDOW
            
            # Get remote URL
            proc = subprocess.Popen(
                ["git", "remote", "get-url", "origin"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                cwd=current_dir
            )
            out, err = proc.communicate()
            if proc.returncode == 0 and out.strip():
                self.git_repo = out.strip()
            
            # Get active branch
            proc = subprocess.Popen(
                ["git", "branch", "--show-current"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                cwd=current_dir
            )
            out, err = proc.communicate()
            if proc.returncode == 0 and out.strip():
                self.git_branch = out.strip()
        except Exception as e:
            pass

    def refresh_git_info(self):
        self.load_git_info()
        git_display = f"{self.git_repo} (branch: {self.git_branch})"
        self.git_val.configure(text=git_display)
        self.log(f"Refreshed Git Info. Repo: {self.git_repo}, Branch: {self.git_branch}")

    def parse_github_url(self, url):
        match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?", url)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def create_widgets(self):
        # Master Layout Padded Frame
        self.main_frame = tk.Frame(self.root, bg=self.colors["bg_dark"], padx=20, pady=20)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. HEADER SECTION
        self.header_frame = tk.Frame(self.main_frame, bg=self.colors["bg_dark"])
        self.header_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.title_icon = tk.Label(self.header_frame, text="🚀", font=("Segoe UI", 28), bg=self.colors["bg_dark"], fg=self.colors["accent_blue"])
        self.title_icon.pack(side=tk.LEFT, padx=(0, 10))
        
        self.title_label = tk.Label(
            self.header_frame, 
            text="ReelScript Developer Hub", 
            font=("Segoe UI", 18, "bold"), 
            bg=self.colors["bg_dark"], 
            fg=self.colors["text_light"]
        )
        self.title_label.pack(side=tk.LEFT, anchor=tk.W)
        
        self.subtitle_label = tk.Label(
            self.main_frame, 
            text="Manage version releases, write changelogs, build PyInstaller executables, and push updates to GitHub.", 
            font=("Segoe UI", 9), 
            bg=self.colors["bg_dark"], 
            fg=self.colors["text_muted"]
        )
        self.subtitle_label.pack(fill=tk.X, anchor=tk.W, pady=(0, 15))

        # 2. VERSION & CHANGELOG CARD
        self.card = tk.LabelFrame(
            self.main_frame, 
            text=" 📦 Release Manager ", 
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["card_bg"], 
            fg=self.colors["accent_blue"],
            bd=1, 
            relief=tk.SOLID, 
            padx=15, 
            pady=15
        )
        self.card.pack(fill=tk.BOTH, pady=(0, 15))

        # Version Row
        self.ver_frame = tk.Frame(self.card, bg=self.colors["card_bg"])
        self.ver_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.ver_label = tk.Label(self.ver_frame, text="Version Number:", font=("Segoe UI", 10), bg=self.colors["card_bg"], fg=self.colors["text_light"])
        self.ver_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.ver_entry = tk.Entry(
            self.ver_frame, 
            font=("Segoe UI", 10, "bold"), 
            bg=self.colors["bg_dark"], 
            fg=self.colors["text_light"],
            insertbackground="white",
            bd=1,
            relief=tk.SOLID,
            width=10
        )
        self.ver_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.ver_entry.insert(0, self.version_data["version"])
        
        # Increment buttons
        self.btn_patch = tk.Button(self.ver_frame, text="+0.0.1 (Patch)", font=("Segoe UI", 8), bg=self.colors["bg_dark"], fg=self.colors["accent_blue"], activebackground=self.colors["accent_blue"], activeforeground="white", bd=0, padx=6, pady=2, cursor="hand2", command=lambda: self.increment_version(0, 0, 1))
        self.btn_patch.pack(side=tk.LEFT, padx=3)
        
        self.btn_minor = tk.Button(self.ver_frame, text="+0.1 (Minor)", font=("Segoe UI", 8), bg=self.colors["bg_dark"], fg=self.colors["accent_blue"], activebackground=self.colors["accent_blue"], activeforeground="white", bd=0, padx=6, pady=2, cursor="hand2", command=lambda: self.increment_version(0, 1, 0))
        self.btn_minor.pack(side=tk.LEFT, padx=3)

        self.btn_major = tk.Button(self.ver_frame, text="+1.0 (Major)", font=("Segoe UI", 8), bg=self.colors["bg_dark"], fg=self.colors["accent_blue"], activebackground=self.colors["accent_blue"], activeforeground="white", bd=0, padx=6, pady=2, cursor="hand2", command=lambda: self.increment_version(1, 0, 0))
        self.btn_major.pack(side=tk.LEFT, padx=3)

        # Installed Version Row
        self.inst_ver_frame = tk.Frame(self.card, bg=self.colors["card_bg"])
        self.inst_ver_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.inst_ver_title = tk.Label(self.inst_ver_frame, text="Locally Installed:", font=("Segoe UI", 9, "bold"), bg=self.colors["card_bg"], fg=self.colors["text_muted"])
        self.inst_ver_title.pack(side=tk.LEFT, padx=(0, 5))
        
        self.inst_ver_label = tk.Label(self.inst_ver_frame, text=self.get_installed_version(), font=("Segoe UI", 9, "italic"), bg=self.colors["card_bg"], fg=self.colors["accent_amber"])
        self.inst_ver_label.pack(side=tk.LEFT)

        # Changelog area
        self.change_label = tk.Label(self.card, text="Changelog Updates (One point per line):", font=("Segoe UI", 10), bg=self.colors["card_bg"], fg=self.colors["text_light"])
        self.change_label.pack(anchor=tk.W, pady=(5, 5))
        
        self.change_text = tk.Text(
            self.card, 
            height=6, 
            font=("Segoe UI", 10), 
            bg=self.colors["bg_dark"], 
            fg=self.colors["text_light"],
            insertbackground="white",
            bd=1,
            relief=tk.SOLID
        )
        self.change_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.change_text.insert(tk.END, "\n".join(self.version_data["changelog"]))

        # Update button
        self.btn_update = tk.Button(
            self.card, 
            text="💾 Save & Update version.json", 
            font=("Segoe UI", 10, "bold"), 
            bg=self.colors["accent_blue"], 
            fg=self.colors["text_light"],
            activebackground="#1466a3",
            activeforeground="white",
            bd=0, 
            pady=6,
            cursor="hand2",
            command=self.save_and_update
        )
        self.btn_update.pack(fill=tk.X)

        # 3. CONTROL CARD & GIT SETUP
        self.control_frame = tk.Frame(self.main_frame, bg=self.colors["bg_dark"])
        self.control_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Git repo row
        self.git_frame = tk.Frame(self.control_frame, bg=self.colors["bg_dark"])
        self.git_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.git_label = tk.Label(self.git_frame, text="GitHub Deployment Target:", font=("Segoe UI", 9, "bold"), bg=self.colors["bg_dark"], fg=self.colors["text_light"])
        self.git_label.pack(side=tk.LEFT)
        
        git_display = f"{self.git_repo} (branch: {self.git_branch})"
        self.git_val = tk.Label(
            self.git_frame, 
            text=git_display, 
            font=("Segoe UI", 9, "italic"), 
            bg=self.colors["bg_dark"], 
            fg=self.colors["accent_green"]
        )
        self.git_val.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        self.btn_refresh = tk.Button(
            self.git_frame, 
            text="Refresh Info", 
            font=("Segoe UI", 8), 
            bg="#27313c", 
            fg=self.colors["text_light"],
            bd=0, 
            padx=10, 
            pady=3,
            cursor="hand2",
            command=self.refresh_git_info
        )
        self.btn_refresh.pack(side=tk.RIGHT)

        # Git token row
        self.token_frame = tk.Frame(self.control_frame, bg=self.colors["bg_dark"])
        self.token_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.token_label = tk.Label(self.token_frame, text="GitHub Personal Access Token (PAT):", font=("Segoe UI", 9, "bold"), bg=self.colors["bg_dark"], fg=self.colors["text_light"])
        self.token_label.pack(side=tk.LEFT)
        
        self.token_entry = tk.Entry(
            self.token_frame,
            font=("Segoe UI", 9),
            bg=self.colors["card_bg"],
            fg=self.colors["text_light"],
            insertbackground="white",
            show="*",
            bd=1,
            relief=tk.SOLID,
            width=30
        )
        self.token_entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        self.token_entry.insert(0, self.github_token)
        self.token_entry.bind("<FocusOut>", lambda e: self.save_github_token(self.token_entry.get().strip()))

        def toggle_token_visibility():
            if self.token_entry.cget("show") == "*":
                self.token_entry.configure(show="")
                self.btn_show_token.configure(text="Hide")
            else:
                self.token_entry.configure(show="*")
                self.btn_show_token.configure(text="Show")

        self.btn_show_token = tk.Button(
            self.token_frame, 
            text="Show", 
            font=("Segoe UI", 8), 
            bg="#27313c", 
            fg=self.colors["text_light"],
            bd=0, 
            padx=10, 
            pady=3,
            cursor="hand2",
            command=toggle_token_visibility
        )
        self.btn_show_token.pack(side=tk.RIGHT)

        # Main Hub Actions
        self.actions_grid = tk.Frame(self.control_frame, bg=self.colors["bg_dark"])
        self.actions_grid.pack(fill=tk.X)
        
        # Build button spans full width on top
        self.btn_build = tk.Button(
            self.actions_grid,
            text="🔨 Build Executable (build.bat)",
            font=("Segoe UI", 10, "bold"),
            bg="#27313c",
            fg=self.colors["text_light"],
            activebackground="#36424e",
            activeforeground="white",
            bd=0,
            pady=10,
            cursor="hand2",
            command=self.start_build
        )
        self.btn_build.pack(fill=tk.X, pady=(0, 10))

        # Push Code Only & Push Release buttons side-by-side
        self.btn_push_code = tk.Button(
            self.actions_grid,
            text="💻 Git Push Code Only",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["accent_blue"],
            fg=self.colors["text_light"],
            activebackground="#1466a3",
            activeforeground="white",
            bd=0,
            pady=10,
            cursor="hand2",
            command=self.push_code_only
        )
        self.btn_push_code.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.btn_deploy = tk.Button(
            self.actions_grid,
            text="🚀 Push Release to GitHub",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["accent_green"],
            fg=self.colors["text_light"],
            activebackground="#0e9f6e",
            activeforeground="white",
            bd=0,
            pady=10,
            cursor="hand2",
            command=self.push_to_github
        )
        self.btn_deploy.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # 4. TERMINAL LOG SECTION
        self.term_frame = tk.Frame(self.main_frame, bg=self.colors["bg_dark"])
        self.term_frame.pack(fill=tk.BOTH, expand=True)
        
        self.term_label = tk.Label(self.term_frame, text="Activity Logs:", font=("Segoe UI", 9, "bold"), bg=self.colors["bg_dark"], fg=self.colors["text_muted"])
        self.term_label.pack(anchor=tk.W, pady=(5, 5))

        self.terminal = scrolledtext.ScrolledText(
            self.term_frame,
            font=("Consolas", 9),
            bg=self.colors["terminal_bg"],
            fg="#22c55e",  # Classic bright green console output
            insertbackground="white",
            bd=1,
            relief=tk.SOLID
        )
        self.terminal.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        self.terminal.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.terminal.see(tk.END)

    def increment_version(self, major, minor, patch):
        try:
            parts = self.ver_entry.get().split('.')
            while len(parts) < 3:
                parts.append('0')
            
            p_major = int(parts[0])
            p_minor = int(parts[1])
            p_patch = int(parts[2])
            
            if major > 0:
                p_major += major
                p_minor = 0
                p_patch = 0
            elif minor > 0:
                p_minor += minor
                p_patch = 0
            elif patch > 0:
                p_patch += patch
                
            new_ver = f"{p_major}.{p_minor}.{p_patch}"
            self.ver_entry.delete(0, tk.END)
            self.ver_entry.insert(0, new_ver)
            self.log(f"Version bumped to: {new_ver}")
        except ValueError:
            messagebox.showerror("Error", "Please make sure version fits format e.g. '2.5' or '2.5.0'")

    def update_installer_iss_version(self, new_ver):
        iss_path = os.path.join(current_dir, "installer.iss")
        if os.path.exists(iss_path):
            try:
                with open(iss_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                updated = False
                for i, line in enumerate(lines):
                    # Look for #define AppVersion "..."
                    match = re.match(r'^#define\s+AppVersion\s+"[^"]+"', line)
                    if match:
                        eol = '\r\n' if line.endswith('\r\n') else '\n'
                        lines[i] = f'#define AppVersion     "{new_ver}"{eol}'
                        updated = True
                        break
                
                if updated:
                    with open(iss_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    self.log(f"📝 Updated version to {new_ver} in installer.iss")
                else:
                    self.log("⚠️ Warning: Could not find #define AppVersion line in installer.iss")
            except Exception as e:
                self.log(f"⚠️ Warning: Failed to update version in installer.iss: {str(e)}")
        else:
            self.log("ℹ️ installer.iss not found in directory. Skipping version update there.")

    def update_other_files_version(self, new_ver):
        # 1. Update reelscript.pyw (DEFAULT_VERSION dict)
        pyw_path = os.path.join(current_dir, "reelscript.pyw")
        if os.path.exists(pyw_path):
            try:
                with open(pyw_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                inside_default_version = False
                updated = False
                today_str = datetime.now().strftime("%Y-%m-%d")
                for i, line in enumerate(lines):
                    if "DEFAULT_VERSION = {" in line:
                        inside_default_version = True
                    if inside_default_version:
                        if '"version":' in line:
                            lines[i] = re.sub(r'"version":\s*"[^"]+"', f'"version": "{new_ver}"', line)
                            updated = True
                        elif '"last_updated":' in line:
                            lines[i] = re.sub(r'"last_updated":\s*"[^"]+"', f'"last_updated": "{today_str}"', line)
                        elif '}' in line:
                            inside_default_version = False
                            break
                
                if updated:
                    with open(pyw_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    self.log(f"📝 Updated DEFAULT_VERSION to {new_ver} in reelscript.pyw")
            except Exception as e:
                self.log(f"⚠️ Warning: Failed to update version in reelscript.pyw: {str(e)}")

        # 2. Update file_version_info.txt
        txt_path = os.path.join(current_dir, "file_version_info.txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Convert "4.5.7" -> "4, 5, 7, 0"
                ver_parts = new_ver.split(".")
                while len(ver_parts) < 4:
                    ver_parts.append("0")
                ver_tuple = ", ".join(ver_parts[:4])
                
                content = re.sub(r'filevers=\([^)]+\)', f'filevers=({ver_tuple})', content)
                content = re.sub(r'prodvers=\([^)]+\)', f'prodvers=({ver_tuple})', content)
                content = re.sub(r"u'FileVersion',\s*u'[^']+'", f"u'FileVersion', u'{new_ver}'", content)
                content = re.sub(r"u'ProductVersion',\s*u'[^']+'", f"u'ProductVersion', u'{new_ver}'", content)
                
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.log(f"📝 Updated version to {new_ver} in file_version_info.txt")
            except Exception as e:
                self.log(f"⚠️ Warning: Failed to update version in file_version_info.txt: {str(e)}")

        # 3. Update index.html
        html_path = os.path.join(current_dir, "index.html")
        if os.path.exists(html_path):
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                updated = False
                for i, line in enumerate(lines):
                    if 'id="about-version"' in line:
                        lines[i] = re.sub(r'id="about-version">[^<]+<', f'id="about-version">{new_ver}<', line)
                        updated = True
                        break
                
                if updated:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    self.log(f"📝 Updated version to {new_ver} in index.html about modal")
            except Exception as e:
                self.log(f"⚠️ Warning: Failed to update version in index.html: {str(e)}")

        # 3. Update README.md
        readme_path = os.path.join(current_dir, "README.md")
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                updated = False
                today_pretty = datetime.now().strftime("%B %d, %Y")
                if today_pretty.split(" ")[1].startswith("0"):
                    today_pretty = today_pretty.replace(" 0", " ")
                
                for i, line in enumerate(lines):
                    if "**Current Version:**" in line:
                        line = re.sub(r'(\*\*Current Version:\*\*\s*)[^\s&]+', rf'\g<1>{new_ver}', line)
                        line = re.sub(r'(\*\*Last Updated:\*\*\s*)[^<\r\n]+', rf'\g<1>{today_pretty}', line)
                        lines[i] = line
                        updated = True
                        break
                
                if updated:
                    with open(readme_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    self.log(f"📝 Updated version to {new_ver} in README.md")
            except Exception as e:
                self.log(f"⚠️ Warning: Failed to update version in README.md: {str(e)}")

    def save_and_update_silent(self):
        new_ver = self.ver_entry.get().strip()
        if not new_ver:
            return False
            
        changes = [line.strip() for line in self.change_text.get("1.0", tk.END).split("\n") if line.strip()]
        
        self.version_data["version"] = new_ver
        self.version_data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        self.version_data["changelog"] = changes
        
        self.save_version_data()
        self.update_installer_iss_version(new_ver)
        self.update_other_files_version(new_ver)
        return True

    def save_and_update(self):
        if self.save_and_update_silent():
            new_ver = self.ver_entry.get().strip()
            self.log(f"💾 Updated release details in version.json and other source files (Version: {new_ver})")
            messagebox.showinfo("Success", f"version.json, installer.iss, and source files updated successfully to v{new_ver}!")
        else:
            messagebox.showerror("Error", "Version cannot be empty!")

    def _enable_buttons(self):
        try:
            self.btn_build.configure(state=tk.NORMAL, bg="#27313c")
            self.btn_push_code.configure(state=tk.NORMAL, bg=self.colors["accent_blue"])
            self.btn_deploy.configure(state=tk.NORMAL, bg=self.colors["accent_green"])
        except Exception as e:
            self.log(f"Error re-enabling buttons: {e}")

    def start_build(self):
        self.save_and_update_silent()
        # Disable buttons during active operation to prevent collisions
        self.btn_build.configure(state=tk.DISABLED, bg="#2d3748")
        self.btn_push_code.configure(state=tk.DISABLED, bg="#2d3748")
        self.btn_deploy.configure(state=tk.DISABLED, bg="#2d3748")
        self.log("🛠️ Starting compilation pipeline...")
        
        # Start PyInstaller compilation in a non-blocking background thread
        threading.Thread(target=self.run_build_thread, daemon=True).start()

    def run_build_thread(self):
        try:
            if not os.path.exists(build_bat):
                self.root.after(0, lambda: self.log("❌ Error: build.bat not found in directory!"))
                return

            self.root.after(0, lambda: self.log("🔨 Spawning compilation subprocess (pyinstaller)..."))
            
            creationflags = 0
            if os.name == 'nt':
                creationflags = 0x08000000  # CREATE_NO_WINDOW
                
            process = subprocess.Popen(
                [build_bat],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
                cwd=current_dir
            )

            # Stream build output to our GUI log console line by line
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                # Forward to main thread to safely update UI widget
                self.root.after(0, lambda l=line.strip(): self.terminal.insert(tk.END, f"   {l}\n"))
                self.root.after(0, lambda: self.terminal.see(tk.END))

            process.wait()
            
            if process.returncode == 0:
                self.root.after(0, lambda: self.log("✨ COMPILATION PIPELINE SUCCESSFUL!\nBinary built at dist/reelscript.exe"))
                self.root.after(0, lambda: messagebox.showinfo("Build Success", "ReelScript executable compiled successfully!"))
            else:
                self.root.after(0, lambda: self.log(f"❌ Error: Compilation failed with return code {process.returncode}"))
                self.root.after(0, lambda: messagebox.showerror("Build Failed", f"PyInstaller build failed with exit code {process.returncode}"))

        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Subprocess Exception: {str(e)}"))
        finally:
            # Re-enable interactive buttons on main thread
            self.root.after(0, self._enable_buttons)

    def run_git_cmd(self, args):
        creationflags = 0
        if os.name == 'nt':
            creationflags = 0x08000000  # CREATE_NO_WINDOW
        
        self.root.after(0, lambda: self.log(f"💻 Running: {' '.join(args)}"))
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
            cwd=current_dir
        )
        
        output_lines = []
        while True:
            line = process.stdout.readline()
            if not line:
                break
            output_lines.append(line)
            self.root.after(0, lambda l=line.strip(): self.terminal.insert(tk.END, f"   {l}\n"))
            self.root.after(0, lambda: self.terminal.see(tk.END))
            
        process.wait()
        return process.returncode, "".join(output_lines)

    def push_code_only(self):
        self.save_and_update_silent()
        # Disable buttons during active operation to prevent collisions
        self.btn_build.configure(state=tk.DISABLED, bg="#2d3748")
        self.btn_push_code.configure(state=tk.DISABLED, bg="#2d3748")
        self.btn_deploy.configure(state=tk.DISABLED, bg="#2d3748")
        self.log("🚀 Starting Git push code pipeline...")
        
        # Start Git push in a non-blocking background thread
        threading.Thread(target=self.run_push_code_thread, daemon=True).start()

    def run_push_code_thread(self):
        try:
            # 1. Stage changes
            self.root.after(0, lambda: self.log("📂 Staging changes with git add..."))
            ret, out = self.run_git_cmd(["git", "add", "-A"])
            if ret != 0:
                self.root.after(0, lambda: self.log("❌ Error: git add failed!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", "git add command failed."))
                return
            
            # 2. Commit changes
            new_ver = self.ver_entry.get().strip()
            changes = [line.strip() for line in self.change_text.get("1.0", tk.END).split("\n") if line.strip()]
            if changes:
                commit_msg = "Update: " + "; ".join(changes)
            else:
                commit_msg = f"Update code (v{new_ver})"
            
            self.root.after(0, lambda: self.log("💾 Committing changes with git commit..."))
            ret, out = self.run_git_cmd(["git", "commit", "-m", commit_msg])
            
            # If nothing to commit, that's fine, we can continue to push.
            if ret != 0 and "nothing to commit" not in out.lower() and "working tree clean" not in out.lower():
                self.root.after(0, lambda: self.log("❌ Error: git commit failed!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", "git commit command failed."))
                return
            
            # 3. Push to remote
            branch = self.git_branch if self.git_branch != "Unknown Branch" else "main"
            self.root.after(0, lambda: self.log(f"📤 Pushing code to GitHub (origin/{branch})..."))
            ret, out = self.run_git_cmd(["git", "push", "origin", branch])
            if ret != 0:
                self.root.after(0, lambda: self.log("❌ Error: git push failed!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", "git push command failed."))
                return
                
            self.root.after(0, lambda: self.log("✅ GIT PUSH CODE COMPLETE!\nChanges pushed successfully to GitHub."))
            self.root.after(0, lambda: messagebox.showinfo("Push Success", f"Changes successfully pushed to GitHub on branch '{branch}'!"))
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Push Exception: {str(e)}"))
            self.root.after(0, lambda: messagebox.showerror("Push Failed", f"An error occurred during push: {str(e)}"))
        finally:
            self.root.after(0, self._enable_buttons)

    def push_to_github(self):
        self.save_and_update_silent()
        # Disable buttons during active operation to prevent collisions
        self.btn_build.configure(state=tk.DISABLED, bg="#2d3748")
        self.btn_push_code.configure(state=tk.DISABLED, bg="#2d3748")
        self.btn_deploy.configure(state=tk.DISABLED, bg="#2d3748")
        self.log("🚀 Starting Git push release pipeline...")
        
        # Start Git push in a non-blocking background thread
        threading.Thread(target=self.run_push_thread, daemon=True).start()

    def run_push_thread(self):
        try:
            exe_path = os.path.join(current_dir, "dist", "ReelScript.exe")
            if not os.path.exists(exe_path):
                # Fallback to lower case if named reelscript.exe
                exe_path = os.path.join(current_dir, "dist", "reelscript.exe")
                if not os.path.exists(exe_path):
                    self.root.after(0, lambda: messagebox.showerror("Error", "Compiled executable not found inside 'dist/' folder.\nPlease run 'Build Executable' first."))
                    return
            
            # Save token just in case
            token = self.token_entry.get().strip()
            self.save_github_token(token)
            
            # 1. Update local C:\ReelScript installation if it exists
            local_install_dir = r"C:\ReelScript"
            if os.path.exists(local_install_dir):
                self.root.after(0, lambda: self.log("📤 Updating local installation at C:\\ReelScript..."))
                try:
                    shutil.copy2(exe_path, os.path.join(local_install_dir, "ReelScript.exe"))
                    shutil.copy2(exe_path, os.path.join(local_install_dir, "reelscript.exe"))
                    shutil.copy2(version_file, os.path.join(local_install_dir, "version.json"))
                except Exception as ex:
                    self.root.after(0, lambda: self.log(f"   (Local C:\\ReelScript update skipped: {str(ex)})"))

            # 2. Stage only version.json and the setup file (ignore other source file edits)
            self.root.after(0, lambda: self.log("📂 Staging only version.json and the setup installer..."))
            
            # Find the active setup file
            setup_file = None
            for fname in ["ReelScript_Setup.exe", "setup_reelscript.exe", "ReelScriptSetup.exe"]:
                path = os.path.join(current_dir, "dist", fname)
                if os.path.exists(path):
                    setup_file = path
                    break
            
            if not setup_file:
                self.root.after(0, lambda: self.log("❌ Error: Setup installer file not found inside 'dist/' folder!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", "Setup installer file not found."))
                return

            rel_setup_path = os.path.relpath(setup_file, current_dir)
            
            # Stage version.json
            ret, out = self.run_git_cmd(["git", "add", "version.json"])
            if ret != 0:
                self.root.after(0, lambda: self.log("❌ Error: git add version.json failed!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", "git add version.json failed."))
                return
                
            # Stage setup file
            ret, out = self.run_git_cmd(["git", "add", rel_setup_path])
            if ret != 0:
                self.root.after(0, lambda: self.log(f"❌ Error: git add {rel_setup_path} failed!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", f"git add {rel_setup_path} failed."))
                return
            
            # 3. Commit changes
            new_ver = self.ver_entry.get().strip()
            changes = [line.strip() for line in self.change_text.get("1.0", tk.END).split("\n") if line.strip()]
            commit_msg = f"Release v{new_ver}\n\nChangelog:\n" + "\n".join([f"- {c}" for c in changes])
            
            self.root.after(0, lambda: self.log("💾 Committing changes with git commit..."))
            ret, out = self.run_git_cmd(["git", "commit", "-m", commit_msg])
            
            # If nothing to commit, that's fine, we can continue to push.
            if ret != 0 and "nothing to commit" not in out.lower() and "working tree clean" not in out.lower():
                self.root.after(0, lambda: self.log("❌ Error: git commit failed!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", "git commit command failed."))
                return
            
            # 4. Push to remote
            branch = self.git_branch if self.git_branch != "Unknown Branch" else "main"
            self.root.after(0, lambda: self.log(f"📤 Pushing to GitHub (origin/{branch})..."))
            ret, out = self.run_git_cmd(["git", "push", "origin", branch])
            if ret != 0:
                self.root.after(0, lambda: self.log("❌ Error: git push failed!"))
                self.root.after(0, lambda: messagebox.showerror("Push Failed", "git push command failed."))
                return

            # 5. Create Tag and Push Tag to origin
            self.root.after(0, lambda: self.log(f"🏷️ Creating tag v{new_ver} locally..."))
            ret, out = self.run_git_cmd(["git", "tag", "-a", f"v{new_ver}", "-m", f"Release v{new_ver}"])
            
            self.root.after(0, lambda: self.log(f"📤 Pushing tag v{new_ver} to origin..."))
            self.run_git_cmd(["git", "push", "origin", f"v{new_ver}"])
            
            # 6. GitHub Release via REST API
            if token:
                owner, repo = self.parse_github_url(self.git_repo)
                if owner and repo:
                    headers = {
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {token}",
                        "X-GitHub-Api-Version": "2022-11-28"
                    }
                    
                    self.root.after(0, lambda: self.log(f"🔍 Checking if GitHub Release for v{new_ver} already exists..."))
                    get_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/v{new_ver}"
                    resp = requests.get(get_url, headers=headers)
                    release_info = None
                    
                    if resp.status_code == 200:
                        release_info = resp.json()
                        self.root.after(0, lambda: self.log(f"ℹ️ Existing Release for v{new_ver} found. Re-using it."))
                    elif resp.status_code == 404:
                        # Create new release
                        self.root.after(0, lambda: self.log(f"🌐 Creating new GitHub Release v{new_ver}..."))
                        release_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
                        release_data = {
                            "tag_name": f"v{new_ver}",
                            "target_commitish": branch,
                            "name": f"v{new_ver}",
                            "body": "\n".join([f"- {c}" for c in changes]) if changes else f"Release v{new_ver}",
                            "draft": False,
                            "prerelease": False
                        }
                        create_resp = requests.post(release_url, headers=headers, json=release_data)
                        if create_resp.status_code in (200, 201):
                            release_info = create_resp.json()
                            self.root.after(0, lambda: self.log(f"✅ GitHub Release v{new_ver} created successfully!"))
                        else:
                            self.root.after(0, lambda: self.log(f"❌ Failed to create GitHub Release: {create_resp.status_code} - {create_resp.text}"))
                    else:
                        self.root.after(0, lambda: self.log(f"❌ Failed to query GitHub Release: {resp.status_code} - {resp.text}"))
                    
                    if release_info:
                        asset_name = os.path.basename(setup_file)
                        
                        # Check if the asset already exists on this release
                        existing_asset = None
                        for asset in release_info.get("assets", []):
                            if asset["name"] == asset_name:
                                existing_asset = asset
                                break
                        
                        if existing_asset:
                            asset_id = existing_asset["id"]
                            self.root.after(0, lambda: self.log(f"🗑️ Found existing asset {asset_name} (ID: {asset_id}) on release. Deleting it first..."))
                            delete_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}"
                            del_resp = requests.delete(delete_url, headers=headers)
                            if del_resp.status_code in (200, 204):
                                self.root.after(0, lambda: self.log(f"✅ Deleted old asset {asset_name}."))
                            else:
                                self.root.after(0, lambda: self.log(f"⚠️ Failed to delete old asset: {del_resp.status_code} - {del_resp.text}"))
                        
                        self.root.after(0, lambda: self.log(f"📤 Uploading {asset_name} to GitHub Release (this may take a moment)..."))
                        upload_url_template = release_info.get("upload_url", "")
                        if upload_url_template:
                            upload_url = upload_url_template.split("{")[0]
                            upload_url = f"{upload_url}?name={asset_name}"
                            
                            upload_headers = {
                                "Accept": "application/vnd.github+json",
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/octet-stream",
                                "X-GitHub-Api-Version": "2022-11-28"
                            }
                            
                            with open(setup_file, "rb") as f:
                                file_data = f.read()
                                
                            upload_resp = requests.post(upload_url, headers=upload_headers, data=file_data, timeout=300)
                            if upload_resp.status_code in (200, 201):
                                self.root.after(0, lambda: self.log(f"🎉 Asset {asset_name} uploaded successfully to GitHub Release!"))
                            else:
                                self.root.after(0, lambda: self.log(f"❌ Failed to upload asset to Release: {upload_resp.status_code} - {upload_resp.text}"))
                        else:
                            self.root.after(0, lambda: self.log("❌ Could not get upload_url from release response."))
                else:
                    self.root.after(0, lambda: self.log(f"⚠️ Could not parse owner/repo from Git URL: {self.git_repo}"))
            else:
                self.root.after(0, lambda: self.log("⚠️ GitHub Token (PAT) not provided. Skipping GitHub Release & asset upload."))
                
            self.root.after(0, lambda: self.log("✅ DEPLOYMENT PIPELINE COMPLETE!\nAll assets pushed successfully to GitHub."))
            self.root.after(0, lambda: messagebox.showinfo("Push Success", f"ReelScript executable and version details successfully pushed to GitHub on branch '{branch}'!"))
            
        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda m=err_msg: self.log(f"❌ Push Exception: {m}"))
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Push Failed", f"An error occurred during push: {m}"))
        finally:
            self.root.after(0, self._enable_buttons)

if __name__ == "__main__":
    root = tk.Tk()
    # Dark Mode Window border styling on modern Windows
    try:
        import ctypes
        # Set dark-mode title bar if on Windows 10/11
        if os.name == 'nt':
            root.update()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            set_imm_dark = ctypes.windll.dwmapi.DwmSetWindowAttribute
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            set_imm_dark(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(ctypes.c_int(1)), 4)
    except:
        pass
        
    app = DeveloperHubApp(root)
    root.mainloop()
