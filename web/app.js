const videoPlayer = document.getElementById('video-player');
const imageViewer = document.getElementById('image-viewer');
const playlistContainer = document.getElementById('playlist');
const fileNameDisplay = document.getElementById('current-file-name');
const playBtn = document.getElementById('play-btn');

let playlist = [];
let currentIndex = -1;

let appState = {};

window.addEventListener('pywebviewready', function() {
    pywebview.api.init().then(response => {
        console.log("Backend ready", response);
        updateState();
    });
});

function updateState() {
    pywebview.api.get_state().then(state => {
        appState = state;
        renderState();
    });
}

function renderState() {
    // Update Favorite Star
    const favBtn = document.getElementById('favorite-btn');
    if (appState.is_favorite) {
        favBtn.innerHTML = '<i class="fa-solid fa-star" style="color: gold;"></i>';
    } else {
        favBtn.innerHTML = '<i class="fa-regular fa-star"></i>';
    }
    
    // Render Move Targets
    const targetsContainer = document.getElementById('move-targets-container');
    if(targetsContainer) {
        targetsContainer.innerHTML = '';
        for (const [name, path] of Object.entries(appState.move_targets || {})) {
            const btn = document.createElement('button');
            btn.innerHTML = `<i class="fa-solid fa-arrow-right-to-bracket"></i> ${name}`;
            btn.onclick = () => {
                pywebview.api.move_file_to(name).then(res => {
                    if(res.status === 'success') {
                        updateState();
                    } else {
                        alert(res.msg);
                    }
                });
            };
            targetsContainer.appendChild(btn);
        }
    }
}

function toggleFavorite() {
    pywebview.api.toggle_favorite().then(state => {
        appState = state;
        renderState();
    });
}

function deleteDupes() {
    if(confirm("Are you sure you want to delete duplicates in this folder?")) {
        pywebview.api.delete_dupes().then(res => {
            alert(res.msg);
        });
    }
}

// Modals
function openAboutModal() {
    document.getElementById('about-modal').style.display = 'block';
}

function openMoveTargetsModal() {
    document.getElementById('targets-modal').style.display = 'block';
    renderTargetsList();
}

function openOptionsModal() {
    document.getElementById('options-modal').style.display = 'block';
    renderOptionsList();
}

function openHotkeysModal() {
    document.getElementById('hotkeys-modal').style.display = 'block';
    renderHotkeysList();
}

function closeModals() {
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
}

function renderTargetsList() {
    const list = document.getElementById('targets-list');
    list.innerHTML = '';
    for (const [name, path] of Object.entries(appState.move_targets || {})) {
        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.justifyContent = 'space-between';
        div.style.marginBottom = '5px';
        div.textContent = `${name} -> ${path}`;
        const remBtn = document.createElement('button');
        remBtn.textContent = 'X';
        remBtn.onclick = () => {
            delete appState.move_targets[name];
            renderTargetsList();
        };
        div.appendChild(remBtn);
        list.appendChild(div);
    }
}

function addTarget() {
    const name = document.getElementById('new-target-name').value;
    const path = document.getElementById('new-target-path').value;
    if(name && path) {
        if(!appState.move_targets) appState.move_targets = {};
        appState.move_targets[name] = path;
        document.getElementById('new-target-name').value = '';
        document.getElementById('new-target-path').value = '';
        renderTargetsList();
    }
}

function browseTargetFolder() {
    pywebview.api.browse_folder().then(path => {
        if (path) {
            document.getElementById('new-target-path').value = path;
        }
    });
}

function saveTargets() {
    pywebview.api.save_move_targets(appState.move_targets).then(state => {
        appState = state;
        renderState();
        closeModals();
    });
}

function renderOptionsList() {
    const list = document.getElementById('options-list');
    list.innerHTML = '';
    const folders = appState.saved_folders || ["", "", "", "", ""];
    const defIndex = appState.default_folder !== undefined ? appState.default_folder : -1;
    
    for (let i = 0; i < 5; i++) {
        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.gap = '5px';
        div.style.marginBottom = '5px';
        div.style.alignItems = 'center';
        
        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'default-folder';
        radio.value = i;
        if (i === defIndex) radio.checked = true;
        
        const input = document.createElement('input');
        input.type = 'text';
        input.id = `opt-folder-${i}`;
        input.value = folders[i] || "";
        input.style.flex = '1';
        
        const browseBtn = document.createElement('button');
        browseBtn.innerHTML = '<i class="fa-solid fa-folder-open"></i>';
        browseBtn.onclick = () => {
            pywebview.api.browse_folder().then(path => {
                if (path) input.value = path;
            });
        };
        
        div.appendChild(radio);
        div.appendChild(input);
        div.appendChild(browseBtn);
        list.appendChild(div);
    }
}

function saveOptionsModal() {
    const folders = [];
    let defIndex = -1;
    for (let i = 0; i < 5; i++) {
        folders.push(document.getElementById(`opt-folder-${i}`).value);
    }
    const selectedRadio = document.querySelector('input[name="default-folder"]:checked');
    if (selectedRadio) {
        defIndex = parseInt(selectedRadio.value);
    }
    
    pywebview.api.save_options(folders, defIndex).then(state => {
        appState = state;
        closeModals();
    });
}

function renderHotkeysList() {
    const prevList = document.getElementById('hotkeys-prev-list');
    const nextList = document.getElementById('hotkeys-next-list');
    prevList.innerHTML = '';
    nextList.innerHTML = '';
    
    const hotkeys = appState.hotkeys || {next: ["ArrowRight", "Space", "", "", ""], prev: ["ArrowLeft", "", "", "", ""]};
    const prevKeys = hotkeys.prev || ["ArrowLeft", "", "", "", ""];
    const nextKeys = hotkeys.next || ["ArrowRight", "Space", "", "", ""];
    
    for(let i = 0; i < 5; i++) {
        // Prev
        const pInput = document.createElement('input');
        pInput.type = 'text';
        pInput.id = `hk-prev-${i}`;
        pInput.value = prevKeys[i] || '';
        pInput.readOnly = true;
        pInput.placeholder = 'Click and press key';
        pInput.style.width = '100%';
        pInput.style.marginBottom = '5px';
        pInput.onkeydown = (e) => {
            e.preventDefault();
            if(e.code === 'Backspace') pInput.value = '';
            else pInput.value = e.code;
        };
        prevList.appendChild(pInput);
        
        // Next
        const nInput = document.createElement('input');
        nInput.type = 'text';
        nInput.id = `hk-next-${i}`;
        nInput.value = nextKeys[i] || '';
        nInput.readOnly = true;
        nInput.placeholder = 'Click and press key';
        nInput.style.width = '100%';
        nInput.style.marginBottom = '5px';
        nInput.onkeydown = (e) => {
            e.preventDefault();
            if(e.code === 'Backspace') nInput.value = '';
            else nInput.value = e.code;
        };
        nextList.appendChild(nInput);
    }
}

function saveHotkeysModal() {
    const nextKeys = [];
    const prevKeys = [];
    for(let i=0; i<5; i++) {
        nextKeys.push(document.getElementById(`hk-next-${i}`).value);
        prevKeys.push(document.getElementById(`hk-prev-${i}`).value);
    }
    pywebview.api.save_hotkeys({next: nextKeys, prev: prevKeys}).then(state => {
        appState = state;
        closeModals();
    });
}


function updatePlaylist() {
    pywebview.api.get_playlist().then(items => {
        playlist = items;
        renderPlaylist();
    });
}

const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const img = entry.target;
            if (img.dataset.src) {
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
            }
            observer.unobserve(img);
        }
    });
}, { root: document.getElementById('playlist'), rootMargin: '50px' });

function renderPlaylist() {
    playlistContainer.innerHTML = '';
    playlist.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'playlist-item' + (index === currentIndex ? ' active' : '');
        div.onclick = () => pywebview.api.play_index(index);
        
        const img = document.createElement('img');
        img.className = 'playlist-thumbnail';
        img.dataset.src = `http://localhost:5050/thumbnail?path=${encodeURIComponent(item.path)}`;
        img.onerror = function() { this.onerror = null; this.src = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='; };
        observer.observe(img);
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'playlist-name';
        nameSpan.textContent = item.name;
        
        div.appendChild(img);
        div.appendChild(nameSpan);
        playlistContainer.appendChild(div);
    });
    
    // Scroll active item into view
    const activeItem = document.querySelector('.playlist-item.active');
    if (activeItem) {
        activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function loadMedia(path, index) {
    if (currentIndex !== index) {
        resetLoopCount();
    }
    currentIndex = index;
    fileNameDisplay.textContent = path.split('\\').pop().split('/').pop();
    
    // Update active class
    renderPlaylist();
    
    const ext = path.split('.').pop().toLowerCase();
    const mediaUrl = `http://localhost:5050/media?path=${encodeURIComponent(path)}`;
    
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
        videoPlayer.style.display = 'none';
        videoPlayer.pause();
        imageViewer.style.display = 'block';
        imageViewer.src = mediaUrl;
        
        playBtn.innerHTML = '<i class="fa-solid fa-play"></i>'; // Images don't play
        
        // Load manga info
        pywebview.api.get_manga_info(path).then(info => {
            mangaTranslations = info || {};
            renderTranslations(path);
        });
        updateImageTimer();
    } else {
        imageViewer.style.display = 'none';
        videoPlayer.style.display = 'block';
        videoPlayer.src = mediaUrl;
        videoPlayer.play();
        playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        document.getElementById('translations-container').innerHTML = '';
        if (imageTimerInterval) {
            clearInterval(imageTimerInterval);
            imageTimerInterval = null;
        }
    }
    updateState();
}

function togglePlay() {
    if (videoPlayer.style.display !== 'none') {
        if (videoPlayer.paused) {
            videoPlayer.play();
            playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        } else {
            videoPlayer.pause();
            playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
        }
    }
}

function changeVolume(val) {
    videoPlayer.volume = val / 100.0;
}

let currentPlayCount = 0;

function resetLoopCount() {
    currentPlayCount = 0;
}

// Auto play next video when ended
videoPlayer.addEventListener('ended', () => {
    const loopEnabled = document.getElementById('loop-checkbox').checked;
    const maxLoops = parseInt(document.getElementById('loop-count').value, 10) || 1;
    
    if (loopEnabled) {
        currentPlayCount++;
        if (currentPlayCount < maxLoops) {
            // Replay the current video
            videoPlayer.currentTime = 0;
            videoPlayer.play();
            return;
        }
    }
    
    // Done looping or loop disabled -> go to next
    pywebview.api.next_media();
});

let imageTimerInterval = null;

function updateImageTimer() {
    if (imageTimerInterval) {
        clearInterval(imageTimerInterval);
        imageTimerInterval = null;
    }
    const val = parseInt(document.getElementById('image-timer').value, 10) || 0;
    if (val > 0 && imageViewer.style.display !== 'none') {
        imageTimerInterval = setInterval(() => {
            pywebview.api.next_media();
        }, val * 1000);
    }
}

// --- Keyboard Shortcuts ---
window.addEventListener('keydown', e => {
    // Prevent triggering if typing in an input or textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    
    const hotkeys = appState.hotkeys || {next: ["ArrowRight", "Space"], prev: ["ArrowLeft"]};
    const nextKeys = hotkeys.next || ["ArrowRight", "Space"];
    const prevKeys = hotkeys.prev || ["ArrowLeft"];
    
    if (prevKeys.includes(e.code)) {
        pywebview.api.prev_media();
        e.preventDefault();
    } else if (nextKeys.includes(e.code)) {
        pywebview.api.next_media();
        e.preventDefault();
    }
});

// --- Manga Translation Features ---
let mangaTranslations = {};
const mediaContainer = document.getElementById('media-container');
const selectionBox = document.getElementById('selection-box');
const transContainer = document.getElementById('translations-container');
const loadingOverlay = document.getElementById('manga-loading');

let isDrawing = false;
let startX = 0, startY = 0;

mediaContainer.addEventListener('mousedown', e => {
    if (imageViewer.style.display === 'none') return;
    if (e.target.closest('.manga-translation-box')) return; // Don't draw if clicking on existing box
    
    isDrawing = true;
    const rect = mediaContainer.getBoundingClientRect();
    startX = e.clientX - rect.left;
    startY = e.clientY - rect.top;
    
    selectionBox.style.left = startX + 'px';
    selectionBox.style.top = startY + 'px';
    selectionBox.style.width = '0px';
    selectionBox.style.height = '0px';
    selectionBox.style.display = 'block';
});

mediaContainer.addEventListener('mousemove', e => {
    if (!isDrawing) return;
    const rect = mediaContainer.getBoundingClientRect();
    const currX = e.clientX - rect.left;
    const currY = e.clientY - rect.top;
    
    selectionBox.style.left = Math.min(startX, currX) + 'px';
    selectionBox.style.top = Math.min(startY, currY) + 'px';
    selectionBox.style.width = Math.abs(currX - startX) + 'px';
    selectionBox.style.height = Math.abs(currY - startY) + 'px';
});

mediaContainer.addEventListener('mouseup', e => {
    if (!isDrawing) return;
    isDrawing = false;
    selectionBox.style.display = 'none';
    
    const rect = mediaContainer.getBoundingClientRect();
    const currX = e.clientX - rect.left;
    const currY = e.clientY - rect.top;
    
    const selLeft = Math.min(startX, currX);
    const selTop = Math.min(startY, currY);
    const selWidth = Math.abs(currX - startX);
    const selHeight = Math.abs(currY - startY);
    
    if (selWidth < 10 || selHeight < 10) return; // Too small
    
    const imgRect = imageViewer.getBoundingClientRect();
    // Calculate relative to the image element
    const relX = (selLeft + rect.left) - imgRect.left;
    const relY = (selTop + rect.top) - imgRect.top;
    
    if (relX < 0 || relY < 0 || relX > imgRect.width || relY > imgRect.height) return; // Outside image
    
    const ocrMode = document.getElementById('ocr-mode').value;
    const currentPath = appState.current_path || playlist[currentIndex].path;
    
    loadingOverlay.style.display = 'block';
    
    pywebview.api.translate_rect(
        currentPath, 
        relX, relY, selWidth, selHeight, 
        ocrMode, 
        imgRect.width, imgRect.height
    ).then(res => {
        loadingOverlay.style.display = 'none';
        if (res.status === 'success') {
            const filename = currentPath.split('\\').pop().split('/').pop();
            if (!mangaTranslations[filename]) mangaTranslations[filename] = [];
            
            mangaTranslations[filename].push({
                rect: res.rect,
                text: res.text,
                orig: res.orig
            });
            
            pywebview.api.save_manga_info(currentPath, mangaTranslations);
            renderTranslations(currentPath);
        } else {
            alert("Translation failed: " + res.msg);
        }
    });
});

function renderTranslations(path) {
    transContainer.innerHTML = '';
    const filename = path.split('\\').pop().split('/').pop();
    const transList = mangaTranslations[filename] || [];
    
    const imgRect = imageViewer.getBoundingClientRect();
    const containerRect = mediaContainer.getBoundingClientRect();
    
    if (imgRect.width === 0) {
        // Image not loaded yet, retry shortly
        setTimeout(() => renderTranslations(path), 100);
        return;
    }
    
    // The actual image size
    const natW = imageViewer.naturalWidth;
    const natH = imageViewer.naturalHeight;
    const ratioW = imgRect.width / natW;
    const ratioH = imgRect.height / natH;
    
    transList.forEach((t, i) => {
        const box = document.createElement('div');
        box.className = 'manga-translation-box';
        
        // t.rect is [orig_x, orig_y, orig_w, orig_h]
        const dispX = t.rect[0] * ratioW;
        const dispY = t.rect[1] * ratioH;
        const dispW = t.rect[2] * ratioW;
        const dispH = t.rect[3] * ratioH;
        
        // Position relative to mediaContainer
        box.style.position = 'absolute';
        box.style.left = (imgRect.left - containerRect.left + dispX) + 'px';
        box.style.top = (imgRect.top - containerRect.top + dispY) + 'px';
        box.style.minWidth = dispW + 'px';
        
        box.style.background = 'rgba(0, 0, 0, 0.8)';
        box.style.color = 'white';
        box.style.padding = '5px';
        box.style.borderRadius = '3px';
        box.style.border = '1px solid #4da6ff';
        box.style.pointerEvents = 'auto';
        box.style.zIndex = '20';
        box.style.fontSize = '14px';
        
        const textArea = document.createElement('textarea');
        textArea.value = t.text;
        textArea.style.width = '100%';
        textArea.style.background = 'transparent';
        textArea.style.color = 'white';
        textArea.style.border = 'none';
        textArea.style.resize = 'vertical';
        textArea.style.outline = 'none';
        textArea.onchange = () => {
            t.text = textArea.value;
            pywebview.api.save_manga_info(path, mangaTranslations);
        };
        
        const delBtn = document.createElement('button');
        delBtn.innerHTML = 'X';
        delBtn.style.position = 'absolute';
        delBtn.style.top = '-10px';
        delBtn.style.right = '-10px';
        delBtn.style.background = 'red';
        delBtn.style.color = 'white';
        delBtn.style.border = 'none';
        delBtn.style.borderRadius = '50%';
        delBtn.style.width = '20px';
        delBtn.style.height = '20px';
        delBtn.style.cursor = 'pointer';
        delBtn.onclick = () => {
            mangaTranslations[filename].splice(i, 1);
            pywebview.api.save_manga_info(path, mangaTranslations);
            renderTranslations(path);
        };
        
        box.appendChild(delBtn);
        box.appendChild(textArea);
        
        // Orig text tooltip
        box.title = t.orig;
        
        transContainer.appendChild(box);
    });
}

// Update translations position when window resizes
window.addEventListener('resize', () => {
    if (imageViewer.style.display !== 'none' && playlist[currentIndex]) {
        renderTranslations(playlist[currentIndex].path);
    }
});

// --- Online Manga Logic ---
const onlineMangaModal = document.getElementById('online-manga-modal');
const nhentaiTagsList = document.getElementById('nhentai-tags-list');
const nhentaiResultsArea = document.getElementById('nhentai-results-area');
const nhentaiSearchInput = document.getElementById('nhentai-search-input');
const onlineMangaStatus = document.getElementById('online-manga-status');

function openOnlineManga() {
    onlineMangaModal.style.display = 'flex';
    loadNhentaiTags();
    pywebview.api.get_manga_download_dir().then(res => {
        document.getElementById('manga-dl-dir-display').innerText = res.dir;
    });
}

function closeOnlineManga() {
    onlineMangaModal.style.display = 'none';
}

function changeMangaDownloadDir() {
    pywebview.api.choose_manga_download_dir().then(res => {
        if (res.status === 'success') {
            document.getElementById('manga-dl-dir-display').innerText = res.dir;
        }
    });
}

function loadNhentaiTags() {
    if (nhentaiTagsList.children.length > 1) return; // Already loaded
    pywebview.api.get_nhentai_tags().then(res => {
        if (res.status === 'success') {
            nhentaiTagsList.innerHTML = '';
            res.tags.forEach(tag => {
                const btn = document.createElement('button');
                btn.className = 'tag-btn';
                btn.style.textAlign = 'left';
                btn.style.padding = '5px';
                btn.style.background = 'transparent';
                btn.style.color = '#ff477e';
                btn.style.border = 'none';
                btn.style.cursor = 'pointer';
                btn.innerText = tag;
                btn.onclick = () => {
                    nhentaiSearchInput.value = tag;
                    searchOnlineManga();
                };
                nhentaiTagsList.appendChild(btn);
            });
        } else {
            nhentaiTagsList.innerHTML = `<span style="color:red">Failed to load: ${res.msg}</span>`;
        }
    });
}

function searchOnlineManga() {
    const query = nhentaiSearchInput.value.trim();
    if (!query) return;
    
    onlineMangaStatus.innerText = `Searching for "${query}"...`;
    nhentaiResultsArea.innerHTML = '';
    
    pywebview.api.search_nhentai(query).then(res => {
        if (res.status === 'success') {
            onlineMangaStatus.innerText = `Found ${res.results.length} results for "${query}"`;
            res.results.forEach(item => {
                const card = document.createElement('div');
                card.style.background = '#333';
                card.style.borderRadius = '5px';
                card.style.padding = '10px';
                card.style.display = 'flex';
                card.style.flexDirection = 'column';
                card.style.gap = '10px';
                
                const img = document.createElement('img');
                img.src = item.thumb;
                img.style.width = '100%';
                img.style.height = '200px';
                img.style.objectFit = 'cover';
                img.style.borderRadius = '3px';
                
                const title = document.createElement('div');
                title.innerText = item.title;
                title.style.fontSize = '12px';
                title.style.color = 'white';
                title.style.textAlign = 'center';
                title.style.flexGrow = '1';
                
                const dlBtn = document.createElement('button');
                dlBtn.innerText = 'Download';
                dlBtn.style.background = '#4CAF50';
                dlBtn.style.color = 'white';
                dlBtn.style.border = 'none';
                dlBtn.style.padding = '5px';
                dlBtn.style.borderRadius = '3px';
                dlBtn.style.cursor = 'pointer';
                dlBtn.onclick = () => {
                    dlBtn.innerText = 'Downloading...';
                    dlBtn.disabled = true;
                    dlBtn.style.background = '#888';
                    pywebview.api.download_nhentai(item.url, item.title);
                };
                
                card.appendChild(img);
                card.appendChild(title);
                card.appendChild(dlBtn);
                nhentaiResultsArea.appendChild(card);
            });
        } else {
            onlineMangaStatus.innerText = `Search failed: ${res.msg}`;
        }
    });
}

function downloadComplete(dir_path) {
    onlineMangaStatus.innerText = `Download complete! Loaded into playlist.`;
    onlineMangaStatus.style.color = '#4CAF50';
    setTimeout(() => { onlineMangaStatus.style.color = '#aaa'; }, 3000);
    // Tell pywebview to load this directory
    pywebview.api.open_manga_viewer(dir_path);
}

function downloadFailed(err) {
    onlineMangaStatus.innerText = `Download failed: ${err}`;
    onlineMangaStatus.style.color = 'red';
}
