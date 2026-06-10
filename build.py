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
    ui_script = os.path.join(script_dir, "XenoPlayer.py")
    ocr_script = os.path.join(script_dir, "ocr_worker.py")
    
    # PHASE A: Package the OCR background runtime execution engine
    print(f"Building background OCR worker binary...")
    PyInstaller.__main__.run([
        ocr_script,
        '--onedir',
        # NOTE: do NOT use --windowed here. windowed mode disables stdout,
        # which breaks capture_output=True in the parent. The flash window
        # is suppressed by CREATE_NO_WINDOW in the subprocess call instead.
        '--clean',
        '--name=ocr_worker',
        '--add-data=manga_ocr_model;manga_ocr_model',
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

    # PHASE B: Package the core application user interface layout
    print(f"Building application master player interface...")
    PyInstaller.__main__.run([
        ui_script,
        '--onedir',        
        '--windowed',
        '--clean',
        '--name=XenoPlayer',
        '--icon=icon.ico',
        '--add-data=web;web',
        '--add-data=manga_ocr_model;manga_ocr_model',
        
        # Inject the newly compiled asset binary folder layout
        f'--add-data={os.path.join(script_dir, "dist", "ocr_worker", "ocr_worker.exe")};.',
        
        '--hidden-import=PyQt6',
        '--hidden-import=pytesseract',
        '--hidden-import=speech_recognition',
        '--hidden-import=cloudscraper',
        '--hidden-import=bs4',
        '--hidden-import=cv2',
        '--hidden-import=numpy',
        '--hidden-import=deep_translator',
        '--hidden-import=send2trash',
        '--hidden-import=gallery_dl',
        '--hidden-import=flask',
        '--hidden-import=webview',
        '--noconfirm'
    ])
    
print("\nBuild complete! Check inside 'dist/XenoPlayer' for your completed execution directory.")

if __name__ == "__main__":
    build()