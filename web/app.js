let videoPlayer, audioPlayer, imageViewer, playlistContainer, fileNameDisplay, playBtn, prevBtn, nextBtn, cm, mlCm, omCm, mediaContainer, selectionBox, transContainer, loadingOverlay, observer;
let currentIsAudio = false;
let normBtn, thresholdSlider, gainSlider, normContainer;

videoPlayer = document.getElementById('video-player');
if (videoPlayer) videoPlayer.crossOrigin = "anonymous";
audioPlayer = document.getElementById('audio-player');
if (audioPlayer) audioPlayer.crossOrigin = "anonymous";
imageViewer = document.getElementById('image-viewer');
playlistContainer = document.getElementById('playlist');
fileNameDisplay = document.getElementById('current-file-name');
if (fileNameDisplay) {
    fileNameDisplay.style.fontWeight = 'bold';
    fileNameDisplay.style.color = 'lightblue';
}

// --- Style Injection for Correct Alignment ---
// This corrects layout issues by injecting a style block directly,
// overriding any problematic external CSS for alignment.
const alignmentStyles = `
    #media-container.splash-view,
    #media-container.splash-view .pane-content {
        justify-content: center !important;
    }
    #media-container {
        padding-left: 25px;
        padding-right: 25px;
        box-sizing: border-box;
    }
    #media-container.align-left { justify-content: flex-start; }
    #media-container.align-center { justify-content: safe center; }
    #media-container.align-right { justify-content: safe flex-end; }

    /* New View Controls Bar */
    #view-controls-bar {
        background: #11111b;
        padding: 5px 20px;
        display: flex;
        align-items: center;
        gap: 20px;
        border-bottom: 1px solid #313244;
    }

    #view-collection-btn {
        background: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 10px;
        cursor: pointer;
        font-size: 13px;
        font-weight: bold;
        transition: all 0.2s ease;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    #view-collection-btn:hover {
        background: #45475a;
        color: #ffffff;
    }

    #alignment-controls {
        display: inline-flex;
    }

    /* Alignment buttons in bottom controls */
    #alignment-controls button {
        background: transparent;
        border: 1px solid #444;
        color: #a0a0b0;
        padding: 4px 8px;
        cursor: pointer;
        font-size: 14px;
        line-height: 1;
    }
    #alignment-controls button:first-child { border-radius: 4px 0 0 4px; }
    #alignment-controls button:last-child { border-radius: 0 4px 4px 0; }
    #alignment-controls button:not(:last-child) { border-right: none; }
    #alignment-controls button:hover {
        background: #45475a;
        color: #cdd6f4;
    }
    #alignment-controls button.active {
        background: #89b4fa;
        color: #11111b;
        border-color: #89b4fa;
    }
`;

playBtn = document.getElementById('play-btn');

// Dynamically create Previous and Next buttons for the media controls
prevBtn = document.createElement('button');
prevBtn.className = playBtn.className;
prevBtn.innerHTML = '<i class="fa-solid fa-backward-step"></i>';
prevBtn.style.marginRight = '10px';
prevBtn.style.cursor = 'pointer';
prevBtn.title = "Previous Media";
prevBtn.onclick = () => handlePrevMedia();
playBtn.parentNode.insertBefore(prevBtn, playBtn);

nextBtn = document.createElement('button');
nextBtn.className = playBtn.className;
nextBtn.innerHTML = '<i class="fa-solid fa-forward-step"></i>';
nextBtn.style.marginLeft = '10px';
nextBtn.style.cursor = 'pointer';
nextBtn.title = "Next Media";
nextBtn.onclick = () => handleNextMedia();
playBtn.parentNode.insertBefore(nextBtn, playBtn.nextSibling);

let playlist = [];
let sortAsc = true;

function toggleSortDir() {
    sortAsc = !sortAsc;
    const btn = document.getElementById('sort-dir-btn');
    if (btn) btn.innerHTML = sortAsc ? '<i class="fa-solid fa-arrow-up"></i>' : '<i class="fa-solid fa-arrow-down"></i>';
    renderPlaylist();
}
let currentIndex = -1;
let selectedIndices = new Set();
let lastSelectedIndex = -1;
let collectionTranslations = {};
let currentAlignment = 'left'; // 'left', 'center', 'right'
let currentZoom = 'fit'; // 'fit', 'original', 'double'
let showDownloadsUI = true;
let listeningInput = null;

let splitScreenActive = false;
let leftPlaylist = [];
let leftCurrentIndex = -1;
let rightPlaylist = [];
let rightCurrentIndex = -1;
let activeSidebarTab = 'left'; // 'left' or 'right'

function handlePrevMedia() {
    if (splitScreenActive) {
        if (activeSidebarTab === 'right') {
            navigatePaneImage(-1);
        } else {
            navigateLeftPane(-1);
        }
    } else {
        pywebview.api.prev_media();
    }
}

function handleNextMedia() {
    if (splitScreenActive) {
        if (activeSidebarTab === 'right') {
            navigatePaneImage(1);
        } else {
            navigateLeftPane(1);
        }
    } else {
        pywebview.api.next_media();
    }
}

cm = document.getElementById('context-menu');
mlCm = document.getElementById('collection-library-context-menu');
omCm = document.getElementById('online-media-context-menu');

window.addEventListener('click', () => {
    if (cm) cm.style.display = 'none';
    if (mlCm) mlCm.style.display = 'none';
    if (omCm) omCm.style.display = 'none';
});
window.addEventListener('contextmenu', e => e.preventDefault());

let appState = {};

window.addEventListener('pywebviewready', function () {
    // --- DOM Element Assignments ---
    videoPlayer = document.getElementById('video-player');
    imageViewer = document.getElementById('image-viewer');
    playlistContainer = document.getElementById('playlist');
    fileNameDisplay = document.getElementById('current-file-name');
    playBtn = document.getElementById('play-btn');
    cm = document.getElementById('context-menu');
    mlCm = document.getElementById('collection-library-context-menu');
    omCm = document.getElementById('online-media-context-menu');
    mediaContainer = document.getElementById('media-container');
    selectionBox = document.getElementById('selection-box');
    transContainer = document.getElementById('translations-container');
    loadingOverlay = document.getElementById('collection-loading');
    normContainer = document.getElementById('norm-controls-container');

    // --- Initial Element Setup ---
    videoPlayer.crossOrigin = "anonymous";
    fileNameDisplay.style.fontWeight = 'bold';
    fileNameDisplay.style.color = 'lightblue';

    // --- Dynamic Element Creation ---
    prevBtn = document.createElement('button');
    prevBtn.className = playBtn.className;
    prevBtn.innerHTML = '<i class="fa-solid fa-backward-step"></i>';
    prevBtn.style.marginRight = '10px';
    prevBtn.style.cursor = 'pointer';
    prevBtn.title = "Previous Media";
    prevBtn.onclick = () => handlePrevMedia();
    playBtn.parentNode.insertBefore(prevBtn, playBtn);

    nextBtn = document.createElement('button');
    nextBtn.className = playBtn.className;
    nextBtn.innerHTML = '<i class="fa-solid fa-forward-step"></i>';
    nextBtn.style.marginLeft = '10px';
    nextBtn.style.cursor = 'pointer';
    nextBtn.title = "Next Media";
    nextBtn.onclick = () => handleNextMedia();
    playBtn.parentNode.insertBefore(nextBtn, playBtn.nextSibling);

    // Setup Audio Normalization controls inside floating window
    const ncc = document.getElementById('norm-controls-container');
    if (ncc && normContainer) {
        ncc.innerHTML = '';
        
        normContainer.style.display = 'flex';
        normContainer.style.flexDirection = 'column';
        normContainer.style.gap = '10px';
        normContainer.style.marginLeft = '0px';
        normContainer.style.color = 'white';
        
        normBtn.style.padding = '6px 10px';
        normBtn.style.borderRadius = '3px';
        normBtn.style.border = 'none';
        normBtn.style.background = '#4CAF50';
        normBtn.style.color = 'white';
        normBtn.style.cursor = 'pointer';
        normBtn.style.width = '100%';
        normBtn.style.fontWeight = 'bold';
        normBtn.style.marginLeft = '0px';
        
        const row1 = document.createElement('div');
        row1.style.display = 'flex';
        row1.style.justifyContent = 'space-between';
        row1.style.alignItems = 'center';
        thresholdSlider.style.width = '120px';
        thresholdSlider.style.cursor = 'pointer';
        
        // Find existing label or create if needed
        const threshLabel = normContainer.querySelector('span') || document.createElement('span');
        threshLabel.innerText = 'Loud:';
        threshLabel.style.fontSize = '12px';
        
        row1.appendChild(threshLabel);
        row1.appendChild(thresholdSlider);
        
        const row2 = document.createElement('div');
        row2.style.display = 'flex';
        row2.style.justifyContent = 'space-between';
        row2.style.alignItems = 'center';
        gainSlider.style.width = '120px';
        gainSlider.style.cursor = 'pointer';
        
        const gainLabel = document.createElement('span');
        gainLabel.innerText = 'Quiet:';
        gainLabel.style.fontSize = '12px';
        
        row2.appendChild(gainLabel);
        row2.appendChild(gainSlider);
        
        normContainer.innerHTML = '';
        normContainer.appendChild(normBtn);
        normContainer.appendChild(row1);
        normContainer.appendChild(row2);
        
        ncc.appendChild(normContainer);
    }

    // --- Initialize IntersectionObserver for lazy loading ---
    observer = new IntersectionObserver((entries, observer) => {
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
    }, { root: playlistContainer, rootMargin: '50px' });

    // --- Attach Event Listeners ---
    attachEventListeners();

    // --- App Initialization ---
    pywebview.api.get_startup_info().then(info => {
        if (info && info.art_path) {
            // Display the startup image
            const mediaUrl = `http://localhost:5050/media?path=${encodeURIComponent(info.art_path)}`;
            imageViewer.style.display = 'block';
            videoPlayer.style.display = 'none';
            imageViewer.src = mediaUrl;

            // Explicitly set pane displays to ensure correct layout and alignment on load
            document.getElementById('left-split-pane').style.display = 'none';
            document.getElementById('right-split-pane').style.display = 'flex';

            // Add a special class for centered startup view
            mediaContainer.classList.add('splash-view');

            // Set a default filename display
            fileNameDisplay.textContent = 'XenoPlayer';
        }

        // Now, proceed with normal initialization
        pywebview.api.init().then(response => {
            updateState();
        });
    });

    // Inject the alignment correction styles into the document head
    const styleSheet = document.createElement("style");
    styleSheet.innerText = alignmentStyles;
    document.head.appendChild(styleSheet);
    updateViewMenuCheckmarks();

    // Create extra viewers for split screen mode
    leftImage = imageViewer.cloneNode(true);
    leftImage.id = 'left-image-viewer';
    document.getElementById('left-split-pane').appendChild(leftImage);

    rightVideo = videoPlayer.cloneNode(true);
    rightVideo.id = 'right-video-player';
    document.getElementById('right-split-pane').appendChild(rightVideo);
    
    rightVideo.addEventListener('loadedmetadata', updateMediaDimensions);
    rightVideo.addEventListener('timeupdate', () => {});
    rightVideo.addEventListener('ended', handleNextMedia);

    leftTextViewer = document.createElement('div');
    leftTextViewer.id = 'left-text-viewer';
    leftTextViewer.className = 'text-viewer-content';
    document.getElementById('left-split-pane').appendChild(leftTextViewer);

    rightTextViewer = document.createElement('div');
    rightTextViewer.id = 'right-text-viewer';
    rightTextViewer.className = 'text-viewer-content';
    document.getElementById('right-split-pane').appendChild(rightTextViewer);

    // Create and add pane type selectors
    const leftHeader = document.getElementById('left-pane-header');
    if (leftHeader) leftHeader.appendChild(createPaneTypeSelector('left'));
    const rightHeader = document.getElementById('right-pane-header');
    if (rightHeader) rightHeader.appendChild(createPaneTypeSelector('right'));

    // Add prominent close buttons to online modals
    addStandardCloseButton('online-media-modal', closeOnlineMedia);
    addStandardCloseButton('online-audio-modal', closeOnlineAudio);
    addStandardCloseButton('online-stories-modal', closeOnlineStories);
    addStandardCloseButton('online-sources-modal', closeOnlineSourcesModal);
    addStandardCloseButton('collection-library-modal', closeCollectionLibrary);

    // Setup Draggables
    const sidebar = document.getElementById('sidebar');
    const sidebarHeader = document.getElementById('sidebar-header');
    if (sidebarHeader && sidebar) {
        sidebarHeader.addEventListener('mousedown', (e) => {
            if (!sidebar.classList.contains('floating')) return;
            if (e.target.closest('button, input, select, a')) return;
            if (e.button !== 0) return;
            let isDraggingSidebar = true;
            let dragStartX = e.clientX;
            let dragStartY = e.clientY;
            const rect = sidebar.getBoundingClientRect();
            let sidebarStartX = rect.left;
            let sidebarStartY = rect.top;
            e.preventDefault();
            
            const onMouseMove = (moveE) => {
                if (!isDraggingSidebar) return;
                const dx = moveE.clientX - dragStartX;
                const dy = moveE.clientY - dragStartY;
                sidebar.style.left = (sidebarStartX + dx) + 'px';
                sidebar.style.top = (sidebarStartY + dy) + 'px';
                sidebar.style.bottom = 'auto';
            };
            const onMouseUp = () => {
                isDraggingSidebar = false;
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            };
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }

    makeDraggable(document.getElementById('audio-norm-window'), document.getElementById('audio-norm-header'));
    makeDraggable(document.getElementById('translate-settings-window'), document.getElementById('translate-settings-header'));
});

function activeMedia() {
    return currentIsAudio ? audioPlayer : videoPlayer;
}

function loadMedia(path, index) {
    // Remove splash view class if it exists
    mediaContainer.classList.remove('splash-view');

    if (splitScreenActive) {
        const cleanPath = path.split('?')[0];
        const ext = cleanPath.split('.').pop().toLowerCase();
        if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
            loadRightMedia(path);
        } else {
            loadLeftMedia(path);
        }
        return;
    }

    if (currentIndex !== index) {
        resetLoopCount();
    }
    currentIndex = index;
    if (showFoldersActive) {
        autoExpandActiveFolder(path);
    }
    const display = document.getElementById('media-dimensions-display');
    if (display) display.textContent = "Resolution: Loading...";
    const isOnline = path.startsWith('http://') || path.startsWith('https');
    const parts = path.split(/[/\\]/);
    const fileName = parts.pop();
    const folderName = parts.pop() || "";
    const fullDisplayName = folderName ? (folderName + " / " + fileName) : fileName;
    fileNameDisplay.textContent = fullDisplayName + '  -  ';

    // Update active class
    renderPlaylist();

    const cleanPath = path.split('?')[0];
    const ext = cleanPath.split('.').pop().toLowerCase();
    const mediaUrl = isOnline ? path : `http://localhost:5050/media?path=${encodeURIComponent(path)}`;

    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
        // Single view image
        document.getElementById('left-split-pane').style.display = 'none';
        document.getElementById('right-split-pane').style.display = 'flex';

        videoPlayer.style.display = 'none';
        videoPlayer.pause();
        audioPlayer.style.display = 'none';
        audioPlayer.pause();
        currentIsAudio = false;
        imageViewer.style.display = 'block';
        imageViewer.src = mediaUrl;

        playBtn.innerHTML = '<i class="fa-solid fa-play"></i>'; // Images don't play

        // Load collection info
        pywebview.api.get_collection_info(path).then(info => {
            collectionTranslations = info || {};
            renderTranslations(path);
        });
        updateImageTimer();
    } else {
        // Single view video or audio
        const isAudio = ['mp3', 'wav', 'wave'].includes(ext);
        currentIsAudio = isAudio;
        const mediaEl = isAudio ? audioPlayer : videoPlayer;
        const otherEl = isAudio ? videoPlayer : audioPlayer;

        document.getElementById('left-split-pane').style.display = 'flex';
        document.getElementById('right-split-pane').style.display = 'none';

        imageViewer.style.display = 'none';
        otherEl.style.display = 'none';
        otherEl.pause();
        mediaEl.style.display = 'block';
        mediaEl.src = mediaUrl;
        mediaEl.play();
        playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        document.getElementById('translations-container').innerHTML = '';
        if (imageTimerInterval) {
            clearInterval(imageTimerInterval);
            imageTimerInterval = null;
        }
        if (appState.saved_volumes && appState.saved_volumes[path] !== undefined) {
            const savedVol = appState.saved_volumes[path];
            mediaEl.volume = savedVol / 100.0;
            // Auto-update volume slider visually if it exists
            const volSlider = document.querySelector('input[type="range"][onchange*="changeVolume"]') || document.querySelector('input[oninput*="changeVolume"]');
            if (volSlider) volSlider.value = savedVol;
        }
    }
    updateState();
}

function updateState() {
    pywebview.api.get_state().then(state => {
        appState = state;
        renderState();
    });
}

function renderState() {
    // Update Recursive Load Checkbox
    const recCheckbox = document.getElementById('recursive-load-checkbox');
    if (recCheckbox) {
        recCheckbox.checked = appState.recursive_load || false;
    }

    // Update Favorite Star
    const favBtn = document.getElementById('favorite-btn');
    if (appState.is_favorite) {
        favBtn.innerHTML = '<i class="fa-solid fa-star" style="color: gold;"></i>';
    } else {
        favBtn.innerHTML = '<i class="fa-regular fa-star"></i>';
    }

    // Render Move Targets
    const targetsContainer = document.getElementById('move-targets-container');
    if (targetsContainer) {
        targetsContainer.innerHTML = '';
        for (const [name, path] of Object.entries(appState.move_targets || {})) {
            const btn = document.createElement('button');
            btn.innerHTML = `<i class="fa-solid fa-arrow-right-to-bracket"></i> ${name}`;
            btn.onclick = () => {
                pywebview.api.move_file_to(name).then(res => {
                    if (res.status === 'success') {
                        updateState();
                    } else {
                        alert(res.msg);
                    }
                });
            };
            targetsContainer.appendChild(btn);
        }
    }

    // Toggle View Collection button visibility based on folder type and active media
    const isVideo = videoPlayer.style.display === 'block';
    const buttons = document.querySelectorAll('button');
    buttons.forEach(b => {
        if (b.innerText.toLowerCase().includes('view collection')) {
            b.style.display = (appState.is_collection_folder && !isVideo) ? 'inline-flex' : 'none';
        }
    });
}

function setMediaAlignment(align) {
    currentAlignment = align;
    applyMediaStyles();
    updateViewMenuCheckmarks();
}

function setMediaZoom(zoom) {
    currentZoom = zoom;
    applyMediaStyles();
    updateViewMenuCheckmarks();
}

function updateMediaDimensions() {
    const display = document.getElementById('media-dimensions-display');
    if (!display) return;

    if (splitScreenActive) {
        const vw = videoPlayer.videoWidth || 0;
        const vh = videoPlayer.videoHeight || 0;
        const iw = imageViewer.naturalWidth || 0;
        const ih = imageViewer.naturalHeight || 0;
        display.textContent = `Resolution: Video ${vw}x${vh} | Image ${iw}x${ih}`;
    } else {
        if (videoPlayer.style.display !== 'none' && videoPlayer.videoWidth) {
            display.textContent = `Resolution: ${videoPlayer.videoWidth} x ${videoPlayer.videoHeight} (Video)`;
        } else if (imageViewer.style.display !== 'none' && imageViewer.naturalWidth) {
            display.textContent = `Resolution: ${imageViewer.naturalWidth} x ${imageViewer.naturalHeight} (Image)`;
        } else {
            display.textContent = "Resolution: Unknown";
        }
    }
}

function applyMediaStyles() {
    // 1. Apply Alignment to #media-container
    mediaContainer.classList.remove('align-left', 'align-center', 'align-right');
    mediaContainer.classList.add(`align-${currentAlignment}`);

    // --- DEFINITIVE FIX for alignment bug ---
    // Force a browser repaint by making a trivial style change and then removing it.
    // This is more reliable than offsetHeight or setTimeout for forcing the browser
    // to apply the alignment classes above before proceeding.
    mediaContainer.style.outline = '1px solid transparent';
    setTimeout(() => { mediaContainer.style.outline = ''; }, 0);
    
    // 2. Apply Zoom class and layout
    imageViewer.classList.remove('zoom-fit', 'zoom-original', 'zoom-double');
    videoPlayer.classList.remove('zoom-fit', 'zoom-original', 'zoom-double');
    imageViewer.classList.add(`zoom-${currentZoom}`);
    videoPlayer.classList.add(`zoom-${currentZoom}`);

    if (splitScreenActive) {
        if (currentZoom === 'fit') {
            imageViewer.style.width = '';
            imageViewer.style.height = '';
            videoPlayer.style.width = '';
            videoPlayer.style.height = '';
        } else if (currentZoom === 'original') {
            imageViewer.style.width = '';
            imageViewer.style.height = '';
            videoPlayer.style.width = '';
            videoPlayer.style.height = '';
        } else if (currentZoom === 'double') {
            let iw = imageViewer.naturalWidth * 2 || 0;
            let ih = imageViewer.naturalHeight * 2 || 0;
            let vw = videoPlayer.videoWidth * 2 || 0;
            let vh = videoPlayer.videoHeight * 2 || 0;
            
            if (iw && ih) {
                imageViewer.style.width = iw + 'px';
                imageViewer.style.height = ih + 'px';
            } else {
                imageViewer.style.width = '';
                imageViewer.style.height = '';
            }
            if (vw && vh) {
                videoPlayer.style.width = vw + 'px';
                videoPlayer.style.height = vh + 'px';
            } else {
                videoPlayer.style.width = '';
                videoPlayer.style.height = '';
            }
        }
        if (rightPlaylist[rightCurrentIndex]) {
            setTimeout(() => {
                renderTranslations(rightPlaylist[rightCurrentIndex].path);
            }, 50);
        }
        return;
    }

    if (currentZoom === 'fit') {
        mediaContainer.style.overflow = 'hidden';
        imageViewer.style.width = '';
        imageViewer.style.height = '';
        videoPlayer.style.width = '';
        videoPlayer.style.height = '';
    } else if (currentZoom === 'original') {
        mediaContainer.style.overflow = 'auto';
        imageViewer.style.width = '';
        imageViewer.style.height = '';
        videoPlayer.style.width = '';
        videoPlayer.style.height = '';
    } else if (currentZoom === 'double') {
        mediaContainer.style.overflow = 'auto';

        let w = 0, h = 0;
        if (imageViewer.style.display !== 'none' && imageViewer.naturalWidth) {
            w = imageViewer.naturalWidth * 2;
            h = imageViewer.naturalHeight * 2;
        } else if (videoPlayer.style.display !== 'none' && videoPlayer.videoWidth) {
            w = videoPlayer.videoWidth * 2;
            h = videoPlayer.videoHeight * 2;
        }

        if (w && h) {
            imageViewer.style.width = w + 'px';
            imageViewer.style.height = h + 'px';
            videoPlayer.style.width = w + 'px';
            videoPlayer.style.height = h + 'px';
        } else {
            imageViewer.style.width = '';
            imageViewer.style.height = '';
            videoPlayer.style.width = '';
            videoPlayer.style.height = '';
        }
    }

    // 3. Re-render translations if image is active and playlist is loaded
    if (imageViewer.style.display !== 'none' && playlist[currentIndex]) {
        setTimeout(() => {
            renderTranslations(playlist[currentIndex].path);
        }, 50);
    }
}

function updateViewMenuCheckmarks() {
    const alignments = ['left', 'center', 'right'];
    alignments.forEach(align => {
        // Update dropdown menu
        const menuBtn = document.getElementById(`align-${align}-btn`);
        if (menuBtn) {
            menuBtn.innerHTML = `<i class="fa-solid fa-align-${align}"></i> ${align.charAt(0).toUpperCase() + align.slice(1)}` +
                (currentAlignment === align ? ' <i class="fa-solid fa-check" style="float: right; margin-top: 3px;"></i>' : '');
        }
        // Update bottom bar buttons
        const bottomBtn = document.getElementById(`btn-align-${align}`);
        if (bottomBtn) {
            if (currentAlignment === align) {
                bottomBtn.classList.add('active');
            } else {
                bottomBtn.classList.remove('active');
            }
        }
    });

    const zooms = {
        'fit': { label: 'Fit Screen', icon: 'fa-compress' },
        'original': { label: 'Original (100%)', icon: 'fa-expand' },
        'double': { label: 'Double (200%)', icon: 'fa-magnifying-glass-plus' }
    };
    for (const [zoom, info] of Object.entries(zooms)) {
        const btn = document.getElementById(`zoom-${zoom}-btn`);
        if (btn) {
            btn.innerHTML = `<i class="fa-solid ${info.icon}"></i> ${info.label}` +
                (currentZoom === zoom ? ' <i class="fa-solid fa-check" style="float: right; margin-top: 3px;"></i>' : '');
        }
    }

    const dlBtn = document.getElementById('view-downloads-btn');
    if (dlBtn) {
        dlBtn.innerHTML = `<i class="fa-solid fa-download"></i> Downloads` +
            (showDownloadsUI ? ' <i class="fa-solid fa-check" style="float: right; margin-top: 3px;"></i>' : '');
    }
}

function toggleDownloads() {
    showDownloadsUI = !showDownloadsUI;
    const container = document.getElementById('global-download-container');
    if (container) {
        container.style.display = showDownloadsUI ? 'flex' : 'none';
    }
    updateViewMenuCheckmarks();
}

function openDownloadHistoryModal() {
    document.getElementById('history-modal').style.display = 'block';
    renderDownloadHistory();
}

function renderDownloadHistory() {
    const list = document.getElementById('history-list');
    list.innerHTML = '<div style="color: #aaa;">Loading...</div>';

    pywebview.api.get_download_history().then(history => {
        list.innerHTML = '';
        if (!history || history.length === 0) {
            list.innerHTML = '<div style="color: #666; text-align: center; padding: 20px;">No download history found.</div>';
            return;
        }

        history.forEach(item => {
            const div = document.createElement('div');
            div.style.background = '#111';
            div.style.padding = '10px';
            div.style.borderRadius = '4px';
            div.style.borderLeft = item.type === 'collection' ? '4px solid #ff477e' : '4px solid #89dceb';
            div.style.display = 'flex';
            div.style.justifyContent = 'space-between';
            div.style.alignItems = 'center';

            const info = document.createElement('div');
            info.style.display = 'flex';
            info.style.flexDirection = 'column';
            info.style.gap = '4px';

            const title = document.createElement('strong');
            title.textContent = item.title;
            title.style.color = '#fff';
            title.style.fontSize = '14px';

            const path = document.createElement('span');
            path.textContent = item.path;
            path.style.color = '#aaa';
            path.style.fontSize = '11px';
            path.style.wordBreak = 'break-all';

            const date = new Date(item.timestamp * 1000).toLocaleString();
            const meta = document.createElement('span');
            meta.innerHTML = `<i class="fa-solid ${item.type === 'collection' ? 'fa-book' : 'fa-music'}"></i> ${item.type.toUpperCase()} &nbsp;&bull;&nbsp; ${date}`;
            meta.style.color = '#666';
            meta.style.fontSize = '10px';

            info.appendChild(title);
            info.appendChild(path);
            info.appendChild(meta);

            const actions = document.createElement('div');
            const openBtn = document.createElement('button');
            openBtn.innerHTML = '<i class="fa-regular fa-folder-open"></i> Open Location';
            openBtn.style.background = '#4CAF50';
            openBtn.style.color = 'white';
            openBtn.style.border = 'none';
            openBtn.style.padding = '6px 12px';
            openBtn.style.borderRadius = '3px';
            openBtn.style.cursor = 'pointer';
            openBtn.style.fontSize = '12px';
            openBtn.style.whiteSpace = 'nowrap';
            openBtn.onclick = () => pywebview.api.open_folder_location(item.path);

            actions.appendChild(openBtn);

            div.appendChild(info);
            div.appendChild(actions);
            list.appendChild(div);
        });
    });
}

function clearDownloadHistory() {
    if (confirm("Are you sure you want to clear your download history? This will not delete the actual files.")) {
        pywebview.api.clear_download_history().then(() => {
            renderDownloadHistory();
        });
    }
}

function toggleFavorite() {
    pywebview.api.toggle_favorite().then(state => {
        appState = state;
        renderState();
    });
}

function deleteDupes() {
    if (confirm("Are you sure you want to delete duplicates in this folder?")) {
        pywebview.api.delete_dupes().then(res => {
            alert(res.msg);
        });
    }
}

function cleanLibrary() {
    if (confirm("Choose a directory to clean. Empty subfolders will be deleted, and nested media files will be pulled up to their parent folders (one level below the selected directory root). Continue?")) {
        pywebview.api.clean_collection_directory().then(res => {
            if (res.status === 'success') {
                alert(res.msg);
                updateState();
                if (typeof renderCollectionLibrary === 'function') {
                    renderCollectionLibrary();
                }
            } else if (res.status === 'error') {
                alert("Error: " + res.msg);
            }
        });
    }
}

// Modals
function openAboutModal() {
    document.getElementById('about-modal').style.display = 'block';
}

let tempFavs = [];

function openFavsModal() {
    document.getElementById('favs-modal').style.display = 'block';
    tempFavs = [...(appState.favorites || [])];
    renderFavsList();
}

function renderFavsList() {
    const list = document.getElementById('favs-list');
    list.innerHTML = '';

    if (tempFavs.length === 0) {
        list.innerHTML = '<div style="color:#aaa;">No favorites saved.</div>';
        return;
    }

    tempFavs.forEach((fav, index) => {
        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.justifyContent = 'space-between';
        div.style.marginBottom = '5px';
        div.style.alignItems = 'center';
        div.style.background = '#222';
        div.style.padding = '5px';
        div.style.borderRadius = '3px';

        const pathSpan = document.createElement('span');
        pathSpan.textContent = fav.split('\\').pop().split('/').pop();
        pathSpan.style.wordBreak = 'break-all';
        pathSpan.style.marginRight = '10px';
        pathSpan.style.fontSize = '12px';

        const remBtn = document.createElement('button');
        remBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        remBtn.style.background = '#d32f2f';
        remBtn.style.color = 'white';
        remBtn.style.border = 'none';
        remBtn.style.padding = '5px 10px';
        remBtn.style.cursor = 'pointer';
        remBtn.style.borderRadius = '3px';
        remBtn.onclick = () => {
            tempFavs.splice(index, 1);
            renderFavsList();
        };

        div.appendChild(pathSpan);
        div.appendChild(remBtn);
        list.appendChild(div);
    });
}

function saveFavsModal() {
    pywebview.api.save_favorites(tempFavs).then(state => {
        appState = state;
        renderState();
        closeModals();
    });
}

function openInstructionsModal() {
    document.getElementById('instructions-modal').style.display = 'block';
    switchTab('tab-main', document.querySelector('.tab-btn'));
}

function switchTab(tabId, btnElement) {
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(b => b.style.background = '#444');
    document.getElementById(tabId).style.display = 'block';
    if (btnElement) {
        btnElement.style.background = '#ff477e';
    }
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

function startListening(input) {
    if (listeningInput) {
        stopListening(listeningInput);
    }
    listeningInput = input;
    input.value = "Listening...";
    input.style.borderColor = "#4CAF50";
    input.style.backgroundColor = "#1e3d24";

    // Add global listeners to capture the next input event
    window.addEventListener('keydown', captureHotkeyEvent, true);
    window.addEventListener('mousedown', captureHotkeyEvent, true);
}

function stopListening(input) {
    input.style.borderColor = "";
    input.style.backgroundColor = "";
    window.removeEventListener('keydown', captureHotkeyEvent, true);
    window.removeEventListener('mousedown', captureHotkeyEvent, true);
    listeningInput = null;
}

function captureHotkeyEvent(e) {
    if (!listeningInput) return;
    e.preventDefault();
    e.stopPropagation();

    let code = "";
    if (e.type === 'keydown') {
        if (e.code === 'Backspace') {
            code = "";
        } else if (e.code === 'Escape') {
            // Cancel assignment
            stopListening(listeningInput);
            return;
        } else {
            code = e.code;
        }
    } else if (e.type === 'mousedown') {
        code = `Mouse${e.button}`;
    }

    listeningInput.value = code;
    stopListening(listeningInput);
}

function closeModals() {
    if (listeningInput) {
        stopListening(listeningInput);
    }
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    stopOnionPolling();
    stopOnionEncryptPolling();
    if (onionStatus && (onionStatus.state === 'packing' || onionStatus.state === 'starting' || onionStatus.state === 'running')) {
        startOnionBackgroundPolling();
    }
}

let onionMode = 'share';
let onionSelectedPaths = [];
let onionPollTimer = null;
let onionBackgroundTimer = null;
let onionStatus = null;
let onionActivePassword = '';
let onionStartPending = false;
let onionStartToken = 0;
let onionEncryptStatus = null;
let onionEncryptPollTimer = null;

function openOnionShareModal() {
    if (onionBackgroundTimer) {
        clearInterval(onionBackgroundTimer);
        onionBackgroundTimer = null;
    }
    const passwordInput = document.getElementById('onion-password');
    const passwordToggle = document.getElementById('onion-password-toggle');
    if (passwordInput) passwordInput.type = 'password';
    if (passwordToggle) passwordToggle.textContent = 'Show';
    document.getElementById('onionshare-modal').style.display = 'block';
    document.getElementById('onion-error').style.display = 'none';
    renderOnionPaths();
    switchOnionMode('share');
    renderEncryptOutputDir();
    renderEncryptStatus(onionEncryptStatus);
    refreshOnionStatus();
    startOnionPolling();
}

function startOnionPolling() {
    stopOnionPolling();
    onionPollTimer = setInterval(refreshOnionStatus, 1000);
}

function stopOnionPolling() {
    if (onionPollTimer) clearInterval(onionPollTimer);
    onionPollTimer = null;
}

function startOnionBackgroundPolling() {
    if (onionBackgroundTimer) return;
    onionBackgroundTimer = setInterval(() => {
        if (!window.pywebview || !pywebview.api) return;
        pywebview.api.get_onion_status().then(s => {
            onionStatus = s;
            updateOnionSidebar(s);
            if (s.state === 'stopped' || s.state === 'error') {
                clearInterval(onionBackgroundTimer);
                onionBackgroundTimer = null;
            }
        }).catch(() => {});
    }, 5000);
}

function refreshOnionStatus() {
    if (!window.pywebview || !pywebview.api) return;
    pywebview.api.get_onion_status().then(s => {
        onionStatus = s;
        renderOnionStatus(s);
    }).catch(() => {});
}

function updateOnionSidebar(s) {
    const btn = document.getElementById('onion-share-btn');
    if (!btn) return;
    if (s.state === 'packing' || s.state === 'starting' || s.state === 'running') {
        btn.innerHTML = '<i class="fa-solid fa-share-nodes"></i> Sharing...';
        btn.style.background = '#a6e3a1';
    } else {
        btn.innerHTML = '<i class="fa-solid fa-share-nodes"></i> Share Files';
        btn.style.background = '#cba6f7';
    }
}

function updateOnionStartState() {
    const s = onionStatus || {};
    const btn = document.getElementById('onion-start-btn');
    if (!btn) return;
    const busy = s.state === 'packing' || s.state === 'starting' || s.state === 'running';
    const ready = !!s.available && (onionMode === 'receive' || !!s.seven_zip_available) && !busy;
    btn.disabled = !ready;
    btn.style.opacity = ready ? '1' : '0.5';
}

function updateEncryptButtonState() {
    const s = onionStatus || {};
    const btn = document.getElementById('onion-encrypt-btn');
    if (!btn) return;
    const encryptBusy = onionEncryptStatus && onionEncryptStatus.state === 'packing';
    const ready = !!s.seven_zip_available && !encryptBusy;
    btn.disabled = !ready;
    btn.style.opacity = ready ? '1' : '0.5';
}

function onionShowError(msg) {
    const el = document.getElementById('onion-error');
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
}

function renderOnionStatus(s) {
    if (onionStartPending && (s.state === 'stopped' || s.state === 'error')) return;
    updateOnionSidebar(s);
    const setup = document.getElementById('onion-setup');
    const active = document.getElementById('onion-active');
    const missing = document.getElementById('onion-missing');
    const receiveInput = document.getElementById('onion-receive-dir');
    if (receiveInput && s.receive_dir && !receiveInput.value) receiveInput.value = s.receive_dir;
    if (receiveInput && s.receive_dir && (s.state === 'starting' || s.state === 'running')) {
        receiveInput.value = s.receive_dir;
    }

    missing.style.display = s.available ? 'none' : 'block';
    const sevenMissing = document.getElementById('onion-7z-missing');
    sevenMissing.style.display = (!s.seven_zip_available && onionMode === 'share') ? 'block' : 'none';
    const encryptSevenMissing = document.getElementById('onion-encrypt-7z-missing');
    if (encryptSevenMissing) {
        encryptSevenMissing.style.display = (!s.seven_zip_available && onionMode === 'encrypt') ? 'block' : 'none';
    }
    updateOnionStartState();
    updateEncryptButtonState();

    const busy = s.state === 'packing' || s.state === 'starting' || s.state === 'running';
    setup.style.display = busy ? 'none' : 'block';
    active.style.display = busy ? 'block' : 'none';

    const icon = document.getElementById('onion-status-icon');
    const text = document.getElementById('onion-status-text');
    const sub = document.getElementById('onion-status-sub');
    const ready = document.getElementById('onion-ready');
    const urlInput = document.getElementById('onion-url');
    const keyInput = document.getElementById('onion-key');
    const keyRow = document.getElementById('onion-key-row');
    const instructions = document.getElementById('onion-instructions');
    const openReceive = document.getElementById('onion-open-receive');
    const archiveNote = document.getElementById('onion-archive-note');
    const copyPassword = document.getElementById('onion-copy-password');
    const log = document.getElementById('onion-log');

    if (s.state === 'packing') {
        icon.className = 'fa-solid fa-circle-notch fa-spin';
        icon.style.color = '#f9e2af';
        text.textContent = 'Encrypting archive...';
        sub.textContent = 'Packing the selected files into a password-protected .7z. Large selections may take a while.';
        ready.style.display = 'none';
    } else if (s.state === 'starting') {
        icon.className = 'fa-solid fa-circle-notch fa-spin';
        icon.style.color = '#f9e2af';
        text.textContent = 'Starting Tor...';
        sub.textContent = 'Publishing the onion address. This can take up to two minutes.';
        ready.style.display = 'none';
    } else if (s.state === 'running') {
        icon.className = 'fa-solid fa-circle-check';
        icon.style.color = '#a6e3a1';
        text.textContent = s.mode === 'receive' ? 'Ready to receive files' : 'Ready to send files';
        sub.textContent = s.auto_stop_minutes > 0
            ? `Stops automatically after ${s.auto_stop_minutes} minute(s).`
            : 'Active until you press Stop.';
        ready.style.display = 'block';
        urlInput.value = s.url || '';
        keyInput.value = s.key || '';
        keyRow.style.display = s.public ? 'none' : 'block';
        openReceive.style.display = s.mode === 'receive' ? 'inline-block' : 'none';
        const isShare = s.mode === 'share';
        archiveNote.style.display = isShare ? 'block' : 'none';
        copyPassword.style.display = isShare && onionActivePassword ? 'inline-block' : 'none';
        const how = s.public ? 'Send this address' : 'Send this address and private key';
        instructions.innerHTML = isShare
            ? `${how} to your friend. In <b>Tor Browser</b>, they download the encrypted .7z archive. Send the archive password separately; they will need 7-Zip or a compatible extractor.`
            : `${how} to your friend. In <b>Tor Browser</b>, they open the address and upload the files.`;
    }

    if (s.state === 'error') {
        const detail = (s.log || []).slice(-8).join('\n');
        onionShowError(s.error ? `${s.error}\n${detail}` : (detail || 'OnionShare stopped before the transfer became ready.'));
    } else {
        onionShowError(s.error || '');
    }
    log.textContent = (s.log || []).join('\n');
    if (s.state === 'stopped' || s.state === 'error') {
        onionActivePassword = '';
        stopOnionPolling();
    }
}

function switchOnionMode(mode) {
    onionMode = mode;
    const shareTab = document.getElementById('onion-tab-share');
    const receiveTab = document.getElementById('onion-tab-receive');
    const encryptTab = document.getElementById('onion-tab-encrypt');
    const sharePanel = document.getElementById('onion-panel-share');
    const receivePanel = document.getElementById('onion-panel-receive');
    const encryptPanel = document.getElementById('onion-panel-encrypt');
    const sharedOptions = document.getElementById('onion-shared-options');
    const errorBox = document.getElementById('onion-error');
    const startBtn = document.getElementById('onion-start-btn');
    const isShare = mode === 'share';
    const isReceive = mode === 'receive';
    const isEncrypt = mode === 'encrypt';

    sharePanel.style.display = isShare ? 'block' : 'none';
    receivePanel.style.display = isReceive ? 'block' : 'none';
    encryptPanel.style.display = isEncrypt ? 'block' : 'none';
    if (sharedOptions) sharedOptions.style.display = isEncrypt ? 'none' : 'flex';
    if (errorBox) errorBox.style.display = 'none';
    if (startBtn) startBtn.style.display = isEncrypt ? 'none' : 'block';

    const setTab = (tab, active, color) => {
        if (!tab) return;
        tab.style.background = active ? color : '#313244';
        tab.style.color = active ? '#11111b' : '#cdd6f4';
    };
    setTab(shareTab, isShare, '#cba6f7');
    setTab(receiveTab, isReceive, '#cba6f7');
    setTab(encryptTab, isEncrypt, '#a6e3a1');

    const sevenMissing = document.getElementById('onion-7z-missing');
    if (sevenMissing) sevenMissing.style.display = 'none';
    const encryptSevenMissing = document.getElementById('onion-encrypt-7z-missing');
    if (encryptSevenMissing) encryptSevenMissing.style.display = (onionStatus && !onionStatus.seven_zip_available && isEncrypt) ? 'block' : 'none';

    updateOnionStartState();
    updateEncryptButtonState();

    if (startBtn) {
        startBtn.innerHTML = isShare
            ? '<i class="fa-solid fa-tower-broadcast"></i> Start Sending'
            : '<i class="fa-solid fa-tower-broadcast"></i> Start Receiving';
    }
    onionShowError('');
    if (!isShare && !isEncrypt && onionStatus && onionStatus.receive_dir) {
        document.getElementById('onion-receive-dir').value = onionStatus.receive_dir;
    }
    if (isEncrypt) {
        renderOnionPaths();
        renderEncryptOutputDir();
        renderEncryptStatus(onionEncryptStatus);
    }
}

function renderOnionPaths() {
    renderOnionPathList('onion-path-list');
    renderOnionPathList('onion-encrypt-path-list');
}

function renderOnionPathList(listId) {
    const list = document.getElementById(listId);
    if (!list) return;
    list.innerHTML = '';
    if (onionSelectedPaths.length === 0) {
        list.textContent = 'No files or folders selected.';
        list.style.color = '#a0a0b0';
        return;
    }
    list.style.color = '#cdd6f4';
    onionSelectedPaths.forEach((path, index) => {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid #1e1e2e;';
        const name = document.createElement('span');
        name.textContent = path.split(/[\\/]/).filter(Boolean).pop() || path;
        name.title = path;
        name.style.cssText = 'flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
        const remove = document.createElement('button');
        remove.textContent = '×';
        remove.style.cssText = 'background:#45272f; color:#f38ba8; border:none; border-radius:3px; padding:1px 7px; cursor:pointer;';
        remove.onclick = () => { onionSelectedPaths.splice(index, 1); renderOnionPaths(); };
        row.appendChild(name);
        row.appendChild(remove);
        list.appendChild(row);
    });
}

function onionAddFiles() {
    pywebview.api.browse_share_files().then(paths => {
        (paths || []).forEach(p => { if (!onionSelectedPaths.includes(p)) onionSelectedPaths.push(p); });
        renderOnionPaths();
        onionShowError('');
    }).catch(err => onionShowError(String(err)));
}

function onionAddFolder() {
    pywebview.api.browse_share_folder().then(path => {
        if (path && !onionSelectedPaths.includes(path)) onionSelectedPaths.push(path);
        renderOnionPaths();
        onionShowError('');
    }).catch(err => onionShowError(String(err)));
}

function onionAddCurrentFolder() {
    const current = appState.current_path || (playlist[currentIndex] && playlist[currentIndex].path);
    if (!current || /^https?:/i.test(current)) {
        onionShowError('Open a local file first.');
        return;
    }
    const clean = current.split('?')[0];
    const cut = Math.max(clean.lastIndexOf('\\'), clean.lastIndexOf('/'));
    if (cut > 0) {
        let folder = clean.slice(0, cut);
        if (/^[A-Za-z]:$/.test(folder)) folder += '\\';
        if (!onionSelectedPaths.includes(folder)) onionSelectedPaths.push(folder);
        renderOnionPaths();
        onionShowError('');
    }
}

function onionAddSelected() {
    const selected = [];
    const hadSelection = typeof selectedIndices !== 'undefined' && selectedIndices.size > 0;
    if (hadSelection) {
        selectedIndices.forEach(index => {
            const item = playlist[index];
            if (item && item.path && !/^https?:/i.test(item.path)) selected.push(item.path);
        });
    }
    if (!selected.length && !hadSelection && currentIndex >= 0 && playlist[currentIndex] && playlist[currentIndex].path) {
        const current = playlist[currentIndex].path;
        if (!/^https?:/i.test(current)) selected.push(current);
    }
    if (!selected.length) {
        onionShowError('Select local files in the playlist first.');
        return;
    }
    selected.forEach(path => { if (!onionSelectedPaths.includes(path)) onionSelectedPaths.push(path); });
    renderOnionPaths();
    onionShowError('');
}

function onionBrowseReceive() {
    pywebview.api.browse_receive_folder().then(path => {
        if (path) document.getElementById('onion-receive-dir').value = path;
    }).catch(err => onionShowError(String(err)));
}

function onionOpenReceive() {
    const dir = document.getElementById('onion-receive-dir').value;
    pywebview.api.open_receive_folder(dir).catch(err => onionShowError(String(err)));
}

function onionStart() {
    if (!window.pywebview || !pywebview.api) return;
    const requestMode = onionMode;
    onionShowError('');
    const passwordInput = document.getElementById('onion-password');
    const password = passwordInput.value || '';
    passwordInput.type = 'password';
    const passwordToggle = document.getElementById('onion-password-toggle');
    if (passwordToggle) passwordToggle.textContent = 'Show';
    if (!onionStatus || !onionStatus.available) {
        onionShowError('OnionShare CLI not found. Install OnionShare, then click Locate CLI.');
        return;
    }
    if (onionStatus.state === 'packing' || onionStatus.state === 'starting' || onionStatus.state === 'running') {
        onionShowError('A transfer is already running.');
        return;
    }
    if (requestMode === 'share' && onionSelectedPaths.length === 0) {
        onionShowError('Add at least one file or folder to send.');
        return;
    }
    if (requestMode === 'share') {
        if (password.length < 6 || !password.trim()) {
            onionShowError('Enter an archive password with at least 6 characters.');
            return;
        }
        if (password.length > 128) {
            onionShowError('Archive password must be 128 characters or fewer.');
            return;
        }
        if (/["\r\n]/.test(password)) {
            onionShowError('Password cannot contain double quotes or line breaks.');
            return;
        }
        if (!onionStatus || !onionStatus.seven_zip_available) {
            onionShowError('7-Zip not found. Install 7-Zip, then click Locate 7z.exe.');
            return;
        }
    }
    const publicKey = !document.getElementById('onion-private').checked;
    const minutes = parseInt(document.getElementById('onion-auto-stop').value || '0', 10) || 0;
    const receiveDir = document.getElementById('onion-receive-dir').value;
    const btn = document.getElementById('onion-start-btn');
    const requestToken = ++onionStartToken;
    onionStartPending = true;

    onionStatus = Object.assign({}, onionStatus || {}, {
        state: requestMode === 'share' ? 'packing' : 'starting',
        mode: requestMode,
        url: null,
        key: null,
        error: null,
        log: []
    });
    renderOnionStatus(onionStatus);
    startOnionPolling();
    btn.disabled = true;
    btn.innerHTML = requestMode === 'share'
        ? '<i class="fa-solid fa-circle-notch fa-spin"></i> Encrypting...'
        : '<i class="fa-solid fa-circle-notch fa-spin"></i> Starting...';

    pywebview.api.start_onion_share(requestMode, onionSelectedPaths, receiveDir, publicKey, minutes, password).then(s => {
        if (requestToken !== onionStartToken) return;
        onionStartPending = false;
        onionStatus = s;
        if (s.ok !== false && requestMode === 'share' && (s.state === 'packing' || s.state === 'starting' || s.state === 'running')) {
            onionActivePassword = password;
        } else if (requestMode === 'receive') {
            onionActivePassword = '';
        }
        renderOnionStatus(s);
        if (s.ok === false) {
            if (s.state === 'stopped' || s.state === 'error') {
                onionActivePassword = '';
                if (s.error === 'Transfer cancelled.') {
                    onionShowError('');
                } else if (!s.error) {
                    onionShowError('Could not start the transfer.');
                }
            }
        }
        if (s.state === 'packing' || s.state === 'starting' || s.state === 'running') {
            startOnionPolling();
            startOnionBackgroundPolling();
        }
        btn.innerHTML = requestMode === 'share'
            ? '<i class="fa-solid fa-tower-broadcast"></i> Start Sending'
            : '<i class="fa-solid fa-tower-broadcast"></i> Start Receiving';
    }).catch(err => {
        if (requestToken !== onionStartToken) return;
        onionStartPending = false;
        onionActivePassword = '';
        const failed = Object.assign({}, onionStatus || {}, {state: 'stopped', error: String(err)});
        onionStatus = failed;
        renderOnionStatus(failed);
        onionShowError(String(err));
        btn.innerHTML = requestMode === 'share'
            ? '<i class="fa-solid fa-tower-broadcast"></i> Start Sending'
            : '<i class="fa-solid fa-tower-broadcast"></i> Start Receiving';
    });
}

function onionStop() {
    onionStartToken++;
    onionStartPending = false;
    onionActivePassword = '';
    const startBtn = document.getElementById('onion-start-btn');
    if (startBtn) {
        startBtn.innerHTML = onionMode === 'share'
            ? '<i class="fa-solid fa-tower-broadcast"></i> Start Sending'
            : '<i class="fa-solid fa-tower-broadcast"></i> Start Receiving';
    }
    const passwordInput = document.getElementById('onion-password');
    const passwordToggle = document.getElementById('onion-password-toggle');
    if (passwordInput) passwordInput.type = 'password';
    if (passwordToggle) passwordToggle.textContent = 'Show';
    const copyPassword = document.getElementById('onion-copy-password');
    if (copyPassword) copyPassword.style.display = 'none';
    pywebview.api.stop_onion_share().then(s => {
        onionStatus = s;
        renderOnionStatus(s);
        if (onionBackgroundTimer) {
            clearInterval(onionBackgroundTimer);
            onionBackgroundTimer = null;
        }
    }).catch(err => {
        const failed = Object.assign({}, onionStatus || {}, {state: 'error', error: String(err)});
        onionStatus = failed;
        renderOnionStatus(failed);
    });
}

function onionTogglePassword() {
    const input = document.getElementById('onion-password');
    const btn = document.getElementById('onion-password-toggle');
    if (!input || !btn) return;
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = 'Hide';
    } else {
        input.type = 'password';
        btn.textContent = 'Show';
    }
}

function onionCopyPassword() {
    if (!onionActivePassword) {
        alert('The archive password is not available. Stop and start a new transfer to set it again.');
        return;
    }
    copyText(onionActivePassword);
}

function onionLocate7z() {
    pywebview.api.browse_seven_zip().then(s => {
        onionStatus = s;
        renderOnionStatus(s);
        updateEncryptButtonState();
        if (s.ok === false) onionShowError(s.error || 'Select 7z.exe.');
    }).catch(err => onionShowError(String(err)));
}

function onionToggleEncryptPassword() {
    const input = document.getElementById('onion-encrypt-password');
    const btn = document.querySelector('#onion-panel-encrypt button[onclick="onionToggleEncryptPassword()"]');
    if (!input) return;
    if (input.type === 'password') {
        input.type = 'text';
        if (btn) btn.textContent = 'Hide';
    } else {
        input.type = 'password';
        if (btn) btn.textContent = 'Show';
    }
}

function renderEncryptOutputDir() {
    const input = document.getElementById('onion-encrypt-dir');
    if (!input || input.value) return;
    if (onionStatus && onionStatus.receive_dir) input.value = onionStatus.receive_dir;
    else if (onionStatus && onionStatus.default_encrypt_dir) input.value = onionStatus.default_encrypt_dir;
}

function onionBrowseEncryptOutput() {
    pywebview.api.browse_encrypt_output().then(path => {
        if (path) document.getElementById('onion-encrypt-dir').value = path;
    }).catch(err => onionShowError(String(err)));
}

function renderEncryptStatus(st) {
    const box = document.getElementById('onion-encrypt-status');
    if (!box) return;
    box.innerHTML = '';
    if (!st) {
        updateEncryptButtonState();
        return;
    }
    if (st.state === 'packing') {
        box.innerHTML = '<div style="background:#181825; border-left:3px solid #f9e2af; padding:10px; font-size:12px;"><i class="fa-solid fa-circle-notch fa-spin" style="color:#f9e2af;"></i> Encrypting archive...</div>';
    } else if (st.state === 'done' && st.archive_path) {
        box.innerHTML = '<div style="background:#181825; border-left:3px solid #a6e3a1; padding:10px; font-size:12px;">'
            + '<div style="color:#a6e3a1; font-weight:bold; margin-bottom:4px;"><i class="fa-solid fa-circle-check"></i> Archive created</div>'
            + '<div style="word-break:break-all; color:#cdd6f4; margin-bottom:8px;">' + (st.archive_path || '') + '</div>'
            + '<div style="display:flex; gap:6px;">'
            + '<button onclick="onionOpenEncryptOutput()" style="background:#a6e3a1; color:#11111b; font-weight:bold;">Open Folder</button>'
            + '<button onclick="copyText(\'' + (st.archive_path || '').replace(/\\/g, '\\\\').replace(/'/g, '\\\'') + '\')" style="background:#45475a; color:#cdd6f4;">Copy Path</button>'
            + '</div></div>';
    } else if (st.state === 'error') {
        box.innerHTML = '<div style="background:#45272f; border:1px solid #f38ba8; border-radius:5px; padding:10px; font-size:12px; color:#f38ba8;">' + (st.error || 'Encryption failed.') + '</div>';
    }
    updateEncryptButtonState();
}

function onionEncrypt() {
    if (!window.pywebview || !pywebview.api) return;
    onionShowError('');
    const password = document.getElementById('onion-encrypt-password').value || '';
    if (password.length < 6 || !password.trim()) {
        renderEncryptStatus({ state: 'error', error: 'Enter an archive password with at least 6 characters.' });
        return;
    }
    if (!onionSelectedPaths.length) {
        renderEncryptStatus({ state: 'error', error: 'Add at least one file or folder.' });
        return;
    }
    const outputDir = document.getElementById('onion-encrypt-dir').value;
    const btn = document.getElementById('onion-encrypt-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Encrypting...';
    pywebview.api.encrypt_files(onionSelectedPaths, password, outputDir).then(st => {
        onionEncryptStatus = st;
        renderEncryptStatus(st);
        btn.innerHTML = '<i class="fa-solid fa-lock"></i> Create Encrypted Archive';
        if (st.state === 'packing') {
            startOnionEncryptPolling();
        }
    }).catch(err => {
        onionEncryptStatus = { state: 'error', error: String(err) };
        renderEncryptStatus(onionEncryptStatus);
        btn.innerHTML = '<i class="fa-solid fa-lock"></i> Create Encrypted Archive';
    });
}

function startOnionEncryptPolling() {
    stopOnionEncryptPolling();
    onionEncryptPollTimer = setInterval(() => {
        pywebview.api.get_encrypt_status().then(st => {
            onionEncryptStatus = st;
            renderEncryptStatus(st);
            if (st.state !== 'packing') stopOnionEncryptPolling();
        }).catch(() => stopOnionEncryptPolling());
    }, 1000);
}

function stopOnionEncryptPolling() {
    if (onionEncryptPollTimer) clearInterval(onionEncryptPollTimer);
    onionEncryptPollTimer = null;
}

function onionOpenEncryptOutput() {
    const path = onionEncryptStatus && onionEncryptStatus.archive_path;
    if (path) pywebview.api.open_encrypt_output(path).catch(err => onionShowError(String(err)));
}

function onionCopy(id) {
    const el = document.getElementById(id);
    if (el && el.value) copyText(el.value);
}

function onionCopyInvite() {
    if (!onionStatus || !onionStatus.url) return;
    if (!onionStatus.public && !onionStatus.key) {
        alert('The private key is still being generated. Try again in a moment.');
        return;
    }
    const isShare = onionStatus.mode === 'share';
    const lines = [
        isShare
            ? 'Download my password-protected archive using Tor Browser:'
            : 'Upload files to me using Tor Browser:',
        '',
        `Address: ${onionStatus.url}`
    ];
    if (!onionStatus.public && onionStatus.key) lines.push(`Private key: ${onionStatus.key}`);
    if (isShare) {
        lines.push('', 'The archive is password-protected. I will send the password separately.');
        lines.push('Extract with 7-Zip: https://www.7-zip.org/');
    }
    lines.push('', 'Tor Browser: https://www.torproject.org/download/');
    copyText(lines.join('\n'));
}

function copyText(text) {
    const fallback = () => {
        const area = document.createElement('textarea');
        area.value = text;
        document.body.appendChild(area);
        area.select();
        try { document.execCommand('copy'); } catch (e) {}
        area.remove();
        return Promise.resolve();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).catch(fallback);
    }
    return fallback();
}

function onionLocateCli() {
    pywebview.api.browse_onionshare_cli().then(s => {
        onionStatus = s;
        renderOnionStatus(s);
        if (s.ok === false) onionShowError(s.error || 'Select onionshare-cli.exe.');
    }).catch(err => onionShowError(String(err)));
}


function toggleTagsSidebar() {
    const sidebar = document.getElementById('tags-sidebar');
    const btn = document.getElementById('toggle-tags-btn');
    if (!sidebar || !btn) return;
    if (sidebar.style.display === 'none') {
        sidebar.style.display = '';
        btn.innerText = 'Hide Tags';
    } else {
        sidebar.style.display = 'none';
        btn.innerText = 'Show Tags';
    }
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
    if (name && path) {
        if (!appState.move_targets) appState.move_targets = {};
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

let tempCollectionSites = [];
let tempStorySites = [];
let tempAudioSites = [];

function renderCollectionSitesEditorList() {
    const container = document.getElementById('collection-sites-list');
    if (!container) return;
    container.innerHTML = '';

    if (tempCollectionSites.length === 0) {
        container.innerHTML = '<div style="color: #888; font-size: 11px; padding: 5px;">No custom collection sites added.</div>';
        return;
    }

    tempCollectionSites.forEach((site, index) => {
        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.justifyContent = 'space-between';
        div.style.alignItems = 'center';
        div.style.marginBottom = '5px';
        div.style.background = '#222';
        div.style.padding = '5px';
        div.style.borderRadius = '3px';

        const info = document.createElement('span');
        info.textContent = `${site.name} (${site.url})`;
        info.style.fontSize = '12px';
        info.style.wordBreak = 'break-all';

        const delBtn = document.createElement('button');
        delBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        delBtn.style.background = '#d32f2f';
        delBtn.style.color = 'white';
        delBtn.style.border = 'none';
        delBtn.style.padding = '3px 8px';
        delBtn.style.cursor = 'pointer';
        delBtn.style.borderRadius = '3px';
        delBtn.style.fontSize = '11px';
        delBtn.onclick = () => {
            tempCollectionSites.splice(index, 1);
            renderCollectionSitesEditorList();
        };

        div.appendChild(info);
        div.appendChild(delBtn);
        container.appendChild(div);
    });
}

function addCollectionSite() {
    const nameInput = document.getElementById('new-site-name');
    const urlInput = document.getElementById('new-site-url');
    if (!nameInput || !urlInput) return;

    const name = nameInput.value.trim();
    const url = urlInput.value.trim();

    if (name && url) {
        tempCollectionSites.push({ name, url });
        nameInput.value = '';
        urlInput.value = '';
        renderCollectionSitesEditorList();
    } else {
        alert('Please enter both site name and URL.');
    }
}

function renderAudioSitesEditorList() {
    const container = document.getElementById('audio-sites-list');
    if (!container) return;
    container.innerHTML = '';

    if (tempAudioSites.length === 0) {
        container.innerHTML = '<div style="color: #888; font-size: 11px; padding: 5px;">No custom audio sites added.</div>';
        return;
    }

    tempAudioSites.forEach((site, index) => {
        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.justifyContent = 'space-between';
        div.style.alignItems = 'center';
        div.style.marginBottom = '5px';
        div.style.background = '#222';
        div.style.padding = '5px';
        div.style.borderRadius = '3px';

        const info = document.createElement('div');
        info.style.display = 'flex';
        info.style.flexDirection = 'column';
        info.style.gap = '3px';
        info.style.fontSize = '12px';
        info.style.wordBreak = 'break-all';
        info.style.flex = '1';

        const nameSpan = document.createElement('span');
        nameSpan.textContent = site.name;
        nameSpan.style.fontWeight = 'bold';

        const urlSpan = document.createElement('span');
        urlSpan.textContent = site.url;
        urlSpan.style.color = '#888';
        urlSpan.style.fontSize = '11px';

        info.appendChild(nameSpan);
        info.appendChild(urlSpan);

        if (site.tags && site.tags.length > 0) {
            const tagsDiv = document.createElement('div');
            tagsDiv.style.display = 'flex';
            tagsDiv.style.flexWrap = 'wrap';
            tagsDiv.style.gap = '3px';
            tagsDiv.style.marginTop = '2px';

            site.tags.forEach(t => {
                const tagSpan = document.createElement('span');
                tagSpan.className = 'tag-badge';
                tagSpan.textContent = t;
                tagsDiv.appendChild(tagSpan);
            });
            info.appendChild(tagsDiv);
        }

        const delBtn = document.createElement('button');
        delBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        delBtn.style.background = '#d32f2f';
        delBtn.style.color = 'white';
        delBtn.style.border = 'none';
        delBtn.style.padding = '3px 8px';
        delBtn.style.cursor = 'pointer';
        delBtn.style.borderRadius = '3px';
        delBtn.style.fontSize = '11px';
        delBtn.onclick = () => {
            tempAudioSites.splice(index, 1);
            renderAudioSitesEditorList();
        };

        div.appendChild(info);
        div.appendChild(delBtn);
        container.appendChild(div);
    });
}

function addAudioSite() {
    const nameInput = document.getElementById('new-audio-site-name');
    const urlInput = document.getElementById('new-audio-site-url');
    const tagsInput = document.getElementById('new-audio-site-tags');
    if (!nameInput || !urlInput) return;

    const name = nameInput.value.trim();
    const url = urlInput.value.trim();
    const tagsVal = tagsInput ? tagsInput.value : '';

    const tags = tagsVal.split(',')
        .map(t => t.trim().toLowerCase())
        .filter(t => t.length > 0);

    if (name && url) {
        tempAudioSites.push({ name, url, tags });
        nameInput.value = '';
        urlInput.value = '';
        if (tagsInput) tagsInput.value = '';
        renderAudioSitesEditorList();
    } else {
        alert('Please enter both site name and URL.');
    }
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

    const appsList = document.getElementById('external-apps-list');
    appsList.innerHTML = '';
    const apps = appState.external_apps || ["", "", "", "", ""];

    for (let i = 0; i < 5; i++) {
        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.gap = '5px';
        div.style.marginBottom = '5px';
        div.style.alignItems = 'center';

        const input = document.createElement('input');
        input.type = 'text';
        input.id = `opt-app-${i}`;
        input.value = apps[i] || "";
        input.style.flex = '1';
        input.placeholder = "e.g. C:\\Path\\To\\Photoshop.exe";

        const browseBtn = document.createElement('button');
        browseBtn.innerHTML = '<i class="fa-solid fa-file"></i>';
        browseBtn.onclick = () => {
            pywebview.api.browse_exe_dialog().then(path => {
                if (path && path.length > 0) input.value = path;
            });
        };

        div.appendChild(input);
        div.appendChild(browseBtn);
        appsList.appendChild(div);
    }

    // Bind Define Favs
    const favsMode = appState.favs_mode || 'folder';
    const folderRadio = document.getElementById('favs-scope-folder');
    const globalRadio = document.getElementById('favs-scope-global');
    if (favsMode === 'global') {
        if (globalRadio) globalRadio.checked = true;
    } else {
        if (folderRadio) folderRadio.checked = true;
    }

    // Render Collection Sites
    tempCollectionSites = [...(appState.collection_sites || [])];
    renderCollectionSitesEditorList();

    // Render Audio Sites
    tempAudioSites = [...(appState.audio_sites || [])];
    renderAudioSitesEditorList();

    // Bind Recursive Load Option
    const optRecCheckbox = document.getElementById('opt-recursive-load');
    if (optRecCheckbox) {
        optRecCheckbox.checked = appState.recursive_load || false;
    }

    // Bind Gemini API Key Option
    const optGeminiKey = document.getElementById('opt-gemini-key');
    if (optGeminiKey) {
        optGeminiKey.value = appState.gemini_api_key || "";
    }
}

function saveOptionsModal() {
    const folders = [];
    for (let i = 0; i < 5; i++) folders.push(document.getElementById(`opt-folder-${i}`).value);

    const apps = [];
    for (let i = 0; i < 5; i++) apps.push(document.getElementById(`opt-app-${i}`).value);

    let defIndex = -1;
    const radios = document.getElementsByName('default-folder');
    for (const r of radios) {
        if (r.checked) defIndex = parseInt(r.value);
    }

    let favsMode = 'folder';
    const favsRadios = document.getElementsByName('favs-scope');
    for (const r of favsRadios) {
        if (r.checked) favsMode = r.value;
    }

    const recursiveLoad = document.getElementById('opt-recursive-load').checked;
    const geminiApiKey = document.getElementById('opt-gemini-key').value.trim();

    appState.saved_folders = folders;
    appState.default_folder = defIndex;
    appState.external_apps = apps;
    appState.favs_mode = favsMode;
    appState.collection_sites = tempCollectionSites;
    appState.audio_sites = tempAudioSites;
    appState.recursive_load = recursiveLoad;
    appState.gemini_api_key = geminiApiKey;

    pywebview.api.save_options(folders, defIndex, apps, favsMode, tempCollectionSites, tempAudioSites, recursiveLoad, geminiApiKey).then(state => {
        appState = state;
        renderState();
        closeModals();
    });
}

function renderHotkeysList() {
    const prevList = document.getElementById('hotkeys-prev-list');
    const nextList = document.getElementById('hotkeys-next-list');
    const pauseList = document.getElementById('hotkeys-pause-list');
    const muteList = document.getElementById('hotkeys-mute-list');
    const splitVideoList = document.getElementById('hotkeys-split-video-list');
    const splitImageList = document.getElementById('hotkeys-split-image-list');
    if (prevList) prevList.innerHTML = '';
    if (nextList) nextList.innerHTML = '';
    if (pauseList) pauseList.innerHTML = '';
    if (muteList) muteList.innerHTML = '';
    if (splitVideoList) splitVideoList.innerHTML = '';
    if (splitImageList) splitImageList.innerHTML = '';

    const hotkeys = appState.hotkeys || { next: ["ArrowRight", "Space", "", "", ""], prev: ["ArrowLeft", "", "", "", ""], 
        pause: ["KeyP", "", "", "", ""], mute: ["KeyM", "", "", "", ""], 
        split_next_video: ["KeyD", "", "", "", ""], split_next_image: ["KeyE", "", "", "", ""] };
    const prevKeys = hotkeys.prev || ["ArrowLeft", "", "", "", ""];
    const nextKeys = hotkeys.next || ["ArrowRight", "Space", "", "", ""];
    const pauseKeys = hotkeys.pause || ["KeyP", "", "", "", ""];
    const muteKeys = hotkeys.mute || ["KeyM", "", "", "", ""];
    const splitNextVideoKeys = hotkeys.split_next_video || ["KeyD", "", "", "", ""];
    const splitNextImageKeys = hotkeys.split_next_image || ["KeyE", "", "", "", ""];

    function addKeyInputs(listEl, keysArr, prefix) {
        if (!listEl) return;
        for (let i = 0; i < 5; i++) {
            const input = document.createElement('input');
            input.type = 'text';
            input.id = `hk-${prefix}-${i}`;
            input.value = keysArr[i] || '';
            input.readOnly = true;
            input.placeholder = 'Click to assign...';
            input.style.width = '100%';
            input.style.marginBottom = '5px';
            input.style.cursor = 'pointer';
            input.onclick = (e) => {
                e.stopPropagation();
                startListening(input);
            };
            listEl.appendChild(input);
        }
    }

    addKeyInputs(prevList, prevKeys, 'prev');
    addKeyInputs(nextList, nextKeys, 'next');
    addKeyInputs(pauseList, pauseKeys, 'pause');
    addKeyInputs(muteList, muteKeys, 'mute');
    addKeyInputs(splitVideoList, splitNextVideoKeys, 'split-video');
    addKeyInputs(splitImageList, splitNextImageKeys, 'split-image');
}

function saveHotkeysModal() {
    const nextKeys = [];
    const prevKeys = [];
    const pauseKeys = [];
    const muteKeys = [];
    const splitVideoKeys = [];
    const splitImageKeys = [];
    for (let i = 0; i < 5; i++) {
        nextKeys.push(document.getElementById(`hk-next-${i}`).value);
        prevKeys.push(document.getElementById(`hk-prev-${i}`).value);
        const pk = document.getElementById(`hk-pause-${i}`);
        const mk = document.getElementById(`hk-mute-${i}`);
        const sv = document.getElementById(`hk-split-video-${i}`);
        const si = document.getElementById(`hk-split-image-${i}`);
        pauseKeys.push(pk ? pk.value : '');
        muteKeys.push(mk ? mk.value : '');
        splitVideoKeys.push(sv ? sv.value : '');
        splitImageKeys.push(si ? si.value : '');
    }
    pywebview.api.save_hotkeys({ 
        next: nextKeys, 
        prev: prevKeys, 
        pause: pauseKeys, 
        mute: muteKeys, 
        split_next_video: splitVideoKeys, 
        split_next_image: splitImageKeys 
    }).then(state => {
        appState = state;
        closeModals();
    });
}


function updatePlaylist() {
    pywebview.api.get_playlist().then(items => {
        playlist = items.map((item, i) => ({ ...item, originalIndex: i }));
        if (splitScreenActive) {
            const videoExts = ['mp4', 'webm', 'ogg', 'mp3', 'wav', 'wave'];
            leftPlaylist = playlist.filter(f => {
                const ext = f.path.split('.').pop().toLowerCase();
                return videoExts.includes(ext);
            });
            
            const imageExts = ['jpg', 'jpeg', 'png', 'webp', 'gif'];
            rightPlaylist = playlist.filter(f => {
                const ext = f.path.split('.').pop().toLowerCase();
                return imageExts.includes(ext);
            });
            
            if (playlist[currentIndex]) {
                const currentPath = playlist[currentIndex].path;
                const leftIdx = leftPlaylist.findIndex(f => f.path === currentPath);
                if (leftIdx !== -1) {
                    leftCurrentIndex = leftIdx;
                }
                const rightIdx = rightPlaylist.findIndex(f => f.path === currentPath);
                if (rightIdx !== -1) {
                    rightCurrentIndex = rightIdx;
                }
            }
        }
        if (showFoldersActive && typeof pywebview.api.get_dir_tree === 'function') {
            pywebview.api.get_dir_tree().then(res => {
                currentSubdirs = res ? res.subdirs : [];
                currentCbzFiles = res ? (res.cbz_files || []) : [];
                currentTreeRoot = res ? (res.root || '') : '';
                activeCbzRoot = res ? (res.cbz_root || '') : '';
                let activePath = playlist[currentIndex]?.path;
                if (splitScreenActive) {
                    if (activeSidebarTab === 'left') {
                        activePath = leftPlaylist[leftCurrentIndex]?.path;
                    } else {
                        activePath = rightPlaylist[rightCurrentIndex]?.path;
                    }
                }
                if (activePath) {
                    autoExpandActiveFolder(activePath);
                }
                renderPlaylist();
            });
        } else {
            currentSubdirs = [];
            currentCbzFiles = [];
            currentTreeRoot = '';
            activeCbzRoot = '';
            renderPlaylist();
        }
    });
}

observer = new IntersectionObserver((entries, observer) => {
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

    let listToRender = playlist;
    let activeIdx = currentIndex;

    if (splitScreenActive) {
        if (activeSidebarTab === 'left') {
            listToRender = leftPlaylist;
            activeIdx = leftCurrentIndex;
        } else {
            listToRender = rightPlaylist;
            activeIdx = rightCurrentIndex;
        }
    }

    const filterSelect = document.getElementById('type-filter');
    if (filterSelect && filterSelect.value !== 'all') {
        const filterValue = filterSelect.value;
        const extMap = {
            'image': ['jpg', 'jpeg', 'png', 'webp', 'gif'],
            'video': ['mp4', 'webm', 'ogg'],
            'audio': ['mp3', 'wav', 'wave'],
            'text': ['txt', 'md', 'json', 'csv']
        };
        const validExts = extMap[filterValue] || [];
        
        listToRender = listToRender.filter(item => {
            const ext = item.path.split('.').pop().toLowerCase();
            return validExts.includes(ext);
        });
    }

    // Search filter
    const searchInput = document.getElementById('playlist-search');
    if (searchInput && searchInput.value.trim()) {
        const query = searchInput.value.trim().toLowerCase();
        listToRender = listToRender.filter(item => item.name.toLowerCase().includes(query));
    }

    // Sort
    const sortSelect = document.getElementById('playlist-sort');
    if (sortSelect) {
        const sortVal = sortSelect.value;
        const dir = sortAsc ? 1 : -1;
        listToRender = [...listToRender].sort((a, b) => {
            if (sortVal === 'date') return dir * ((a.date || 0) - (b.date || 0));
            if (sortVal === 'size') return dir * ((a.size || 0) - (b.size || 0));
            return dir * a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
        });
    }

    // Toggle folder tree container visibility and render if active
    const folderTreeContainer = document.getElementById('folder-tree-container');
    if (folderTreeContainer) {
        if (showFoldersActive) {
            folderTreeContainer.style.display = 'block';
            renderFolderTree(listToRender, currentSubdirs);
        } else {
            folderTreeContainer.style.display = 'none';
        }
    }

    listToRender.forEach((item, index) => {
        const div = document.createElement('div');
        const itemOrigIdx = item.originalIndex !== undefined ? item.originalIndex : index;
        const isActive = !splitScreenActive ? (itemOrigIdx === activeIdx) : (index === activeIdx);
        const isSelected = selectedIndices.has(itemOrigIdx);
        div.className = 'playlist-item' + (isActive ? ' active' : '') + (isSelected ? ' selected' : '');

        div.onclick = (e) => {
            if (e.ctrlKey || e.metaKey) {
                if (selectedIndices.has(itemOrigIdx)) selectedIndices.delete(itemOrigIdx);
                else selectedIndices.add(itemOrigIdx);
                lastSelectedIndex = itemOrigIdx;
            } else if (e.shiftKey && lastSelectedIndex !== -1) {
                selectedIndices.clear();
                const start = Math.min(lastSelectedIndex, itemOrigIdx);
                const end = Math.max(lastSelectedIndex, index);
                for (let i = start; i <= end; i++) selectedIndices.add(i);
            } else {
                selectedIndices.clear();
                selectedIndices.add(itemOrigIdx);
                lastSelectedIndex = itemOrigIdx;

                if (splitScreenActive) {
                    if (activeSidebarTab === 'left') {
                        leftCurrentIndex = index;
                        loadLeftMedia(item.path);
                    } else {
                        rightCurrentIndex = index;
                        loadRightMedia(item.path);
                    }
                } else {
                    pywebview.api.play_index(item.originalIndex !== undefined ? item.originalIndex : index);
                }
            }
            renderPlaylist();
        };

        div.onmousedown = (e) => {
            if (e.button === 2) {
                e.preventDefault();
                try {
                    if (!selectedIndices.has(index)) {
                        selectedIndices.clear();
                        selectedIndices.add(index);
                        lastSelectedIndex = index;
                        document.querySelectorAll('.playlist-item').forEach(el => el.classList.remove('selected'));
                        div.classList.add('selected');
                    }
                    showContextMenu(e.clientX, e.clientY);
                } catch (err) {
                    alert("Error on right click: " + err);
                }
            }
        };

        // Also suppress contextmenu just in case it leaks through
        div.oncontextmenu = (e) => e.preventDefault();

        const img = document.createElement('img');
        img.className = 'playlist-thumbnail';
        img.dataset.src = `http://localhost:5050/thumbnail?path=${encodeURIComponent(item.path)}`;
        img.onerror = function () { this.onerror = null; this.src = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='; };
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
        activeItem.scrollIntoView({ block: 'nearest' });
    }
}

function showContextMenu(x, y) {
    try {
        const cmLocal = document.getElementById('context-menu');
        if (!cmLocal) {
            alert("Context menu element not found in DOM!");
            return;
        }
        cmLocal.style.display = 'block';

        if (x + cmLocal.offsetWidth > window.innerWidth) x = window.innerWidth - cmLocal.offsetWidth;
        if (y + cmLocal.offsetHeight > window.innerHeight) y = window.innerHeight - cmLocal.offsetHeight;
        cmLocal.style.left = x + 'px';
        cmLocal.style.top = y + 'px';

        const renameBtn = document.getElementById('cm-rename-btn');
        if (renameBtn) renameBtn.style.display = (selectedIndices.size === 1) ? 'block' : 'none';

        // Populate Open With
        const apps = appState.external_apps || [];
        const validApps = apps.filter(a => a.trim() !== "");
        const openWithContainer = document.getElementById('cm-open-with-container');
        const openWithList = document.getElementById('cm-open-with-list');

        if (validApps.length > 0 && openWithContainer && openWithList) {
            openWithContainer.style.display = 'block';
            openWithList.innerHTML = '';
            for (const appPath of validApps) {
                const btn = document.createElement('button');
                btn.className = 'cm-btn';
                const appName = appPath.split('\\').pop().split('/').pop();
                btn.innerHTML = `<i class="fa-solid fa-rocket"></i> ${appName}`;
                btn.onclick = () => {
                    cmLocal.style.display = 'none';
                    if (lastSelectedIndex !== -1 && playlist[lastSelectedIndex]) {
                        pywebview.api.open_with(playlist[lastSelectedIndex].path, appPath).then(res => {
                            if (res.status === 'error') alert("Failed to open: " + res.msg);
                        });
                    }
                };
                openWithList.appendChild(btn);
            }
        } else if (openWithContainer) {
            openWithContainer.style.display = 'none';
        }

        const tContainer = document.getElementById('cm-move-targets');
        if (tContainer) {
            tContainer.innerHTML = '';
            for (const [name, path] of Object.entries(appState.move_targets || {})) {
                const btn = document.createElement('button');
                btn.className = 'cm-btn';
                btn.innerHTML = `<i class="fa-solid fa-arrow-right-to-bracket"></i> ${name}`;
                btn.onclick = () => cmMoveTo(name);
                tContainer.appendChild(btn);
            }
            const browseBtn = document.createElement('button');
            browseBtn.className = 'cm-btn';
            browseBtn.innerHTML = `<i class="fa-solid fa-folder-open"></i> Browse...`;
            browseBtn.onclick = () => {
                pywebview.api.browse_folder().then(path => {
                    if (path) cmMoveTo(path);
                });
            };
            tContainer.appendChild(browseBtn);
        }

        // Add a "Make Collection" / "Unmark as Collection" button to the context menu
        let markCollectionBtn = document.getElementById('cm-mark-collection');
        if (!markCollectionBtn) {
            markCollectionBtn = document.createElement('button');
            markCollectionBtn.id = 'cm-mark-collection';
            markCollectionBtn.className = 'cm-btn';
            cmLocal.appendChild(markCollectionBtn);
        }

        if (appState.is_collection_folder) {
            markCollectionBtn.innerHTML = '<i class="fa-solid fa-book-open-reader"></i> Unmark as Collection';
            markCollectionBtn.onclick = () => {
                cmLocal.style.display = 'none';
                pywebview.api.unmark_as_collection().then(state => {
                    appState = state;
                    renderState();
                });
            };
        } else {
            markCollectionBtn.innerHTML = '<i class="fa-solid fa-book"></i> Make Collection';
            markCollectionBtn.onclick = () => {
                cmLocal.style.display = 'none';
                pywebview.api.mark_as_collection().then(state => {
                    appState = state;
                    renderState();
                });
            };
        }
        markCollectionBtn.style.display = 'block';
    } catch (err) {
        alert("Error in showContextMenu: " + err.message);
    }
}

function getSelectedPaths() {
    return Array.from(selectedIndices).map(idx => playlist[idx].path);
}

function cmPlay() {
    if (selectedIndices.size > 0) {
        pywebview.api.play_index(Array.from(selectedIndices)[0]);
    }
}

function cmRename() {
    cm.style.display = 'none';
    if (selectedIndices.size === 1) {
        const idx = selectedIndices.values().next().value;
        const oldPath = playlist[idx].path;
        const oldName = playlist[idx].name;
        const newName = prompt("Rename file to:", oldName);
        if (newName && newName !== oldName) {
            pywebview.api.rename_file(oldPath, newName).then(res => {
                if (res.status === 'ok') updateState();
                else alert(res.message);
            });
        }
    }
}

function cmOpenFolder() {
    cm.style.display = 'none';
    if (lastSelectedIndex !== -1 && playlist[lastSelectedIndex]) {
        pywebview.api.open_folder_location(playlist[lastSelectedIndex].path);
    }
}

function cmOpenXenoPix() {
    cm.style.display = 'none';
    let targetPath = null;
    if (lastSelectedIndex !== -1 && playlist[lastSelectedIndex]) {
        targetPath = playlist[lastSelectedIndex].path;
    }
    pywebview.api.open_xenopix(targetPath).then(res => {
        if (res.status === 'error') {
            alert(res.msg);
        }
    });
}

function cmDelete() {
    if (selectedIndices.size === 0) return;
    if (confirm(`Are you sure you want to delete ${selectedIndices.size} file(s)?`)) {
        pywebview.api.delete_files(getSelectedPaths()).then(res => {
            if (res.status === 'success') {
                selectedIndices.clear();
                updatePlaylist();
            } else {
                alert(res.msg);
            }
        });
    }
}

function cmMoveTo(target) {
    if (selectedIndices.size === 0) return;
    pywebview.api.move_files(getSelectedPaths(), target).then(res => {
        if (res.status === 'success') {
            selectedIndices.clear();
            updatePlaylist();
        } else {
            alert(res.msg);
        }
    });
}

function togglePlay() {
    const el = splitScreenActive ? videoPlayer : activeMedia();
    if (el.style.display !== 'none') {
        if (el.paused) {
            el.play();
            playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        } else {
            el.pause();
            playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
        }
    }
}

function changeVolume(val) {
    const el = splitScreenActive ? videoPlayer : activeMedia();
    el.volume = val / 100.0;
    if (splitScreenActive) {
        if (leftPlaylist[leftCurrentIndex]) {
            pywebview.api.save_volume(leftPlaylist[leftCurrentIndex].path, val);
        }
    } else {
        if (currentIndex >= 0 && playlist[currentIndex]) {
            pywebview.api.save_volume(playlist[currentIndex].path, val).then(() => {
                if (!appState.saved_volumes) appState.saved_volumes = {};
                appState.saved_volumes[playlist[currentIndex].path] = val;
            });
        }
    }
}

let currentPlayCount = 0;

function resetLoopCount() {
    currentPlayCount = 0;
}

function formatTime(seconds) {
    if (isNaN(seconds) || !isFinite(seconds)) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
}

function onTimeUpdate() {
    const el = activeMedia();
    const progressSlider = document.getElementById('progress-slider');
    const currentTimeDisplay = document.getElementById('current-time');

    if (el.duration) {
        progressSlider.value = (el.currentTime / el.duration) * 100;
        currentTimeDisplay.textContent = formatTime(el.currentTime);
    }
}

videoPlayer.addEventListener('timeupdate', onTimeUpdate);
audioPlayer.addEventListener('timeupdate', onTimeUpdate);

function onLoadedMetadata() {
    const el = activeMedia();
    const progressSlider = document.getElementById('progress-slider');
    const totalTimeDisplay = document.getElementById('total-time');
    const currentTimeDisplay = document.getElementById('current-time');

    totalTimeDisplay.textContent = formatTime(el.duration);
    progressSlider.value = 0;
    currentTimeDisplay.textContent = "0:00";

    if (!currentIsAudio) {
        updateMediaDimensions();

        // Only run the repaint fix on the very first load.
        if (currentIndex === 0 && !videoPlayer.dataset.initialLoadDone) {
            videoPlayer.dataset.initialLoadDone = 'true';
            imageViewer.dataset.initialLoadDone = 'true'; // Sync the flag
            applyMediaStyles(); // Apply the correct styles first.
            setTimeout(() => {
                const originalZoom = currentZoom;
                setMediaZoom('double'); // Force a repaint by changing zoom
                setMediaZoom(originalZoom); // Immediately revert
            }, 10);
        } else {
            applyMediaStyles();
        }
    } else {
        applyMediaStyles();
    }
}

videoPlayer.addEventListener('loadedmetadata', onLoadedMetadata);
audioPlayer.addEventListener('loadedmetadata', onLoadedMetadata);

document.addEventListener('DOMContentLoaded', () => {
    initSplitResizer();
    const progressSlider = document.getElementById('progress-slider');
    if (progressSlider) {
        progressSlider.addEventListener('input', () => {
            const el = activeMedia();
            if (el.duration) {
                el.currentTime = (progressSlider.value / 100) * el.duration;
            }
        });
    }
});

function onEnded() {
    const el = activeMedia();
    const loopEnabled = document.getElementById('loop-checkbox').checked;
    const maxLoops = parseInt(document.getElementById('loop-count').value, 10) || 1;

    if (loopEnabled) {
        currentPlayCount++;
        if (currentPlayCount < maxLoops) {
            // Replay the current media
            el.currentTime = 0;
            el.play();
            return;
        }
    }

    // Done looping or loop disabled -> go to next
    handleNextMedia();
}

videoPlayer.addEventListener('ended', onEnded);
audioPlayer.addEventListener('ended', onEnded);

let imageTimerInterval = null;

function updateImageTimer() {
    if (imageTimerInterval) {
        clearInterval(imageTimerInterval);
        imageTimerInterval = null;
    }
    const val = parseInt(document.getElementById('image-timer').value, 10) || 0;
    if (val > 0 && imageViewer.style.display !== 'none') {
        imageTimerInterval = setInterval(() => {
            if (splitScreenActive) {
                navigatePaneImage(1);
            } else {
                handleNextMedia();
            }
        }, val * 1000);
    }
}

// --- Keyboard & Mouse Shortcuts ---
window.addEventListener('keydown', e => {
    // Prevent triggering if typing in an input or textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    const hotkeys = appState.hotkeys || { next: ["ArrowRight", "Space", "", "", ""], prev: ["ArrowLeft", "", "", "", ""], 
        pause: ["KeyP", "", "", "", ""], mute: ["KeyM", "", "", "", ""], 
        split_next_video: ["KeyD", "", "", "", ""], split_next_image: ["KeyE", "", "", "", ""] };
    const pauseKeys = hotkeys.pause || ["KeyP", "", "", "", ""];
    const muteKeys = hotkeys.mute || ["KeyM", "", "", "", ""];
    const splitNextVideoKeys = hotkeys.split_next_video || ["KeyD", "", "", "", ""];
    const splitNextImageKeys = hotkeys.split_next_image || ["KeyE", "", "", "", ""];

    // Play / Pause Toggle
    if (pauseKeys.includes(e.code) || pauseKeys.includes(e.key) || e.code === 'KeyP' || e.code === 'KeyK' || e.code === 'MediaPlayPause') {
        const topAudioBar = document.getElementById('top-audio-bar');
        if (topAudioBar && topAudioBar.style.display !== 'none') {
            topAudioTogglePlay();
        } else {
            togglePlay();
        }
        e.preventDefault();
        return;
    }

    // Top Inline Audio: KeyN (next), KeyB (prev/back)
    const topAudioBar = document.getElementById('top-audio-bar');
    if (topAudioBar && topAudioBar.style.display !== 'none') {
        if (e.code === 'KeyN') {
            topAudioNext();
            e.preventDefault();
            return;
        } else if (e.code === 'KeyB') {
            topAudioPrev();
            e.preventDefault();
            return;
        }
    }

    // Toggle Favorite: KeyF
    if (e.code === 'KeyF') {
        toggleFavorite();
        e.preventDefault();
        return;
    }

    // Toggle Split Screen Layout: KeyS
    if (e.code === 'KeyS') {
        toggleSplitScreen();
        e.preventDefault();
        return;
    }

    // Mute Audio
    if (muteKeys.includes(e.code) || muteKeys.includes(e.key) || e.code === 'KeyM') {
        const el = splitScreenActive ? videoPlayer : activeMedia();
        if (el) {
            el.muted = !el.muted;
        }
        e.preventDefault();
        return;
    }

    // Split Screen specific keys
    if (splitScreenActive) {
        if (splitNextVideoKeys.includes(e.code) || splitNextVideoKeys.includes(e.key) || e.code === 'KeyA' || e.code === 'KeyD') {
            if (e.code === 'KeyA' || (splitNextVideoKeys.includes(e.code) && splitNextVideoKeys.indexOf(e.code) < splitNextVideoKeys.indexOf('KeyD'))) {
                navigateLeftPane(-1);
            } else {
                navigateLeftPane(1);
            }
            e.preventDefault();
            return;
        }
        if (splitNextImageKeys.includes(e.code) || splitNextImageKeys.includes(e.key) || e.code === 'KeyQ' || e.code === 'KeyE') {
            if (e.code === 'KeyQ') {
                navigatePaneImage(-1);
            } else {
                navigatePaneImage(1);
            }
            e.preventDefault();
            return;
        }
        // Video Pane (Left): KeyA (prev), KeyD (next)
        if (e.code === 'KeyA') {
            navigateLeftPane(-1);
            e.preventDefault();
            return;
        } else if (e.code === 'KeyD') {
            navigateLeftPane(1);
            e.preventDefault();
            return;
        }
        // Image Pane (Right): KeyQ (prev), KeyE (next)
        if (e.code === 'KeyQ') {
            navigatePaneImage(-1);
            e.preventDefault();
            return;
        } else if (e.code === 'KeyE') {
            navigatePaneImage(1);
            e.preventDefault();
            return;
        }
    }

    const nextKeys = hotkeys.next || ["ArrowRight", "Space"];
    const prevKeys = hotkeys.prev || ["ArrowLeft"];

    if (prevKeys.includes(e.code)) {
        handlePrevMedia();
        e.preventDefault();
    } else if (nextKeys.includes(e.code)) {
        handleNextMedia();
        e.preventDefault();
    }
});

window.addEventListener('mousedown', e => {
    // If user is currently assigning a hotkey, don't execute actions
    if (listeningInput) return;

    // Prevent triggering if clicking inside interactive UI elements
    if (
        e.target.closest('button') ||
        e.target.closest('input') ||
        e.target.closest('select') ||
        e.target.closest('textarea') ||
        e.target.closest('a') ||
        e.target.closest('.modal') ||
        e.target.closest('#sidebar') ||
        e.target.closest('#bottom-controls') ||
        e.target.closest('#menu-bar') ||
        e.target.closest('.context-menu')
    ) {
        return;
    }

    const hotkeys = appState.hotkeys || { next: ["ArrowRight", "Space"], prev: ["ArrowLeft"] };
    const nextKeys = hotkeys.next || ["ArrowRight", "Space"];
    const prevKeys = hotkeys.prev || ["ArrowLeft"];

    const mouseCode = `Mouse${e.button}`;

    if (prevKeys.includes(mouseCode)) {
        handlePrevMedia();
        e.preventDefault();
    } else if (nextKeys.includes(mouseCode)) {
        handleNextMedia();
        e.preventDefault();
    }
});

// --- Collection Translation Features ---
mediaContainer = document.getElementById('media-container');
selectionBox = document.getElementById('selection-box');
transContainer = document.getElementById('translations-container');
loadingOverlay = document.getElementById('collection-loading');

let isDrawing = false;
let startX = 0, startY = 0;

mediaContainer.addEventListener('mousedown', e => {
    const isLeftImgVisible = leftImage && leftImage.style.display !== 'none' && leftImage.offsetParent;
    const isRightImgVisible = imageViewer && imageViewer.style.display !== 'none' && imageViewer.offsetParent;
    if (!isLeftImgVisible && !isRightImgVisible) return;
    if (e.target.closest('.collection-translation-box')) return; // Don't draw if clicking on existing box

    isDrawing = true;
    const rect = mediaContainer.getBoundingClientRect();
    startX = e.clientX - rect.left;
    startY = e.clientY - rect.top;

    selectionBox.style.left = (startX + mediaContainer.scrollLeft) + 'px';
    selectionBox.style.top = (startY + mediaContainer.scrollTop) + 'px';
    selectionBox.style.width = '0px';
    selectionBox.style.height = '0px';
    selectionBox.style.display = 'block';
});

mediaContainer.addEventListener('mousemove', e => {
    if (!isDrawing) return;
    const rect = mediaContainer.getBoundingClientRect();
    const currX = e.clientX - rect.left;
    const currY = e.clientY - rect.top;

    selectionBox.style.left = (Math.min(startX, currX) + mediaContainer.scrollLeft) + 'px';
    selectionBox.style.top = (Math.min(startY, currY) + mediaContainer.scrollTop) + 'px';
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

    // Determine which image viewer the selection was made on
    let activeImg = null;
    const selCenterX = selLeft + selWidth / 2 + rect.left;
    const selCenterY = selTop + selHeight / 2 + rect.top;
    if (leftImage && leftImage.style.display !== 'none' && leftImage.offsetParent) {
        const imgRect = leftImage.getBoundingClientRect();
        if (selCenterX >= imgRect.left && selCenterX <= imgRect.right && selCenterY >= imgRect.top && selCenterY <= imgRect.bottom) {
            activeImg = leftImage;
        }
    }
    if (!activeImg && imageViewer && imageViewer.style.display !== 'none' && imageViewer.offsetParent) {
        const imgRect = imageViewer.getBoundingClientRect();
        if (selCenterX >= imgRect.left && selCenterX <= imgRect.right && selCenterY >= imgRect.top && selCenterY <= imgRect.bottom) {
            activeImg = imageViewer;
        }
    }
    if (!activeImg) return;

    const imgRect = activeImg.getBoundingClientRect();
    // Calculate relative to the image element
    const relX = (selLeft + rect.left) - imgRect.left;
    const relY = (selTop + rect.top) - imgRect.top;

    if (relX < 0 || relY < 0 || relX > imgRect.width || relY > imgRect.height) return; // Outside image

    const ocrMode = document.getElementById('ocr-mode')?.value || 'Japanese (Manga OCR)';
    const targetLang = document.getElementById('target-lang')?.value || 'English (en)';
    const ocrSourceLang = document.getElementById('ocr-source-lang')?.value || 'auto';
    const currentPath = appState.current_path || playlist[currentIndex].path;

    loadingOverlay.style.display = 'block';

    pywebview.api.translate_rect(
        currentPath,
        relX, relY, selWidth, selHeight,
        ocrMode,
        imgRect.width, imgRect.height,
        targetLang,
        ocrSourceLang
    ).then(res => {
        loadingOverlay.style.display = 'none';
        if (res.status === 'success') {
            const filename = currentPath.split('\\').pop().split('/').pop();
            if (!collectionTranslations[filename]) collectionTranslations[filename] = [];

            collectionTranslations[filename].push({
                rect: res.rect,
                text: res.text,
                orig: res.orig
            });

            pywebview.api.save_collection_info(currentPath, collectionTranslations);
            renderTranslations(currentPath, activeImg);
        } else {
            alert("Translation failed: " + res.msg);
        }
    });
});

function renderTranslations(path, targetViewer) {
    transContainer.innerHTML = '';
    const filename = path.split('\\').pop().split('/').pop();
    const transList = collectionTranslations[filename] || [];

    const activeImageViewer = targetViewer || ((imageViewer.style.display !== 'none') ? imageViewer : leftImage);
    if (!activeImageViewer) return;

    const imgRect = activeImageViewer.getBoundingClientRect();
    const containerRect = mediaContainer.getBoundingClientRect();

    if (imgRect.width === 0) {
        // Image not loaded yet, retry shortly
        setTimeout(() => renderTranslations(path, targetViewer), 100);
        return;
    }

    // The actual image size
    const natW = activeImageViewer.naturalWidth;
    const natH = activeImageViewer.naturalHeight;
    const ratioW = natW > 0 ? imgRect.width / natW : 0;
    const ratioH = natH > 0 ? imgRect.height / natH : 0;

    transList.forEach((t, i) => {
        const box = document.createElement('div');
        box.className = 'collection-translation-box';

        // t.rect is [orig_x, orig_y, orig_w, orig_h]
        const dispX = t.rect[0] * ratioW;
        const dispY = t.rect[1] * ratioH;
        const dispW = t.rect[2] * ratioW;
        const dispH = t.rect[3] * ratioH;

        // Position relative to mediaContainer
        box.style.position = 'absolute';
        const boxX = imgRect.left - containerRect.left + dispX + mediaContainer.scrollLeft;
        const boxY = imgRect.top - containerRect.top + dispY + mediaContainer.scrollTop;

        box.style.left = boxX + 'px';
        box.style.top = boxY + 'px';
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
            pywebview.api.save_collection_info(path, collectionTranslations);
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
            collectionTranslations[filename].splice(i, 1);
            pywebview.api.save_collection_info(path, collectionTranslations);
            renderTranslations(path, targetViewer);
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
    // Re-render for any visible image viewers
    if (splitScreenActive) {
        if (leftImage.style.display !== 'none' && leftPlaylist[leftCurrentIndex]) {
            renderTranslations(leftPlaylist[leftCurrentIndex].path, leftImage);
        }
        if (imageViewer.style.display !== 'none' && rightPlaylist[rightCurrentIndex]) {
            renderTranslations(rightPlaylist[rightCurrentIndex].path, imageViewer);
        }
    } else if (imageViewer.style.display !== 'none' && playlist[currentIndex]) {
        renderTranslations(playlist[currentIndex].path, imageViewer);
    }
});

// --- Online Media Logic ---
const onlineCollectionModal = document.getElementById('online-media-modal');
const nhentaiTagsList = document.getElementById('nhentai-tags-list');
const nhentaiResultsArea = document.getElementById('nhentai-results-area');
const nhentaiSearchInput = document.getElementById('nhentai-search-input');
const onlineCollectionStatus = document.getElementById('online-media-status');

function renderOnlineCollectionSources() {
    const select = document.getElementById('collection-source-select');
    if (!select) return;

    select.innerHTML = '';
    
    const sites = appState.collection_sites || [];
    sites.forEach(site => {
        const opt = document.createElement('option');
        opt.value = site.id;
        opt.textContent = site.name;
        select.appendChild(opt);
    });
}

let cachedPopularTags = { nhentai: [], danbooru: [], hentaiyoga: [], rule34art: [], ehentai: [] };

function onCollectionSourceChanged() {
    const select = document.getElementById('collection-source-select');
    if (!select) return;

    const searchInput = document.getElementById('collection-tag-search');
    if (searchInput) searchInput.value = '';

    const val = select.value;
    const browseBtn = document.getElementById('browse-source-btn');
    const directDownloadContainer = document.getElementById('collection-direct-download-container');
    const searchContainer = document.getElementById('nhentai-search-container');
    const sidebar = nhentaiTagsList.parentNode;
    const resultsArea = document.getElementById('nhentai-results-area');
    const hentaiYogaMediaType = document.getElementById('hentaiyoga-media-type');

    if (hentaiYogaMediaType) {
        hentaiYogaMediaType.style.display = (val === 'hentaiyoga') ? 'inline-block' : 'none';
    }

    const isBuiltIn = ['nhentai', 'danbooru', 'hentaiyoga', 'rule34art', 'ehentai'].includes(val);
    if (isBuiltIn) {
        if (browseBtn) browseBtn.style.display = 'none';
        if (directDownloadContainer) directDownloadContainer.style.display = 'none';
        if (searchContainer) searchContainer.style.display = 'flex';
        if (sidebar) sidebar.style.display = 'block';
        if (resultsArea) {
            resultsArea.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: #666; margin-top: 20px;">Enter a search term or click a popular tag to begin.</div>';
        }

        renderFavoriteCollectionTags();
        if (val === 'nhentai') {
            loadNhentaiTags();
        } else if (val === 'danbooru') {
            loadDanbooruTags();
        } else if (val === 'hentaiyoga') {
            loadHentaiYogaTags();
        } else if (val === 'rule34art') {
            loadRule34ArtTags();
        } else {
            loadEhentaiTags();
        }
    } else {
        const site = (appState.collection_sites || []).find(s => s.id === val);

        if (browseBtn) browseBtn.style.display = 'inline-block';
        if (directDownloadContainer) directDownloadContainer.style.display = 'block';
        if (searchContainer) searchContainer.style.display = 'flex';
        if (sidebar) sidebar.style.display = 'none';

        if (resultsArea && site) {
            resultsArea.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: #bbb; margin-top: 20px; font-size: 14px; line-height: 1.8;">
                <strong>${site.name}</strong> selected.<br><br>
                Type a query in the search bar above to scrape results via AI auto-configured selectors, or use the direct downloader.
            </div>`;
        }
    }
}

function browseSelectedCollectionSource() {
    const select = document.getElementById('collection-source-select');
    if (!select) return;

    const val = select.value;
    const isBuiltIn = ['nhentai', 'danbooru', 'hentaiyoga', 'rule34art', 'ehentai'].includes(val);
    if (!isBuiltIn) {
        const site = (appState.collection_sites || []).find(s => s.id === val);
        if (site && site.domain) {
            let targetUrl = site.domain;
            if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
                targetUrl = 'https://' + targetUrl;
            }
            pywebview.api.open_external_url(targetUrl);
        }
    }
}

function downloadDirectCollectionUrl() {
    const urlInput = document.getElementById('collection-direct-url');
    if (!urlInput) return;

    const url = urlInput.value.trim();
    if (!url) {
        alert('Please paste a valid collection URL to download.');
        return;
    }

    let title = 'Downloaded_Collection';
    try {
        const urlObj = new URL(url);
        const pathParts = urlObj.pathname.split('/').filter(p => p);
        if (pathParts.length > 0) {
            title = pathParts[pathParts.length - 1];
        }
    } catch (e) { }

    let mediaType = "all";
    const mediaTypeSelect = document.getElementById('hentaiyoga-media-type');
    if (mediaTypeSelect && mediaTypeSelect.style.display !== 'none') {
        mediaType = mediaTypeSelect.value;
    }

    onlineCollectionStatus.innerText = 'Starting direct download...';
    pywebview.api.download_nhentai(url, title, mediaType);
    urlInput.value = '';
}

function previewDirectCollectionUrl() {
    const urlInput = document.getElementById('collection-direct-url');
    if (!urlInput) return;

    const url = urlInput.value.trim();
    if (!url) {
        alert('Please paste a valid collection URL to browse/play.');
        return;
    }

    onlineCollectionStatus.innerText = 'Scraping gallery media...';
    
    const select = document.getElementById('collection-source-select');
    const source = select ? select.value : '';

    pywebview.api.scrape_custom_gallery(url, source).then(res => {
        if (res.status === 'success' && res.playlist && res.playlist.length > 0) {
            onlineCollectionStatus.innerText = `Scraped ${res.playlist.length} items from gallery. Opening slideshow player...`;
            
            pywebview.api.set_ftp_playlist(res.playlist, 0).then(() => {
                let title = 'Gallery Preview';
                try {
                    const u = new URL(url);
                    title = u.pathname.split('/').filter(p => p).pop() || 'Gallery Preview';
                } catch(e) {}
                
                pywebview.api.open_in_app_browser('http://localhost:5050/ftp_player', decodeURIComponent(title));
            });
        } else {
            onlineCollectionStatus.innerText = 'Failed to scrape gallery contents.';
            alert('Failed to scrape gallery:\n' + (res.msg || 'No images or videos found on the target page.'));
        }
    });
}

function openOnlineMedia() {
    onlineCollectionModal.style.display = 'flex';
    renderOnlineCollectionSources();
    document.getElementById('collection-source-select').value = 'nhentai';
    onCollectionSourceChanged();
    loadNhentaiTags();
    renderFavoriteCollectionTags();
    pywebview.api.get_collection_download_dir().then(res => {
        document.getElementById('collection-dl-dir-display').innerText = res.dir;
    });
}

function closeOnlineMedia() {
    onlineCollectionModal.style.display = 'none';
    const modalContent = document.querySelector('#online-media-modal .modal-content');
    const icon = document.getElementById('collection-max-icon');
    if (modalContent && modalContent.classList.contains('maximized')) {
        modalContent.classList.remove('maximized');
    }
    if (icon) {
        icon.className = 'fa-regular fa-square';
        icon.parentNode.title = 'Maximize';
    }
}

function toggleMaximizeCollectionBrowser() {
    const modalContent = document.querySelector('#online-media-modal .modal-content');
    const icon = document.getElementById('collection-max-icon');
    if (!modalContent || !icon) return;

    if (modalContent.classList.contains('maximized')) {
        modalContent.classList.remove('maximized');
        icon.className = 'fa-regular fa-square';
        icon.parentNode.title = 'Maximize';
    } else {
        modalContent.classList.add('maximized');
        icon.className = 'fa-regular fa-window-restore';
        icon.parentNode.title = 'Restore';
    }
}

function toggleMaximizeStoriesBrowser() {
    const modalContent = document.querySelector('#online-stories-modal .modal-content');
    const icon = document.getElementById('stories-max-icon');
    if (!modalContent || !icon) return;
    if (modalContent.classList.contains('maximized')) {
        modalContent.classList.remove('maximized');
        icon.className = 'fa-regular fa-square';
    } else {
        modalContent.classList.add('maximized');
        icon.className = 'fa-regular fa-window-restore';
    }
}

function toggleMaximizeAudioBrowser() {
    const modalContent = document.querySelector('#online-audio-modal .modal-content');
    const icon = document.getElementById('audio-max-icon');
    if (!modalContent || !icon) return;
    if (modalContent.classList.contains('maximized')) {
        modalContent.classList.remove('maximized');
        icon.className = 'fa-regular fa-square';
    } else {
        modalContent.classList.add('maximized');
        icon.className = 'fa-regular fa-window-restore';
    }
}

function loadNextOnlineMediaPage() { console.log('Load Next Media Page'); }
function loadNextOnlineStoriesPage() { console.log('Load Next Stories Page'); }
function loadNextOnlineAudioPage() { console.log('Load Next Audio Page'); }


function changeCollectionDownloadDir() {
    pywebview.api.choose_collection_download_dir().then(res => {
        if (res.status === 'success') {
            document.getElementById('collection-dl-dir-display').innerText = res.dir;
        }
    });
}

let tagSearchTimeout = null;

function onCollectionTagSearchChanged() {
    const input = document.getElementById('collection-tag-search');
    if (!input) return;
    const query = input.value.trim().toLowerCase();

    const select = document.getElementById('collection-source-select');
    const source = select ? select.value : 'nhentai';

    if (source === 'nhentai') {
        renderNhentaiPopularTagsFiltered(query);
    } else if (source === 'danbooru') {
        if (tagSearchTimeout) clearTimeout(tagSearchTimeout);
        tagSearchTimeout = setTimeout(() => {
            loadDanbooruTags(query);
        }, 300);
    } else if (source === 'hentaiyoga') {
        if (tagSearchTimeout) clearTimeout(tagSearchTimeout);
        tagSearchTimeout = setTimeout(() => {
            loadHentaiYogaTags(query);
        }, 300);
    } else if (source === 'rule34art') {
        if (tagSearchTimeout) clearTimeout(tagSearchTimeout);
        tagSearchTimeout = setTimeout(() => {
            loadRule34ArtTags(query);
        }, 300);
    } else if (source === 'ehentai') {
        if (tagSearchTimeout) clearTimeout(tagSearchTimeout);
        tagSearchTimeout = setTimeout(() => {
            loadEhentaiTags(query);
        }, 300);
    }
}

function loadNhentaiTags() {
    if (nhentaiTagsList.dataset.loadedSource === 'nhentai') {
        renderNhentaiPopularTags();
        return;
    }
    nhentaiTagsList.innerHTML = '<div style="padding: 10px; color: #888; font-size: 11px;">Loading tags...</div>';
    pywebview.api.get_nhentai_tags().then(res => {
        if (res.status === 'success') {
            cachedPopularTags.nhentai = res.tags || [];
            nhentaiTagsList.dataset.loadedSource = 'nhentai';
            renderNhentaiPopularTags();
        } else {
            nhentaiTagsList.innerHTML = `<span style="color:red; font-size: 11px;">Failed to load: ${res.msg}</span>`;
        }
    });
}

function renderNhentaiPopularTagsFiltered(query = "") {
    nhentaiTagsList.innerHTML = '';
    let tags = cachedPopularTags.nhentai || [];
    if (query) {
        tags = tags.filter(t => t.toLowerCase().includes(query));
    }
    const favTags = (appState.favorite_collection_tags && appState.favorite_collection_tags.nhentai) || [];

    if (tags.length === 0) {
        nhentaiTagsList.innerHTML = '<div style="color: #666; font-size: 12px; padding: 5px;">No tags found.</div>';
        return;
    }

    tags.forEach(tag => {
        const isFav = favTags.includes(tag);
        const row = createCollectionTagRow(tag, 'nhentai', '#ff477e', isFav);
        nhentaiTagsList.appendChild(row);
    });
}

function renderNhentaiPopularTags() {
    renderNhentaiPopularTagsFiltered("");
}

function loadDanbooruTags(query = "") {
    if (!query && cachedPopularTags.danbooru.length > 0) {
        renderDanbooruPopularTags();
        return;
    }
    nhentaiTagsList.innerHTML = '<div style="padding: 10px; color: #888; font-size: 11px;">Loading tags...</div>';
    pywebview.api.get_danbooru_tags(query).then(res => {
        if (res.status === 'success') {
            if (!query) {
                cachedPopularTags.danbooru = res.tags || [];
                nhentaiTagsList.dataset.loadedSource = 'danbooru';
            }
            renderDanbooruPopularTagsList(res.tags || []);
        } else {
            nhentaiTagsList.innerHTML = `<span style="color:red; font-size: 11px;">Failed to load: ${res.msg}</span>`;
        }
    });
}

function renderDanbooruPopularTagsList(tags) {
    nhentaiTagsList.innerHTML = '';
    const favTags = (appState.favorite_collection_tags && appState.favorite_collection_tags.danbooru) || [];

    if (tags.length === 0) {
        nhentaiTagsList.innerHTML = '<div style="color: #666; font-size: 12px; padding: 5px;">No tags found.</div>';
        return;
    }

    tags.forEach(tag => {
        const isFav = favTags.includes(tag);
        const row = createCollectionTagRow(tag, 'danbooru', '#cba6f7', isFav);
        nhentaiTagsList.appendChild(row);
    });
}

function renderDanbooruPopularTags() {
    renderDanbooruPopularTagsList(cachedPopularTags.danbooru);
}

function loadHentaiYogaTags(query = "") {
    if (!query && cachedPopularTags.hentaiyoga && cachedPopularTags.hentaiyoga.length > 0) {
        renderHentaiYogaPopularTags();
        return;
    }
    nhentaiTagsList.innerHTML = '<div style="padding: 10px; color: #888; font-size: 11px;">Loading tags...</div>';
    pywebview.api.get_hentai_yoga_tags(query).then(res => {
        if (res.status === 'success') {
            if (!query) {
                cachedPopularTags.hentaiyoga = res.tags || [];
                nhentaiTagsList.dataset.loadedSource = 'hentaiyoga';
            }
            renderHentaiYogaPopularTagsList(res.tags || []);
        } else {
            nhentaiTagsList.innerHTML = `<span style="color:red; font-size: 11px;">Failed to load: ${res.msg}</span>`;
        }
    });
}

function renderHentaiYogaPopularTagsList(tags) {
    nhentaiTagsList.innerHTML = '';
    const favTags = (appState.favorite_collection_tags && appState.favorite_collection_tags.hentaiyoga) || [];

    if (tags.length === 0) {
        nhentaiTagsList.innerHTML = '<div style="color: #666; font-size: 12px; padding: 5px;">No tags found.</div>';
        return;
    }

    tags.forEach(tag => {
        const isFav = favTags.includes(tag);
        const row = createCollectionTagRow(tag, 'hentaiyoga', '#89dceb', isFav);
        nhentaiTagsList.appendChild(row);
    });
}

function renderHentaiYogaPopularTags() {
    renderHentaiYogaPopularTagsList(cachedPopularTags.hentaiyoga || []);
}

function loadRule34ArtTags(query = "") {
    if (!query && cachedPopularTags.rule34art && cachedPopularTags.rule34art.length > 0) {
        renderRule34ArtPopularTags();
        return;
    }
    nhentaiTagsList.innerHTML = '<div style="padding: 10px; color: #888; font-size: 11px;">Loading categories...</div>';
    pywebview.api.get_rule34art_tags(query).then(res => {
        if (res.status === 'success') {
            if (!query) {
                cachedPopularTags.rule34art = res.tags || [];
                nhentaiTagsList.dataset.loadedSource = 'rule34art';
            }
            renderRule34ArtPopularTagsList(res.tags || []);
        } else {
            nhentaiTagsList.innerHTML = `<div style="color: red; font-size: 11px; padding: 5px;">Error: ${res.msg}</div>`;
        }
    });
}

function renderRule34ArtPopularTagsList(tags) {
    nhentaiTagsList.innerHTML = '';
    const favTags = (appState.favorite_collection_tags && appState.favorite_collection_tags.rule34art) || [];
    if (tags.length === 0) {
        nhentaiTagsList.innerHTML = '<div style="color: #666; font-size: 12px; padding: 5px;">No categories found.</div>';
        return;
    }
    tags.forEach(tag => {
        const isFav = favTags.includes(tag);
        const row = createCollectionTagRow(tag, 'rule34art', '#f38ba8', isFav);
        nhentaiTagsList.appendChild(row);
    });
}

function renderRule34ArtPopularTags() {
    renderRule34ArtPopularTagsList(cachedPopularTags.rule34art || []);
}

function loadEhentaiTags(query = "") {
    if (!query && cachedPopularTags.ehentai && cachedPopularTags.ehentai.length > 0) {
        renderEhentaiPopularTags();
        return;
    }
    nhentaiTagsList.innerHTML = '<div style="padding: 10px; color: #888; font-size: 11px;">Loading tags...</div>';
    pywebview.api.get_ehentai_tags(query).then(res => {
        if (res.status === 'success') {
            if (!query) {
                cachedPopularTags.ehentai = res.tags || [];
                nhentaiTagsList.dataset.loadedSource = 'ehentai';
            }
            renderEhentaiPopularTagsList(res.tags || []);
        } else {
            nhentaiTagsList.innerHTML = `<div style="color: red; font-size: 11px; padding: 5px;">Error: ${res.msg}</div>`;
        }
    });
}

function renderEhentaiPopularTagsList(tags) {
    nhentaiTagsList.innerHTML = '';
    const favTags = (appState.favorite_collection_tags && appState.favorite_collection_tags.ehentai) || [];
    if (tags.length === 0) {
        nhentaiTagsList.innerHTML = '<div style="color: #666; font-size: 12px; padding: 5px;">No tags found.</div>';
        return;
    }
    tags.forEach(tag => {
        const isFav = favTags.includes(tag);
        const row = createCollectionTagRow(tag, 'ehentai', '#fab387', isFav);
        nhentaiTagsList.appendChild(row);
    });
}

function renderEhentaiPopularTags() {
    renderEhentaiPopularTagsList(cachedPopularTags.ehentai || []);
}

function renderFavoriteCollectionTags() {
    const container = document.getElementById('favorite-tags-list');
    if (!container) return;
    container.innerHTML = '';

    const select = document.getElementById('collection-source-select');
    const source = select ? select.value : 'nhentai';

    const favTags = (appState.favorite_collection_tags && appState.favorite_collection_tags[source]) || [];
    const sourceColor = source === 'nhentai' ? '#ff477e' : (source === 'danbooru' ? '#cba6f7' : (source === 'rule34art' ? '#f38ba8' : (source === 'ehentai' ? '#fab387' : '#89dceb')));

    if (favTags.length === 0) {
        container.innerHTML = '<span style="color: #666; font-size: 11px; font-style: italic; padding: 5px;">No favorite tags yet.</span>';
        return;
    }

    favTags.forEach(tag => {
        const row = createCollectionTagRow(tag, source, sourceColor, true);
        container.appendChild(row);
    });
}

function createCollectionTagRow(tag, source, color, isFav) {
    const row = document.createElement('div');
    row.className = 'tag-row-item';
    row.style.display = 'flex';
    row.style.justifyContent = 'space-between';
    row.style.alignItems = 'center';
    row.style.gap = '5px';
    row.style.width = '100%';

    const btn = document.createElement('button');
    btn.className = 'tag-btn';
    btn.style.textAlign = 'left';
    btn.style.padding = '5px 0';
    btn.style.background = 'transparent';
    btn.style.color = color;
    btn.style.border = 'none';
    btn.style.cursor = 'pointer';
    btn.style.flexGrow = '1';
    btn.style.overflow = 'hidden';
    btn.style.textOverflow = 'ellipsis';
    btn.style.whiteSpace = 'nowrap';
    btn.style.fontSize = '13px';
    btn.innerText = tag;
    btn.onclick = () => {
        nhentaiSearchInput.value = tag;
        searchOnlineMedia();
    };

    const favBtn = document.createElement('button');
    favBtn.className = 'tag-fav-btn';
    favBtn.style.background = 'transparent';
    favBtn.style.border = 'none';
    favBtn.style.cursor = 'pointer';
    favBtn.style.padding = '5px';
    favBtn.style.color = isFav ? '#ffbc47' : '#555';
    favBtn.innerHTML = isFav ? '<i class="fa-solid fa-star"></i>' : '<i class="fa-regular fa-star"></i>';
    favBtn.onclick = (e) => {
        e.stopPropagation();
        toggleFavoriteCollectionTag(tag, source);
    };

    row.appendChild(btn);
    row.appendChild(favBtn);
    return row;
}

function toggleFavoriteCollectionTag(tag, source) {
    if (!appState.favorite_collection_tags) {
        appState.favorite_collection_tags = { nhentai: [], danbooru: [], hentaiyoga: [] };
    }
    if (!appState.favorite_collection_tags[source]) {
        appState.favorite_collection_tags[source] = [];
    }

    const favs = appState.favorite_collection_tags[source];
    const index = favs.indexOf(tag);
    if (index >= 0) {
        favs.splice(index, 1);
    } else {
        favs.push(tag);
    }

    pywebview.api.save_favorite_collection_tags(appState.favorite_collection_tags).then(state => {
        appState = state;
        renderFavoriteCollectionTags();
        if (source === 'nhentai') {
            renderNhentaiPopularTags();
        } else if (source === 'danbooru') {
            renderDanbooruPopularTags();
        } else if (source === 'hentaiyoga') {
            renderHentaiYogaPopularTags();
        } else if (source === 'rule34art') {
            renderRule34ArtPopularTags();
        } else if (source === 'ehentai') {
            renderEhentaiPopularTags();
        }
    });
}

function searchOnlineMedia() {
    const query = nhentaiSearchInput.value.trim();
    if (!query) return;

    onlineCollectionStatus.innerText = `Searching for "${query}"...`;
    nhentaiResultsArea.innerHTML = '';

    const select = document.getElementById('collection-source-select');
    const source = select ? select.value : 'nhentai';

    let searchPromise;
    const isBuiltIn = ['nhentai', 'danbooru', 'hentaiyoga', 'rule34art', 'ehentai'].includes(source);
    if (!isBuiltIn) {
        searchPromise = pywebview.api.search_custom_collection(source, query);
    } else if (source === 'danbooru') {
        searchPromise = pywebview.api.search_danbooru(query);
    } else if (source === 'hentaiyoga') {
        searchPromise = pywebview.api.search_hentai_yoga(query);
    } else if (source === 'rule34art') {
        searchPromise = pywebview.api.search_rule34art(query);
    } else if (source === 'ehentai') {
        searchPromise = pywebview.api.search_ehentai(query);
    } else {
        searchPromise = pywebview.api.search_nhentai(query);
    }

    searchPromise.then(res => {
        if (res.status === 'success') {
            onlineCollectionStatus.innerText = `Found ${res.results.length} results for "${query}"`;
            res.results.forEach(item => {
                const card = document.createElement('div');
                card.style.background = '#333';
                card.style.borderRadius = '5px';
                card.style.padding = '10px';
                card.style.display = 'flex';
                card.style.flexDirection = 'column';
                card.style.gap = '10px';

                const img = document.createElement('img');
                // Proxy thumbnails through our local server to bypass hotlink protection
                if (item.thumb && source !== 'danbooru') {
                    img.src = `http://127.0.0.1:5050/imgproxy?url=${encodeURIComponent(item.thumb)}`;
                } else {
                    img.src = item.thumb || '';
                }
                img.style.width = '100%';
                img.style.height = '150px';
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
                
                const isCustom = !['nhentai', 'danbooru', 'hentaiyoga', 'rule34art', 'ehentai'].includes(source);
                if (isCustom) {
                    dlBtn.innerText = 'Load Gallery';
                    dlBtn.style.background = '#89b4fa';
                    dlBtn.style.color = '#111';
                }
                
                dlBtn.onclick = () => {
                    if (isCustom) {
                        const dlInput = document.getElementById('collection-direct-url');
                        if (dlInput) {
                            dlInput.value = item.url;
                            previewDirectCollectionUrl();
                        }
                    } else {
                        dlBtn.innerText = 'Downloading...';
                        dlBtn.disabled = true;
                        dlBtn.style.background = '#888';
                        let mediaType = "all";
                        if (source === 'hentaiyoga') {
                            const mediaTypeSelect = document.getElementById('hentaiyoga-media-type');
                            if (mediaTypeSelect) mediaType = mediaTypeSelect.value;
                        }
                        pywebview.api.download_nhentai(item.url, item.title, mediaType);
                    }
                };

                card.oncontextmenu = (e) => {
                    e.preventDefault();
                    if (!omCm) return;
                    omCm.style.display = 'block';

                    let x = e.clientX;
                    let y = e.clientY;
                    if (x + omCm.offsetWidth > window.innerWidth) x = window.innerWidth - omCm.offsetWidth;
                    if (y + omCm.offsetHeight > window.innerHeight) y = window.innerHeight - omCm.offsetHeight;
                    omCm.style.left = x + 'px';
                    omCm.style.top = y + 'px';

                    document.getElementById('om-cm-tags').onclick = () => {
                        omCm.style.display = 'none';
                        onlineCollectionStatus.innerText = 'Fetching tags...';
                        pywebview.api.get_collection_details(item.url, source).then(res => {
                            if (res.status === 'success') {
                                onlineCollectionStatus.innerText = '';
                                alert(`Tags for ${item.title}:\n\n` + (res.tags.length > 0 ? res.tags.join(', ') : 'No tags found.'));
                            } else {
                                onlineCollectionStatus.innerText = `Failed to fetch tags: ${res.msg}`;
                            }
                        });
                    };

                    document.getElementById('om-cm-count').onclick = () => {
                        omCm.style.display = 'none';
                        onlineCollectionStatus.innerText = 'Fetching image count...';
                        pywebview.api.get_collection_details(item.url, source).then(res => {
                            if (res.status === 'success') {
                                onlineCollectionStatus.innerText = '';
                                alert(`Image Count for ${item.title}:\n\n${res.image_count}`);
                            } else {
                                onlineCollectionStatus.innerText = `Failed to fetch image count: ${res.msg}`;
                            }
                        });
                    };

                    document.getElementById('om-cm-open').onclick = () => {
                        omCm.style.display = 'none';
                        pywebview.api.open_external_url(item.url);
                    };
                };

                card.appendChild(img);
                card.appendChild(title);
                card.appendChild(dlBtn);
                nhentaiResultsArea.appendChild(card);
            });
        } else {
            onlineCollectionStatus.innerText = `Search failed: ${res.msg}`;
        }
    });
}

function onCollectionColumnsChanged() {
    const sel = document.getElementById('collection-columns-select');
    const cols = sel ? parseInt(sel.value) : 6;
    const area = document.getElementById('nhentai-results-area');
    if (area) {
        area.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    }
}

function onCollectionThumbSizeChanged() {
    const slider = document.getElementById('collection-thumb-size');
    if (!slider) return;
    const size = slider.value + 'px';
    const imgs = document.querySelectorAll('#nhentai-results-area img');
    imgs.forEach(img => {
        img.style.height = size;
    });
}

function onStoryColumnsChanged() {
    const sel = document.getElementById('story-columns-select');
    const cols = sel ? parseInt(sel.value) : 3;
    const area = document.getElementById('online-stories-results-area');
    if (area) {
        area.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    }
}

function onStoryThumbSizeChanged() {
    const slider = document.getElementById('story-thumb-size');
    if (!slider) return;
    const size = slider.value + 'px';
    const imgs = document.querySelectorAll('#online-stories-results-area img');
    imgs.forEach(img => {
        img.style.height = size;
    });
}

function onAudioColumnsChanged() {
    const sel = document.getElementById('audio-columns-select');
    const cols = sel ? parseInt(sel.value) : 3;
    const area = document.getElementById('online-audio-list');
    if (area) {
        area.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    }
}

function onAudioThumbSizeChanged() {
    const slider = document.getElementById('audio-thumb-size');
    if (!slider) return;
    const size = slider.value + 'px';
    const cards = document.querySelectorAll('#online-audio-list .audio-site-card, #online-playlists-grid .audio-site-card');
    cards.forEach(card => {
        card.style.minHeight = size;
    });
}

function updateGlobalDownloadUI(title, progressText, percent, isComplete = false, isError = false) {
    let container = document.getElementById('global-download-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'global-download-container';
        container.style.position = 'fixed';
        container.style.bottom = '20px';
        container.style.right = '20px';
        container.style.width = '320px';
        container.style.maxHeight = '60vh';
        container.style.overflowY = 'auto';
        container.style.zIndex = '9999';
        container.style.display = showDownloadsUI ? 'flex' : 'none';
        container.style.flexDirection = 'column';
        container.style.gap = '10px';
        container.style.pointerEvents = 'none'; // So you can click things behind it
        document.body.appendChild(container);

        let header = document.createElement('div');
        header.style.display = 'flex';
        header.style.justifyContent = 'space-between';
        header.style.alignItems = 'center';
        header.style.pointerEvents = 'auto'; // allow clicking

        let headerTitle = document.createElement('strong');
        headerTitle.textContent = 'Downloads';
        headerTitle.style.color = '#fff';
        headerTitle.style.fontSize = '14px';

        let clearBtn = document.createElement('button');
        clearBtn.innerHTML = '<i class="fa-solid fa-broom"></i> Clear Completed';
        clearBtn.style.background = '#444';
        clearBtn.style.color = '#fff';
        clearBtn.style.border = 'none';
        clearBtn.style.padding = '5px 10px';
        clearBtn.style.borderRadius = '3px';
        clearBtn.style.cursor = 'pointer';
        clearBtn.style.fontSize = '11px';
        clearBtn.onclick = () => {
            const items = container.querySelectorAll('div[data-status="complete"], div[data-status="error"]');
            items.forEach(item => item.remove());
        };

        header.appendChild(headerTitle);
        header.appendChild(clearBtn);
        container.appendChild(header);
    }

    let safeId = 'dl-' + encodeURIComponent(title).replace(/[^a-zA-Z0-9]/g, '');
    let el = document.getElementById(safeId);

    if (!el) {
        el = document.createElement('div');
        el.id = safeId;
        el.style.background = 'rgba(30, 30, 30, 0.95)';
        el.style.border = '1px solid #4CAF50';
        el.style.borderRadius = '5px';
        el.style.padding = '10px';
        el.style.color = 'white';
        el.style.boxShadow = '0 4px 6px rgba(0,0,0,0.5)';
        el.style.pointerEvents = 'auto'; // allow clicking the X button
        container.appendChild(el);
    }

    if (isError) {
        el.dataset.status = 'error';
        el.style.borderColor = '#d32f2f';
        el.innerHTML = `
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <strong style="font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${title}">${title}</strong>
                <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; color: white; cursor: pointer; font-size: 16px; line-height: 1;">&times;</button>
            </div>
            <div style="font-size: 11px; color: #f38ba8;">Error: ${progressText}</div>
        `;
    } else if (isComplete) {
        el.dataset.status = 'complete';
        el.style.borderColor = '#4CAF50';
        el.innerHTML = `
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <strong style="font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${title}">${title}</strong>
                <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; color: white; cursor: pointer; font-size: 16px; line-height: 1;">&times;</button>
            </div>
            <div style="font-size: 11px; color: #a6e3a1;">Download Complete!</div>
        `;
    } else {
        el.dataset.status = 'active';
        el.style.borderColor = '#4da6ff';
        el.innerHTML = `
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px; align-items: center;">
                <strong style="font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${title.replace(/"/g, '&quot;')}">${title.replace(/"/g, '&quot;')}</strong>
                <div>
                    <button onclick="pywebview.api.cancel_download(decodeURIComponent('${encodeURIComponent(title)}'))" style="background: none; border: none; color: #f38ba8; cursor: pointer; font-size: 14px; margin-right: 5px;" title="Cancel Download"><i class="fa-solid fa-stop"></i></button>
                    <button onclick="this.parentElement.parentElement.parentElement.remove()" style="background: none; border: none; color: white; cursor: pointer; font-size: 16px; line-height: 1;">&times;</button>
                </div>
            </div>
            <div style="font-size: 11px; color: #ccc;">${progressText} (${percent}%)</div>
            <div style="width: 100%; background: #444; border-radius: 3px; margin-top: 5px; height: 6px; overflow: hidden;">
                <div style="width: ${percent}%; background: #4da6ff; height: 100%; border-radius: 3px; transition: width 0.2s;"></div>
            </div>
        `;
    }
}

function updateDownloadProgress(current, total, title) {
    const statusEl = document.getElementById('online-media-status');
    let percent = 0;
    let progressText = "";
    let isBytes = total > 10000 || current > 10000;

    if (total > 0) {
        percent = Math.round((current / total) * 100);
        progressText = isBytes
            ? `${(current / 1048576).toFixed(2)} MB / ${(total / 1048576).toFixed(2)} MB`
            : `${current} / ${total} images`;
    } else {
        progressText = isBytes
            ? `${(current / 1048576).toFixed(2)} MB`
            : `${current} images`;
    }

    if (statusEl) {
        statusEl.style.color = '';
        if (total > 0) {
            statusEl.innerHTML = `<span style="color: #fff;">Downloading: ${title}</span> <br> <span style="font-size: 11px; color: #ccc;">${progressText} (${percent}%)</span>
            <div style="width: 100%; background: #444; border-radius: 3px; margin-top: 5px; height: 8px; overflow: hidden;">
                <div style="width: ${percent}%; background: #4CAF50; height: 100%; border-radius: 3px; transition: width 0.2s;"></div>
            </div>`;
        } else {
            statusEl.innerText = `Downloading: ${title}... ${progressText} downloaded`;
        }
    }

    updateGlobalDownloadUI(title, progressText, percent);
}

function downloadComplete(dir_path, title) {
    onlineCollectionStatus.innerText = `Download complete! Loaded into playlist.`;
    onlineCollectionStatus.style.color = '#4CAF50';
    setTimeout(() => { onlineCollectionStatus.style.color = '#aaa'; }, 3000);

    if (title) {
        updateGlobalDownloadUI(title, "", 100, true, false);
    }
}

function downloadFailed(err, title) {
    onlineCollectionStatus.innerText = `Download failed: ${err}`;
    onlineCollectionStatus.style.color = 'red';

    if (title) {
        updateGlobalDownloadUI(title, err, 0, false, true);
    }
}

// --- Audio Normalization Filter ---
let audioCtx = null;
let sourceNode = null;
let compressorNode = null;
let makeupGainNode = null;
let isNormalized = false;

// Create the toggle button dynamically and place it next to the play button
// Create the toggle button dynamically
normBtn = document.createElement('button');
normBtn.innerHTML = 'Norm: OFF';
normBtn.style.padding = '5px 10px';
normBtn.style.marginLeft = '10px';
normBtn.style.borderRadius = '3px';
normBtn.style.border = 'none';
normBtn.style.background = '#555';
normBtn.style.color = 'white';
normBtn.style.cursor = 'pointer';

normContainer = document.createElement('div');
normContainer.style.display = 'inline-flex';
normContainer.style.alignItems = 'center';
normContainer.style.marginLeft = '10px';
normContainer.style.gap = '5px';
normContainer.style.color = 'white';

const threshLabel = document.createElement('span');
threshLabel.innerText = 'Loud:';
threshLabel.style.fontSize = '12px';

thresholdSlider = document.createElement('input');
thresholdSlider.type = 'range';
thresholdSlider.min = '-60';
thresholdSlider.max = '0';
thresholdSlider.value = '-35';
thresholdSlider.title = 'Threshold (Loud sounds)';
thresholdSlider.style.width = '60px';

const gainLabel = document.createElement('span');
gainLabel.innerText = 'Quiet:';
gainLabel.style.fontSize = '12px';

gainSlider = document.createElement('input');
gainSlider.type = 'range';
gainSlider.min = '0.5';
gainSlider.max = '4.0';
gainSlider.step = '0.1';
gainSlider.value = '1.2';
gainSlider.title = 'Makeup Gain (Quiet sounds)';
gainSlider.style.width = '60px';

normContainer.appendChild(normBtn);
normContainer.appendChild(threshLabel);
normContainer.appendChild(thresholdSlider);
normContainer.appendChild(gainLabel);
normContainer.appendChild(gainSlider);

normBtn.addEventListener('click', () => {
    isNormalized = !isNormalized;
    normBtn.innerText = isNormalized ? 'Norm: ON' : 'Norm: OFF';
    normBtn.style.background = isNormalized ? '#4CAF50' : '#555';
    applyAudioRouting();
});

thresholdSlider.addEventListener('input', () => {
    if (compressorNode && audioCtx) {
        compressorNode.threshold.setValueAtTime(parseFloat(thresholdSlider.value), audioCtx.currentTime);
    }
});

gainSlider.addEventListener('input', () => {
    if (makeupGainNode && audioCtx) {
        makeupGainNode.gain.setValueAtTime(parseFloat(gainSlider.value), audioCtx.currentTime);
    }
});

function applyAudioRouting() {
    if (!audioCtx || !sourceNode) return;

    // Disconnect everything first to prevent double-routing
    sourceNode.disconnect();
    if (compressorNode) compressorNode.disconnect();
    if (makeupGainNode) makeupGainNode.disconnect();

    if (isNormalized) {
        sourceNode.connect(compressorNode);
        compressorNode.connect(makeupGainNode);
        makeupGainNode.connect(audioCtx.destination);
    } else {
        sourceNode.connect(audioCtx.destination); // Direct bypass
    }
}

videoPlayer.addEventListener('play', () => {
    if (!audioCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AudioContext();
        sourceNode = audioCtx.createMediaElementSource(videoPlayer);

        compressorNode = audioCtx.createDynamicsCompressor();
        // Settings for volume normalization (dynamic range compression)
        compressorNode.threshold.setValueAtTime(parseFloat(thresholdSlider.value), audioCtx.currentTime); // Catch loud sounds even earlier
        compressorNode.knee.setValueAtTime(5, audioCtx.currentTime); // Harder clamp on peaks
        compressorNode.ratio.setValueAtTime(20, audioCtx.currentTime); // Maximum compression ratio
        compressorNode.attack.setValueAtTime(0.002, audioCtx.currentTime); // Faster attack to immediately squash sudden noises
        compressorNode.release.setValueAtTime(0.1, audioCtx.currentTime);

        // Gain node to make up for the lost volume and boost quiet sounds
        makeupGainNode = audioCtx.createGain();
        makeupGainNode.gain.setValueAtTime(parseFloat(gainSlider.value), audioCtx.currentTime); // Reduced makeup gain

        applyAudioRouting();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
});

// --- Collection Library Logic ---
let currentCollectionLibrary = [];
const collectionLibraryModal = document.getElementById('collection-library-modal');
const collectionLibraryGrid = document.getElementById('collection-library-grid');
const collectionLibraryStatus = document.getElementById('collection-library-status');

function openCollectionLibrary() {
    collectionLibraryModal.style.display = 'flex';
    collectionLibraryStatus.innerText = 'Loading collection...';
    collectionLibraryGrid.innerHTML = '';

    pywebview.api.get_collection_library().then(res => {
        if (res.status === 'success') {
            currentCollectionLibrary = res.library;
            collectionLibraryStatus.innerText = `Found ${currentCollectionLibrary.length} collection.`;
            renderCollectionLibrary();
        } else {
            collectionLibraryStatus.innerText = `Error loading library: ${res.msg}`;
        }
    });
}

function renderCollectionLibrary() {
    collectionLibraryGrid.innerHTML = '';

    if (currentCollectionLibrary.length === 0) {
        collectionLibraryGrid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: #666; margin-top: 20px;">No collection found. Mark a folder as collection or download some to see them here!</div>';
        return;
    }

    const sortMode = document.getElementById('collection-sort') ? document.getElementById('collection-sort').value : 'recent';
    let sortedLibrary = [...currentCollectionLibrary];

    if (sortMode === 'recent') {
        sortedLibrary.sort((a, b) => b.mtime - a.mtime);
    } else if (sortMode === 'az') {
        sortedLibrary.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortMode === 'za') {
        sortedLibrary.sort((a, b) => b.name.localeCompare(a.name));
    }

    sortedLibrary.forEach(collection => {
        const card = document.createElement('div');
        card.style.background = '#333';
        card.style.borderRadius = '5px';
        card.style.padding = '10px';
        card.style.display = 'flex';
        card.style.flexDirection = 'column';
        card.style.gap = '10px';
        card.style.cursor = 'pointer';
        card.title = 'Double-click to read | Right-click for options';
        card.ondblclick = () => {
            closeCollectionLibrary();
            pywebview.api.open_collection_viewer(collection.path);
        };
        card.oncontextmenu = (e) => {
            e.preventDefault();
            e.stopPropagation();

            if (mlCm) {
                mlCm.style.display = 'block';
                let x = e.clientX;
                let y = e.clientY;
                if (x + mlCm.offsetWidth > window.innerWidth) x = window.innerWidth - mlCm.offsetWidth;
                if (y + mlCm.offsetHeight > window.innerHeight) y = window.innerHeight - mlCm.offsetHeight;
                mlCm.style.left = x + 'px';
                mlCm.style.top = y + 'px';

                document.getElementById('ml-cm-rename').onclick = () => {
                    mlCm.style.display = 'none';
                    const newName = prompt(`Rename collection "${collection.name}" to:`, collection.name);
                    if (newName && newName !== collection.name) {
                        pywebview.api.rename_collection(collection.path, newName).then(res => {
                            if (res.status === 'success') openCollectionLibrary();
                            else alert("Failed to rename: " + res.msg);
                        });
                    }
                };

                document.getElementById('ml-cm-unmark').onclick = () => {
                    mlCm.style.display = 'none';
                    pywebview.api.unmark_folder_as_collection(collection.path).then(res => {
                        if (res.status === 'success') {
                            openCollectionLibrary();
                            updateState();
                        } else alert("Failed to unmark: " + res.msg);
                    });
                };

                document.getElementById('ml-cm-delete').onclick = () => {
                    mlCm.style.display = 'none';
                    if (confirm(`Are you sure you want to delete the collection "${collection.name}" and its folder from your disk?`)) {
                        pywebview.api.delete_collection_folder(collection.path).then(res => {
                            if (res.status === 'success') openCollectionLibrary();
                            else alert("Failed to delete: " + res.msg);
                        });
                    }
                };
            }
        };

        const imgContainer = document.createElement('div');
        imgContainer.style.position = 'relative';

        const img = document.createElement('img');
        if (collection.thumb) {
            img.src = `http://localhost:5050/thumbnail?path=${encodeURIComponent(collection.thumb)}`;
        } else {
            img.src = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='; // Transparent pixel
            img.style.background = '#111';
        }
        img.style.width = '100%';
        img.style.height = '200px';
        img.style.objectFit = 'cover';
        img.style.borderRadius = '3px';
        img.style.display = 'block';

        imgContainer.appendChild(img);

        if (collection.page_count !== undefined) {
            const pageBadge = document.createElement('div');
            pageBadge.innerHTML = `<i class="fa-regular fa-images"></i> ${collection.page_count}`;
            pageBadge.style.position = 'absolute';
            pageBadge.style.bottom = '5px';
            pageBadge.style.right = '5px';
            pageBadge.style.background = 'rgba(0, 0, 0, 0.8)';
            pageBadge.style.color = 'white';
            pageBadge.style.padding = '3px 6px';
            pageBadge.style.borderRadius = '4px';
            pageBadge.style.fontSize = '11px';
            imgContainer.appendChild(pageBadge);
        }

        const title = document.createElement('div');
        title.innerText = collection.name;
        title.style.fontSize = '12px';
        title.style.color = 'white';
        title.style.textAlign = 'center';
        title.style.flexGrow = '1';
        title.style.wordBreak = 'break-word';

        card.appendChild(imgContainer);
        card.appendChild(title);
        collectionLibraryGrid.appendChild(card);
    });
}

function closeCollectionLibrary() {
    collectionLibraryModal.style.display = 'none';
}

function checkForUpdates() {
    pywebview.api.check_for_updates().then(res => {
        if (res.status === 'update_available') {
            if (confirm(`A new version (${res.version}) is available!\nWould you like to open the download page?`)) {
                pywebview.api.open_external_url(res.url);
            }
        } else if (res.status === 'up_to_date') {
            alert(`You are using the latest version (${res.version}).`);
        } else {
            alert(`Failed to check for updates: ${res.msg}\n\nPlease check www.xenohead.com manually.`);
        }
    });
}

imageViewer.addEventListener('load', () => {
    updateMediaDimensions();
    
    // Only run the repaint fix on the very first load.
    if (currentIndex === 0 && !imageViewer.dataset.initialLoadDone) {
        imageViewer.dataset.initialLoadDone = 'true';
        videoPlayer.dataset.initialLoadDone = 'true'; // Sync the flag
        applyMediaStyles(); // Apply the correct styles first.
        setTimeout(() => {
            const originalZoom = currentZoom;
            setMediaZoom('double'); // Force a repaint by changing zoom
            setMediaZoom(originalZoom); // Immediately revert
        }, 10);
    } else {
        applyMediaStyles();
    }
});

// --- Online Audio Logic ---
const onlineAudioModal = document.getElementById('online-audio-modal');
let activeAudioTagFilters = new Set();
let audioSearchQuery = "";

let currentTracksList = [];
let filteredTracksList = [];
let tracksSearchQuery = "";
let browserSourceType = ""; // "site" or "playlist"
let browserSourceName = "";
let currentAudioTab = "sites"; // "sites" or "playlists"
let tracksLoadedCount = 200;

function openOnlineAudio() {
    if (onlineAudioModal) {
        pywebview.api.get_state().then(state => {
            appState = state;
            activeAudioTagFilters.clear();
            audioSearchQuery = "";
            const box = document.getElementById('audio-search-box');
            if (box) box.value = "";
            onlineAudioModal.style.display = 'flex';
            switchAudioTab('sites');
        }).catch(err => {
            console.error("Error updating state in openOnlineAudio:", err);
            activeAudioTagFilters.clear();
            audioSearchQuery = "";
            const box = document.getElementById('audio-search-box');
            if (box) box.value = "";
            onlineAudioModal.style.display = 'flex';
            switchAudioTab('sites');
        });
    }
}

function closeOnlineAudio() {
    if (onlineAudioModal) {
        onlineAudioModal.style.display = 'none';
        const audio = document.getElementById('modal-audio-element');
        if (audio) {
            audio.pause();
        }
    }
}

function onAudioSearchChanged() {
    const box = document.getElementById('audio-search-box');
    if (box) {
        audioSearchQuery = box.value.trim().toLowerCase();
        renderOnlineAudioList();
    }
}

function clearAudioFilters() {
    activeAudioTagFilters.clear();
    audioSearchQuery = "";
    const box = document.getElementById('audio-search-box');
    if (box) box.value = "";
    renderOnlineAudioList();
}

function switchAudioTab(tab) {
    currentAudioTab = tab;

    const btnSites = document.getElementById('audio-btn-sites');
    const btnPlaylists = document.getElementById('audio-btn-playlists');

    if (btnSites) btnSites.classList.toggle('active', tab === 'sites');
    if (btnPlaylists) btnPlaylists.classList.toggle('active', tab === 'playlists');

    const viewSites = document.getElementById('audio-tab-sites-view');
    const viewPlaylists = document.getElementById('audio-tab-playlists-view');
    const viewTracks = document.getElementById('audio-tracks-browser-view');

    if (viewSites) viewSites.style.display = (tab === 'sites') ? 'flex' : 'none';
    if (viewPlaylists) viewPlaylists.style.display = (tab === 'playlists') ? 'flex' : 'none';
    if (viewTracks) viewTracks.style.display = 'none';

    if (tab === 'sites') {
        renderOnlineAudioList();
    } else {
        renderOnlinePlaylistsGrid();
    }
}

function renderOnlineAudioList() {
    try {
        const container = document.getElementById('online-audio-list');
        if (!container) return;
        container.innerHTML = '';

        const rawSites = appState.audio_sites || [];
        const sites = rawSites.map(s => {
            if (!s) return null;
            // Map tags from notes
            const tags = s.notes ? s.notes.split(',').map(t => t.trim().toLowerCase()).filter(t => t.length > 0) : [];
            return {
                id: s.id,
                name: s.name,
                url: s.domain,
                tags: tags
            };
        }).filter(s => s !== null);

        // Extract all unique tags
        const allTags = new Set();
        sites.forEach(site => {
            if (site && site.tags && Array.isArray(site.tags)) {
                site.tags.forEach(t => {
                    if (t) allTags.add(t.trim().toLowerCase());
                });
            }
        });

        // Render tag filter bar
        const filterBar = document.getElementById('audio-tags-filter-bar');
        if (filterBar) {
            filterBar.innerHTML = '';
            if (allTags.size === 0) {
                const noTags = document.createElement('span');
                noTags.style.color = '#666';
                noTags.style.fontSize = '11px';
                noTags.textContent = 'No tags available';
                filterBar.appendChild(noTags);
            } else {
                allTags.forEach(tag => {
                    const pill = document.createElement('span');
                    pill.className = 'tag-filter-pill' + (activeAudioTagFilters.has(tag) ? ' active' : '');
                    pill.textContent = tag;
                    pill.onclick = () => {
                        if (activeAudioTagFilters.has(tag)) {
                            activeAudioTagFilters.delete(tag);
                        } else {
                            activeAudioTagFilters.add(tag);
                        }
                        renderOnlineAudioList();
                    };
                    filterBar.appendChild(pill);
                });
            }
        }

        // Filter audio sites
        const filteredSites = sites.filter(site => {
            if (!site) return false;

            // Tag filter matching (must match all selected tags)
            if (activeAudioTagFilters.size > 0) {
                const siteTags = site.tags || [];
                for (const activeTag of activeAudioTagFilters) {
                    if (!siteTags.includes(activeTag)) return false;
                }
            }

            // Search text matching
            if (audioSearchQuery) {
                const nameMatch = (site.name || "").toLowerCase().includes(audioSearchQuery);
                const urlMatch = (site.url || "").toLowerCase().includes(audioSearchQuery);
                const tagMatch = (site.tags || []).some(t => t && t.toLowerCase().includes(audioSearchQuery));
                if (!nameMatch && !urlMatch && !tagMatch) return false;
            }

            return true;
        });

        if (filteredSites.length === 0) {
            container.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: #888; padding: 30px; font-size: 13px;">
                No audio sites found matching search criteria. Add custom sites in Edit -> Options.
            </div>`;
            return;
        }

        filteredSites.forEach(site => {
            const card = document.createElement('div');
            card.className = 'audio-site-card';

            // Top info section
            const topSection = document.createElement('div');
            topSection.style.display = 'flex';
            topSection.style.flexDirection = 'column';

            const title = document.createElement('div');
            title.className = 'audio-site-card-title';
            title.textContent = site.name || 'Unnamed Site';
            title.title = site.name || '';

            const url = document.createElement('div');
            url.className = 'audio-site-card-url';
            url.textContent = site.url || '';
            url.title = site.url || '';

            topSection.appendChild(title);
            topSection.appendChild(url);

            // Tags section
            const tagsWrapper = document.createElement('div');
            tagsWrapper.className = 'audio-site-card-tags';
            if (site.tags && site.tags.length > 0) {
                site.tags.forEach(t => {
                    if (t) {
                        const tagSpan = document.createElement('span');
                        tagSpan.className = 'tag-badge';
                        tagSpan.textContent = t;
                        tagsWrapper.appendChild(tagSpan);
                    }
                });
            }
            topSection.appendChild(tagsWrapper);

            card.appendChild(topSection);

            // Actions section
            const actions = document.createElement('div');
            actions.className = 'audio-site-card-actions';

            const openBtn = document.createElement('button');
            openBtn.className = 'btn-in-app';
            openBtn.innerHTML = '<i class="fa-solid fa-folder-open"></i> Browse';
            openBtn.onclick = () => {
                openTracksBrowser("site", site.name, site.url);
            };

            const extBtn = document.createElement('button');
            extBtn.className = 'btn-ext';
            extBtn.innerHTML = '<i class="fa-solid fa-globe"></i> External';
            extBtn.onclick = () => {
                pywebview.api.open_external_url(site.url);
            };

            actions.appendChild(openBtn);
            actions.appendChild(extBtn);
            card.appendChild(actions);

            container.appendChild(card);
        });
    } catch (e) {
        console.error("Error in renderOnlineAudioList:", e);
    }
}

function renderOnlinePlaylistsGrid() {
    const container = document.getElementById('online-playlists-grid');
    if (!container) return;
    container.innerHTML = '';

    const playlists = appState.online_playlists || {};
    const playlistNames = Object.keys(playlists);

    if (playlistNames.length === 0) {
        container.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: #888; padding: 30px; font-size: 13px;">
            No online playlists created yet. Click "New Playlist" in the sidebar to get started!
        </div>`;
        return;
    }

    playlistNames.forEach(name => {
        const tracks = playlists[name] || [];
        const card = document.createElement('div');
        card.className = 'audio-site-card';
        card.style.borderColor = 'rgba(203, 166, 247, 0.2)';

        const topSection = document.createElement('div');
        topSection.style.display = 'flex';
        topSection.style.flexDirection = 'column';

        const title = document.createElement('div');
        title.className = 'audio-site-card-title';
        title.style.color = '#cba6f7';
        title.textContent = name;
        title.title = name;

        const info = document.createElement('div');
        info.className = 'audio-site-card-url';
        info.innerHTML = `<i class="fa-solid fa-music"></i> ${tracks.length} track(s)`;

        topSection.appendChild(title);
        topSection.appendChild(info);
        card.appendChild(topSection);

        const actions = document.createElement('div');
        actions.className = 'audio-site-card-actions';

        const playBtn = document.createElement('button');
        playBtn.className = 'btn-in-app';
        playBtn.style.backgroundColor = '#cba6f7';
        playBtn.style.color = '#11111b';
        playBtn.innerHTML = '<i class="fa-solid fa-play"></i> Play';
        playBtn.onclick = () => {
            if (tracks.length === 0) {
                alert("Playlist is empty. Browse sites and add tracks first!");
                return;
            }
            pywebview.api.play_online_playlist(tracks, 0);
        };

        const browseBtn = document.createElement('button');
        browseBtn.className = 'btn-ext';
        browseBtn.innerHTML = '<i class="fa-solid fa-folder-open"></i> View';
        browseBtn.onclick = () => {
            openTracksBrowser("playlist", name, tracks);
        };

        const delBtn = document.createElement('button');
        delBtn.className = 'btn-ext';
        delBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        delBtn.style.flex = '0 0 auto';
        delBtn.style.width = '32px';
        delBtn.style.padding = '6px 0';
        delBtn.onclick = (e) => {
            e.stopPropagation();
            if (confirm(`Are you sure you want to delete the playlist "${name}"?`)) {
                deleteOnlinePlaylist(name);
            }
        };

        actions.appendChild(playBtn);
        actions.appendChild(browseBtn);
        actions.appendChild(delBtn);
        card.appendChild(actions);

        container.appendChild(card);
    });
}

function openCreatePlaylistPrompt() {
    const name = prompt("Enter new online playlist name:");
    if (!name) return;
    const cleanName = name.trim();
    if (!cleanName) return;

    if (!appState.online_playlists) appState.online_playlists = {};
    if (appState.online_playlists[cleanName]) {
        alert("A playlist with this name already exists.");
        return;
    }

    appState.online_playlists[cleanName] = [];
    pywebview.api.save_online_playlists(appState.online_playlists).then(state => {
        appState = state;
        if (currentAudioTab === "playlists") {
            renderOnlinePlaylistsGrid();
        }
        updatePlaylistDropdown();
    });
}

function deleteOnlinePlaylist(name) {
    if (appState.online_playlists && appState.online_playlists[name]) {
        delete appState.online_playlists[name];
        pywebview.api.save_online_playlists(appState.online_playlists).then(state => {
            appState = state;
            if (currentAudioTab === "playlists") {
                renderOnlinePlaylistsGrid();
            }
            updatePlaylistDropdown();
        });
    }
}

function updatePlaylistDropdown() {
    const select = document.getElementById('playlist-add-target');
    if (!select) return;
    select.innerHTML = '<option value="">Add to Playlist...</option>';

    const playlists = appState.online_playlists || {};
    for (const name of Object.keys(playlists)) {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
    }
}

function openTracksBrowser(type, name, data) {
    browserSourceType = type;
    browserSourceName = name;
    tracksSearchQuery = "";
    tracksLoadedCount = 200;

    const searchBox = document.getElementById('tracks-search-box');
    if (searchBox) searchBox.value = "";

    document.getElementById('audio-tab-sites-view').style.display = 'none';
    document.getElementById('audio-tab-playlists-view').style.display = 'none';
    document.getElementById('audio-tracks-browser-view').style.display = 'flex';

    document.getElementById('tracks-browser-title').textContent = name;
    const subtitle = document.getElementById('tracks-browser-subtitle');

    const headerActions = document.getElementById('tracks-browser-header-actions');
    if (headerActions) {
        headerActions.style.display = 'flex';
        const dropdown = document.getElementById('playlist-add-target');
        const btnAddAll = document.getElementById('btn-add-all-tracks');
        if (dropdown) dropdown.style.display = (type === 'site') ? 'block' : 'none';
        if (btnAddAll) btnAddAll.style.display = (type === 'site') ? 'block' : 'none';
    }

    updatePlaylistDropdown();

    if (type === 'site') {
        subtitle.textContent = `Scraping audio tracks from: ${data}`;
        const container = document.getElementById('audio-tracks-list');
        if (container) container.innerHTML = '<div style="text-align: center; color: #888; padding: 30px;"><i class="fa-solid fa-spinner fa-spin"></i> Scraping audio links... Please wait.</div>';

        pywebview.api.scrape_audio_links(data).then(res => {
            if (res.status === 'success') {
                currentTracksList = res.tracks || [];
                subtitle.textContent = `Found ${currentTracksList.length} streamable track(s) on: ${data}`;
                applyTracksFilter();
                renderTracksList();
            } else {
                if (container) container.innerHTML = `<div style="text-align: center; color: #f38ba8; padding: 30px;"><i class="fa-solid fa-circle-exclamation"></i> Error: ${res.msg}</div>`;
                subtitle.textContent = `Scrape failed.`;
            }
        });
    } else {
        currentTracksList = data || [];
        subtitle.textContent = `Online Playlist - ${currentTracksList.length} track(s)`;
        applyTracksFilter();
        renderTracksList();
    }
}

function onTracksSearchChanged() {
    const box = document.getElementById('tracks-search-box');
    if (box) {
        tracksSearchQuery = box.value.trim().toLowerCase();
        tracksLoadedCount = 200;
        applyTracksFilter();
        renderTracksList();
    }
}

function applyTracksFilter() {
    if (!tracksSearchQuery) {
        filteredTracksList = [...currentTracksList];
    } else {
        filteredTracksList = currentTracksList.filter(t => t.name.toLowerCase().includes(tracksSearchQuery));
    }
}

function exitTracksBrowser() {
    document.getElementById('audio-tracks-browser-view').style.display = 'none';
    if (currentAudioTab === 'sites') {
        document.getElementById('audio-tab-sites-view').style.display = 'flex';
        renderOnlineAudioList();
    } else {
        document.getElementById('audio-tab-playlists-view').style.display = 'flex';
        renderOnlinePlaylistsGrid();
    }
}

function renderTracksList() {
    const container = document.getElementById('audio-tracks-list');
    if (!container) return;
    container.innerHTML = '';

    if (filteredTracksList.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: #666; padding: 30px; font-size: 13px;">
            No tracks found matching your filter criteria.
        </div>`;
        return;
    }

    const tracksToShow = filteredTracksList.slice(0, tracksLoadedCount);

    tracksToShow.forEach((track, index) => {
        const row = document.createElement('div');
        row.className = 'audio-track-row';

        const info = document.createElement('div');
        info.className = 'audio-track-info';

        const num = document.createElement('span');
        num.className = 'audio-track-num';
        num.textContent = (index + 1).toString().padStart(2, '0');

        const name = document.createElement('span');
        name.className = 'audio-track-name';
        name.textContent = track.name;
        name.title = track.name;

        info.appendChild(num);
        info.appendChild(name);
        row.appendChild(info);

        const actions = document.createElement('div');
        actions.className = 'audio-track-actions';

        const playBtn = document.createElement('button');
        playBtn.className = 'btn-play-track';
        playBtn.title = "Play this track directly in pop-up player";
        playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
        playBtn.onclick = () => {
            playModalTrack(filteredTracksList, index);
        };
        actions.appendChild(playBtn);

        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'btn-download-track';
        downloadBtn.title = "Download this track to active folder";
        downloadBtn.innerHTML = '<i class="fa-solid fa-download"></i>';
        downloadBtn.onclick = () => {
            downloadBtn.disabled = true;
            downloadBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
            pywebview.api.download_online_track(track.url, track.name).then(res => {
                if (res.status === 'started') {
                    // download started
                } else {
                    alert(res.msg);
                    downloadBtn.disabled = false;
                    downloadBtn.innerHTML = '<i class="fa-solid fa-download"></i>';
                }
            });
        };
        actions.appendChild(downloadBtn);

        if (browserSourceType === "site") {
            const addBtn = document.createElement('button');
            addBtn.innerHTML = '<i class="fa-solid fa-plus"></i>';
            addBtn.title = "Add to selected playlist";
            addBtn.onclick = () => {
                const select = document.getElementById('playlist-add-target');
                const playlistName = select ? select.value : '';
                addTrackToPlaylist(track, playlistName);
            };
            actions.appendChild(addBtn);
        } else {
            const delBtn = document.createElement('button');
            delBtn.className = 'btn-delete-track';
            delBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
            delBtn.title = "Remove from this playlist";
            delBtn.onclick = () => {
                const originalIndex = currentTracksList.indexOf(track);
                if (originalIndex !== -1) {
                    deleteTrackFromPlaylist(originalIndex);
                }
            };
            actions.appendChild(delBtn);
        }

        row.appendChild(actions);
        container.appendChild(row);
    });

    if (filteredTracksList.length > tracksLoadedCount) {
        const remaining = filteredTracksList.length - tracksLoadedCount;
        const loadMoreRow = document.createElement('div');
        loadMoreRow.style.padding = '10px';
        loadMoreRow.style.textAlign = 'center';

        const loadMoreBtn = document.createElement('button');
        loadMoreBtn.className = 'btn-ext';
        loadMoreBtn.style.padding = '6px 15px';
        loadMoreBtn.style.fontSize = '12px';
        loadMoreBtn.innerHTML = `<i class="fa-solid fa-chevron-down"></i> Load More (${remaining} remaining)`;
        loadMoreBtn.onclick = () => {
            tracksLoadedCount += 200;
            renderTracksList();
        };

        loadMoreRow.appendChild(loadMoreBtn);
        container.appendChild(loadMoreRow);
    }
}

function addTrackToPlaylist(track, playlistName) {
    if (!playlistName) {
        alert("Please select a playlist first.");
        return;
    }
    if (!appState.online_playlists) appState.online_playlists = {};
    if (!appState.online_playlists[playlistName]) appState.online_playlists[playlistName] = [];

    const list = appState.online_playlists[playlistName];
    if (list.some(t => t.url === track.url)) {
        alert("This track is already in the playlist.");
        return;
    }

    list.push(track);
    pywebview.api.save_online_playlists(appState.online_playlists).then(state => {
        appState = state;
        alert(`Added "${track.name}" to playlist "${playlistName}"`);
    });
}

function addAllTracksToSelectedPlaylist() {
    const select = document.getElementById('playlist-add-target');
    if (!select || !select.value) {
        alert("Please select a target playlist first.");
        return;
    }
    const playlistName = select.value;
    if (!appState.online_playlists) appState.online_playlists = {};
    if (!appState.online_playlists[playlistName]) appState.online_playlists[playlistName] = [];

    const list = appState.online_playlists[playlistName];
    let addedCount = 0;

    filteredTracksList.forEach(track => {
        if (!list.some(t => t.url === track.url)) {
            list.push(track);
            addedCount++;
        }
    });

    if (addedCount === 0) {
        alert("All filtered tracks are already in this playlist.");
        return;
    }

    pywebview.api.save_online_playlists(appState.online_playlists).then(state => {
        appState = state;
        alert(`Successfully added ${addedCount} track(s) to "${playlistName}".`);
    });
}

function deleteTrackFromPlaylist(index) {
    if (browserSourceType !== "playlist") return;
    const playlistName = browserSourceName;

    if (appState.online_playlists && appState.online_playlists[playlistName]) {
        appState.online_playlists[playlistName].splice(index, 1);
        pywebview.api.save_online_playlists(appState.online_playlists).then(state => {
            appState = state;
            currentTracksList = appState.online_playlists[playlistName] || [];
            applyTracksFilter();
            renderTracksList();
        });
    }
}

function playCurrentTracksBrowserList() {
    if (filteredTracksList.length === 0) {
        alert("No tracks to play.");
        return;
    }
    playModalTrack(filteredTracksList, 0);
}

let modalCurrentIndex = -1;
let modalCurrentTracks = [];

function playModalTrack(tracks, index) {
    modalCurrentTracks = tracks;
    modalCurrentIndex = index;

    const audio = document.getElementById('modal-audio-element');
    const container = document.getElementById('modal-audio-player-container');
    const trackName = document.getElementById('modal-player-track-name');
    const playBtn = document.getElementById('modal-player-play-btn');

    if (!audio || !container || !trackName || !playBtn) return;

    const track = tracks[index];
    if (!track) return;

    if (videoPlayer && !videoPlayer.paused) {
        togglePlay();
    }

    trackName.textContent = track.name;
    audio.src = track.url;
    audio.play();

    container.style.display = 'flex';
    playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
}

function toggleModalPlay() {
    const audio = document.getElementById('modal-audio-element');
    const playBtn = document.getElementById('modal-player-play-btn');
    if (!audio || !playBtn) return;

    if (audio.paused) {
        audio.play();
        playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        if (videoPlayer && !videoPlayer.paused) {
            togglePlay();
        }
    } else {
        audio.pause();
        playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
    }
}

function playNextModalTrack() {
    if (modalCurrentTracks.length === 0 || modalCurrentIndex === -1) return;
    let nextIndex = modalCurrentIndex + 1;
    if (nextIndex < modalCurrentTracks.length) {
        playModalTrack(modalCurrentTracks, nextIndex);
    } else {
        modalCurrentIndex = -1;
        const audio = document.getElementById('modal-audio-element');
        const playBtn = document.getElementById('modal-player-play-btn');
        if (audio) audio.pause();
        if (playBtn) playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
    }
}

function playPrevModalTrack() {
    if (modalCurrentTracks.length === 0 || modalCurrentIndex === -1) return;
    let prevIndex = modalCurrentIndex - 1;
    if (prevIndex >= 0) {
        playModalTrack(modalCurrentTracks, prevIndex);
    }
}

function downloadCompleteNotify(name) {
    updateState();
    updatePlaylist();
    renderTracksList();

    const directBtn = document.getElementById('audio-direct-dl-btn');
    if (directBtn && directBtn.dataset.activeTitle === name) {
        directBtn.innerHTML = '<i class="fa-solid fa-download"></i> Browse';
        directBtn.disabled = false;
        directBtn.style.background = '#4CAF50';
        delete directBtn.dataset.activeTitle;
    }

    updateGlobalDownloadUI(name, "", 100, true, false);
}

function downloadFailedNotify(name, msg) {
    renderTracksList();

    const directBtn = document.getElementById('audio-direct-dl-btn');
    if (directBtn && directBtn.dataset.activeTitle === name) {
        directBtn.innerHTML = '<i class="fa-solid fa-download"></i> Browse';
        directBtn.disabled = false;
        directBtn.style.background = '#4CAF50';
        delete directBtn.dataset.activeTitle;
    }

    updateGlobalDownloadUI(name, msg, 0, false, true);
}

function updateAudioDownloadProgress(current, total, title) {
    const rows = document.querySelectorAll('.audio-track-row');
    for (const row of rows) {
        const nameEl = row.querySelector('.audio-track-name');
        if (nameEl && nameEl.textContent === title) {
            const btn = row.querySelector('.btn-download-track');
            if (btn) {
                if (total > 0) {
                    const percent = Math.round((current / total) * 100);
                    btn.innerHTML = `<span style="font-size: 11px; font-weight: bold;">${percent}%</span>`;
                    btn.style.background = `linear-gradient(90deg, #4CAF50 ${percent}%, #444 ${percent}%)`;
                    btn.style.color = '#fff';
                    btn.style.minWidth = '45px';
                } else {
                    const mb = (current / 1048576).toFixed(1);
                    btn.innerHTML = `<span style="font-size: 11px; font-weight: bold;">${mb}MB</span>`;
                }
            }
            break;
        }
    }

    const directBtn = document.getElementById('audio-direct-dl-btn');
    if (directBtn && directBtn.dataset.activeTitle === title) {
        if (total > 0) {
            const percent = Math.round((current / total) * 100);
            directBtn.innerHTML = `<span style="font-size: 11px; font-weight: bold;">${percent}%</span>`;
            directBtn.style.background = `linear-gradient(90deg, #4CAF50 ${percent}%, #444 ${percent}%)`;
        } else {
            const mb = (current / 1048576).toFixed(1);
            directBtn.innerHTML = `<span style="font-size: 11px; font-weight: bold;">${mb}MB</span>`;
        }
    }

    let percent = total > 0 ? Math.round((current / total) * 100) : 0;
    let progressText = total > 0
        ? `${(current / 1048576).toFixed(2)} MB / ${(total / 1048576).toFixed(2)} MB`
        : `${(current / 1048576).toFixed(2)} MB`;
    updateGlobalDownloadUI(title, progressText, percent);
}

// Bind modal player audio events
(function initModalAudioEvents() {
    const modalAudio = document.getElementById('modal-audio-element');
    const modalProgressSlider = document.getElementById('modal-player-progress-slider');
    const modalCurrentTimeDisplay = document.getElementById('modal-player-current-time');
    const modalTotalTimeDisplay = document.getElementById('modal-player-total-time');

    if (modalAudio) {
        modalAudio.addEventListener('timeupdate', () => {
            if (modalAudio.duration) {
                modalProgressSlider.value = (modalAudio.currentTime / modalAudio.duration) * 100;
                modalCurrentTimeDisplay.textContent = formatTime(modalAudio.currentTime);
            }
        });

        modalAudio.addEventListener('loadedmetadata', () => {
            modalTotalTimeDisplay.textContent = formatTime(modalAudio.duration);
            modalProgressSlider.value = 0;
            modalCurrentTimeDisplay.textContent = "0:00";
        });

        modalAudio.addEventListener('ended', () => {
            playNextModalTrack();
        });
    }

    if (modalProgressSlider) {
        modalProgressSlider.addEventListener('input', () => {
            if (modalAudio && modalAudio.duration) {
                modalAudio.currentTime = (modalProgressSlider.value / 100) * modalAudio.duration;
            }
        });
    }
})();


// --- Split Screen Logic Functions ---
function toggleSplitScreen() {
    splitScreenActive = !splitScreenActive;
    const container = document.getElementById('media-container');
    const toggleBtn = document.getElementById('split-screen-toggle-btn');
    const tabs = document.getElementById('split-tabs-container');
    const leftHeader = document.getElementById('left-pane-header');
    const rightHeader = document.getElementById('right-pane-header');
    
    if (splitScreenActive) {
        container.classList.add('split-active');
        toggleBtn.innerHTML = '<i class="fa-solid fa-columns"></i> Single View';
        tabs.style.display = 'flex';
        leftHeader.style.display = 'flex';
        rightHeader.style.display = 'flex';
        document.getElementById('split-resizer').style.display = 'block';
        
        // Populate left playlist from current playlist, filtering to videos
        const videoExts = ['mp4', 'webm', 'ogg', 'mp3', 'wav', 'wave'];
        leftPlaylist = playlist.filter(f => {
            const ext = f.path.split('.').pop().toLowerCase();
            return videoExts.includes(ext);
        });
        
        if (playlist[currentIndex]) {
            const currentPath = playlist[currentIndex].path;
            const leftIdx = leftPlaylist.findIndex(f => f.path === currentPath);
            if (leftIdx !== -1) {
                leftCurrentIndex = leftIdx;
            } else {
                leftCurrentIndex = leftPlaylist.length > 0 ? 0 : -1;
            }
        } else {
            leftCurrentIndex = leftPlaylist.length > 0 ? 0 : -1;
        }
        
        if (leftPlaylist.length === 0) {
            leftPlaylist = playlist.slice();
            leftCurrentIndex = currentIndex;
        }
        
        if (leftPlaylist[leftCurrentIndex]) {
            document.getElementById('left-pane-file-name').textContent = leftPlaylist[leftCurrentIndex].name;
            loadLeftMedia(leftPlaylist[leftCurrentIndex].path);
        } else {
            document.getElementById('left-pane-file-name').textContent = "No folder loaded";
        }
        
        // Right playlist defaults to images from current playlist (if any)
        const imageExts = ['jpg', 'jpeg', 'png', 'webp', 'gif'];
        rightPlaylist = playlist.filter(f => {
            const ext = f.path.split('.').pop().toLowerCase();
            return imageExts.includes(ext);
        });
        
        if (playlist[currentIndex]) {
            const currentPath = playlist[currentIndex].path;
            const rightIdx = rightPlaylist.findIndex(f => f.path === currentPath);
            if (rightIdx !== -1) {
                rightCurrentIndex = rightIdx;
            } else {
                rightCurrentIndex = rightPlaylist.length > 0 ? 0 : -1;
            }
        } else {
            rightCurrentIndex = rightPlaylist.length > 0 ? 0 : -1;
        }
        
        if (rightPlaylist[rightCurrentIndex]) {
            document.getElementById('right-pane-file-name').textContent = rightPlaylist[rightCurrentIndex].name;
            loadRightMedia(rightPlaylist[rightCurrentIndex].path);
        } else {
            document.getElementById('right-pane-file-name').textContent = "No folder loaded";
        }
        
        activeSidebarTab = 'left';
        document.getElementById('tab-btn-left').style.background = '#313244';
        document.getElementById('tab-btn-left').style.color = '#cdd6f4';
        document.getElementById('tab-btn-right').style.background = '#181825';
        document.getElementById('tab-btn-right').style.color = '#a0a0b0';
        
    } else {
        container.classList.remove('split-active');
        toggleBtn.innerHTML = '<i class="fa-solid fa-columns"></i> Split View';
        tabs.style.display = 'none';
        leftHeader.style.display = 'none';
        rightHeader.style.display = 'none';
        document.getElementById('split-resizer').style.display = 'none';
        document.getElementById('left-split-pane').style.removeProperty('width');
        document.getElementById('right-split-pane').style.removeProperty('width');
        
        // Restore single screen display styles on panes
        document.getElementById('left-split-pane').style.display = '';
        document.getElementById('right-split-pane').style.display = '';
        
        if (leftPlaylist[leftCurrentIndex]) {
            const mainIdx = playlist.findIndex(f => f.path === leftPlaylist[leftCurrentIndex].path);
            if (mainIdx !== -1) {
                currentIndex = mainIdx;
            }
            loadMedia(leftPlaylist[leftCurrentIndex].path, currentIndex);
        } else if (rightPlaylist[rightCurrentIndex]) {
            const mainIdx = playlist.findIndex(f => f.path === rightPlaylist[rightCurrentIndex].path);
            if (mainIdx !== -1) {
                currentIndex = mainIdx;
            }
            loadMedia(rightPlaylist[rightCurrentIndex].path, currentIndex);
        }
    }
    renderPlaylist();
}

function switchSidebarTab(tab) {
    if (!splitScreenActive) return;
    activeSidebarTab = tab;
    
    const leftTabBtn = document.getElementById('tab-btn-left');
    const rightTabBtn = document.getElementById('tab-btn-right');
    
    if (tab === 'left') {
        leftTabBtn.classList.add('active');
        rightTabBtn.classList.remove('active');
        leftTabBtn.style.background = '#313244';
        leftTabBtn.style.color = '#cdd6f4';
        rightTabBtn.style.background = '#181825';
        rightTabBtn.style.color = '#a0a0b0';
    } else {
        rightTabBtn.classList.add('active');
        leftTabBtn.classList.remove('active');
        rightTabBtn.style.background = '#313244';
        rightTabBtn.style.color = '#cdd6f4';
        leftTabBtn.style.background = '#181825';
        leftTabBtn.style.color = '#a0a0b0';
    }
    
    renderPlaylist();
}

function browsePaneFolder(side) {
    pywebview.api.browse_folder().then(dirPath => {
        if (!dirPath) return;
        
        pywebview.api.get_directory_files(dirPath).then(files => {
            if (!files || files.length === 0) {
                alert("No media files found in " + dirPath);
                return;
            }
            
            if (side === 'left') {
                const videoExts = ['mp4', 'webm', 'ogg', 'mp3', 'wav', 'wave'];
                leftPlaylist = files.filter(f => {
                    const ext = f.name.split('.').pop().toLowerCase();
                    return videoExts.includes(ext);
                });
                
                if (leftPlaylist.length === 0) {
                    alert("No video/audio files found in " + dirPath);
                    document.getElementById('left-pane-file-name').textContent = "No videos found";
                    return;
                }
                
                leftCurrentIndex = 0;
                loadLeftMedia(leftPlaylist[0].path);
                
                activeSidebarTab = 'left';
                document.getElementById('tab-btn-left').classList.add('active');
                document.getElementById('tab-btn-right').classList.remove('active');
                document.getElementById('tab-btn-left').style.background = '#313244';
                document.getElementById('tab-btn-left').style.color = '#cdd6f4';
                document.getElementById('tab-btn-right').style.background = '#181825';
                document.getElementById('tab-btn-right').style.color = '#a0a0b0';
                
                renderPlaylist();
            } else if (side === 'right') {
                const imageExts = ['jpg', 'jpeg', 'png', 'webp', 'gif'];
                rightPlaylist = files.filter(f => {
                    const ext = f.name.split('.').pop().toLowerCase();
                    return imageExts.includes(ext);
                });
                
                if (rightPlaylist.length === 0) {
                    alert("No image files found in " + dirPath);
                    document.getElementById('right-pane-file-name').textContent = "No images found";
                    return;
                }
                
                rightCurrentIndex = 0;
                loadRightMedia(rightPlaylist[0].path);
                
                activeSidebarTab = 'right';
                document.getElementById('tab-btn-right').classList.add('active');
                document.getElementById('tab-btn-left').classList.remove('active');
                document.getElementById('tab-btn-right').style.background = '#313244';
                document.getElementById('tab-btn-right').style.color = '#cdd6f4';
                document.getElementById('tab-btn-left').style.background = '#181825';
                document.getElementById('tab-btn-left').style.color = '#a0a0b0';
                
                renderPlaylist();
            }
        });
    });
}

function loadLeftMedia(path) {
    const isOnline = path.startsWith('http://') || path.startsWith('https://');
    const mediaUrl = isOnline ? path : `http://localhost:5050/media?path=${encodeURIComponent(path)}`;
    
    videoPlayer.src = mediaUrl;
    videoPlayer.style.display = 'block';
    videoPlayer.play();
    playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
    
    const parts = path.split(/[/\\]/);
    const fileName = parts.pop();
    const folderName = parts.pop() || "";
    const fullDisplayName = folderName ? (folderName + " / " + fileName) : fileName;
    document.getElementById('left-pane-file-name').textContent = fullDisplayName;
    
    const idx = leftPlaylist.findIndex(item => item.path === path);
    if (idx !== -1) {
        leftCurrentIndex = idx;
    }
}

function loadRightMedia(path) {
    const isOnline = path.startsWith('http://') || path.startsWith('https://');
    const mediaUrl = isOnline ? path : `http://localhost:5050/media?path=${encodeURIComponent(path)}`;
    
    imageViewer.src = mediaUrl;
    imageViewer.style.display = 'block';
    
    const parts = path.split(/[/\\]/);
    const fileName = parts.pop();
    const folderName = parts.pop() || "";
    const fullDisplayName = folderName ? (folderName + " / " + fileName) : fileName;
    document.getElementById('right-pane-file-name').textContent = fullDisplayName;
    
    pywebview.api.get_collection_info(path).then(info => {
        collectionTranslations = info || {};
        renderTranslations(path);
    });
    
    const idx = rightPlaylist.findIndex(item => item.path === path);
    if (idx !== -1) {
        rightCurrentIndex = idx;
    }
    
    updateImageTimer();
}

function navigateLeftPane(direction) {
    if (!splitScreenActive || leftPlaylist.length === 0) return;
    
    let newIdx = leftCurrentIndex + direction;
    if (newIdx < 0) {
        newIdx = leftPlaylist.length - 1;
    } else if (newIdx >= leftPlaylist.length) {
        newIdx = 0;
    }
    
    leftCurrentIndex = newIdx;
    loadLeftMedia(leftPlaylist[leftCurrentIndex].path);
    if (activeSidebarTab === 'left') {
        renderPlaylist();
    }
}

function navigatePaneImage(direction) {
    if (!splitScreenActive || rightPlaylist.length === 0) return;
    
    let newIdx = rightCurrentIndex + direction;
    if (newIdx < 0) {
        newIdx = rightPlaylist.length - 1;
    } else if (newIdx >= rightPlaylist.length) {
        newIdx = 0;
    }
    
    rightCurrentIndex = newIdx;
    loadRightMedia(rightPlaylist[rightCurrentIndex].path);
    if (activeSidebarTab === 'right') {
        renderPlaylist();
    }
}

function toggleRecursiveLoad(enabled) {
    pywebview.api.save_recursive_load(enabled).then(state => {
        appState = state;
        renderState();
    });
}

function loadFolderAction() {
    pywebview.api.browse_folder().then(path => {
        if (path) {
            pywebview.api.load_selected_directory(path);
        }
    });
}

// --- Folder Tree-view & Navigation Helpers ---
let showFoldersActive = false;
let currentSubdirs = [];
let currentCbzFiles = [];
let currentTreeRoot = '';
let activeCbzRoot = '';
const openFolders = new Set();

function toggleShowFolders(enabled) {
    showFoldersActive = enabled;
    updatePlaylist();
}

function autoExpandActiveFolder(activePath) {
    if (!activePath) return;
    const isWindows = activePath.includes('\\');
    const separator = isWindows ? '\\' : '/';
    const parts = activePath.split(/[/\\]/);
    
    for (let i = 1; i < parts.length - 1; i++) {
        const parentParts = parts.slice(0, i + 1);
        let parentPath = parentParts.join(separator);
        if (isWindows && parentParts[0].endsWith(':') && parentParts.length > 1) {
            parentPath = parentParts[0] + separator + parentParts.slice(1).join(separator);
        }
        openFolders.add(parentPath);
    }
}

function getCommonRootPath(flatPlaylist) {
    if (!flatPlaylist || flatPlaylist.length === 0) return '';
    const paths = flatPlaylist.map(item => item.path.replace(/\\/g, '/'));
    const firstParts = paths[0].split('/');
    let commonPrefixLength = 0;
    
    while (commonPrefixLength < firstParts.length - 1) {
        const part = firstParts[commonPrefixLength];
        const allMatch = paths.every(p => p.split('/')[commonPrefixLength] === part);
        if (allMatch) {
            commonPrefixLength++;
        } else {
            break;
        }
    }
    
    const rootParts = firstParts.slice(0, commonPrefixLength);
    const isWindows = flatPlaylist[0].path.includes('\\');
    const separator = isWindows ? '\\' : '/';
    let rootPath = rootParts.join(separator);
    if (isWindows && rootParts[0].endsWith(':') && rootParts.length > 1) {
        rootPath = rootParts[0] + separator + rootParts.slice(1).join(separator);
    }
    return rootPath;
}

function getParentDirectory(path) {
    if (!path) return null;
    const isWindows = path.includes('\\');
    const separator = isWindows ? '\\' : '/';
    const normPath = path.replace(/\\/g, '/');
    const parts = normPath.split('/');
    if (parts.length <= 1) return null;
    
    parts.pop();
    let parent = parts.join(separator);
    if (isWindows && parent.endsWith(':')) {
        parent += '\\';
    }
    return parent;
}

function buildFolderOnlyTree(flatPlaylist, subdirs, cbzFiles, rootPath) {
    const tree = { name: 'Root', type: 'directory', children: [], path: '' };
    if ((!flatPlaylist || flatPlaylist.length === 0) && (!subdirs || subdirs.length === 0) && (!cbzFiles || cbzFiles.length === 0)) return tree;
    
    let commonRoot = rootPath || '';
    if (!commonRoot && flatPlaylist && flatPlaylist.length > 0) {
        commonRoot = getCommonRootPath(flatPlaylist);
    } else if (!commonRoot && subdirs && subdirs.length > 0) {
        const paths = subdirs.map(p => p.replace(/\\/g, '/'));
        const parts = paths[0].split('/');
        parts.pop();
        commonRoot = parts.join('/');
    } else if (!commonRoot && cbzFiles && cbzFiles.length > 0) {
        commonRoot = getParentDirectory(cbzFiles[0]) || '';
    }
    
    tree.path = commonRoot;
    
    const commonNorm = commonRoot.replace(/\\/g, '/');
    const commonParts = commonNorm ? commonNorm.split('/') : [];
    const commonPrefixLength = commonParts.length;
    
    function ensureDirectoryPath(dirPath) {
        const parts = dirPath.replace(/\\/g, '/').split('/');
        const relParts = parts.slice(commonPrefixLength);
        let currentNode = tree;
        relParts.forEach((part, i) => {
            let dirNode = currentNode.children.find(c => c.type === 'directory' && c.name === part);
            if (!dirNode) {
                const dirParts = parts.slice(0, commonPrefixLength + i + 1);
                const isWindows = dirPath.includes('\\');
                const separator = isWindows ? '\\' : '/';
                let currentDirPath = dirParts.join(separator);
                if (isWindows && dirParts[0].endsWith(':') && dirParts.length > 1) {
                    currentDirPath = dirParts[0] + separator + dirParts.slice(1).join(separator);
                }
                
                dirNode = {
                    name: part,
                    type: 'directory',
                    path: currentDirPath,
                    children: [],
                    open: openFolders.has(currentDirPath)
                };
                currentNode.children.push(dirNode);
            }
            currentNode = dirNode;
        });
        return currentNode;
    }

    function addDirectoryToTree(dirPath) {
        ensureDirectoryPath(dirPath);
    }
    
    if (subdirs) {
        subdirs.forEach(addDirectoryToTree);
    }
    
    if (flatPlaylist) {
        flatPlaylist.forEach(item => {
            ensureDirectoryPath(getParentDirectory(item.path) || '');
        });
    }

    (cbzFiles || []).forEach(archivePath => {
        const parent = getParentDirectory(archivePath) || '';
        const parentNode = ensureDirectoryPath(parent);
        if (!parentNode.children.some(child => child.type === 'archive' && child.path === archivePath)) {
            parentNode.children.push({
                name: archivePath.split(/[/\\]/).pop(),
                type: 'archive',
                path: archivePath,
                children: []
            });
        }
    });
    
    return tree;
}

function renderFolderTree(listToRender, currentSubdirs) {
    const container = document.getElementById('folder-tree');
    if (!container) return;
    container.innerHTML = '';
    
    const commonRoot = currentTreeRoot || getCommonRootPath(listToRender);
    const parentDir = getParentDirectory(commonRoot);
    
    const headerDiv = document.createElement('div');
    headerDiv.style.display = 'flex';
    headerDiv.style.justifyContent = 'space-between';
    headerDiv.style.alignItems = 'center';
    headerDiv.style.marginBottom = '6px';
    headerDiv.style.fontSize = '12px';
    headerDiv.style.fontWeight = 'bold';
    headerDiv.style.color = '#cdd6f4';
    headerDiv.innerHTML = `<span>Folders</span>`;
    
    const isCbzRoot = activeCbzRoot && commonRoot.replace(/\\/g, '/') === activeCbzRoot.replace(/\\/g, '/');
    if (isCbzRoot) {
        const closeArchiveBtn = document.createElement('button');
        closeArchiveBtn.className = 'go-up-btn';
        closeArchiveBtn.style.background = 'none';
        closeArchiveBtn.style.border = 'none';
        closeArchiveBtn.style.color = '#a6e3a1';
        closeArchiveBtn.style.cursor = 'pointer';
        closeArchiveBtn.style.fontSize = '11px';
        closeArchiveBtn.style.padding = '2px 5px';
        closeArchiveBtn.textContent = 'Close CBZ';
        closeArchiveBtn.onclick = () => {
            pywebview.api.close_cbz_archive().then(result => {
                if (result && result.status === 'error') alert(result.msg);
            });
        };
        headerDiv.appendChild(closeArchiveBtn);
    } else if (parentDir) {
        const goUpBtn = document.createElement('button');
        goUpBtn.className = 'go-up-btn';
        goUpBtn.style.background = 'none';
        goUpBtn.style.border = 'none';
        goUpBtn.style.color = '#a6e3a1';
        goUpBtn.style.cursor = 'pointer';
        goUpBtn.style.fontSize = '11px';
        goUpBtn.style.padding = '2px 5px';
        goUpBtn.innerHTML = `<i class="fa-solid fa-level-up-alt" style="transform: rotate(-90deg); margin-right: 4px;"></i>Up`;
        goUpBtn.onclick = () => {
            pywebview.api.load_selected_directory(parentDir);
        };
        headerDiv.appendChild(goUpBtn);
    }
    container.appendChild(headerDiv);
    
    const tree = buildFolderOnlyTree(listToRender, currentSubdirs, currentCbzFiles, commonRoot);
    
    function renderFolderNode(node, depth) {
        if (node.name === 'Root') {
            node.children.forEach(child => renderFolderNode(child, depth));
            return;
        }
        
        const div = document.createElement('div');
        div.className = 'tree-folder-item';
        div.style.paddingLeft = (10 + depth * 12) + 'px';
        
        const toggleIcon = document.createElement('span');
        toggleIcon.style.marginRight = '6px';
        toggleIcon.style.display = 'inline-block';
        toggleIcon.style.width = '12px';
        toggleIcon.style.textAlign = 'center';
        toggleIcon.style.cursor = node.type === 'archive' ? 'default' : 'pointer';
        toggleIcon.innerHTML = node.type === 'archive' ? '<i class="fa-solid fa-arrow-turn-down" style="font-size: 8px;"></i>' : (node.open ? '<i class="fa-solid fa-chevron-down" style="font-size: 8px;"></i>' : '<i class="fa-solid fa-chevron-right" style="font-size: 8px;"></i>');
        toggleIcon.onclick = (e) => {
            e.stopPropagation();
            if (node.type === 'archive') return;
            if (openFolders.has(node.path)) {
                openFolders.delete(node.path);
            } else {
                openFolders.add(node.path);
            }
            renderPlaylist();
        };
        
        const folderIcon = document.createElement('span');
        folderIcon.innerHTML = node.type === 'archive'
            ? '<i class="fa-solid fa-folder-open" style="color: #f9e2af; margin-right: 6px;"></i>'
            : '<i class="fa-solid fa-folder" style="color: #f9e2af; margin-right: 6px;"></i>';
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'playlist-name';
        nameSpan.style.whiteSpace = 'nowrap';
        nameSpan.style.overflow = 'hidden';
        nameSpan.style.textOverflow = 'ellipsis';
        nameSpan.textContent = node.name;
        
        div.appendChild(toggleIcon);
        div.appendChild(folderIcon);
        div.appendChild(nameSpan);
        
        div.onclick = (e) => {
            if (e.detail > 1) return;
            const openFolder = node.type === 'archive'
                ? pywebview.api.open_cbz_archive(node.path)
                : pywebview.api.load_selected_directory(node.path);
            openFolder.then(result => {
                if (result && result.status === 'error') {
                    alert(result.msg);
                    return;
                }
                updatePlaylist();
            }).catch(error => alert(`Could not open folder: ${error}`));
        };
        
        div.ondblclick = (e) => {
            e.stopPropagation();
        };
        
        container.appendChild(div);
        
        if (node.open && node.children) {
            const sortedChildren = [...node.children].sort((a, b) => {
                return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
            });
            sortedChildren.forEach(child => renderFolderNode(child, depth + 1));
        }
    }
    
    tree.children.sort((a, b) => {
        return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    });
    tree.children.forEach(child => renderFolderNode(child, 0));
}


const onlineSourcesModal = document.getElementById('online-sources-modal');

function openOnlineSourcesModal() {
    tempCollectionSites = [...(appState.collection_sites || [])];
    tempAudioSites = [...(appState.audio_sites || [])];
    tempStorySites = [...(appState.story_sites || [])];

    onlineSourcesModal.style.display = 'block';
    renderCollectionSitesEditorList();
    renderAudioSitesEditorList();
    renderStorySitesEditorList();
}

function closeOnlineSourcesModal() {
    onlineSourcesModal.style.display = 'none';
}

function renderGridEditorList(containerId, list, addCallback) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    if (list.length === 0) {
        container.innerHTML = '<div style="color:#888;font-size:11px;padding:5px;">No sites defined.</div>';
        return;
    }

    // Header row
    const header = document.createElement('div');
    header.style.cssText = 'display:grid;grid-template-columns:1fr 150px 1fr 28px;gap:5px;padding:3px 6px;background:#1e1e2e;border-radius:3px;margin-bottom:3px;font-size:10px;font-weight:bold;color:#888;';
    header.innerHTML = '<span>Display Name</span><span>Domain / URL</span><span>Notes</span><span></span>';
    container.appendChild(header);

    list.forEach((site, index) => {
        const div = document.createElement('div');
        div.style.cssText = 'display:grid;grid-template-columns:1fr 150px 1fr 28px;gap:5px;align-items:center;padding:4px 6px;border-bottom:1px solid #2a2a3e;font-size:11px;';

        const makeInput = (val, placeholder, onchange) => {
            const inp = document.createElement('input');
            inp.type = 'text';
            inp.value = val || '';
            inp.placeholder = placeholder;
            inp.style.cssText = 'width:100%;min-width:0;font-size:11px;background:#1a1a2e;border:1px solid #444;color:#cdd6f4;border-radius:3px;padding:2px 5px;box-sizing:border-box;';
            inp.oninput = onchange;
            return inp;
        };

        const nameInp = makeInput(site.name,   'Display name',  () => { list[index].name = nameInp.value; });
        const domInp  = makeInput(site.domain, 'Domain or URL', () => { list[index].domain = domInp.value; });
        const noteInp = makeInput(site.notes,  'Notes / Tags',  () => { list[index].notes = noteInp.value; });

        const delBtn = document.createElement('button');
        delBtn.textContent = '\u2715';
        delBtn.title = 'Remove';
        delBtn.style.cssText = 'background:#e06c75;color:white;border:none;border-radius:3px;cursor:pointer;padding:2px 5px;font-size:11px;width:26px;';
        delBtn.onclick = () => {
            list.splice(index, 1);
            addCallback();
        };

        div.appendChild(nameInp);
        div.appendChild(domInp);
        div.appendChild(noteInp);
        div.appendChild(delBtn);
        container.appendChild(div);
    });
}

function renderCollectionSitesEditorList() {
    renderGridEditorList('collection-sites-list', tempCollectionSites, renderCollectionSitesEditorList);
}

function renderAudioSitesEditorList() {
    renderGridEditorList('audio-sites-list', tempAudioSites, renderAudioSitesEditorList);
}

function renderStorySitesEditorList() {
    renderGridEditorList('story-sites-list', tempStorySites, renderStorySitesEditorList);
}

function slugify(str) {
    return str.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || ('site_' + Date.now());
}

function addGridSite(nameEl, domEl, notesEl, list, renderCallback) {
    const nameInput = document.getElementById(nameEl);
    const domInput  = document.getElementById(domEl);
    const noteInput = document.getElementById(notesEl);
    if (!nameInput) return;
    const name = nameInput.value.trim();
    if (name) {
        const id = slugify(name);
        list.push({
            id,
            name,
            domain: domInput ? domInput.value.trim() : '',
            notes:  noteInput ? noteInput.value.trim() : ''
        });
        nameInput.value = '';
        if (domInput)  domInput.value = '';
        if (noteInput) noteInput.value = '';
        renderCallback();
    } else {
        alert('Please enter a display name.');
    }
}

function addCollectionSiteSource() {
    addGridSite('new-collection-name', 'new-collection-domain', 'new-collection-notes', tempCollectionSites, renderCollectionSitesEditorList);
}

function addAudioSiteSource() {
    addGridSite('new-audio-name', 'new-audio-domain', 'new-audio-notes', tempAudioSites, renderAudioSitesEditorList);
}

function addStorySiteSource() {
    addGridSite('new-story-name', 'new-story-domain', 'new-story-notes', tempStorySites, renderStorySitesEditorList);
}

function guessStorySiteConfig() {
    const urlInput = document.getElementById('story-config-guesser-url');
    const url = urlInput.value.trim();
    if (!url) {
        alert('Please paste a URL to guess from.');
        return;
    }

    const guessBtn = urlInput.nextElementSibling;
    guessBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Guessing...';
    guessBtn.disabled = true;

    pywebview.api.guess_story_site_selectors(url).then(res => {
        guessBtn.innerHTML = 'Guess Config';
        guessBtn.disabled = false;

        if (res.status === 'success') {
            const config = res.config;
            
            try {
                const urlObj = new URL(url);
                let name = urlObj.hostname.replace(/^www\./, '').split('.')[0];
                name = name.charAt(0).toUpperCase() + name.slice(1);
                document.getElementById('new-story-name').value = name;
                document.getElementById('new-story-domain').value = urlObj.origin;
            } catch(e) { /* ignore if URL is invalid */ }

            document.getElementById('new-story-notes').value = JSON.stringify(config);
            
            alert('Successfully guessed configuration! The fields below have been pre-filled. Review and click "Add".');
        } else {
            alert('Failed to guess configuration:\n' + res.msg);
        }
    });
}

function guessCollectionSiteConfig() {
    const urlInput = document.getElementById('collection-config-guesser-url');
    const url = urlInput.value.trim();
    if (!url) {
        alert('Please paste a URL to guess from.');
        return;
    }

    const guessBtn = urlInput.nextElementSibling;
    guessBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Guessing...';
    guessBtn.disabled = true;

    pywebview.api.guess_story_site_selectors(url).then(res => {
        guessBtn.innerHTML = 'Guess Config';
        guessBtn.disabled = false;

        if (res.status === 'success') {
            const config = res.config;
            
            try {
                const urlObj = new URL(url);
                let name = urlObj.hostname.replace(/^www\./, '').split('.')[0];
                name = name.charAt(0).toUpperCase() + name.slice(1);
                document.getElementById('new-collection-name').value = name;
                document.getElementById('new-collection-domain').value = urlObj.origin;
            } catch(e) { /* ignore if URL is invalid */ }

            document.getElementById('new-collection-notes').value = JSON.stringify(config);
            
            alert('Successfully guessed configuration! The fields below have been pre-filled. Review and click "Add".');
        } else {
            alert('Failed to guess configuration:\n' + res.msg);
        }
    });
}

function guessAudioSiteConfig() {
    const urlInput = document.getElementById('audio-config-guesser-url');
    const url = urlInput.value.trim();
    if (!url) {
        alert('Please paste a URL to guess from.');
        return;
    }

    const guessBtn = urlInput.nextElementSibling;
    guessBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Guessing...';
    guessBtn.disabled = true;

    pywebview.api.guess_story_site_selectors(url).then(res => {
        guessBtn.innerHTML = 'Guess Config';
        guessBtn.disabled = false;

        if (res.status === 'success') {
            const config = res.config;
            
            try {
                const urlObj = new URL(url);
                let name = urlObj.hostname.replace(/^www\./, '').split('.')[0];
                name = name.charAt(0).toUpperCase() + name.slice(1);
                document.getElementById('new-audio-name').value = name;
                document.getElementById('new-audio-domain').value = urlObj.origin;
            } catch(e) { /* ignore if URL is invalid */ }

            document.getElementById('new-audio-notes').value = JSON.stringify(config);
            
            alert('Successfully guessed configuration! The fields below have been pre-filled. Review and click "Add".');
        } else {
            alert('Failed to guess configuration:\n' + res.msg);
        }
    });
}

function saveOnlineSourcesModal() {
    appState.collection_sites = tempCollectionSites;
    appState.audio_sites = tempAudioSites;
    appState.story_sites = tempStorySites;

    pywebview.api.save_online_sources(tempCollectionSites, tempAudioSites, tempStorySites).then(state => {
        appState = state;
        closeModals();
    });
}

function exportOnlineSourcesFile() {
    pywebview.api.export_online_sources(tempCollectionSites, tempAudioSites, tempStorySites).then(result => {
        if (result && result.status === 'ok') {
            alert('Sources exported to:\n' + result.path);
        }
    });
}

function importOnlineSourcesFile() {
    pywebview.api.import_online_sources().then(result => {
        if (result && result.status === 'ok') {
            tempCollectionSites = result.collection_sites || [];
            tempAudioSites = result.audio_sites || [];
            tempStorySites = result.story_sites || [];
            renderCollectionSitesEditorList();
            renderAudioSitesEditorList();
            renderStorySitesEditorList();
        }
    });
}
const onlineStoriesModal = document.getElementById('online-stories-modal');

function openOnlineStories() {
    if (onlineStoriesModal) {
        pywebview.api.get_state().then(state => {
            appState = state;
            onlineStoriesModal.style.display = 'flex';
            renderOnlineStorySources();
            onStorySourceChanged();
        });
    }
}

function closeOnlineStories() {
    if (onlineStoriesModal) {
        onlineStoriesModal.style.display = 'none';
    }
}

function renderOnlineStorySources() {
    const select = document.getElementById('story-source-select');
    if (!select) return;

    select.innerHTML = '';
    
    const sites = appState.story_sites || [];
    if (sites.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'No story sites configured';
        opt.disabled = true;
        select.appendChild(opt);
        return;
    }

    sites.forEach(site => {
        const opt = document.createElement('option');
        opt.value = site.id;
        opt.textContent = site.name;
        select.appendChild(opt);
    });
}

function onStorySourceChanged() {
    const resultsArea = document.getElementById('online-stories-results-area');
    if (resultsArea) {
        resultsArea.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: #666; margin-top: 20px;">
            Enter a search term to begin.
        </div>`;
    }
    const searchInput = document.getElementById('story-search-input');
    if (searchInput) searchInput.value = '';
    const status = document.getElementById('online-stories-status');
    if (status) status.innerText = '';
}

function searchOnlineStories() {
    const sourceSelect = document.getElementById('story-source-select');
    const searchInput = document.getElementById('story-search-input');
    const resultsArea = document.getElementById('online-stories-results-area');
    const status = document.getElementById('online-stories-status');

    if (!sourceSelect || !searchInput || !resultsArea || !status) return;

    const sourceId = sourceSelect.value;
    const query = searchInput.value.trim();

    if (!sourceId) {
        alert("Please select a site to search.");
        return;
    }
    if (!query) {
        alert("Please enter a search query.");
        return;
    }

    status.innerText = `Searching for "${query}"...`;
    resultsArea.innerHTML = '';

    pywebview.api.search_online_stories(sourceId, query).then(res => {
        if (res.status === 'success') {
            status.innerText = `Found ${res.results.length} results for "${query}"`;
            renderStoryResults(res.results);
        } else {
            status.innerText = `Search failed: ${res.msg}`;
            resultsArea.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: #f38ba8; margin-top: 20px;">
                Error: ${res.msg}
            </div>`;
        }
    });
}

function renderStoryResults(results) {
    const resultsArea = document.getElementById('online-stories-results-area');
    if (!resultsArea) return;
    resultsArea.innerHTML = '';

    if (!results || results.length === 0) {
        resultsArea.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: #888; margin-top: 20px;">
            No stories found matching your search.
        </div>`;
        return;
    }

    results.forEach(item => {
        const card = document.createElement('div');
        card.className = 'audio-site-card'; // Re-using this class for similar styling
        card.style.cursor = 'pointer';
        card.style.borderColor = 'rgba(250, 179, 135, 0.2)';
        card.onclick = () => {
            if (item.url) {
                pywebview.api.open_external_url(item.url);
            }
        };

        const title = document.createElement('div');
        title.className = 'audio-site-card-title';
        title.style.color = '#fab387';
        title.textContent = item.title || 'Untitled Story';

        const author = document.createElement('div');
        author.className = 'audio-site-card-url'; // Re-using for style
        author.textContent = item.author ? `by ${item.author}` : '';
        author.style.color = '#ccc';

        const summary = document.createElement('p');
        summary.textContent = item.summary || '';
        summary.style.cssText = 'font-size: 11px; color: #999; margin-top: 8px; text-align: left; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;';

        card.appendChild(title);
        card.appendChild(author);
        card.appendChild(summary);
        resultsArea.appendChild(card);
    });
}

// --- Added Helper/UI Functions ---

function toggleSidebarControls() {
    const controls = document.getElementById('sidebar-controls');
    if (!controls) return;
    if (controls.style.display === 'none') {
        controls.style.display = '';
    } else {
        controls.style.display = 'none';
    }
}

function toggleSidebarCollapse() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    sidebar.classList.toggle('collapsed');
    
    const btn = document.getElementById('sidebar-collapse-btn');
    if (btn) {
        const icon = btn.querySelector('i');
        if (sidebar.classList.contains('collapsed')) {
            icon.className = 'fa-solid fa-chevron-down';
        } else {
            icon.className = 'fa-solid fa-chevron-up';
        }
    }
}

function toggleAudioNormWindow() {
    const win = document.getElementById('audio-norm-window');
    if (!win) return;
    if (win.style.display === 'none') {
        win.style.display = 'block';
    } else {
        win.style.display = 'none';
    }
}

let languagesLoaded = false;
function loadAvailableLanguages() {
    if (languagesLoaded) return;
    pywebview.api.get_available_languages().then(res => {
        if (res && res.status === 'success') {
            const fromSelect = document.getElementById('model-from');
            const toSelect = document.getElementById('model-to');
            if (fromSelect && toSelect) {
                fromSelect.innerHTML = '';
                toSelect.innerHTML = '';
                res.languages.forEach(lang => {
                    const optFrom = document.createElement('option');
                    optFrom.value = lang.code;
                    optFrom.textContent = lang.name;
                    if (lang.code === 'ja') optFrom.selected = true;
                    fromSelect.appendChild(optFrom);

                    const optTo = document.createElement('option');
                    optTo.value = lang.code;
                    optTo.textContent = lang.name;
                    if (lang.code === 'en') optTo.selected = true;
                    toSelect.appendChild(optTo);
                });
                languagesLoaded = true;
            }
        }
    });
}

let tesseractLangsLoaded = false;
function loadTesseractLanguages() {
    if (tesseractLangsLoaded) return;
    pywebview.api.get_tesseract_languages().then(res => {
        if (res && res.status === 'success') {
            const sourceSelect = document.getElementById('ocr-source-lang');
            if (sourceSelect) {
                sourceSelect.innerHTML = '<option value="auto" selected>Auto Detect</option>';
                res.languages.forEach(lang => {
                    const opt = document.createElement('option');
                    opt.value = lang.code;
                    opt.textContent = lang.name;
                    sourceSelect.appendChild(opt);
                });
                tesseractLangsLoaded = true;
            }
        }
    });
}

function toggleTranslateWindow() {
    const win = document.getElementById('translate-settings-window');
    if (!win) return;
    if (win.style.display === 'none') {
        win.style.display = 'block';
        loadAvailableLanguages();
        loadTesseractLanguages();
    } else {
        win.style.display = 'none';
    }
}

function downloadModelAction() {
    const fromCode = document.getElementById('model-from').value.trim().toLowerCase();
    const toCode = document.getElementById('model-to').value.trim().toLowerCase();
    if (!fromCode || !toCode) {
        alert("Please enter both 'From' and 'To' language codes.");
        return;
    }
    
    const btn = document.getElementById('btn-download-model');
    const status = document.getElementById('download-model-status');
    btn.disabled = true;
    status.style.display = 'block';
    status.innerText = "Downloading model assets...";
    
    pywebview.api.download_translation_model(fromCode, toCode).then(res => {
        btn.disabled = false;
        if (res && res.status === 'success') {
            status.innerText = "Successfully downloaded!";
            setTimeout(() => { status.style.display = 'none'; }, 3000);
        } else {
            status.innerText = "Failed: " + (res ? res.msg : "");
        }
    });
}

function addStandardCloseButton(modalId, closeFunction) {
    const modal = document.getElementById(modalId);
    if (!modal) return;

    const header = modal.querySelector('.modal-header');
    if (!header) {
        console.warn(`Modal header not found for #${modalId}`);
        return;
    }
    
    // Make header a flex container to position the button correctly
    header.style.display = 'flex';
    header.style.alignItems = 'center';

    // Hide existing small 'x' if it exists.
    const existingClose = header.querySelector('span.close, span.close-btn, .close-button, [onclick*="close"]');
    if (existingClose && existingClose.tagName.toLowerCase() === 'span') {
        existingClose.style.display = 'none';
    }

    const closeBtn = document.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.style.cssText = `
        background: #555; color: white; border: 1px solid #666; padding: 5px 15px;
        border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 13px;
        margin-left: auto; order: 10;
    `;
    closeBtn.onmouseover = () => { closeBtn.style.background = '#666'; };
    closeBtn.onmouseout = () => { closeBtn.style.background = '#555'; };
    closeBtn.onclick = closeFunction;
    
    header.appendChild(closeBtn);
}

function makeDraggable(win, header) {
    if (!win || !header) return;
    let isDragging = false, startX = 0, startY = 0, startLeft = 0, startTop = 0;
    header.addEventListener('mousedown', (e) => {
        if (e.target.closest('button, input, select, a, span.close')) return;
        if (e.button !== 0) return;
        
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = win.getBoundingClientRect();
        startLeft = rect.left;
        startTop = rect.top;
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        win.style.left = (startLeft + dx) + 'px';
        win.style.top = (startTop + dy) + 'px';
        win.style.right = 'auto';
        win.style.bottom = 'auto';
    });

    document.addEventListener('mouseup', () => { isDragging = false; });
}

// --- FTP / CopyParty Browser ---
let ftpCurrentUrl = '';
let currentFtpListing = null;
let ftpActiveFilter = 'all';

function openFtpBrowser() {
    document.getElementById('ftp-browser-modal').style.display = 'flex';
    const url = document.getElementById('ftp-url-input').value.trim();
    if (url) ftpNavigateTo(url);
}

function closeFtpBrowser() {
    document.getElementById('ftp-browser-modal').style.display = 'none';
}

function ftpLoadPreset() {
    const sel = document.getElementById('ftp-preset-select');
    if (sel.value) {
        document.getElementById('ftp-url-input').value = sel.value;
        ftpNavigateTo(sel.value);
    }
}

function ftpNavigateTo(url) {
    url = url.trim();
    if (!url) return;
    if (!url.endsWith('/')) url += '/';
    ftpCurrentUrl = url;
    document.getElementById('ftp-url-input').value = url;
    document.getElementById('ftp-status').textContent = 'Loading...';
    document.getElementById('ftp-listing').innerHTML = '<div style="color:#888;text-align:center;padding:20px;">Loading...</div>';
    ftpUpdateBreadcrumb(url);
    pywebview.api.browse_copyparty(url).then(res => {
        document.getElementById('ftp-status').textContent = '';
        if (res.status === 'error') {
            document.getElementById('ftp-listing').innerHTML = `<div style="color:#f38ba8;padding:10px;">Error: ${res.msg}</div>`;
            return;
        }
        currentFtpListing = res;
        ftpRenderListing(res);
    });
}

function ftpUpdateBreadcrumb(url) {
    try {
        const u = new URL(url);
        const parts = u.pathname.split('/').filter(p => p);
        let crumbs = `<a href="#" onclick="ftpNavigateTo('${u.origin}/')" style="color:#89b4fa;">${u.hostname}</a>`;
        let built = u.origin + '/';
        parts.forEach(p => {
            built += p + '/';
            const cap = built;
            crumbs += ` / <a href="#" onclick="ftpNavigateTo('${cap}')" style="color:#89b4fa;">${decodeURIComponent(p)}</a>`;
        });
        document.getElementById('ftp-breadcrumb').innerHTML = crumbs;
    } catch(e) {
        document.getElementById('ftp-breadcrumb').textContent = url;
    }
}

function ftpFormatSize(bytes) {
    if (!bytes) return '';
    if (bytes > 1e12) return (bytes/1e12).toFixed(1) + ' TiB';
    if (bytes > 1e9)  return (bytes/1e9).toFixed(1) + ' GiB';
    if (bytes > 1e6)  return (bytes/1e6).toFixed(1) + ' MiB';
    return (bytes/1e3).toFixed(0) + ' KiB';
}

function ftpRenderListing(res) {
    const container = document.getElementById('ftp-listing');
    container.innerHTML = '';
    const base = res.base_url;

    document.addEventListener('click', ftpHideCtxMenu, { once: true });

    // Up button
    try {
        const u = new URL(base);
        const parts = u.pathname.split('/').filter(p => p);
        if (parts.length > 0) {
            const upUrl = u.origin + '/' + parts.slice(0, -1).join('/') + (parts.length > 1 ? '/' : '');
            const upRow = document.createElement('div');
            upRow.style.cssText = 'display:flex;align-items:center;gap:10px;padding:7px 10px;cursor:pointer;border-radius:4px;color:#cdd6f4;margin-bottom:4px;';
            upRow.onmouseover = () => upRow.style.background = '#2a2a3e';
            upRow.onmouseout  = () => upRow.style.background = '';
            upRow.onclick = () => ftpNavigateTo(upUrl);
            upRow.innerHTML = '<i class="fa-solid fa-arrow-up" style="color:#a6e3a1;width:16px;"></i><span>.. (up)</span>';
            container.appendChild(upRow);
        }
    } catch(e) {}

    // Dirs
    res.dirs.forEach(d => {
        const dirUrl = base + d.href;
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:7px 10px;cursor:pointer;border-radius:4px;color:#cdd6f4;';
        row.onmouseover = () => row.style.background = '#2a2a3e';
        row.onmouseout  = () => row.style.background = '';
        row.onclick = () => ftpNavigateTo(dirUrl);
        const meta = d.files ? `<span style="color:#555;font-size:11px;margin-left:auto;">${d.files} files &nbsp;${ftpFormatSize(d.sz)}</span>` : '';
        row.innerHTML = `<i class="fa-solid fa-folder" style="color:#f9e2af;width:16px;"></i><span style="flex:1;">${decodeURIComponent(d.name)}/</span>${meta}`;
        container.appendChild(row);
    });

    if (res.files.length > 0) {
        // Type filter pills
        const typeCounts = {};
        res.files.forEach(f => { typeCounts[f.type] = (typeCounts[f.type] || 0) + 1; });
        const typeInfo = {
            image:   { label: 'Images',   icon: 'fa-image',       color: '#89b4fa' },
            video:   { label: 'Videos',   icon: 'fa-film',        color: '#cba6f7' },
            audio:   { label: 'Audio',    icon: 'fa-music',       color: '#89dceb' },
            manga:   { label: 'Manga',    icon: 'fa-book',        color: '#f38ba8' },
            archive: { label: 'Archives', icon: 'fa-file-zipper', color: '#f9e2af' },
            doc:     { label: 'Docs',     icon: 'fa-file-lines',  color: '#a6e3a1' },
            file:    { label: 'Other',    icon: 'fa-file',        color: '#888'    },
        };

        ftpActiveFilter = 'all';
        const filterBar = document.createElement('div');
        filterBar.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 8px 0;';

        const allPill = document.createElement('span');
        allPill.style.cssText = 'padding:3px 10px;border-radius:12px;font-size:11px;cursor:pointer;background:#313244;color:#cdd6f4;border:1px solid #45475a;';
        allPill.textContent = `All (${res.files.length})`;
        allPill.dataset.filter = 'all';
        filterBar.appendChild(allPill);

        Object.keys(typeCounts).sort().forEach(type => {
            const ti = typeInfo[type] || typeInfo.file;
            const pill = document.createElement('span');
            pill.style.cssText = `padding:3px 10px;border-radius:12px;font-size:11px;cursor:pointer;background:#1a1a2e;color:${ti.color};border:1px solid #2a2a3e;`;
            pill.innerHTML = `<i class="fa-solid ${ti.icon}" style="margin-right:4px;"></i>${ti.label} (${typeCounts[type]})`;
            pill.dataset.filter = type;
            filterBar.appendChild(pill);
        });

        container.appendChild(filterBar);

        const grid = document.createElement('div');
        grid.id = 'ftp-file-grid';
        ftpApplyGridColumns(grid);

        const renderCards = (filter) => {
            grid.innerHTML = '';
            const shown = filter === 'all' ? res.files : res.files.filter(f => f.type === filter);
            // Update pill highlights
            filterBar.querySelectorAll('span').forEach(p => {
                p.style.background = p.dataset.filter === filter ? '#313244' : '#1a1a2e';
                p.style.borderColor = p.dataset.filter === filter ? '#585b70' : '#2a2a3e';
            });

            shown.forEach(f => {
                const fileUrl = base + f.href;
                const name = decodeURIComponent(f.name);
                const ti = typeInfo[f.type] || typeInfo.file;
                const card = document.createElement('div');
                card.style.cssText = 'background:#111827;border-radius:5px;overflow:hidden;cursor:pointer;border:1px solid #2a2a3e;display:flex;flex-direction:column;transition:border-color 0.15s;position:relative;';
                card.onmouseover = () => card.style.borderColor = ti.color;
                card.onmouseout  = () => card.style.borderColor = '#2a2a3e';

                const thumbDiv = document.createElement('div');
                thumbDiv.style.cssText = 'width:100%;aspect-ratio:16/9;background:#0a0a14;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative;';

                if (f.type === 'image') {
                    const img = document.createElement('img');
                    img.src = fileUrl + '?th=w';
                    img.loading = 'lazy';
                    img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
                    img.onerror = () => {
                        if (img.src !== fileUrl) {
                            img.src = fileUrl;
                        } else {
                            img.style.display = 'none';
                            thumbDiv.innerHTML = `<i class="fa-solid ${ti.icon}" style="font-size:30px;color:${ti.color};"></i>`;
                        }
                    };
                    thumbDiv.appendChild(img);
                } else if (f.type === 'video') {
                    const vid = document.createElement('video');
                    vid.src = fileUrl + '#t=3';
                    vid.preload = 'metadata';
                    vid.muted = true;
                    vid.style.cssText = 'width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0;';
                    vid.addEventListener('loadeddata', () => { vid.currentTime = 3; });
                    thumbDiv.appendChild(vid);
                    const icon = document.createElement('i');
                    icon.className = `fa-solid ${ti.icon}`;
                    icon.style.cssText = `font-size:30px;color:rgba(203,166,247,0.85);position:relative;z-index:1;pointer-events:none;`;
                    thumbDiv.appendChild(icon);
                } else {
                    thumbDiv.innerHTML = `<i class="fa-solid ${ti.icon}" style="font-size:30px;color:${ti.color};"></i>`;
                }

                // Type badge
                const badge = document.createElement('span');
                badge.style.cssText = `position:absolute;top:4px;right:4px;background:rgba(0,0,0,0.65);color:${ti.color};font-size:8px;padding:1px 4px;border-radius:3px;`;
                badge.textContent = (f.ext || f.type).replace('.','').toUpperCase();
                thumbDiv.appendChild(badge);

                const infoDiv = document.createElement('div');
                infoDiv.style.cssText = 'padding:4px 6px;';
                infoDiv.innerHTML = `<div style="font-size:10px;color:#cdd6f4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${name}">${name}</div><div style="font-size:9px;color:#555;">${ftpFormatSize(f.sz)}</div>`;

                card.appendChild(thumbDiv);
                card.appendChild(infoDiv);
                card.onclick = () => ftpPlayFile(fileUrl);
                card.oncontextmenu = (e) => { e.preventDefault(); e.stopPropagation(); ftpShowCtxMenu(e.clientX, e.clientY, fileUrl, f.type); };
                grid.appendChild(card);
            });

            if (shown.length === 0) {
                grid.innerHTML = '<div style="color:#666;font-size:11px;padding:10px;">No files of this type.</div>';
            }
        };

        filterBar.addEventListener('click', (e) => {
            const pill = e.target.closest('[data-filter]');
            if (pill) { ftpActiveFilter = pill.dataset.filter; renderCards(ftpActiveFilter); }
        });

        renderCards('all');
        container.appendChild(grid);
    }

    if (res.dirs.length === 0 && res.files.length === 0) {
        container.innerHTML = '<div style="color:#666;text-align:center;padding:20px;">Empty directory.</div>';
    }
}

function toggleMaximizeFtpBrowser() {
    const modalContent = document.querySelector('#ftp-browser-modal .modal-content');
    const icon = document.getElementById('ftp-max-icon');
    if (!modalContent || !icon) return;

    if (modalContent.classList.contains('maximized')) {
        modalContent.classList.remove('maximized');
        icon.className = 'fa-regular fa-square';
        icon.parentNode.title = 'Maximize';
    } else {
        modalContent.classList.add('maximized');
        icon.className = 'fa-regular fa-window-restore';
        icon.parentNode.title = 'Restore';
    }
}

function ftpShowCtxMenu(x, y, url, type) {
    ftpHideCtxMenu();
    const menu = document.createElement('div');
    menu.id = 'ftp-ctx-menu';
    menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;background:#1e1e2e;border:1px solid #444;border-radius:6px;z-index:9999;padding:4px 0;min-width:160px;box-shadow:0 4px 16px rgba(0,0,0,0.6);`;

    const makeItem = (icon, label, cb) => {
        const item = document.createElement('div');
        item.style.cssText = 'padding:8px 16px;cursor:pointer;color:#cdd6f4;font-size:13px;display:flex;align-items:center;gap:10px;';
        item.onmouseover = () => item.style.background = '#2a2a3e';
        item.onmouseout  = () => item.style.background = '';
        item.innerHTML = `<i class="fa-solid ${icon}" style="width:14px;"></i>${label}`;
        item.onclick = (e) => { e.stopPropagation(); ftpHideCtxMenu(); cb(); };
        return item;
    };

    menu.appendChild(makeItem('fa-play', 'Play', () => ftpPlayFile(url)));
    if (type === 'video') {
        menu.appendChild(makeItem('fa-eye', 'Preview 10s', () => ftpPreview10s(url)));
    }
    menu.appendChild(makeItem('fa-arrow-up-right-from-square', 'Go to website', () => pywebview.api.open_external_url(url)));
    
    // Parse the filename from the URL to display in notifications
    let filename = 'file';
    try {
        const u = new URL(url);
        filename = u.pathname.split('/').filter(p => p).pop() || 'file';
    } catch(e) {
        filename = url.substring(url.lastIndexOf('/') + 1) || 'file';
    }
    const cleanFilename = decodeURIComponent(filename).split('?')[0];

    menu.appendChild(makeItem('fa-download', 'Download', () => {
        pywebview.api.download_online_track(url, cleanFilename);
        alert(`Starting download for: ${cleanFilename}\nCheck main playlist or active directory once complete.`);
    }));

    document.body.appendChild(menu);

    // Auto-close on next click
    setTimeout(() => document.addEventListener('click', ftpHideCtxMenu, { once: true }), 50);
}

function ftpHideCtxMenu() {
    const m = document.getElementById('ftp-ctx-menu');
    if (m) m.remove();
    ftpStopPreview();
}

let ftpPreviewTimer = null;

function ftpPreview10s(url) {
    ftpStopPreview();

    const overlay = document.createElement('div');
    overlay.id = 'ftp-preview-overlay';
    overlay.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9998;background:#000;border-radius:8px;overflow:hidden;border:2px solid #a6e3a1;box-shadow:0 4px 24px rgba(0,0,0,0.8);width:360px;';

    const bar = document.createElement('div');
    bar.style.cssText = 'background:#1e1e2e;padding:6px 10px;display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#cdd6f4;';
    bar.innerHTML = '<span><i class="fa-solid fa-eye" style="color:#a6e3a1;margin-right:6px;"></i>10s Preview</span>';
    const closeBtn = document.createElement('button');
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = 'background:none;border:none;color:#888;cursor:pointer;font-size:14px;';
    closeBtn.onclick = ftpStopPreview;
    bar.appendChild(closeBtn);

    const vid = document.createElement('video');
    vid.src = url;
    vid.autoplay = true;
    vid.controls = true;
    vid.muted = false;
    vid.style.cssText = 'width:100%;display:block;max-height:200px;';

    const countdown = document.createElement('div');
    countdown.style.cssText = 'background:#1e1e2e;padding:4px 10px;font-size:11px;color:#888;text-align:right;';
    countdown.textContent = 'Stops in 10s';

    overlay.appendChild(bar);
    overlay.appendChild(vid);
    overlay.appendChild(countdown);
    document.body.appendChild(overlay);

    let remaining = 10;
    ftpPreviewTimer = setInterval(() => {
        remaining--;
        countdown.textContent = `Stops in ${remaining}s`;
        if (remaining <= 0) ftpStopPreview();
    }, 1000);
}

function ftpStopPreview() {
    if (ftpPreviewTimer) { clearInterval(ftpPreviewTimer); ftpPreviewTimer = null; }
    const o = document.getElementById('ftp-preview-overlay');
    if (o) { const v = o.querySelector('video'); if (v) { v.pause(); v.src = ''; } o.remove(); }
}

function ftpPlayFile(url) {
    ftpStopPreview();
    if (!currentFtpListing || !currentFtpListing.files) return;

    // Filter playlist based on active tab/filter
    const filtered = ftpActiveFilter === 'all' 
        ? currentFtpListing.files 
        : currentFtpListing.files.filter(f => f.type === ftpActiveFilter);

    // Build absolute URL playlist
    const playlist = filtered.map(f => ({
        name: f.name,
        type: f.type,
        url: currentFtpListing.base_url + f.href
    }));

    const idx = playlist.findIndex(f => f.url === url);

    const clickedItem = playlist[idx];
    if (clickedItem && clickedItem.type === 'audio') {
        playTopAudio(playlist, idx);
        return;
    }

    pywebview.api.set_ftp_playlist(playlist, idx).then(() => {
        let filename = 'File Preview';
        try {
            const u = new URL(url);
            filename = u.pathname.split('/').filter(p => p).pop() || 'File Preview';
        } catch(e) {
            filename = url.substring(url.lastIndexOf('/') + 1) || 'File Preview';
        }
        const cleanFilename = decodeURIComponent(filename).split('?')[0];
        pywebview.api.open_in_app_browser('http://localhost:5050/ftp_player', cleanFilename);
    });
}

function ftpApplyGridColumns(grid) {
    if (!grid) return;
    const cols = document.getElementById('ftp-cols-select')?.value || '6';
    if (cols === 'auto') {
        grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;';
    } else {
        grid.style.cssText = `display:grid;grid-template-columns:repeat(${cols},1fr);gap:8px;`;
    }
}

function ftpChangeCols(val) {
    const grid = document.getElementById('ftp-file-grid');
    if (grid) {
        ftpApplyGridColumns(grid);
    }
}

let topAudioPlaylist = [];
let topAudioIndex = -1;

function playTopAudio(playlist, index) {
    topAudioPlaylist = playlist;
    topAudioIndex = index;
    
    const bar = document.getElementById('top-audio-bar');
    const audio = document.getElementById('top-audio-element');
    const nameEl = document.getElementById('top-audio-name');
    const playBtn = document.getElementById('top-audio-play-btn');
    
    if (!bar || !audio || !nameEl || !playBtn) return;
    
    const item = playlist[index];
    if (!item) return;
    
    nameEl.textContent = decodeURIComponent(item.name);
    nameEl.title = decodeURIComponent(item.name);
    
    audio.src = item.url;
    audio.play();
    
    playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
    bar.style.display = 'flex';
    
    audio.onended = () => {
        topAudioNext();
    };
}

function topAudioTogglePlay() {
    const audio = document.getElementById('top-audio-element');
    const playBtn = document.getElementById('top-audio-play-btn');
    if (!audio || !playBtn) return;
    
    if (audio.paused) {
        audio.play();
        playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
    } else {
        audio.pause();
        playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
    }
}

function topAudioNext() {
    if (topAudioPlaylist.length === 0) return;
    topAudioIndex = (topAudioIndex + 1) % topAudioPlaylist.length;
    playTopAudio(topAudioPlaylist, topAudioIndex);
}

function topAudioPrev() {
    if (topAudioPlaylist.length === 0) return;
    topAudioIndex = (topAudioIndex - 1 + topAudioPlaylist.length) % topAudioPlaylist.length;
    playTopAudio(topAudioPlaylist, topAudioIndex);
}

function topAudioClose() {
    const bar = document.getElementById('top-audio-bar');
    const audio = document.getElementById('top-audio-element');
    if (audio) {
        audio.pause();
        audio.src = '';
    }
    if (bar) {
        bar.style.display = 'none';
    }
}

function initSplitResizer() {
    const resizer = document.getElementById('split-resizer');
    const leftPane = document.getElementById('left-split-pane');
    const rightPane = document.getElementById('right-split-pane');
    const container = document.getElementById('media-container');

    if (!resizer || !leftPane || !rightPane || !container) return;

    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        document.body.style.cursor = 'col-resize';
        const overlay = document.createElement('div');
        overlay.id = 'resize-overlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;cursor:col-resize;';
        document.body.appendChild(overlay);
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        
        const containerRect = container.getBoundingClientRect();
        const offsetLeft = e.clientX - containerRect.left;
        let percentage = (offsetLeft / containerRect.width) * 100;
        
        if (percentage < 10) percentage = 10;
        if (percentage > 90) percentage = 90;
        
        leftPane.style.setProperty('width', `${percentage}%`, 'important');
        rightPane.style.setProperty('width', `${100 - percentage}%`, 'important');
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = '';
            const overlay = document.getElementById('resize-overlay');
            if (overlay) overlay.remove();
        }
    });
}
