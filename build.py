import os
import sys
import subprocess
import shutil
import json
from datetime import datetime

def build():
    print("Checking for PyInstaller...")
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ui_script = os.path.join(script_dir, "XenoPlayer.py")
    ocr_script = os.path.join(script_dir, "ocr_worker.py")

    # Record the build version/commit so packaged apps can check Git for updates.
    version_path = os.path.join(script_dir, "version.json")
    version = "0.0.0"
    try:
        with open(version_path, "r", encoding="utf-8") as f:
            version = json.load(f).get("version", version)
    except Exception:
        pass
    commit = ""
    git_env = os.environ.copy()
    git_env["GIT_TERMINAL_PROMPT"] = "0"
    git_env["GCM_INTERACTIVE"] = "never"
    try:
        commit = subprocess.check_output(
            ["git", "-C", script_dir, "rev-parse", "HEAD"],
            text=True, encoding="utf-8", errors="replace", env=git_env,
        ).strip()
    except Exception:
        pass
    remote_main = ""
    try:
        remote_line = subprocess.check_output(
            ["git", "-C", script_dir, "ls-remote", "origin", "refs/heads/main"],
            text=True, encoding="utf-8", errors="replace", env=git_env,
        ).strip()
        if remote_line:
            remote_main = remote_line.split()[0]
    except Exception:
        try:
            remote_main = subprocess.check_output(
                ["git", "-C", script_dir, "rev-parse", "origin/main"],
                text=True, encoding="utf-8", errors="replace", env=git_env,
            ).strip()
        except Exception:
            pass
    build_info_path = os.path.join(script_dir, "build_info.json")
    with open(build_info_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": version,
                "commit": commit,
                "remote_main": remote_main,
                "build_date": datetime.now().isoformat(timespec="seconds"),
            },
            f,
            indent=4,
        )
    print(
        f"Build info: version {version}, commit {commit or 'unknown'}, "
        f"remote main {remote_main or 'unknown'}"
    )
    
    # Clean up old spec files to force PyInstaller to generate new ones with correct paths
    for spec in ["XenoPlayer.spec", "ocr_worker.spec"]:
        spec_path = os.path.join(script_dir, spec)
        if os.path.exists(spec_path):
            print(f"Removing old spec file: {spec}")
            try:
                os.remove(spec_path)
            except Exception as e:
                print(f"Warning: could not remove {spec}: {e}")
            
    manga_model_exists = os.path.exists(os.path.join(script_dir, "manga_ocr_model"))
    if not manga_model_exists:
        print("Warning: manga_ocr_model directory not found. Skipping bundling of the model files.")

    # PHASE A: Package the OCR background runtime execution engine
    print(f"Building background OCR worker binary in isolated process...")
    cmd_a = [
        sys.executable, "-m", "PyInstaller",
        ocr_script,
        '--onefile',
        '--clean',
        '--name=ocr_worker',
    ]
    if manga_model_exists:
        cmd_a.append('--add-data=manga_ocr_model;manga_ocr_model')
    cmd_a.extend([
        '--hidden-import=manga_ocr',
        '--collect-all=unidic_lite',
        '--collect-all=fugashi',
        '--collect-all=manga_ocr',
        '--collect-submodules=transformers',
        '--collect-data=transformers',
        '--collect-submodules=torch',
        '--exclude-module=torch.cuda',
        '--exclude-module=torch.utils.tensorboard',
        '--exclude-module=triton',
        '--noconfirm'
    ])
    subprocess.run(cmd_a, check=True)

    # PHASE B: Package the core application user interface layout
    print(f"Building application master player interface in isolated process...")
    cmd_b = [
        sys.executable, "-m", "PyInstaller",
        ui_script,
        '--onefile',
        '--windowed',
        '--clean',
        '--name=XenoPlayer',
        '--icon=icon.ico',
        '--add-data=web;web',
        f'--add-data={os.path.join(script_dir, "MAINLIST.json")};.',
        f'--add-data={os.path.join(script_dir, "version.json")};.',
        f'--add-data={os.path.join(script_dir, "build_info.json")};.',
    ]
    if manga_model_exists:
        cmd_b.append('--add-data=manga_ocr_model;manga_ocr_model')
    cmd_b.extend([
        # Bundle the worker executable inside the one-file app.
        f'--add-data={os.path.join(script_dir, "dist", "ocr_worker.exe")};.',
        
        '--hidden-import=PyQt6',
        '--hidden-import=pytesseract',
        '--hidden-import=speech_recognition',
        '--hidden-import=cloudscraper',
        '--hidden-import=bs4',
        '--hidden-import=edge_tts',
        '--collect-all=edge_tts',
        '--hidden-import=aiohttp',
        '--collect-all=aiohttp',
        '--hidden-import=cv2',
        '--hidden-import=numpy',
        '--hidden-import=deep_translator',
        '--hidden-import=send2trash',
        '--hidden-import=gallery_dl',
        '--hidden-import=flask',
        '--hidden-import=webview',
        '--hidden-import=cv2',  
        '--noconfirm'
    ])
    subprocess.run(cmd_b, check=True)
    
    # Copy dist/ocr_worker directory into dist/XenoPlayer/ocr_worker/
    onefile_exe = os.path.join(script_dir, "dist", "XenoPlayer.exe")
    worker_exe = os.path.join(script_dir, "dist", "ocr_worker.exe")
    if os.path.exists(onefile_exe):
        print(f"\nBuild complete: {onefile_exe}")
    else:
        print("\nWARNING: dist/XenoPlayer.exe was not produced.")
    if os.path.exists(worker_exe):
        print(f"OCR worker bundled from: {worker_exe}")
    print("Single-file build complete.")

if __name__ == "__main__":
    build()