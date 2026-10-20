import os
import sys

# 1. Force CPU mode and disable warnings
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# 2. CRITICAL: Disable transformers lazy-loading system to fix the 'name' is not defined bug
os.environ["TRANSFORMERS_DYNAMIC_MODULES_PREVENT_IMPORTS"] = "1"
os.environ["FORCE_TRANSFORMERS_NO_LAZY"] = "1" 

if getattr(sys, 'frozen', False):
    os.environ["TRANSFORMERS_CACHE"] = os.path.join(sys._MEIPASS, "manga_ocr_model")

class DummyWriter:
    encoding = 'utf-8'
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False
if sys.stdout is None: sys.stdout = DummyWriter()
if sys.stderr is None: sys.stderr = DummyWriter()

import shutil
import json
import hashlib
import re
import threading

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFileDialog, QListWidget, QListWidgetItem,
    QListView, QCheckBox, QSpinBox, QLabel, QDial,
    QSlider, QDialog, QMenu, QMenuBar, QInputDialog, QMessageBox,
    QAbstractItemView, QStackedWidget, QComboBox, QLineEdit,
    QRubberBand, QTextEdit, QScrollArea
    )

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QThread, pyqtSignal, QSize, QSettings, QPoint, QRect, QTimer
from PyQt6.QtGui import QImage, QPixmap, QIcon, QMovie, QKeySequence


def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Lazy-loaded so the app doesn't freeze on initial startup/download
manga_ocr_model = None

try:
    from PIL import Image, ImageDraw, ImageFont
    import argostranslate.package
    import argostranslate.translate
    import pytesseract
    
    # On Windows, automatically point to the default Tesseract install path if not in system PATH
    if os.name == 'nt' and not shutil.which('tesseract'):
        for path in [r'D:\Programs\Tesseract-OCR\tesseract.exe', r'C:\Program Files\Tesseract-OCR\tesseract.exe']:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break
    import tempfile
    
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False

def ensure_japanese_offline_model():
    """Guarantees the Japanese-to-English neural translation engine is ready on the CPU."""
    if not TRANSLATION_AVAILABLE:
        return
    try:
        # Sync index catalog without requiring API tokens
        argostranslate.package.update_package_index()
        
        # Verify if local cache already has the package
        installed = argostranslate.package.get_installed_packages()
        if not any(p.from_code == "ja" and p.to_code == "en" for p in installed):
            available = argostranslate.package.get_available_packages()
            ja_en_pack = next(filter(lambda x: x.from_code == "ja" and x.to_code == "en", available), None)
            if ja_en_pack:
                argostranslate.package.install_from_path(ja_en_pack.download())
    except Exception as e:
        print(f"Offline model sync skipped/failed: {e}")

class SelectableImageLabel(QLabel):
    selection_made = pyqtSignal(QRect)
    selection_cleared = pyqtSignal()    
    next_page_requested = pyqtSignal()
    prev_page_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.pos()
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()
        elif event.button() == Qt.MouseButton.RightButton:
            self.rubber_band.hide()
            self.selection_cleared.emit()
            self.next_page_requested.emit()
        elif event.button() == Qt.MouseButton.ForwardButton:
            self.next_page_requested.emit()
        elif event.button() == Qt.MouseButton.BackButton:
            self.prev_page_requested.emit()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.rubber_band.hide()
            rect = self.rubber_band.geometry()
            if rect.width() > 10 and rect.height() > 10:
                self.selection_made.emit(rect)
            else:
                self.prev_page_requested.emit()
            self.origin = QPoint()

class TranslationWorker(QThread):
    result_ready = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, image, ocr_mode, target_lang, priority_list=None):
        super().__init__()
        self.ocr_mode = ocr_mode
        self.target_lang = target_lang
        self.priority_list = priority_list or ["offline"]
        from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        self.img_bytes = ba.data()

    def run(self):
        import io
        import subprocess
        from PIL import Image
        import argostranslate.translate
        
        try:
            pil_img = Image.open(io.BytesIO(self.img_bytes))
            
            if self.ocr_mode == "Japanese (Manga OCR)":
                self.status_update.emit("Spawning OCR Worker Process...")
                
                temp_dir = tempfile.gettempdir()
                temp_img_path = os.path.join(temp_dir, "manga_ocr_crop.png")
                pil_img.save(temp_img_path)
                
                if getattr(sys, 'frozen', False):
                    exe_dir = os.path.dirname(sys.executable)
                    worker_exe = os.path.join(exe_dir, "ocr_worker", "ocr_worker.exe")
                    if not os.path.exists(worker_exe):
                        worker_exe = os.path.join(exe_dir, "ocr_worker.exe")
                    base_dir = sys._MEIPASS
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    worker_exe = sys.executable
                    
                model_path = find_manga_ocr_model_path()
                if getattr(sys, 'frozen', False):
                    cmd = [worker_exe, temp_img_path, model_path]
                else:
                    worker_script = os.path.join(base_dir, "ocr_worker.py")
                    cmd = [worker_exe, worker_script, temp_img_path, model_path]
                
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                        env=env, creationflags=creationflags)
                
                try: os.remove(temp_img_path)
                except: pass
                
                extracted_text = result.stdout.strip()
                
                if result.returncode != 0 or extracted_text.startswith("ERROR:"):
                    self.error_occurred.emit(f"OCR Worker Failed:\n{extracted_text}\n{result.stderr}")
                    return
                
                # Sanitize the string before processing
                extracted_text = extracted_text.replace(" ", "").replace("\n", "")
                source_lang = 'ja'
            else:
                import pytesseract
                self.status_update.emit(f"Reading text with Tesseract ({self.ocr_mode})...")
                lang_map = {
                    "Russian": ("rus", "ru"),
                    "Chinese (Simplified)": ("chi_sim", "zh"),
                    "Chinese (Traditional)": ("chi_tra", "zh"),
                    "English": ("eng", "en"),
                    "Japanese (Tesseract)": ("jpn", "ja")
                }
                tess_lang, source_lang = lang_map.get(self.ocr_mode, ("eng", "en"))
                extracted_text = pytesseract.image_to_string(pil_img, lang=tess_lang).strip()
            
            if not extracted_text:
                self.error_occurred.emit("No text recognized. Try selecting a tighter box around the text.")
                return

            self.status_update.emit("Processing translation...")
            
            # Dynamic destination fallback
            lang_code = self.target_lang.split("(")[-1].replace(")", "").strip()
            if "-" in lang_code: 
                lang_code = lang_code.split("-")[0] # Normalize 'zh-CN' to 'zh' style for Argos
                
            from translation_manager import get_best_translation
            translated_text = get_best_translation(extracted_text, source_lang, lang_code, self.priority_list)
            self.result_ready.emit(extracted_text, translated_text)
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            try:
                from translation_manager import log_translation_message
                log_translation_message(f"TranslationWorker.run failed: {e}\nTraceback:\n{tb}")
            except:
                pass
            self.error_occurred.emit(f"{str(e)}\n\n{tb}")

def find_manga_ocr_model_path():
    """Locates the manga_ocr_model directory in both dev and frozen states."""
    if getattr(sys, 'frozen', False):
        # In a frozen build, the model is in the _MEIPASS directory
        base_dir = sys._MEIPASS
    else:
        # In a dev environment, it's relative to this script
        base_dir = os.path.dirname(os.path.abspath(__file__))

    model_path = os.path.normpath(os.path.join(base_dir, 'manga_ocr_model'))
    if not os.path.exists(os.path.join(model_path, "config.json")):
        # Fallback for running from within a subfolder in dev
        model_path = os.path.normpath(os.path.join(base_dir, '..', 'manga_ocr_model'))

    return model_path

class SavedTranslationLabel(QLabel):
    deleted = pyqtSignal(object)
    updated = pyqtSignal(object)
    edit_requested = pyqtSignal(object)
    
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.trans_data = data
        self.setText(data.get("text", ""))
        self.setStyleSheet("background-color: rgba(0, 0, 0, 200); color: #fff200; font-weight: bold; padding: 5px; border-radius: 5px; border: 2px solid #4CAF50;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMouseTracking(True)
        self.resizing = False
        self.dragging = False
        self.drag_pos = None
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                self.edit_requested.emit(self)
            else:
                self.deleted.emit(self)
        elif event.button() == Qt.MouseButton.LeftButton:
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.pos().x() > self.width() - 15 and event.pos().y() > self.height() - 15:
                    self.resizing = True
                else:
                    self.dragging = True
                self.drag_pos = event.globalPosition().toPoint()
            else:
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.pos().x() > self.width() - 15 and event.pos().y() > self.height() - 15:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
        if self.dragging and self.drag_pos:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.drag_pos = event.globalPosition().toPoint()
        elif self.resizing and self.drag_pos:
            delta = event.globalPosition().toPoint() - self.drag_pos
            new_w = max(30, self.width() + delta.x())
            new_h = max(30, self.height() + delta.y())
            self.resize(new_w, new_h)
            self.drag_pos = event.globalPosition().toPoint()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.dragging or self.resizing:
                self.dragging = False
                self.resizing = False
                self.updated.emit(self)
            else:
                super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)

class HotkeyConfigDialog(QDialog):
    def __init__(self, current_next, current_prev, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Hotkeys")
        self.setStyleSheet("background-color: #222; color: white;")
        layout = QVBoxLayout(self)
        
        self.next_key = current_next
        self.prev_key = current_prev
        
        self.lbl_info = QLabel("Click a button and press any key to assign it.")
        layout.addWidget(self.lbl_info)
        
        self.btn_next = QPushButton(f"Next Page: {self.next_key}")
        self.btn_next.setStyleSheet("background-color: #333; color: white; padding: 10px;")
        self.btn_next.clicked.connect(self.record_next)
        layout.addWidget(self.btn_next)
        
        self.btn_prev = QPushButton(f"Prev Page: {self.prev_key}")
        self.btn_prev.setStyleSheet("background-color: #333; color: white; padding: 10px;")
        self.btn_prev.clicked.connect(self.record_prev)
        layout.addWidget(self.btn_prev)
        
        btn_box = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_ok)
        btn_box.addWidget(self.btn_cancel)
        layout.addLayout(btn_box)
        
        self.recording = None
        
    def record_next(self):
        self.recording = "next"
        self.btn_next.setText("Press any key...")
        self.btn_next.setFocus()
        
    def record_prev(self):
        self.recording = "prev"
        self.btn_prev.setText("Press any key...")
        self.btn_prev.setFocus()
        
    def keyPressEvent(self, event):
        if self.recording:
            key_code = event.key()
            key_str = QKeySequence(key_code).toString()
            if not key_str:
                key_str = str(key_code)
            
            if self.recording == "next":
                self.next_key = key_str
                self.btn_next.setText(f"Next Page: {self.next_key}")
            else:
                self.prev_key = key_str
                self.btn_prev.setText(f"Prev Page: {self.prev_key}")
            self.recording = None
            event.accept()
        else:
            super().keyPressEvent(event)


class CollectionViewerWindow(QDialog):
    def __init__(self, directory, image_paths, parent=None):
        super().__init__(parent)
        # Force-load local language assets on window launch in background to prevent UI freeze
        threading.Thread(target=ensure_japanese_offline_model, daemon=True).start()
        self.directory = directory
        self.image_paths = image_paths
        self.current_index = 0
        self.json_path = os.path.join(self.directory, "collection_info.json")
        self.current_pixmap = None
        
        self.collection_translations = {}
        self.saved_labels = []
        self.last_selection_rect = None
        self.last_translated_text = ""
        self.last_orig_text = ""
        
        self.view_mode = "fit"
        self.zoom_factor = 1.0
        
        self.settings = QSettings("XenoPlayer", "CollectionViewer")
        self.hotkey_next = self.settings.value("hotkey_next", "Right")
        self.hotkey_prev = self.settings.value("hotkey_prev", "Left")
        
        self.setWindowTitle("Collection Viewer")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.showMaximized()
        self.setStyleSheet("background-color: black; color: white;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
    def showEvent(self, event):
        super().showEvent(event)
        
        if hasattr(self, '_ui_setup_done'):
            return
        self._ui_setup_done = True

        layout = QVBoxLayout(self)
        
        # Top Bar
        top_layout = QHBoxLayout()
        
        self.page_count_label = QLabel("1/1")
        self.page_count_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #4da6ff; margin-right: 15px;")
        top_layout.addWidget(self.page_count_label)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter Collection Name...")
        self.name_edit.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        top_layout.addWidget(QLabel("Collection Name:"))
        top_layout.addWidget(self.name_edit)
        
        self.btn_save = QPushButton("Save Info")
        self.btn_save.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_save.clicked.connect(self.save_collection_info)
        top_layout.addWidget(self.btn_save)
        
        self.combo_ai_provider = QComboBox()
        self.combo_ai_provider.addItems(["Cloudflare", "Gemini", "Google Translate", "Offline"])
        self.combo_ai_provider.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        top_layout.addWidget(QLabel("AI Provider:"))
        top_layout.addWidget(self.combo_ai_provider)

        self.combo_ocr_lang = QComboBox()
        self.combo_ocr_lang.addItems(["Japanese (Manga OCR)", "Russian", "Chinese (Simplified)", "Chinese (Traditional)", "English", "Japanese (Tesseract)"])
        self.combo_ocr_lang.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        top_layout.addWidget(QLabel("OCR:"))
        top_layout.addWidget(self.combo_ocr_lang)
        
        self.combo_target_lang = QComboBox()
        self.combo_target_lang.addItems(["English (en)", "Spanish (es)", "French (fr)", "German (de)", "Italian (it)", "Portuguese (pt)", "Russian (ru)", "Chinese Simplified (zh-CN)", "Chinese Traditional (zh-TW)", "Japanese (ja)"])
        self.combo_target_lang.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        top_layout.addWidget(QLabel("To:"))
        top_layout.addWidget(self.combo_target_lang)

        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_fit.clicked.connect(self.set_fit_mode)
        top_layout.addWidget(self.btn_fit)

        self.btn_original = QPushButton("Original")
        self.btn_original.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_original.clicked.connect(self.set_original_mode)
        top_layout.addWidget(self.btn_original)

        self.btn_hotkeys = QPushButton("Hotkeys")
        self.btn_hotkeys.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_hotkeys.clicked.connect(self.configure_hotkeys)
        top_layout.addWidget(self.btn_hotkeys)
        
        self.btn_close = QPushButton("Close Viewer")
        self.btn_close.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_close.clicked.connect(self.close)
        top_layout.addWidget(self.btn_close)
        
        layout.addLayout(top_layout)
        
        # Image Display
        self.image_label = SelectableImageLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.selection_made.connect(self.process_translation)
        self.image_label.selection_cleared.connect(self.hide_translation)        
        self.image_label.next_page_requested.connect(self.go_next_page)
        self.image_label.prev_page_requested.connect(self.go_prev_page)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: black; border: none;")
        self.scroll_area.setWidget(self.image_label)
        
        layout.addWidget(self.scroll_area, stretch=1)
        
        # Translation Overlay (Interactive)
        self.translation_container = QWidget(self)
        self.translation_container.setStyleSheet("background-color: rgba(0, 0, 0, 220); border-radius: 8px;")
        container_layout = QVBoxLayout(self.translation_container)
        
        self.translation_text = QTextEdit()
        self.translation_text.setStyleSheet("color: #fff200; font-size: 22px; font-weight: bold; background: transparent; border: none;")
        self.translation_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.translation_text.setAcceptRichText(False)
        self.translation_text.setMaximumWidth(800)
        self.translation_text.setMaximumHeight(150)
        
        buttons_layout = QHBoxLayout()
        self.btn_save_translation = QPushButton("Save Translation")
        self.btn_save_translation.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px; border-radius: 3px; font-size: 16px;")
        self.btn_save_translation.clicked.connect(self.save_current_translation)
        self.btn_save_translation.hide()
        
        self.btn_burn_translation = QPushButton("🔥 Burn to Image")
        self.btn_burn_translation.setStyleSheet("background-color: #d32f2f; color: white; padding: 5px; border-radius: 3px; font-size: 16px;")
        self.btn_burn_translation.clicked.connect(self.burn_current_translation)
        self.btn_burn_translation.hide()
        
        buttons_layout.addWidget(self.btn_save_translation)
        buttons_layout.addWidget(self.btn_burn_translation)
        
        container_layout.addWidget(self.translation_text)
        container_layout.addLayout(buttons_layout)
        self.translation_container.hide()
        
        # Bottom Bar
        bottom_layout = QHBoxLayout()
        
        bottom_layout.addStretch()
        
        bottom_layout.addWidget(QLabel("⏱️ Auto-Advance:"))
        self.timer_spinbox = QSpinBox()
        self.timer_spinbox.setRange(0, 10)
        self.timer_spinbox.setSuffix("s")
        self.timer_spinbox.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.timer_spinbox.valueChanged.connect(self.update_auto_timer)
        bottom_layout.addWidget(self.timer_spinbox)
        
        layout.addLayout(bottom_layout)
        
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.go_next_page)
        
        # Toast Notification
        self.toast_label = QLabel(self)
        self.toast_label.setStyleSheet("background-color: rgba(200, 50, 50, 230); color: white; font-size: 18px; font-weight: bold; padding: 10px 20px; border-radius: 5px;")
        self.toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_label.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.timeout.connect(self.toast_label.hide)
        self.toast_timer.setSingleShot(True)
        
        self.load_collection_info()
        self.load_current_image()
        
        self.setFocus()
        
        # Ensure the first image sizes correctly after layout
        QTimer.singleShot(100, self.update_image_view)

    def update_auto_timer(self, val):
        if val > 0:
            self.auto_timer.start(val * 1000)
        else:
            self.auto_timer.stop()
        
    def show_toast(self, message, is_error=True):
        if is_error:
            try:
                from translation_manager import log_translation_message
                log_translation_message(f"ERROR TOAST: {message}")
            except:
                pass
            return
        bg_color = "rgba(50, 200, 50, 230)"
        self.toast_label.setStyleSheet(f"background-color: {bg_color}; color: white; font-size: 18px; font-weight: bold; padding: 10px 20px; border-radius: 5px;")
        self.toast_label.setText(message)
        self.toast_label.adjustSize()
        ox = (self.width() - self.toast_label.width()) // 2
        self.toast_label.move(ox, 20) # Top of the screen
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start(3000)
        
    def load_collection_info(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'name' in data:
                        self.name_edit.setText(data['name'])
                    if 'translations' in data:
                        self.collection_translations = data['translations']
                    if 'order' in data:
                        saved_order = data['order']
                        valid_saved = [os.path.join(self.directory, p) for p in saved_order if os.path.exists(os.path.join(self.directory, p))]
                        for img in self.image_paths:
                            if img not in valid_saved:
                                valid_saved.append(img)
                        self.image_paths = valid_saved
                    if 'last_index' in data:
                        idx = data['last_index']
                        if 0 <= idx < len(self.image_paths):
                            self.current_index = idx
            except Exception as e:
                print(f"Error loading collection info: {e}")
                
    def save_collection_info(self, silent=False):
        if type(silent) is not bool:
            silent = False
        data = {
            "name": self.name_edit.text(),
            "order": [os.path.basename(p) for p in self.image_paths],
            "translations": self.collection_translations,
            "last_index": self.current_index
        }
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            collection_marker = os.path.join(self.directory, ".collection")
            if not os.path.exists(collection_marker):
                open(collection_marker, 'w').close()
            if not silent:
                self.show_toast("Collection info saved successfully!", is_error=False)
            self.name_edit.clearFocus()
            self.setFocus()
        except Exception as e:
            self.show_toast(f"Failed to save: {e}")
            
    def load_current_image(self):
        if 0 <= self.current_index < len(self.image_paths):
            self.hide_translation()
            path = self.image_paths[self.current_index]
            self.current_pixmap = QPixmap(path)
            self.update_image_view()
            self.render_saved_translations()
            if self.timer_spinbox.value() > 0:
                self.auto_timer.start(self.timer_spinbox.value() * 1000)
            
    def hide_translation(self):
        if hasattr(self, 'translation_container'):
            self.translation_container.hide()

    def process_translation(self, rect):
        self.last_selection_rect = rect
        cropped = self.image_label.grab(rect).toImage()
        selected_provider = self.combo_ai_provider.currentText().lower()
        
        provider_map = {
            "cloudflare": "cloudflare",
            "gemini": "gemini",
            "google translate": "google",
            "offline": "offline"
        }
        provider = provider_map.get(selected_provider, "offline")
        
        self.translation_worker = TranslationWorker(
            cropped, 
            self.combo_ocr_lang.currentText(), 
            self.combo_target_lang.currentText(),
            priority_list=[provider]
        )
        self.translation_worker.result_ready.connect(self.show_translation)
        self.translation_worker.error_occurred.connect(self.show_translation_error)
        self.translation_worker.status_update.connect(self.show_translation_status)
        self.translation_worker.start()
        self.setWindowTitle("Collection Viewer - TRANSLATING...")
        self.hide_translation()
        
    def show_translation_status(self, status_text):
        self.translation_text.setText(status_text)
        self.btn_save_translation.hide()
        self.btn_burn_translation.hide()
        self.translation_container.adjustSize()
        
        ox = (self.width() - self.translation_container.width()) // 2
        oy = self.height() - self.translation_container.height() - 50
        self.translation_container.move(ox, oy)
        self.translation_container.show()
        self.translation_container.raise_()

    def show_translation(self, orig, translated):
        self.update_image_view() # Restore title
        self.last_orig_text = orig
        self.last_translated_text = translated
        
        self.translation_text.setText(translated)
        if self.last_selection_rect:
            self.btn_save_translation.show()
            self.btn_burn_translation.show()
        else:
            self.btn_save_translation.hide()
            self.btn_burn_translation.hide()
            
        self.translation_container.adjustSize()
        
        ox = (self.width() - self.translation_container.width()) // 2
        oy = self.height() - self.translation_container.height() - 50
        self.translation_container.move(ox, oy)
        self.translation_container.show()
        self.translation_container.raise_()
        
    def save_current_translation(self):
        if not self.current_pixmap or not self.last_selection_rect: return
        
        filename = os.path.basename(self.image_paths[self.current_index])
        
        # Map widget rect to original image rect
        lbl_size = self.image_label.size()
        pix_size = self.current_pixmap.size()
        scaled_size = pix_size.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio)
        
        offset_x = (lbl_size.width() - scaled_size.width()) / 2
        offset_y = (lbl_size.height() - scaled_size.height()) / 2
        
        sx = self.last_selection_rect.x() - offset_x
        sy = self.last_selection_rect.y() - offset_y
        sw = self.last_selection_rect.width()
        sh = self.last_selection_rect.height()
        
        ratio_w = pix_size.width() / scaled_size.width()
        ratio_h = pix_size.height() / scaled_size.height()
        
        orig_x = int(sx * ratio_w)
        orig_y = int(sy * ratio_h)
        orig_w = int(sw * ratio_w)
        orig_h = int(sh * ratio_h)
        
        current_text = self.translation_text.toPlainText()
        
        trans_data = {
            "rect": [orig_x, orig_y, orig_w, orig_h],
            "text": current_text,
            "orig": self.last_orig_text
        }
        
        if filename not in self.collection_translations:
            self.collection_translations[filename] = []
        self.collection_translations[filename].append(trans_data)
        
        self.save_collection_info()
        self.hide_translation()
        self.render_saved_translations()
        
    def burn_current_translation(self):
        if not self.current_pixmap or not self.last_selection_rect: return
        
        filepath = self.image_paths[self.current_index]
        
        # Map widget rect to original image rect
        lbl_size = self.image_label.size()
        pix_size = self.current_pixmap.size()
        scaled_size = pix_size.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio)
        
        offset_x = (lbl_size.width() - scaled_size.width()) / 2
        offset_y = (lbl_size.height() - scaled_size.height()) / 2
        
        sx = self.last_selection_rect.x() - offset_x
        sy = self.last_selection_rect.y() - offset_y
        sw = self.last_selection_rect.width()
        sh = self.last_selection_rect.height()
        
        ratio_w = pix_size.width() / scaled_size.width()
        ratio_h = pix_size.height() / scaled_size.height()
        
        orig_x = int(sx * ratio_w)
        orig_y = int(sy * ratio_h)
        orig_w = int(sw * ratio_w)
        orig_h = int(sh * ratio_h)
        
        current_text = self.translation_text.toPlainText()
        
        import subprocess
        magick_path = r"D:\Programs\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
        
        try:
            # Build the ImageMagick command using 'caption:' for auto-wrapping and auto-sizing
            cmd = [
                magick_path,
                filepath,
                "-size", f"{orig_w}x{orig_h}",
                "-background", "white",
                "-fill", "black",
                "-gravity", "center",
                f"caption:{current_text}",
                "-geometry", f"+{orig_x}+{orig_y}",
                "-composite",
                filepath
            ]
            
            # Hide the command prompt window on Windows
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            
            subprocess.run(cmd, check=True, creationflags=creationflags)
            
            self.show_toast("Text burned flawlessly via ImageMagick!", is_error=False)
            
            self.hide_translation()
            # Reload the newly modified image
            self.current_pixmap = QPixmap(filepath)
            self.update_image_view()
            self.render_saved_translations()
            
        except FileNotFoundError:
            self.show_toast("ImageMagick not found at the specified path.")
        except subprocess.CalledProcessError as e:
            self.show_toast(f"ImageMagick failed with error code: {e.returncode}")
        except Exception as e:
            self.show_toast(f"Failed to burn text: {e}")
        
    def show_translation_error(self, err):
        self.update_image_view()
        self.hide_translation()
        self.show_toast(f"Could not translate: {err}")
            
    def set_fit_mode(self):
        self.view_mode = "fit"
        self.update_image_view()
        self.render_saved_translations()

    def set_original_mode(self):
        self.view_mode = "original"
        self.update_image_view()
        self.render_saved_translations()

    def configure_hotkeys(self):
        dialog = HotkeyConfigDialog(self.hotkey_next, self.hotkey_prev, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.hotkey_next = dialog.next_key
            self.hotkey_prev = dialog.prev_key
            self.settings.setValue("hotkey_next", self.hotkey_next)
            self.settings.setValue("hotkey_prev", self.hotkey_prev)
            self.show_toast(f"Hotkeys updated! Next: {self.hotkey_next}, Prev: {self.hotkey_prev}", is_error=False)

    def update_image_view(self):
        if self.current_pixmap and not self.current_pixmap.isNull():
            if self.view_mode == "fit":
                viewport_size = self.scroll_area.viewport().size()
                target_size = self.current_pixmap.size().scaled(viewport_size, Qt.AspectRatioMode.KeepAspectRatio)
            elif self.view_mode == "original":
                target_size = self.current_pixmap.size()
            else:
                target_size = self.current_pixmap.size() * self.zoom_factor
                
            scaled_pixmap = self.current_pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setFixedSize(target_size)
            self.setWindowTitle(f"Collection Viewer - {self.name_edit.text() or 'Unknown'} - ({self.current_index + 1}/{len(self.image_paths)})")
            if hasattr(self, 'page_count_label'):
                self.page_count_label.setText(f"Page: {self.current_index + 1} / {len(self.image_paths)}")
            
    def render_saved_translations(self):
        for lbl in self.saved_labels:
            lbl.deleteLater()
        self.saved_labels.clear()
        
        if not self.current_pixmap: return
        filename = os.path.basename(self.image_paths[self.current_index])
        if filename not in self.collection_translations: return
        
        lbl_size = self.image_label.size()
        pix_size = self.current_pixmap.size()
        scaled_size = pix_size.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio)
        
        offset_x = (lbl_size.width() - scaled_size.width()) / 2
        offset_y = (lbl_size.height() - scaled_size.height()) / 2
        ratio_w = scaled_size.width() / pix_size.width()
        ratio_h = scaled_size.height() / pix_size.height()
        
        for t_data in self.collection_translations[filename]:
            rect = t_data.get("rect", [0, 0, 0, 0])
            x = int(rect[0] * ratio_w + offset_x)
            y = int(rect[1] * ratio_h + offset_y)
            w = int(rect[2] * ratio_w)
            h = int(rect[3] * ratio_h)
            
            lbl = SavedTranslationLabel(t_data, self.image_label)
            lbl.move(x, y)
            lbl.setFixedWidth(w)
            lbl.adjustSize()
            lbl.deleted.connect(self.delete_saved_translation)
            lbl.updated.connect(self.update_saved_translation)
            lbl.edit_requested.connect(self.edit_saved_translation)
            lbl.show()
            self.saved_labels.append(lbl)
            
    def update_saved_translation(self, lbl):
        filename = os.path.basename(self.image_paths[self.current_index])
        if filename not in self.collection_translations: return
        
        lbl_size = self.image_label.size()
        pix_size = self.current_pixmap.size()
        scaled_size = pix_size.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio)
        
        offset_x = (lbl_size.width() - scaled_size.width()) / 2
        offset_y = (lbl_size.height() - scaled_size.height()) / 2
        
        ratio_w = pix_size.width() / scaled_size.width()
        ratio_h = pix_size.height() / scaled_size.height()
        
        rect = lbl.geometry()
        sx = rect.x() - offset_x
        sy = rect.y() - offset_y
        
        orig_x = int(sx * ratio_w)
        orig_y = int(sy * ratio_h)
        orig_w = int(rect.width() * ratio_w)
        orig_h = int(rect.height() * ratio_h)
        
        # update trans_data inplace
        lbl.trans_data["rect"] = [orig_x, orig_y, orig_w, orig_h]
        self.save_collection_info(silent=True)
            
    def edit_saved_translation(self, lbl):
        current_text = lbl.trans_data.get("text", "")
        new_text, ok = QInputDialog.getMultiLineText(self, "Edit Translation", "Enter new text:", current_text)
        if ok and new_text != current_text:
            lbl.trans_data["text"] = new_text
            lbl.setText(new_text)
            self.save_collection_info(silent=True)
            
    def delete_saved_translation(self, lbl):
        filename = os.path.basename(self.image_paths[self.current_index])
        if filename in self.collection_translations:
            if lbl.trans_data in self.collection_translations[filename]:
                self.collection_translations[filename].remove(lbl.trans_data)
                self.save_collection_info(silent=True)
        self.render_saved_translations()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image_view()
        self.render_saved_translations()
        
    def go_next_page(self):
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self.load_current_image()

    def go_prev_page(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()

    def keyPressEvent(self, event):
        key_str = QKeySequence(event.key()).toString()
        if key_str == self.hotkey_next:
            self.go_next_page()
            event.accept()
        elif key_str == self.hotkey_prev:
            self.go_prev_page()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)
            
    def closeEvent(self, event):
        super().closeEvent(event)
            
    def wheelEvent(self, event):
        if not self.current_pixmap or self.current_pixmap.isNull():
            super().wheelEvent(event)
            return
        
        angle = event.angleDelta().y()
        if angle != 0:
            if self.view_mode == "fit":
                viewport_size = self.scroll_area.viewport().size()
                current_size = self.current_pixmap.size().scaled(viewport_size, Qt.AspectRatioMode.KeepAspectRatio)
                self.zoom_factor = current_size.width() / self.current_pixmap.width()
            elif self.view_mode == "original":
                self.zoom_factor = 1.0
            
            if angle > 0:
                self.zoom_factor *= 1.1
            else:
                self.zoom_factor /= 1.1
                
            self.zoom_factor = max(0.1, min(self.zoom_factor, 10.0))
            self.view_mode = "zoom"
            self.update_image_view()
            self.render_saved_translations()
            event.accept()
        else:
            super().wheelEvent(event)


def main():
    import traceback
    try:
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        folder = sys.argv[1] if len(sys.argv) > 1 else ""
        if folder and os.path.isfile(folder):
            folder = os.path.dirname(folder)
        if not folder or not os.path.isdir(folder):
            folder = QFileDialog.getExistingDirectory(None, "Select Collection Folder")
        if not folder:
            return
        image_paths = []
        for f in os.listdir(folder):
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                image_paths.append(os.path.join(folder, f))
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", os.path.basename(s))]
        image_paths.sort(key=natural_sort_key)
        window = CollectionViewerWindow(folder, image_paths)
        window.exec()
    except Exception as e:
        with open("crash_log.txt", "w") as f:
            f.write(traceback.format_exc())
        print(f"Crashed! Log written to crash_log.txt: {e}")

if __name__ == "__main__":
    main()