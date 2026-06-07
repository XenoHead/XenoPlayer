import os
lines = open('MEDIAPLAYER.py', encoding='utf-8', errors='replace').readlines()

out = []
# Imports and globals (lines 0 to 44)
out.extend(lines[0:45])

# SelectableImageLabel
out.extend(lines[211:241])

# TranslationWorker
out.extend(lines[241:294])

# SavedTranslationLabel
out.extend(lines[406:456])

# MangaViewerWindow
out.extend(lines[456:869])

# Execution block
out.append('\nif __name__ == "__main__":\n')
out.append('    import sys\n')
out.append('    app = QApplication.instance() or QApplication(sys.argv)\n')
out.append('    folder = sys.argv[1] if len(sys.argv) > 1 else ""\n')
out.append('    if not folder or not os.path.isdir(folder):\n')
out.append('        print("Please provide a valid directory.")\n')
out.append('        sys.exit(1)\n')
out.append('    image_paths = []\n')
out.append('    for f in os.listdir(folder):\n')
out.append('        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):\n')
out.append('            image_paths.append(os.path.join(folder, f))\n')
out.append('    import re\n')
out.append('    def natural_sort_key(s):\n')
out.append('        return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", os.path.basename(s))]\n')
out.append('    image_paths.sort(key=natural_sort_key)\n')
out.append('    window = MangaViewerWindow(folder, image_paths)\n')
out.append('    window.exec()\n')

with open('MangaViewer.py', 'w', encoding='utf-8') as f:
    f.writelines(out)
print('Created MangaViewer.py')
