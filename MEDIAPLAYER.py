import sys
import os
import shutil
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QListWidget, QListWidgetItem,
                             QListView, QCheckBox, QSpinBox, QLabel, QDial,
                             QSlider, QDialog, QMenu, QInputDialog, QMessageBox,
                             QAbstractItemView, QStackedWidget, QComboBox)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QThread, pyqtSignal, QSize, QSettings
from PyQt6.QtGui import QImage, QPixmap, QIcon, QMovie

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

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
                QMessageBox.warning(self, "Error", f"Could not rename (it might be playing!):\n{e}")

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

class MediaPlayer(QWidget):
    def __init__(self, filepath=None):
        super().__init__()
        self.settings = QSettings("SimpleMediaPlayer", "LastSession")
        
        favs = self.settings.value("favorites")
        if favs is None:
            self.favorites = []
        elif isinstance(favs, str):
            self.favorites = [favs]
        else:
            self.favorites = list(favs)
        self.favorites = [f for f in self.favorites if os.path.isfile(f)]
        
        self.setWindowTitle("Simple Media Player")
        self.setGeometry(100, 100, 1280, 720)
        self.setStyleSheet("background-color: black; color: white;")
        
        # Main Layout (Vertical split)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)
        
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
        main_layout.addLayout(progress_layout)

        # Controls Layout
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(10, 5, 10, 5)
        self.btn_open = QPushButton("Open File")
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Sort: Name", "Sort: Date", "Sort: Size"])
        self.combo_sort.currentIndexChanged.connect(self.apply_sorting)
        self.btn_show_favs = QPushButton("Play Favorites")
        self.btn_play_unfavs = QPushButton("Play Unfavorites")
        self.btn_play_pause = QPushButton("Play / Pause")
        self.btn_prev = QPushButton("Previous")
        self.btn_next = QPushButton("Next")
        self.btn_fav_toggle = QPushButton("☆ Favorite")
        
        button_style = "background-color: #333; padding: 10px; border-radius: 5px; color: white;"
        for btn in [self.btn_open, self.combo_sort, self.btn_show_favs, self.btn_play_unfavs, self.btn_play_pause, self.btn_prev, self.btn_next, self.btn_fav_toggle]:
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
        controls_layout.addWidget(self.lbl_vol)
        controls_layout.addWidget(self.dial_vol)
        main_layout.addLayout(controls_layout)
        
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
            self.playlist.sort()
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
            self.playlist.sort()
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
                    
        unfav_playlist.sort()
        
        if not unfav_playlist:
            QMessageBox.information(self, "No Unfavorites", "All videos in this folder are already favorited!")
            return
            
        self.playlist = unfav_playlist
        self.current_index = 0
        self.play_current()

    def change_volume(self, value):
        self.audio_output.setVolume(value / 100.0)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "", 
            "Media Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.mpg *.mpeg *.jpg *.jpeg *.png *.webp *.gif);;All Files (*)"
        )
        if filepath:
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
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_play_pause()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
            
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
                    QMessageBox.warning(self, "Error", f"Could not rename:\n{e}")
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
        
        folder_name, ok = QInputDialog.getText(self, "Move Files", "Target folder name (created if missing):")
        if ok and folder_name:
            current_playing = self.playlist[self.current_index]
            target_dir = os.path.join(os.path.dirname(paths[0]), folder_name)
            try:
                os.makedirs(target_dir, exist_ok=True)
                for p in paths:
                    shutil.move(p, target_dir)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not move files:\n{e}")
                
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
        
        reply = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to permanently delete {len(paths)} file(s)?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
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
