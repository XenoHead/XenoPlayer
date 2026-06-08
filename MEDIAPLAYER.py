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

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from manga_ocr import MangaOcr
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

class CustomQuestionDialog(QDialog):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet("background-color: #222; color: white;")
        layout = QVBoxLayout(self)
        
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        
        btn_layout = QHBoxLayout()
        btn_yes = QPushButton("Yes")
        btn_yes.setStyleSheet("background-color: #d32f2f; color: white; padding: 5px; border-radius: 3px;")
        btn_yes.clicked.connect(self.accept)
        
        btn_no = QPushButton("No")
        btn_no.setStyleSheet("background-color: #555; color: white; padding: 5px; border-radius: 3px;")
        btn_no.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_yes)
        btn_layout.addWidget(btn_no)
        layout.addLayout(btn_layout)

def natural_sort_key(s):
    # Only sort by the filename itself to prevent numbers in parent directories from interfering
    basename = os.path.basename(s)
    
    # Primary sort: ignores punctuation/spaces so 'img_1', 'img-2', 'img 3' group correctly
    primary_parts = []
    for text in re.split(r'(\d+)', basename):
        if text.isdigit():
            primary_parts.append(int(text))
        else:
            primary_parts.append(re.sub(r'[\W_]+', '', text).lower())
            
    # Secondary sort: preserves exact punctuation as a tiebreaker
    secondary_parts = [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', basename)]
    
    return (primary_parts, secondary_parts)

# Custom Video Widget for double-click full screen toggle
class CustomVideoWidget(QVideoWidget):
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

class CustomImageWidget(QLabel):
    doubleClicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_pixmap = None
        self.movie_obj = None
        self.movie_filepath = None

    def load_image(self, filepath):
        if self.movie_obj:
            self.movie_obj.stop()
            self.movie_obj = None
        self.clear()
        
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.gif':
            self.movie_filepath = filepath
            self.movie_obj = QMovie(filepath)
            self.setMovie(self.movie_obj)
            self.movie_obj.start()
            self.original_pixmap = None
            self.update_movie_size()
        else:
            self.movie_filepath = None
            self.original_pixmap = QPixmap(filepath)
            self.update_view()

    def update_movie_size(self):
        if self.movie_obj and self.movie_filepath:
            orig_size = QPixmap(self.movie_filepath).size()
            if orig_size.isValid() and self.size().isValid():
                scaled = orig_size.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
                if scaled.width() > 0 and scaled.height() > 0:
                    self.movie_obj.setScaledSize(scaled)

    def update_view(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            self.setPixmap(self.original_pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.movie_obj:
            self.update_movie_size()
        else:
            self.update_view()
        
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

SUPPORTED_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.mpg', '.mpeg', '.jpg', '.jpeg', '.png', '.webp', '.gif'}

class ThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, QImage)

    def __init__(self):
        super().__init__()
        self.items = []
        self.running = True

    def set_items(self, items):
        self.items = items

    def run(self):
        if not CV2_AVAILABLE:
            print("OpenCV not available. Please run: pip install opencv-python numpy")
            return
            
        for idx, filepath in self.items:
            if not self.running:
                break
            img = self.generate_thumbnail(filepath)
            if img:
                self.thumbnail_ready.emit(idx, img)

    def generate_thumbnail(self, filepath):
        try:
            ext = os.path.splitext(filepath)[1].lower()
            if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
                img = QImage(filepath)
                if not img.isNull():
                    return img.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                return None
                
            cap = cv2.VideoCapture(filepath)
            if not cap.isOpened():
                return None
                
            # Attempt to jump forward to avoid black intro frames
            cap.set(cv2.CAP_PROP_POS_FRAMES, 30)
            ret, frame = cap.read()
            
            if not ret:
                # If seeking breaks the stream, re-open and grab the first frame
                cap.release()
                cap = cv2.VideoCapture(filepath)
                ret, frame = cap.read()
            
            cap.release()
            
            if ret and frame is not None:
                frame = cv2.resize(frame, (160, 90))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                # Use .tobytes() to prevent PyQt6 silent memoryview failures
                qt_img = QImage(frame.tobytes(), w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
                return qt_img
        except Exception as e:
            print(f"Thumbnail error for {filepath}: {e}")
            
        return None

class SelectableImageLabel(QLabel):
    selection_made = pyqtSignal(QRect)
    selection_cleared = pyqtSignal()
    
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

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.rubber_band.hide()
            rect = self.rubber_band.geometry()
            if rect.width() > 10 and rect.height() > 10:
                self.selection_made.emit(rect)
            self.origin = QPoint()

class TranslationWorker(QThread):
    result_ready = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, image, ocr_mode):
        super().__init__()
        self.ocr_mode = ocr_mode
        from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        self.img_bytes = ba.data()

    def run(self):
        import io
        global manga_ocr_model
        try:
            pil_img = Image.open(io.BytesIO(self.img_bytes))
            
            if self.ocr_mode == "Japanese (Manga OCR)":
                if manga_ocr_model is None:
                    self.status_update.emit("Initializing AI Model...\n(This will download ~400MB on first run. Please wait...)")
                    from manga_ocr import MangaOcr
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
            # Target 'en' for English. Change this to 'es', 'fr', etc. if you want another output language!
            translated_text = GoogleTranslator(source=source_lang, target='en').translate(extracted_text)
            self.result_ready.emit(extracted_text, translated_text)
        except Exception as e:
            self.error_occurred.emit(str(e))
class FavoritesWindow(QDialog):
    def __init__(self, favorites, parent=None):
        super().__init__(parent)
        self.favorites = favorites
        self.parent_player = parent
        self.setWindowTitle("Select a Favorite to Play")
        self.resize(700, 400)
        self.selected_index = -1
        
        main_layout = QHBoxLayout(self)
        
        # Left Side (List & Rename)
        left_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("background-color: #222; color: white;")
        for i, filepath in enumerate(self.favorites):
            item = QListWidgetItem(os.path.basename(filepath))
            item.setToolTip(filepath)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list_widget.addItem(item)
            
        left_layout.addWidget(self.list_widget)
        
        self.btn_rename = QPushButton("Rename Selected")
        self.btn_rename.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_rename.clicked.connect(self.rename_selected)
        left_layout.addWidget(self.btn_rename)
        
        main_layout.addLayout(left_layout, stretch=1)
        
        # Right Side (Mini Player & Sample Button)
        right_layout = QVBoxLayout()
        
        self.sample_player = QMediaPlayer()
        self.sample_audio = QAudioOutput()
        self.sample_player.setAudioOutput(self.sample_audio)
        self.sample_video = QVideoWidget()
        self.sample_video.setStyleSheet("background-color: black;")
        self.sample_player.setVideoOutput(self.sample_video)
        
        right_layout.addWidget(self.sample_video, stretch=1)
        
        self.btn_sample = QPushButton("Sample Video (5s)")
        self.btn_sample.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_sample.clicked.connect(self.play_sample)
        right_layout.addWidget(self.btn_sample)
        
        main_layout.addLayout(right_layout, stretch=1)
        
        self.list_widget.itemDoubleClicked.connect(self.on_double_click)
        self.sample_player.positionChanged.connect(self.check_sample_time)
        
    def on_double_click(self, item):
        self.selected_index = item.data(Qt.ItemDataRole.UserRole)
        self.sample_player.stop()
        self.accept()
        
    def rename_selected(self):
        item = self.list_widget.currentItem()
        if not item: return
        
        self.sample_player.stop()
        
        idx = item.data(Qt.ItemDataRole.UserRole)
        old_path = self.favorites[idx]
        old_base, ext = os.path.splitext(os.path.basename(old_path))
        
        new_base, ok = QInputDialog.getText(self, "Rename Favorite", "New name:", text=old_base)
        if ok and new_base:
            new_path = os.path.join(os.path.dirname(old_path), new_base + ext)
            try:
                os.rename(old_path, new_path)
                self.favorites[idx] = new_path
                item.setText(os.path.basename(new_path))
                item.setToolTip(new_path)
                
                if self.parent_player:
                    self.parent_player.favorites = self.favorites
                    self.parent_player.settings.setValue("favorites", self.favorites)
                    
                    if self.parent_player.playlist:
                        for i in range(len(self.parent_player.playlist)):
                            if self.parent_player.playlist[i] == old_path:
                                self.parent_player.playlist[i] = new_path
                        if self.parent_player.current_index >= 0 and self.parent_player.playlist[self.parent_player.current_index] == new_path:
                            self.parent_player.setWindowTitle(f"Playing: {os.path.basename(new_path)}")
                            
            except Exception as e:
                if self.parent_player:
                    self.parent_player.show_toast(f"Could not rename (it might be playing!):\n{e}")

    def play_sample(self):
        item = self.list_widget.currentItem()
        if not item: return
        
        if self.parent_player and self.parent_player.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.parent_player.media_player.pause()
            
        idx = item.data(Qt.ItemDataRole.UserRole)
        path = self.favorites[idx]
        
        self.sample_player.setSource(QUrl.fromLocalFile(path))
        self.sample_player.play()
        
    def check_sample_time(self, position):
        if position >= 5000:
            self.sample_player.stop()

    def closeEvent(self, event):
        self.sample_player.stop()
        super().closeEvent(event)

class SavedTranslationLabel(QLabel):
    deleted = pyqtSignal(object)
    updated = pyqtSignal(object)
    
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
        self.showFullScreen()
        self.setStyleSheet("background-color: black; color: white;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        layout = QVBoxLayout(self)
        
        # Top Bar
        top_layout = QHBoxLayout()
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
        self.setFocus()
        
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
        self.translation_worker = TranslationWorker(cropped, self.combo_ocr_lang.currentText())
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
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right:
            if self.current_index < len(self.image_paths) - 1:
                self.current_index += 1
                self.load_current_image()
        elif event.key() == Qt.Key.Key_Left:
            if self.current_index > 0:
                self.current_index -= 1
                self.load_current_image()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
            
    def wheelEvent(self, event):
        # Disabled mouse wheel page changing per user request
        super().wheelEvent(event)

class MoveTargetsDialog(QDialog):
    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self.targets = targets
        self.setWindowTitle("Configure Move Targets")
        self.resize(500, 300)
        self.setStyleSheet("background-color: #222; color: white;")
        
        layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("background-color: #111; color: white;")
        self.update_list()
        layout.addWidget(self.list_widget)
        
        form_layout = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name (e.g., Manga)")
        self.name_edit.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Target Path")
        self.path_edit.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        
        self.btn_browse = QPushButton("Browse")
        self.btn_browse.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_browse.clicked.connect(self.browse_path)
        
        form_layout.addWidget(self.name_edit)
        form_layout.addWidget(self.path_edit)
        form_layout.addWidget(self.btn_browse)
        
        layout.addLayout(form_layout)
        
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add / Update")
        self.btn_add.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_add.clicked.connect(self.add_target)
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_remove.clicked.connect(self.remove_target)
        self.btn_close = QPushButton("Close")
        self.btn_close.setStyleSheet("background-color: #333; color: white; padding: 5px; border-radius: 3px;")
        self.btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        
    def update_list(self):
        self.list_widget.clear()
        for name, path in self.targets.items():
            self.list_widget.addItem(f"{name}  ->  {path}")
            
    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Target Directory")
        if path:
            self.path_edit.setText(path)
            
    def add_target(self):
        name = self.name_edit.text().strip()
        path = self.path_edit.text().strip()
        if name and path:
            self.targets[name] = path
            self.update_list()
            self.name_edit.clear()
            self.path_edit.clear()
            
    def remove_target(self):
        item = self.list_widget.currentItem()
        if item:
            text = item.text()
            name = text.split("  ->  ")[0]
            if name in self.targets:
                del self.targets[name]
                self.update_list()
                
    def on_item_clicked(self, item):
        text = item.text()
        name, path = text.split("  ->  ")
        self.name_edit.setText(name)
        self.path_edit.setText(path)

class MediaPlayer(QWidget):
    def __init__(self, filepath=None):
        super().__init__()
        self.settings = QSettings("XenoPlayer", "LastSession")
        
        favs = self.settings.value("favorites")
        if favs is None:
            self.favorites = []
        elif isinstance(favs, str):
            self.favorites = [favs]
        else:
            self.favorites = list(favs)
        self.favorites = [f for f in self.favorites if os.path.isfile(f)]
        
        try:
            self.move_targets = json.loads(self.settings.value("move_targets", defaultValue="{}"))
        except Exception:
            self.move_targets = {}
            
        try:
            self.saved_volumes = json.loads(self.settings.value("saved_volumes", defaultValue="{}"))
        except Exception:
            self.saved_volumes = {}
            
        try:
            self.max_volume = int(self.settings.value("max_volume", defaultValue=100))
        except Exception:
            self.max_volume = 100
            
        self.setWindowTitle("XenoPlayer")
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")))
        self.setGeometry(100, 100, 1280, 720)
        self.setStyleSheet("background-color: black; color: white;")
        
        # Main Layout (Vertical split)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)
        
        # Menu Bar
        self.menu_bar = QMenuBar(self)
        self.menu_bar.setStyleSheet("background-color: #222; color: white; padding: 5px;")
        
        # File Menu
        file_menu = self.menu_bar.addMenu("File")
        action_open = file_menu.addAction("Load Folder/File")
        action_open.triggered.connect(self.open_file)
        action_exit = file_menu.addAction("Exit")
        action_exit.triggered.connect(self.close)
        
        # Edit Menu
        edit_menu = self.menu_bar.addMenu("Edit")
        action_move_targets = edit_menu.addAction("Move Targets")
        action_move_targets.triggered.connect(self.open_move_targets_dialog)
        action_delete_dupes = edit_menu.addAction("Delete Dupes")
        action_delete_dupes.triggered.connect(self.delete_duplicates)
        
        # Help Menu
        help_menu = self.menu_bar.addMenu("Help")
        action_about = help_menu.addAction("About")
        action_about.triggered.connect(self.show_about_dialog)
        
        main_layout.addWidget(self.menu_bar)
        
        # Toast Notification
        self.toast_label = QLabel(self)
        self.toast_label.setStyleSheet("background-color: rgba(200, 50, 50, 230); color: white; font-size: 18px; font-weight: bold; padding: 10px 20px; border-radius: 5px;")
        self.toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_label.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.timeout.connect(self.toast_label.hide)
        self.toast_timer.setSingleShot(True)
        
        # Stacked Widget for Video vs Image
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, stretch=1)

        # Setup Multimedia
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)

        self.video_widget = CustomVideoWidget() # Use custom widget for double-click
        self.media_player.setVideoOutput(self.video_widget)
        self.video_widget.doubleClicked.connect(self.toggle_fullscreen)
        self.stacked_widget.addWidget(self.video_widget)
        
        self.image_widget = CustomImageWidget()
        self.image_widget.doubleClicked.connect(self.toggle_fullscreen)
        self.stacked_widget.addWidget(self.image_widget)
        
        self.media_player.errorOccurred.connect(self.handle_error)
        self.media_player.mediaStatusChanged.connect(self.handle_status)
        
        self.controls_container = QWidget()
        container_layout = QVBoxLayout(self.controls_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Progress and Time Layout
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(10, 0, 10, 0)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: white;")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.time_label.setFixedWidth(120) # Give it some width to prevent text jumping

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.progress_slider.sliderMoved.connect(self.set_media_position)
        
        self.media_player.positionChanged.connect(self.update_ui_with_time)
        self.media_player.durationChanged.connect(self.update_ui_with_time)
        
        progress_layout.addWidget(self.progress_slider)
        progress_layout.addWidget(self.time_label)
        container_layout.addLayout(progress_layout)

        # Controls Layout
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(10, 5, 10, 5)
        self.btn_open = QPushButton("Load Folder/File")
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Sort: Name", "Sort: Date", "Sort: Size"])
        self.combo_sort.currentIndexChanged.connect(self.apply_sorting)
        self.btn_show_favs = QPushButton("Play Favorites")
        self.btn_play_unfavs = QPushButton("Play Unfavorites")
        self.btn_read_manga = QPushButton("📖 Read Manga")
        self.btn_move_targets = QPushButton("📂 Move Targets")
        self.btn_delete_dupes = QPushButton("🗑️ Delete Dupes")
        self.btn_play_pause = QPushButton("Play / Pause")
        self.btn_prev = QPushButton("Previous")
        self.btn_next = QPushButton("Next")
        self.btn_fav_toggle = QPushButton("☆ Favorite")
        
        button_style = "background-color: #333; padding: 10px; border-radius: 5px; color: white;"
        for btn in [self.btn_open, self.combo_sort, self.btn_show_favs, self.btn_play_unfavs, self.btn_read_manga, self.btn_move_targets, self.btn_delete_dupes, self.btn_play_pause, self.btn_prev, self.btn_next, self.btn_fav_toggle]:
            btn.setStyleSheet(button_style)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus) 
            controls_layout.addWidget(btn)
            
        self.chk_loop = QCheckBox("Loop")
        self.chk_loop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.lbl_loop = QLabel("Count:")
        self.spin_loop = QSpinBox()
        self.spin_loop.setRange(0, 999)
        self.spin_loop.setValue(1)
        self.spin_loop.setToolTip("0 for infinite loops")
        self.spin_loop.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.spin_loop.setStyleSheet("background-color: #333; color: white;")
        
        self.chk_show_all = QCheckBox("Show All in Folder")
        self.chk_show_all.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chk_show_all.stateChanged.connect(lambda: self.update_playlist_ui())
        
        self.lbl_max_vol = QLabel("Max Vol:")
        self.dial_max_vol = QDial()
        self.dial_max_vol.setRange(0, 100)
        self.dial_max_vol.setValue(self.max_volume)
        self.dial_max_vol.setFixedSize(40, 40)
        self.dial_max_vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dial_max_vol.valueChanged.connect(self.change_max_volume)
        
        self.lbl_vol = QLabel("Vol:")
        self.dial_vol = QDial()
        self.dial_vol.setRange(0, 100)
        self.dial_vol.setValue(100)
        self.dial_vol.setFixedSize(40, 40)
        self.dial_vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dial_vol.valueChanged.connect(self.change_volume)
            
        controls_layout.addSpacing(20)
        controls_layout.addWidget(self.chk_loop)
        controls_layout.addWidget(self.lbl_loop)
        controls_layout.addWidget(self.spin_loop)
        controls_layout.addSpacing(20)
        controls_layout.addWidget(self.chk_show_all)
        controls_layout.addStretch()
        controls_layout.addWidget(self.lbl_max_vol)
        controls_layout.addWidget(self.dial_max_vol)
        controls_layout.addWidget(self.lbl_vol)
        controls_layout.addWidget(self.dial_vol)
        container_layout.addLayout(controls_layout)
        
        main_layout.addWidget(self.controls_container)
        
        # Playlist Bar (Bottom)
        self.playlist_widget = QListWidget()
        self.playlist_widget.setFixedHeight(170)
        self.playlist_widget.setViewMode(QListView.ViewMode.IconMode)
        self.playlist_widget.setFlow(QListView.Flow.LeftToRight)
        self.playlist_widget.setWrapping(False)
        self.playlist_widget.setSpacing(10)
        self.playlist_widget.setIconSize(QSize(160, 90))
        self.playlist_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.playlist_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.playlist_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_widget.setStyleSheet(
            "QListWidget { background-color: #111; border: none; padding: 10px; } "
            "QListWidget::item { color: #ccc; } "
            "QListWidget::item:selected { background-color: #333; border-radius: 5px; }"
        )
        self.playlist_widget.itemDoubleClicked.connect(self.play_from_list)
        self.playlist_widget.customContextMenuRequested.connect(self.show_context_menu)
        main_layout.addWidget(self.playlist_widget)
        
        # Connections
        self.btn_open.clicked.connect(self.open_file)
        self.btn_prev.clicked.connect(self.prev_video)
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)
        self.btn_next.clicked.connect(self.next_video)
        self.btn_show_favs.clicked.connect(self.play_favorites)
        self.btn_play_unfavs.clicked.connect(self.play_unfavorites)
        self.btn_read_manga.clicked.connect(self.open_manga_viewer)
        self.btn_move_targets.clicked.connect(self.open_move_targets_dialog)
        self.btn_delete_dupes.clicked.connect(self.delete_duplicates)
        self.btn_fav_toggle.clicked.connect(self.toggle_favorite)
        
        self.playlist = []
        self.current_index = -1
        self.current_loop_count = 0
        self.list_items_map = {} # Maps index -> QListWidgetItem
        
        # Thumbnail Background Worker
        self.thumbnail_worker = ThumbnailWorker()
        self.thumbnail_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        
        if filepath:
            self.load_directory(filepath)
        else:
            last_video = self.settings.value("last_video", defaultValue=None)
            if last_video and os.path.isfile(last_video):
                self.load_directory(last_video)
            
    def set_media_position(self, position):
        self.media_player.setPosition(position)

    def handle_error(self, error, error_string):
        print(f"Media Player Error: {error} - {error_string}")

    def handle_status(self, status):
        print(f"Media Status: {status}")
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.chk_loop.isChecked():
                max_loops = self.spin_loop.value()
                if max_loops == 0 or self.current_loop_count < max_loops:
                    self.current_loop_count += 1
                    self.media_player.setPosition(0)
                    self.media_player.play()
                    return
            self.next_video()

    def format_time(self, ms):
        if ms < 0:
            return "00:00"
        s = ms // 1000
        m = s // 60
        s %= 60
        h = m // 60
        m %= 60
        if h > 0:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    def update_ui_with_time(self, *args): # Handles both positionChanged and durationChanged
        position = self.media_player.position()
        duration = self.media_player.duration()

        if duration > 0:
            self.progress_slider.setRange(0, duration)
            self.progress_slider.setValue(position)
            self.time_label.setText(f"{self.format_time(position)} / {self.format_time(duration)}")
        else:
            self.progress_slider.setRange(0, 0)
            self.progress_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")

    def load_directory(self, filepath):
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath):
            print(f"File not found: {filepath}")
            return
            
        directory = os.path.dirname(filepath)
        
        try:
            files = os.listdir(directory)
        except OSError:
            return
            
        self.playlist = []
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                self.playlist.append(os.path.join(directory, f))
                
        sort_text = self.combo_sort.currentText()
        if "Name" in sort_text:
            self.playlist.sort(key=natural_sort_key)
        elif "Date" in sort_text:
            self.playlist.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0)
        elif "Size" in sort_text:
            self.playlist.sort(key=lambda x: os.path.getsize(x) if os.path.exists(x) else 0)
                
        try:
            self.current_index = self.playlist.index(filepath)
        except ValueError:
            self.playlist.append(filepath)
            self.current_index = len(self.playlist) - 1
            
        self.play_current()
        
    def apply_sorting(self):
        if not self.playlist:
            return
        current_playing = self.playlist[self.current_index] if self.current_index >= 0 else None
        
        sort_text = self.combo_sort.currentText()
        if "Name" in sort_text:
            self.playlist.sort(key=natural_sort_key)
        elif "Date" in sort_text:
            self.playlist.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0)
        elif "Size" in sort_text:
            self.playlist.sort(key=lambda x: os.path.getsize(x) if os.path.exists(x) else 0)
            
        if current_playing in self.playlist:
            self.current_index = self.playlist.index(current_playing)
        self.update_playlist_ui()

    def play_current(self):
        if 0 <= self.current_index < len(self.playlist):
            self.current_loop_count = 0
            filepath = self.playlist[self.current_index]
            self.settings.setValue("last_video", filepath)
            self.setWindowTitle(f"Playing: {os.path.basename(filepath)}")
            
            ext = os.path.splitext(filepath)[1].lower()
            if ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
                self.media_player.stop()
                self.stacked_widget.setCurrentWidget(self.image_widget)
                self.image_widget.load_image(filepath)
            else:
                self.stacked_widget.setCurrentWidget(self.video_widget)
                self.media_player.setSource(QUrl.fromLocalFile(filepath))
                
                vol = self.saved_volumes.get(filepath, 100)
                self.dial_vol.blockSignals(True)
                self.dial_vol.setValue(vol)
                effective_vol = min(vol, self.max_volume)
                self.audio_output.setVolume(effective_vol / 100.0)
                self.dial_vol.blockSignals(False)
                
                self.media_player.play()
                
            self.update_playlist_ui()
            self.update_ui_with_time() # Initial update for new video
            self.update_favorite_button()
            
    def update_playlist_ui(self):
        is_showing_all = hasattr(self, 'chk_show_all') and self.chk_show_all.isChecked()
        
        if is_showing_all:
            start_idx = 0
            end_idx = len(self.playlist)
        else:
            # Limit to 5 before and 5 after
            start_idx = max(0, self.current_index - 5)
            end_idx = min(len(self.playlist), self.current_index + 6)
            
        expected_count = end_idx - start_idx
        
        # Check if we can just update the selection without rebuilding thumbnails
        if self.playlist_widget.count() == expected_count and expected_count > 0:
            match = True
            for i in range(expected_count):
                list_idx = start_idx + i
                item = self.playlist_widget.item(i)
                if not item or item.data(Qt.ItemDataRole.UserRole) != list_idx or item.toolTip() != os.path.basename(self.playlist[list_idx]):
                    match = False
                    break
                    
            if match:
                for i in range(self.playlist_widget.count()):
                    item = self.playlist_widget.item(i)
                    list_idx = start_idx + i
                    if list_idx == self.current_index:
                        item.setBackground(Qt.GlobalColor.darkBlue)
                    else:
                        item.setData(Qt.ItemDataRole.BackgroundRole, None)
                        
                if self.current_index in self.list_items_map:
                    self.playlist_widget.scrollToItem(self.list_items_map[self.current_index])
                return

        # Stop previous worker safely
        self.thumbnail_worker.running = False
        self.thumbnail_worker.wait()
        
        self.playlist_widget.clear()
        self.list_items_map.clear()
        if not self.playlist: return
        
        worker_items = []
        
        for i in range(start_idx, end_idx):
            filepath = self.playlist[i]
            name = os.path.basename(filepath)
            
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(160, 115))
            item.setToolTip(name)
            item.setData(Qt.ItemDataRole.UserRole, i)
            # Create a placeholder icon space
            item.setIcon(QIcon())
            
            if i == self.current_index:
                item.setBackground(Qt.GlobalColor.darkBlue)
                
            self.playlist_widget.addItem(item)
            self.list_items_map[i] = item
            worker_items.append((i, filepath))
            
        # Ensure the selected item is visible
        if self.current_index in self.list_items_map:
            self.playlist_widget.scrollToItem(self.list_items_map[self.current_index])
            
        # Start thumbnail worker for visible items
        self.thumbnail_worker.running = True
        self.thumbnail_worker.set_items(worker_items)
        self.thumbnail_worker.start()

    def on_thumbnail_ready(self, idx, qimage):
        if idx in self.list_items_map:
            pixmap = QPixmap.fromImage(qimage)
            self.list_items_map[idx].setIcon(QIcon(pixmap))
            
    def toggle_favorite(self):
        if not self.playlist or self.current_index < 0:
            return
        filepath = self.playlist[self.current_index]
        if filepath in self.favorites:
            self.favorites.remove(filepath)
        else:
            self.favorites.append(filepath)
        self.settings.setValue("favorites", self.favorites)
        self.update_favorite_button()
        
    def update_favorite_button(self):
        if not self.playlist or self.current_index < 0:
            return
        filepath = self.playlist[self.current_index]
        if filepath in self.favorites:
            self.btn_fav_toggle.setText("★ Unfavorite")
            self.btn_fav_toggle.setStyleSheet("background-color: #555; color: gold; padding: 10px; border-radius: 5px;")
        else:
            self.btn_fav_toggle.setText("☆ Favorite")
            self.btn_fav_toggle.setStyleSheet("background-color: #333; color: white; padding: 10px; border-radius: 5px;")

    def play_favorites(self):
        if not self.favorites:
            return
        dialog = FavoritesWindow(self.favorites, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_index >= 0:
            self.playlist = list(self.favorites)
            self.current_index = dialog.selected_index
            self.play_current()

    def play_unfavorites(self):
        if not self.playlist:
            return
            
        current_file = self.playlist[self.current_index] if self.current_index >= 0 else self.playlist[0]
        directory = os.path.dirname(current_file)
        
        try:
            files = os.listdir(directory)
        except OSError:
            return
            
        unfav_playlist = []
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                full_path = os.path.join(directory, f)
                if full_path not in self.favorites:
                    unfav_playlist.append(full_path)
                    
        unfav_playlist.sort(key=natural_sort_key)
        
        if not unfav_playlist:
            self.show_toast("All videos in this folder are already favorited!", is_error=False)
            return
            
        self.playlist = unfav_playlist
        self.current_index = 0
        self.play_current()

    def open_manga_viewer(self):
        if not self.playlist:
            return
            
        directory = os.path.dirname(self.playlist[self.current_index]) if self.current_index >= 0 else os.path.dirname(self.playlist[0])
        
        image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        images = [p for p in self.playlist if os.path.splitext(p)[1].lower() in image_exts]
        
        if not images:
            self.show_toast("No images found in this folder for Manga Viewer.", is_error=False)
            return
            
        images.sort(key=natural_sort_key)
        
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            
        dialog = MangaViewerWindow(directory, images, self)
        dialog.exec()

    def open_move_targets_dialog(self):
        dialog = MoveTargetsDialog(self.move_targets.copy(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.move_targets = dialog.targets
            self.settings.setValue("move_targets", json.dumps(self.move_targets))

    def change_max_volume(self, value):
        self.max_volume = value
        self.settings.setValue("max_volume", value)
        self.change_volume(self.dial_vol.value())

    def change_volume(self, value):
        effective_vol = min(value, self.max_volume)
        self.audio_output.setVolume(effective_vol / 100.0)
        if self.playlist and self.current_index >= 0:
            filepath = self.playlist[self.current_index]
            self.saved_volumes[filepath] = value
            self.settings.setValue("saved_volumes", json.dumps(self.saved_volumes))

    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("About")
        dialog.setFixedSize(400, 300)
        dialog.setStyleSheet("background-color: #222; color: white;")
        layout = QVBoxLayout(dialog)
        
        lbl_logo = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "XenoHead_logo.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
            
        pixmap = QPixmap(logo_path).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        lbl_logo.setPixmap(pixmap)
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_logo)
        
        lbl_title = QLabel("<h2>XenoPlayer</h2>")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_title)
        
        lbl_web = QLabel("<a href='http://www.xenohead.com' style='color: #4da6ff; font-size: 16px;'>www.xenohead.com</a>")
        lbl_web.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_web.setOpenExternalLinks(True)
        layout.addWidget(lbl_web)
        
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #333; padding: 5px; border-radius: 3px;")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        
        dialog.exec()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.playlist_widget.show()
            self.controls_container.show()
        else:
            self.showFullScreen()
            self.playlist_widget.hide()
            self.controls_container.hide()

    def open_file(self):
        last_dir = self.settings.value("last_directory", defaultValue="")
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Media", last_dir, 
            "Media Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.mpg *.mpeg *.jpg *.jpeg *.png *.webp *.gif);;All Files (*)"
        )
        if filepath:
            self.settings.setValue("last_directory", os.path.dirname(filepath))
            self.load_directory(filepath)
            
    def toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def play_from_list(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None:
            self.current_index = idx
            self.play_current()
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right:
            self.next_video()
        elif event.key() == Qt.Key.Key_Left:
            self.prev_video()
        elif event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_play_pause()
        elif event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.toggle_fullscreen()
            else:
                self.close()
        elif event.key() == Qt.Key.Key_Home:
            if self.playlist:
                self.current_index = 0
                self.play_current()
        elif event.key() == Qt.Key.Key_End:
            if self.playlist:
                self.current_index = len(self.playlist) - 1
                self.play_current()
        elif event.key() == Qt.Key.Key_F2:
            items = self.playlist_widget.selectedItems()
            if not items and self.current_index in self.list_items_map:
                items = [self.list_items_map[self.current_index]]
            if items:
                self.rename_files(items)
        elif event.key() == Qt.Key.Key_Delete:
            items = self.playlist_widget.selectedItems()
            if not items and self.current_index in self.list_items_map:
                items = [self.list_items_map[self.current_index]]
            if items:
                self.delete_files(items)
        elif event.key() == Qt.Key.Key_F3:
            items = self.playlist_widget.selectedItems()
            if not items and self.current_index in self.list_items_map:
                items = [self.list_items_map[self.current_index]]
            if items:
                self.move_files(items)
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            rate = self.media_player.playbackRate()
            self.media_player.setPlaybackRate(min(4.0, rate + 0.25))
            if self.playlist and self.current_index >= 0:
                self.setWindowTitle(f"Playing: {os.path.basename(self.playlist[self.current_index])} - Speed: {self.media_player.playbackRate()}x")
        elif event.key() == Qt.Key.Key_Minus:
            rate = self.media_player.playbackRate()
            self.media_player.setPlaybackRate(max(0.25, rate - 0.25))
            if self.playlist and self.current_index >= 0:
                self.setWindowTitle(f"Playing: {os.path.basename(self.playlist[self.current_index])} - Speed: {self.media_player.playbackRate()}x")
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.prev_video()
        elif event.angleDelta().y() < 0:
            self.next_video()
        else:
            super().wheelEvent(event)
            
    def next_video(self):
        if not self.playlist: return
        self.current_index = (self.current_index + 1) % len(self.playlist)
        self.play_current()
        
    def prev_video(self):
        if not self.playlist: return
        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.play_current()

    def show_context_menu(self, pos):
        selected_items = self.playlist_widget.selectedItems()
        if not selected_items:
            return
            
        menu = QMenu()
        menu.setStyleSheet("background-color: #333; color: white;")
        rename_action = menu.addAction("Rename File(s)")
        move_action = menu.addAction("Move to Folder")
        delete_action = menu.addAction("Delete File(s)")
        
        action = menu.exec(self.playlist_widget.viewport().mapToGlobal(pos))
        
        if action == rename_action:
            self.rename_files(selected_items)
        elif action == move_action:
            self.move_files(selected_items)
        elif action == delete_action:
            self.delete_files(selected_items)
            
    def get_selected_filepaths(self, items):
        return [self.playlist[item.data(Qt.ItemDataRole.UserRole)] for item in items]

    def rename_files(self, items):
        paths = self.get_selected_filepaths(items)
        if not paths: return
        
        current_playing = self.playlist[self.current_index]
        new_current = current_playing
        
        if len(paths) == 1:
            old_path = paths[0]
            old_base, ext = os.path.splitext(os.path.basename(old_path))
            new_base, ok = QInputDialog.getText(self, "Rename File", "New name:", text=old_base)
            if ok and new_base:
                new_path = os.path.join(os.path.dirname(old_path), new_base + ext)
                try:
                    os.rename(old_path, new_path)
                    if old_path == current_playing: new_current = new_path
                except Exception as e:
                    self.show_toast(f"Could not rename: {e}")
        else:
            base_name, ok = QInputDialog.getText(self, "Mass Rename", "Enter base name (will append _001, _002, etc.):")
            if ok and base_name:
                for i, old_path in enumerate(paths):
                    ext = os.path.splitext(old_path)[1]
                    new_path = os.path.join(os.path.dirname(old_path), f"{base_name}_{i+1:03d}{ext}")
                    try:
                        os.rename(old_path, new_path)
                        if old_path == current_playing: new_current = new_path
                    except Exception as e:
                        print(f"Failed to rename {old_path}: {e}")
                        
        self.load_directory(new_current)

    def move_files(self, items):
        paths = self.get_selected_filepaths(items)
        if not paths: return
        
        options = list(self.move_targets.keys())
        target_name, ok = QInputDialog.getItem(
            self, "Move Files", 
            "Select target or type new subfolder name:", 
            options, 0, True
        )
        
        if ok and target_name:
            current_playing = self.playlist[self.current_index]
            
            if target_name in self.move_targets:
                target_dir = self.move_targets[target_name]
            else:
                target_dir = os.path.join(os.path.dirname(paths[0]), target_name)
                
            try:
                os.makedirs(target_dir, exist_ok=True)
                for p in paths:
                    shutil.move(p, target_dir)
            except Exception as e:
                self.show_toast(f"Could not move files: {e}")
                
            # If we moved the currently playing file, reload the folder it was moved out of so we can keep playing
            remaining = [p for p in self.playlist if p not in paths]
            if current_playing in paths and remaining:
                self.load_directory(remaining[0])
            elif remaining:
                self.load_directory(current_playing)
            else:
                self.playlist = []
                self.update_playlist_ui()
                self.media_player.stop()

    def delete_files(self, items):
        paths = self.get_selected_filepaths(items)
        if not paths: return
        
        dialog = CustomQuestionDialog(self, "Confirm Delete", f"Are you sure you want to permanently delete {len(paths)} file(s)?")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            current_playing = self.playlist[self.current_index]
            for p in paths:
                try: os.remove(p)
                except Exception as e: print(f"Delete failed: {e}")
                
            remaining = [p for p in self.playlist if p not in paths]
            if current_playing in paths and remaining:
                self.load_directory(remaining[0])
            elif remaining:
                self.load_directory(current_playing)
            else:
                self.playlist.clear()
                self.update_playlist_ui()
                self.media_player.stop()

    def delete_duplicates(self):
        if not self.playlist:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        
        # Group by size first to save time hashing massive files
        size_groups = {}
        for filepath in self.playlist:
            if not os.path.exists(filepath):
                continue
            try:
                sz = os.path.getsize(filepath)
                if sz not in size_groups:
                    size_groups[sz] = []
                size_groups[sz].append(filepath)
            except Exception:
                pass
                
        # Only hash files that share an exact byte size with another file
        potential_dupes = [paths for sz, paths in size_groups.items() if len(paths) > 1]
        duplicates = []
        
        try:
            for group in potential_dupes:
                seen_hashes = {}
                for filepath in group:
                    file_hash = hashlib.md5()
                    with open(filepath, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            file_hash.update(chunk)
                    digest = file_hash.hexdigest()
                    
                    if digest in seen_hashes:
                        duplicates.append((filepath, seen_hashes[digest]))
                    else:
                        seen_hashes[digest] = filepath
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.show_toast(f"Error scanning for duplicates: {e}")
            return
            
        QApplication.restoreOverrideCursor()
        
        if not duplicates:
            self.show_toast("No duplicate files found in the current folder.", is_error=False)
            return
            
        msg = f"Found {len(duplicates)} duplicate file(s):\n\n"
        for dup, orig in duplicates[:10]:
            msg += f"'{os.path.basename(dup)}' matches '{os.path.basename(orig)}'\n"
        if len(duplicates) > 10:
            msg += f"...and {len(duplicates) - 10} more.\n"
            
        msg += "\nDo you want to delete the duplicates?"
        
        dialog = CustomQuestionDialog(self, "Delete Duplicates", msg)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            errors = []
            for dup, _ in duplicates:
                try: os.remove(dup)
                except Exception as e: errors.append(f"Failed to delete {os.path.basename(dup)}:\n{e}")
                
            # Pass empty items to force a reload and cleanup
            if errors: self.show_toast("\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else ""))
            self.delete_files([])
        
    def closeEvent(self, event):
        self.thumbnail_worker.running = False
        self.thumbnail_worker.wait()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    filepath = None
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        
    player = MediaPlayer(filepath)
    player.show()
    
    sys.exit(app.exec())
