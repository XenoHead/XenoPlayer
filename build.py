import os
import sys
import subprocess

def build():
    print("Checking for PyInstaller...")
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        
    import PyInstaller.__main__
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_script = os.path.join(script_dir, "XenoPlayer.py")
    
    print(f"Building executable for {target_script}...")
    PyInstaller.__main__.run([
        target_script,
        '--onefile',
        '--windowed',
        '--name=XenoPlayer',
        '--icon=icon.ico',
        '--add-data=web;web',
        '--add-data=manga_ocr_model;manga_ocr_model',
        '--hidden-import=PyQt6',
        '--hidden-import=pytesseract',
        '--hidden-import=speech_recognition',
        '--hidden-import=manga_ocr',
        '--hidden-import=cloudscraper',
        '--hidden-import=bs4',
        '--hidden-import=cv2',
        '--hidden-import=numpy',
        '--hidden-import=deep_translator',
        '--hidden-import=flask',
        '--hidden-import=webview',
        '--hidden-import=MangaViewer',
        '--noconfirm'
    ])
    print("\nBuild complete! You can find your standalone executable in the 'dist' folder.")

if __name__ == "__main__":
    build()