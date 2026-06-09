import sys
import os
import shutil
import json
import hashlib
import re
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QListWidget, QListWidgetItem,
                             QListView, QCheckBox, QSpinBox, QLabel, QDial,
                             QSlider, QDialog, QMenu, QMenuBar, QInputDialog, QMessageBox,
                             QAbstractItemView, QStackedWidget, QComboBox, QLineEdit,
                             QRubberBand, QTextEdit)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QThread, pyqtSignal, QSize, QSettings, QPoint, QRect, QTimer
from PyQt6.QtGui import QImage, QPixmap, QIcon, QMovie

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

try:
    from PIL import Image, ImageDraw, ImageFont
    from deep_translator import GoogleTranslator
    import pytesseract
    
    # On Windows, automatically point to the default Tesseract install path if not in system PATH
    if os.name == 'nt' and not shutil.which('tesseract'):
        for path in [r'D:\Programs\Tesseract-OCR\tesseract.exe', r'C:\Program Files\Tesseract-OCR\tesseract.exe']:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break
    import tempfile
    
    # Lazy-loaded so the app doesn't freeze on initial startup/download
    manga_ocr_model = None
            
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False

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

    def __init__(self, image, ocr_mode, target_lang):
        super().__init__()
        self.ocr_mode = ocr_mode
        self.target_lang = target_lang
        from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        self.img_bytes = ba.data()

    def run(self):
        import io
        from PIL import Image
        from deep_translator import GoogleTranslator
        global manga_ocr_model
        try:
            pil_img = Image.open(io.BytesIO(self.img_bytes))
            
            if self.ocr_mode == "Japanese (Manga OCR)":
                if manga_ocr_model is None:
                    self.status_update.emit("Initializing AI Model...")
                    from manga_ocr import MangaOcr
                    model_path = resource_path('manga_ocr_model')
                    if os.path.exists(model_path):
                        manga_ocr_model = MangaOcr(pretrained_model_name_or_path=model_path)
                    else:
                        manga_ocr_model = MangaOcr()
                    
                self.status_update.emit("Reading text with Manga OCR...")
                extracted_text = manga_ocr_model(pil_img).strip()
                source_lang = 'ja'
            else:
                import pytesseract
                self.status_update.emit(f"Reading text with Tesseract ({self.ocr_mode})...")
                lang_map = {
                    "Russian": ("rus", "ru"),
                    "Chinese (Simplified)": ("chi_sim", "zh-CN"),
                    "Chinese (Traditional)": ("chi_tra", "zh-TW"),
                    "English": ("eng", "en"),
                    "Japanese (Tesseract)": ("jpn", "ja")
                }
                tess_lang, source_lang = lang_map.get(self.ocr_mode, ("eng", "en"))
                extracted_text = pytesseract.image_to_string(pil_img, lang=tess_lang).strip()
            
            if not extracted_text:
                self.error_occurred.emit("No text recognized. Try selecting a tighter box around the text.")
                return

            self.status_update.emit("Translating text...")
            lang_code = self.target_lang.split("(")[-1].replace(")", "").strip()
            translated_text = GoogleTranslator(source=source_lang, target=lang_code).translate(extracted_text)
            self.result_ready.emit(extracted_text, translated_text)
        except Exception as e:
            self.error_occurred.emit(str(e))
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
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.edit_requested.emit(self)
            else:
                self.deleted.emit(self)
        elif event.button() == Qt.MouseButton.LeftButton:
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
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
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
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

class VoiceListenerThread(QThread):
    next_page = pyqtSignal()
    prev_page = pyqtSignal()
    status_update = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True

    def run(self):
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                self.status_update.emit("calibrating")
                print("Voice control activated. Calibrating to ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Listening for voice commands ('next', 'back')...")
                self.status_update.emit("listening")
                while self.running:
                    try:
                        audio = recognizer.listen(source, timeout=1, phrase_time_limit=3)
                        self.status_update.emit("processing")
                        text = recognizer.recognize_google(audio).lower()
                        print(f"Voice recognized: {text}")
                        self.status_update.emit("recognized")
                        if "next" in text or "forward" in text or "next page" in text:
                            self.next_page.emit()
                        elif "back" in text or "previous" in text or "prev page" in text:
                            self.prev_page.emit()
                        import time
                        time.sleep(0.5)
                        self.status_update.emit("listening")
                    except sr.WaitTimeoutError:
                        self.status_update.emit("listening")
                        continue
                    except sr.UnknownValueError:
                        self.status_update.emit("listening")
                        continue
                    except sr.RequestError as e:
                        print(f"Voice Request Error: {e}")
                        self.status_update.emit("error")
                        import time; time.sleep(1)
                        self.status_update.emit("listening")
                        continue
                    except Exception as e:
                        print(f"Voice loop error: {e}")
                        self.status_update.emit("error")
                        import time; time.sleep(1)
                        self.status_update.emit("listening")
                        continue
        except Exception as e:
            print(f"Fatal Voice Error (e.g. missing dependencies/microphone): {e}")
            self.status_update.emit("fatal")
            return

    def stop(self):
        self.running = False
        self.wait()

class MangaViewerWindow(QDialog):
    def __init__(self, directory, image_paths, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.image_paths = image_paths
        self.current_index = 0
        self.json_path = os.path.join(self.directory, "manga_info.json")
        self.current_pixmap = None
        
        self.manga_translations = {}
        self.saved_labels = []
        self.last_selection_rect = None
        self.last_translated_text = ""
        self.last_orig_text = ""
        
        self.setWindowTitle("Manga Viewer")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.showMaximized()
        self.setStyleSheet("background-color: black; color: white;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
    def showEvent(self, event):
        super().showEvent(event)
        self.showMaximized()
        
        layout = QVBoxLayout(self)
        
        # Top Bar
        top_layout = QHBoxLayout()
        
        self.page_count_label = QLabel("1/1")
        self.page_count_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #4da6ff; margin-right: 15px;")
        top_layout.addWidget(self.page_count_label)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter Manga Name...")
        self.name_edit.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        top_layout.addWidget(QLabel("Manga Name:"))
        top_layout.addWidget(self.name_edit)
        
        self.btn_save = QPushButton("Save Info")
        self.btn_save.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_save.clicked.connect(self.save_manga_info)
        top_layout.addWidget(self.btn_save)
        
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
        layout.addWidget(self.image_label, stretch=1)
        
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
        
        self.btn_voice = QPushButton("🎤 Voice: ON")
        self.btn_voice.setCheckable(True)
        self.btn_voice.setChecked(True)
        self.btn_voice.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px; border-radius: 3px;")
        self.btn_voice.clicked.connect(self.toggle_voice)
        bottom_layout.addWidget(self.btn_voice)
        
        self.voice_indicator = QLabel("🟡 Calibrating...")
        self.voice_indicator.setStyleSheet("color: yellow; font-weight: bold; margin-left: 10px;")
        bottom_layout.addWidget(self.voice_indicator)
        
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
        
        self.load_manga_info()
        self.load_current_image()
        
        self.voice_thread = VoiceListenerThread(self)
        self.voice_thread.next_page.connect(self.go_next_page)
        self.voice_thread.prev_page.connect(self.go_prev_page)
        self.voice_thread.status_update.connect(self.handle_voice_status)
        self.voice_thread.start()
        
        self.setFocus()
        
        # Ensure the first image sizes correctly after layout
        QTimer.singleShot(100, self.update_image_view)

    def handle_voice_status(self, status):
        if status == "calibrating":
            self.voice_indicator.setText("🟡 Calibrating...")
            self.voice_indicator.setStyleSheet("color: yellow; font-weight: bold; margin-left: 10px;")
        elif status == "listening":
            self.voice_indicator.setText("🟢 Listening...")
            self.voice_indicator.setStyleSheet("color: #4CAF50; font-weight: bold; margin-left: 10px;")
        elif status == "processing":
            self.voice_indicator.setText("🔵 Processing...")
            self.voice_indicator.setStyleSheet("color: #2196F3; font-weight: bold; margin-left: 10px;")
        elif status == "recognized":
            self.voice_indicator.setText("✨ Heard!")
            self.voice_indicator.setStyleSheet("color: #E040FB; font-weight: bold; margin-left: 10px;")
        elif status == "error":
            self.voice_indicator.setText("🔴 Error")
            self.voice_indicator.setStyleSheet("color: #F44336; font-weight: bold; margin-left: 10px;")
        elif status == "fatal":
            self.voice_indicator.setText("❌ Offline (Mic/Libs Error)")
            self.voice_indicator.setStyleSheet("color: #9E9E9E; font-weight: bold; margin-left: 10px;")
            self.btn_voice.setChecked(False)
            self.btn_voice.setText("🎤 Voice: OFF")
            self.btn_voice.setStyleSheet("background-color: #555; color: white; padding: 5px; border-radius: 3px;")

    def toggle_voice(self, checked):
        if checked:
            self.btn_voice.setText("🎤 Voice: ON")
            self.btn_voice.setStyleSheet("background-color: #4CAF50; color: white; padding: 5px; border-radius: 3px;")
            self.voice_thread = VoiceListenerThread(self)
            self.voice_thread.next_page.connect(self.go_next_page)
            self.voice_thread.prev_page.connect(self.go_prev_page)
            self.voice_thread.status_update.connect(self.handle_voice_status)
            self.voice_thread.start()
        else:
            self.btn_voice.setText("🎤 Voice: OFF")
            self.btn_voice.setStyleSheet("background-color: #555; color: white; padding: 5px; border-radius: 3px;")
            if self.voice_thread:
                self.voice_thread.stop()
                self.voice_thread = None
            self.voice_indicator.setText("⚪ Disabled")
            self.voice_indicator.setStyleSheet("color: #9E9E9E; font-weight: bold; margin-left: 10px;")
            
    def update_auto_timer(self, val):
        if val > 0:
            self.auto_timer.start(val * 1000)
        else:
            self.auto_timer.stop()
        
    def show_toast(self, message, is_error=True):
        bg_color = "rgba(200, 50, 50, 230)" if is_error else "rgba(50, 200, 50, 230)"
        self.toast_label.setStyleSheet(f"background-color: {bg_color}; color: white; font-size: 18px; font-weight: bold; padding: 10px 20px; border-radius: 5px;")
        self.toast_label.setText(message)
        self.toast_label.adjustSize()
        ox = (self.width() - self.toast_label.width()) // 2
        self.toast_label.move(ox, 20) # Top of the screen
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start(3000)
        
    def load_manga_info(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'name' in data:
                        self.name_edit.setText(data['name'])
                    if 'translations' in data:
                        self.manga_translations = data['translations']
                    if 'order' in data:
                        saved_order = data['order']
                        valid_saved = [os.path.join(self.directory, p) for p in saved_order if os.path.exists(os.path.join(self.directory, p))]
                        for img in self.image_paths:
                            if img not in valid_saved:
                                valid_saved.append(img)
                        self.image_paths = valid_saved
            except Exception as e:
                print(f"Error loading manga info: {e}")
                
    def save_manga_info(self):
        data = {
            "name": self.name_edit.text(),
            "order": [os.path.basename(p) for p in self.image_paths],
            "translations": self.manga_translations
        }
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            self.show_toast("Manga info saved successfully!", is_error=False)
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
        if not self.current_pixmap: return
        if not TRANSLATION_AVAILABLE:
            self.show_toast("Dependencies Missing: run 'pip install manga-ocr Pillow deep-translator'")
            return
            
        self.last_selection_rect = rect
        cropped = self.image_label.grab(rect).toImage()
        self.translation_worker = TranslationWorker(cropped, self.combo_ocr_lang.currentText(), self.combo_target_lang.currentText())
        self.translation_worker.result_ready.connect(self.show_translation)
        self.translation_worker.error_occurred.connect(self.show_translation_error)
        self.translation_worker.status_update.connect(self.show_translation_status)
        self.translation_worker.start()
        self.setWindowTitle(f"Manga Viewer - TRANSLATING...")
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
        
        if filename not in self.manga_translations:
            self.manga_translations[filename] = []
        self.manga_translations[filename].append(trans_data)
        
        self.save_manga_info()
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
            
    def update_image_view(self):
        if self.current_pixmap and not self.current_pixmap.isNull():
            scaled_pixmap = self.current_pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
            self.setWindowTitle(f"Manga Viewer - {self.name_edit.text() or 'Unknown'} - ({self.current_index + 1}/{len(self.image_paths)})")
            if hasattr(self, 'page_count_label'):
                self.page_count_label.setText(f"Page: {self.current_index + 1} / {len(self.image_paths)}")
            
    def render_saved_translations(self):
        for lbl in self.saved_labels:
            lbl.deleteLater()
        self.saved_labels.clear()
        
        if not self.current_pixmap: return
        filename = os.path.basename(self.image_paths[self.current_index])
        if filename not in self.manga_translations: return
        
        lbl_size = self.image_label.size()
        pix_size = self.current_pixmap.size()
        scaled_size = pix_size.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio)
        
        offset_x = (lbl_size.width() - scaled_size.width()) / 2
        offset_y = (lbl_size.height() - scaled_size.height()) / 2
        ratio_w = scaled_size.width() / pix_size.width()
        ratio_h = scaled_size.height() / pix_size.height()
        
        for t_data in self.manga_translations[filename]:
            rect = t_data.get("rect", [0, 0, 0, 0])
            x = int(rect[0] * ratio_w + offset_x)
            y = int(rect[1] * ratio_h + offset_y)
            w = int(rect[2] * ratio_w)
            h = int(rect[3] * ratio_h)
            
            lbl = SavedTranslationLabel(t_data, self.image_label)
            lbl.setGeometry(x, y, w, h)
            lbl.deleted.connect(self.delete_saved_translation)
            lbl.updated.connect(self.update_saved_translation)
            lbl.edit_requested.connect(self.edit_saved_translation)
            lbl.show()
            self.saved_labels.append(lbl)
            
    def update_saved_translation(self, lbl):
        filename = os.path.basename(self.image_paths[self.current_index])
        if filename not in self.manga_translations: return
        
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
        self.save_manga_info()
            
    def edit_saved_translation(self, lbl):
        current_text = lbl.trans_data.get("text", "")
        new_text, ok = QInputDialog.getMultiLineText(self, "Edit Translation", "Enter new text:", current_text)
        if ok and new_text != current_text:
            lbl.trans_data["text"] = new_text
            lbl.setText(new_text)
            self.save_manga_info()
            
    def delete_saved_translation(self, lbl):
        filename = os.path.basename(self.image_paths[self.current_index])
        if filename in self.manga_translations:
            if lbl.trans_data in self.manga_translations[filename]:
                self.manga_translations[filename].remove(lbl.trans_data)
                self.save_manga_info()
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
        if event.key() == Qt.Key.Key_Right:
            self.go_next_page()
        elif event.key() == Qt.Key.Key_Left:
            self.go_prev_page()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
            
    def closeEvent(self, event):
        if hasattr(self, 'voice_thread') and self.voice_thread is not None and self.voice_thread.isRunning():
            self.voice_thread.stop()
        super().closeEvent(event)
            
    def wheelEvent(self, event):
        # Disabled mouse wheel page changing per user request
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
            print("Please provide a valid directory.")
            sys.exit(1)
        image_paths = []
        for f in os.listdir(folder):
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                image_paths.append(os.path.join(folder, f))
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", os.path.basename(s))]
        image_paths.sort(key=natural_sort_key)
        window = MangaViewerWindow(folder, image_paths)
        window.exec()
    except Exception as e:
        with open("crash_log.txt", "w") as f:
            f.write(traceback.format_exc())
        print(f"Crashed! Log written to crash_log.txt: {e}")

if __name__ == "__main__":
    main()
