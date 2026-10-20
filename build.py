import os
import sys
import subprocess
import shutil

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
        '--onedir',
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
        '--onedir',        
        '--windowed',
        '--clean',
        '--name=XenoPlayer',
        '--icon=icon.ico',
        '--add-data=web;web',
        f'--add-data={os.path.join(script_dir, "MAINLIST.json")};.',
    ]
    if manga_model_exists:
        cmd_b.append('--add-data=manga_ocr_model;manga_ocr_model')
    cmd_b.extend([
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
        '--hidden-import=cv2',  
        '--noconfirm'
    ])
    subprocess.run(cmd_b, check=True)
    
    # Copy dist/ocr_worker directory into dist/XenoPlayer/ocr_worker/
    src_dir = os.path.join(script_dir, "dist", "ocr_worker")
    dst_dir = os.path.join(script_dir, "dist", "XenoPlayer", "ocr_worker")
    if os.path.exists(src_dir):
        print("Copying background OCR worker directory to XenoPlayer release package...")
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)
    else:
        print(f"WARNING: Background OCR worker source directory not found at: {src_dir}")
    
    print("\nBuild complete! Check inside 'dist/XenoPlayer' for your completed execution directory.")

if __name__ == "__main__":
    build()