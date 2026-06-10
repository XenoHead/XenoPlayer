import os
import sys
import io

# Force UTF-8 on stdout/stderr so Japanese text survives the pipe.
# fileno() raises when there is no real console (--windowed frozen build),
# so we fall back to wrapping the binary buffer directly.
try:
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
try:
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)
except Exception:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Completely lock out CUDA calls and disconnect from the network
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# Force transformers to disable lazy structural loading
os.environ["TRANSFORMERS_DYNAMIC_MODULES_PREVENT_IMPORTS"] = "1"
os.environ["FORCE_TRANSFORMERS_NO_LAZY"] = "1"

def main():
    if len(sys.argv) < 3:
        print("ERROR: Missing parameters.")
        sys.exit(1)

    img_path = sys.argv[1]
    model_path = sys.argv[2]

    try:
        from PIL import Image
        from manga_ocr import MangaOcr
        
        if not os.path.exists(img_path):
            print("ERROR: Image crop file missing.")
            sys.exit(1)

        img = Image.open(img_path)
        
        if os.path.exists(model_path) and os.path.exists(os.path.join(model_path, "config.json")):
            mocr = MangaOcr(pretrained_model_name_or_path=model_path)
        else:
            mocr = MangaOcr()

        text = mocr(img).strip()
        # Write directly to the binary buffer to guarantee UTF-8 bytes
        # reach the parent process pipe regardless of stdout wrapping state.
        sys.stdout.buffer.write((text + '\n').encode('utf-8'))
        sys.stdout.buffer.flush()
        
    except Exception as e:
        import traceback
        print(f"ERROR: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()