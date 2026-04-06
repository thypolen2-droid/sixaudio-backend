/**
 * Audio Player JavaScript
 * Handles all player functionality including playback, navigation, and UI updates
 * @version 2.1 - Added Continue Listening Feature
 * @author TTS System
 */

// ============================================
// CONFIGURATION
// ============================================
/**
 * Debug Log on UI
 */
const debugLog = (msg, level = 'info') => {
    const el = document.getElementById('debugOutput');
    if (!el) return;
    const item = document.createElement('div');
    const color = level === 'error' ? '#f00' : (level === 'success' ? '#0f0' : '#0ff');
    item.style.color = color;
    item.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    el.appendChild(item);
    el.parentElement.scrollTop = el.scrollHeight;
    console.log(`[DEBUG] ${msg}`);
};

const CONFIG = {
    // If running on local network (IP), hostname (localhost), or development, use relative paths.
    // ONLY use the production backend if specifically on one of our cloud domains.
    API_BASE_URL: (
        window.location.hostname.includes('onrender.com') || 
        window.location.hostname.includes('firebaseapp.com')
    ) ? 'https://sixaudio-backend.onrender.com' : ''
};

// ============================================
// STATE MANAGEMENT
// ============================================
const PlayerState = {
    currentFiles: [],
    currentIndex: -1,
    currentStory: "",
    isPlaying: false,
    isShuffled: false,
    isRepeating: false,
    currentSpeed: 1.0
};

// ============================================
// PROGRESS TRACKING
// ============================================
const ProgressTracker = {
    STORAGE_KEY: 'tts_listening_progress',

    /**
     * Save current listening progress (both locally and to server)
     */
    async save() {
        if (PlayerState.currentStory && PlayerState.currentIndex >= 0) {
            const progress = {
                story: PlayerState.currentStory,
                chapterIndex: PlayerState.currentIndex,
                chapterFile: PlayerState.currentFiles[PlayerState.currentIndex],
                playbackTime: DOM.audioPlayer.currentTime,
                timestamp: new Date().toISOString(),
                speed: PlayerState.currentSpeed
            };

            // Save to localStorage
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(progress));

            // Also save to server for cross-device sync
            try {
                await fetch(CONFIG.API_BASE_URL + '/api/progress/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(progress)
                });
                console.log('💾 Progress saved (local + server)');
            } catch (error) {
                console.log('💾 Progress saved (local only)');
            }
        }
    },

    /**
     * Load saved listening progress (from server first, then localStorage)
     * @returns {Object|null} Saved progress or null
     */
    async load() {
        try {
            // Try loading from server first for cross-device sync
            const response = await fetch(CONFIG.API_BASE_URL + '/api/progress/load');
            if (response.ok) {
                const serverProgress = await response.json();
                if (serverProgress && serverProgress.story) {
                    console.log('📖 Progress loaded from server');
                    return serverProgress;
                }
            }
        } catch (error) {
            console.log('⚠️ Could not load from server, using local storage');
        }

        // Fallback to localStorage
        try {
            const saved = localStorage.getItem(this.STORAGE_KEY);
            if (saved) {
                const progress = JSON.parse(saved);
                console.log('📖 Progress loaded from localStorage');
                return progress;
            }
        } catch (error) {
            console.error('Error loading progress:', error);
        }
        return null;
    },

    /**
     * Clear saved progress
     */
    clear() {
        localStorage.removeItem(this.STORAGE_KEY);
        console.log('🗑️ Progress cleared');
    },

    /**
     * Check if there's saved progress
     * @returns {boolean}
     */
    hasProgress() {
        return localStorage.getItem(this.STORAGE_KEY) !== null;
    }
};

// ============================================
// DOM ELEMENTS
// ============================================
const DOM = {
    // Audio
    audioPlayer: document.getElementById('audioPlayer'),

    // Player Views
    playerView: document.getElementById('playerView'),
    miniPlayer: document.getElementById('miniPlayer'),

    // Controls
    playBtn: document.getElementById('playBtn'),
    prevBtn: document.getElementById('prevBtn'),
    nextBtn: document.getElementById('nextBtn'),
    shuffleBtn: document.getElementById('shuffleBtn'),
    repeatBtn: document.getElementById('repeatBtn'),
    playerClose: document.getElementById('playerClose'),

    // Mini Player Controls
    miniPlayBtn: document.getElementById('miniPlayBtn'),
    miniPrevBtn: document.getElementById('miniPrevBtn'),
    miniNextBtn: document.getElementById('miniNextBtn'),

    // Progress
    waveform: document.getElementById('waveform'),
    currentTimeEl: document.getElementById('currentTime'),
    totalTimeEl: document.getElementById('totalTime'),

    // Track Info
    trackTitle: document.getElementById('trackTitle'),
    trackArtist: document.getElementById('trackArtist'),
    miniTrackTitle: document.getElementById('miniTrackTitle'),
    miniTrackArtist: document.getElementById('miniTrackArtist'),

    // UI Elements
    storySelect: document.getElementById('storySelect'),
    chapterList: document.getElementById('chapterList'),
    sectionTitle: document.getElementById('sectionTitle'),
    searchBar: document.getElementById('searchBar'),

    // Sidebar & Menu
    menuIcon: document.querySelector('.menu-icon'),
    sidebar: document.getElementById('sidebar'),
    menuClose: document.getElementById('menuClose'),
    sidebarOverlay: document.getElementById('sidebarOverlay'),
    menuScrapeBtn: document.getElementById('menuScrapeBtn'),
    menuCheckUpdatesBtn: document.getElementById('menuCheckUpdatesBtn'),
    menuConvertBtn: document.getElementById('menuConvertBtn'),
    menuCleanBtn: document.getElementById('menuCleanBtn'),
    taskStatus: document.getElementById('taskStatus'),

    // Modal
    scrapeModal: document.getElementById('scrapeModal'),
    scrapeModalClose: document.getElementById('scrapeModalClose'),
    scrapeModalCancel: document.getElementById('scrapeModalCancel'),
    scrapeUrl: document.getElementById('scrapeUrl'),
    scrapeFast: document.getElementById('scrapeFast'),
    scrapeHeadless: document.getElementById('scrapeHeadless'),
    startScrapeBtn: document.getElementById('startScrapeBtn'),

    // Library Interface
    libraryGrid: document.getElementById('libraryGrid'),
    libraryEmpty: document.getElementById('libraryEmpty'),
    continueSection: document.getElementById('continueSection'),
    continueCard: document.getElementById('continueCard'),
    continueTitle: document.getElementById('continueTitle'),
    continueChapter: document.getElementById('continueChapter'),
    continueMeta: document.getElementById('continueMeta'),
    continuePercent: document.getElementById('continuePercent'),
    continueFill: document.getElementById('continueFill'),
    continueTime: document.getElementById('continueTime'),
    resumeBtn: document.getElementById('resumeBtn'),
    searchIcon: document.getElementById('searchIcon'),
    searchContainer: document.getElementById('searchContainer'),
    librarySearch: document.getElementById('librarySearch'),
    searchClose: document.getElementById('searchClose')
};

// ============================================
// LIBRARY INTERFACE
// ============================================

/**
 * List of available stories stored globally
 */
let availableStories = [];

/**
 * Load and display the library grid
 */
async function loadLibrary() {
    try {
        debugLog('Fetching library from: ' + (CONFIG.API_BASE_URL || '/') + '/api/stories');
        const response = await fetch(CONFIG.API_BASE_URL + '/api/stories?t=' + Date.now());
        
        if (!response.ok) throw new Error('HTTP status ' + response.status);
        
        const data = await response.json();
        availableStories = data.stories || [];

        debugLog('Success: Found ' + availableStories.length + ' stories');

        console.log('📚 Loaded', availableStories.length, 'stories');

        if (availableStories.length === 0) {
            DOM.libraryGrid.innerHTML = `
                <div class="library-empty">
                    <div class="empty-icon">📚</div>
                    <p>No audiobooks yet</p>
                    <p class="empty-hint">Use the menu to add stories</p>
                </div>
            `;
        } else {
            renderLibraryGrid(availableStories);
        }

        // Show Continue Listening section if there's progress
        await updateContinueListening();

    } catch (error) {
        debugLog('Error loading library: ' + error.message, 'error');
        console.error('Error loading library:', error);
        DOM.libraryGrid.innerHTML = `
            <div class="library-empty">
                <div class="empty-icon">❌</div>
                <p>Error loading library</p>
                <p class="empty-hint">${error.message}</p>
            </div>
        `;
    }
}

/**
 * Render the library grid with story cards
 */
function renderLibraryGrid(stories) {
    DOM.libraryEmpty.style.display = 'none ';

    DOM.libraryGrid.innerHTML = stories.map((story, index) => `
        <div class="story-card" data-story="${story}" onclick="selectStoryForChapterView('${story}')" style="animation-delay: ${index * 0.05}s">
            <div class="story-card-artwork">
                ${getStoryIcon(index)}
            </div>
            <div class="story-card-info">
                <div class="story-card-title">${story}</div>
                <div class="story-card-meta">Fiction</div>
                <div class="story-card-chapters" id="chapters-${index}">Loading...</div>
            </div>
        </div>
    `).join('');

    // Load chapter counts asynchronously
    stories.forEach((story, index) => {
        fetch(`/api/stories/${encodeURIComponent(story)}`)
            .then(res => res.json())
            .then(data => {
                const chapterEl = document.getElementById(`chapters-${index}`);
                if (chapterEl) {
                    const count = data.files ? data.files.length : 0;
                    chapterEl.textContent = `${count} chapter${count !== 1 ? 's' : ''}`;
                }
            })
            .catch(() => {
                const chapterEl = document.getElementById(`chapters-${index}`);
                if (chapterEl) chapterEl.textContent = 'Unknown';
            });
    });
}

/**
 * Get emoji icon for story based on index
 */
function getStoryIcon(index) {
    const icons = ['📖', '🎭', '🚀', '🏰', '🔮', '⚔️', '🌟', '🎪', '🌊', '🎨', '🎵', '🎬', '🌌', '🐉', '🕯️', '🧿', '🧬', '🧭'];
    return icons[index % icons.length];
}

/**
 * Select a story and load its chapters
 */
async function selectStory(storyName) {
    console.log('📚 Selected story:', storyName);

    PlayerState.currentStory = storyName;
    PlayerState.currentFiles = [];
    PlayerState.currentIndex = -1;

    try {
        const response = await fetch(`/api/stories/${encodeURIComponent(storyName)}`);
        const data = await response.json();

        if (data.files && data.files.length > 0) {
            PlayerState.currentFiles = data.files;
            console.log('📑 Loaded', data.files.length, 'chapters');

            // Start playing first chapter
            playFile(0);
        } else {
            console.warn('No chapters found for', storyName);
            alert(`No chapters found for "${storyName}"`);
        }
    } catch (error) {
        console.error('Error loading chapters:', error);
        alert('Failed to load chapters');
    }
}

/**
 * Update the Continue Listening section
 */
async function updateContinueListening() {
    const progress = await ProgressTracker.load();

    if (!progress || !progress.story) {
        DOM.continueSection.style.display = 'none';
        return;
    }

    // Show the section
    DOM.continueSection.style.display = 'block';

    // Update UI
    DOM.continueTitle.textContent = progress.story;
    DOM.continueChapter.textContent = `Chapter ${progress.chapterIndex + 1}: ${getChapterName(progress.chapterFile)}`;
    DOM.continueMeta.textContent = 'Narrated by AI';

    // Calculate progress percentage
    const totalChapters = await getChapterCount(progress.story);
    const progressPercent = totalChapters > 0
        ? Math.round(((progress.chapterIndex + 1) / totalChapters) * 100)
        : 0;

    DOM.continuePercent.textContent = `${progressPercent}% COMPLETED`;
    DOM.continueFill.style.width = `${progressPercent}%`;

    // Format time
    DOM.continueTime.textContent = formatTime(progress.playbackTime || 0);

    // Add click handler
    DOM.continueCard.onclick = async () => {
        await resumeListening();
    };

    DOM.resumeBtn.onclick = async (e) => {
        e.stopPropagation();
        await resumeListening();
    };
}

/**
 * Get chapter name from filename
 */
function getChapterName(filename) {
    if (!filename) return 'Unknown';
    const name = filename.replace('.mp3', '').replace(/_/g, ' ');
    return name.length > 30 ? name.substring(0, 30) + '...' : name;
}

/**
 * Get chapter count for a story
 */
async function getChapterCount(storyName) {
    try {
        const response = await fetch(`/api/stories/${encodeURIComponent(storyName)}`);
        const data = await response.json();
        return data.files ? data.files.length : 0;
    } catch (error) {
        return 0;
    }
}

/**
 * Initialize search functionality
 */
function initializeSearch() {
    if (!DOM.searchIcon || !DOM.searchContainer || !DOM.librarySearch) return;

    // Toggle search bar
    DOM.searchIcon.addEventListener('click', () => {
        DOM.searchContainer.style.display = 'flex';
        DOM.librarySearch.focus();
    });

    DOM.searchClose.addEventListener('click', () => {
        DOM.searchContainer.style.display = 'none';
        DOM.librarySearch.value = '';
        renderLibraryGrid(availableStories);
    });

    // Search as user types
    DOM.librarySearch.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = availableStories.filter(story =>
            story.toLowerCase().includes(query)
        );
        renderLibraryGrid(filtered);
    });
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * Format seconds to MM:SS
 * @param {number} seconds - Time in seconds
 * @returns {string} Formatted time string
 */
function formatTime(seconds) {
    if (isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Show empty state message
 * @param {string} message - Message to display
 */
function showEmptyState(message = 'Select a story to start listening') {
    DOM.chapterList.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">🎧</div>
            <div>${message}</div>
        </div>
    `;
    DOM.sectionTitle.style.display = 'none';
}

/**
 * Log error to console
 * @param {string} context - Error context
 * @param {Error} error - Error object
 */
function logError(context, error) {
    console.error(`[Player Error - ${context}]:`, error);
    showToast(`Error: ${error.message || error}`, 'error');
}

/**
 * Show a simple notification toast
 * @param {string} message 
 * @param {string} type 
 */
function showToast(message, type = 'info') {
    // Basic alert for now, can be improved to a better UI toast later
    console.log(`[${type.toUpperCase()}] ${message}`);
    if (type === 'error') alert(message);
}

/**
 * Open a modal by ID
 * @param {string} id 
 */
function openModal(id) {
    document.getElementById(id).classList.add('active');
}

/**
 * Close a modal by ID
 * @param {string} id 
 */
function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// ============================================
// WAVEFORM FUNCTIONS
// ============================================

/**
 * Generate waveform visualization bars
 */
function generateWaveform() {
    DOM.waveform.innerHTML = '';
    const barCount = 50;

    for (let i = 0; i < barCount; i++) {
        const bar = document.createElement('div');
        bar.className = 'waveform-bar';
        const height = Math.random() * 80 + 20;
        bar.style.height = `${height}%`;
        DOM.waveform.appendChild(bar);
    }
}

/**
 * Update waveform progress based on current playback time
 */
function updateWaveform() {
    if (!DOM.audioPlayer.duration) return;

    const progress = DOM.audioPlayer.currentTime / DOM.audioPlayer.duration;
    const bars = DOM.waveform.querySelectorAll('.waveform-bar');

    bars.forEach((bar, index) => {
        if (index / bars.length < progress) {
            bar.classList.add('active');
        } else {
            bar.classList.remove('active');
        }
    });
}

// ============================================
// API FUNCTIONS
// ============================================

/**
 * Load all available stories from server
 */
async function loadStories() {
    try {
        const response = await fetch(CONFIG.API_BASE_URL + '/api/stories');
        const data = await response.json();

        data.stories.forEach(story => {
            const option = document.createElement('option');
            option.value = story;
            option.textContent = story;
            DOM.storySelect.appendChild(option);
        });
    } catch (error) {
        logError('loadStories', error);
        showEmptyState('Error loading stories. Please refresh the page.');
    }
}

/**
 * Load chapters for selected story
 */
async function loadChapters() {
    PlayerState.currentStory = DOM.storySelect.value;

    if (!PlayerState.currentStory) {
        showEmptyState();
        return;
    }

    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/stories/${encodeURIComponent(PlayerState.currentStory)}`);
        const data = await response.json();
        PlayerState.currentFiles = data.files;

        DOM.sectionTitle.style.display = 'block';
        DOM.chapterList.innerHTML = '';

        PlayerState.currentFiles.forEach((file, index) => {
            const item = createChapterItem(file, index);
            DOM.chapterList.appendChild(item);
        });
    } catch (error) {
        logError('loadChapters', error);
        showEmptyState('Error loading chapters. Please try again.');
    }
}

/**
 * Create chapter list item element
 * @param {string} file - Chapter filename
 * @param {number} index - Chapter index
 * @returns {HTMLElement} Chapter item element
 */
function createChapterItem(file, index) {
    const item = document.createElement('div');
    item.className = 'chapter-item';
    item.innerHTML = `
        <div class="chapter-number">${(index + 1).toString().padStart(2, '0')}</div>
        <div class="chapter-info">
            <div class="chapter-title">${file.replace('.mp3', '')}</div>
            <div class="chapter-duration">Chapter ${index + 1}</div>
        </div>
    `;

    item.onclick = () => {
        closePlayerOnMobile();
        setTimeout(() => playFile(index), 300);
    };

    return item;
}

// ============================================
// PLAYBACK FUNCTIONS
// ============================================

/**
 * Play file at specified index
 * @param {number} index - File index to play
 * @param {number} startTime - Optional start time in seconds
 */
function playFile(index, startTime = 0) {
    if (index < 0 || index >= PlayerState.currentFiles.length) return;

    PlayerState.currentIndex = index;
    const file = PlayerState.currentFiles[index];

    // Update UI
    updateChapterActiveState(index);
    updateTrackInfo(file);

    // Load and play audio
    DOM.audioPlayer.src = `/stream/${encodeURIComponent(PlayerState.currentStory)}/${encodeURIComponent(file)}`;
    DOM.audioPlayer.playbackRate = PlayerState.currentSpeed;

    // Set start time when metadata is loaded
    if (startTime > 0) {
        DOM.audioPlayer.addEventListener('loadedmetadata', function setStartTime() {
            DOM.audioPlayer.currentTime = startTime;
            DOM.audioPlayer.removeEventListener('loadedmetadata', setStartTime);
        });
    }

    DOM.audioPlayer.play();

    // Update player state
    showPlayer();
    setPlayingState(true);
    generateWaveform();
}

/**
 * Update active state for chapter items
 * @param {number} activeIndex - Index of active chapter
 */
function updateChapterActiveState(activeIndex) {
    document.querySelectorAll('.chapter-item').forEach((el, i) => {
        el.classList.toggle('active', i === activeIndex);
    });
}

/**
 * Update track information display
 * @param {string} file - Current file name
 */
function updateTrackInfo(file) {
    const title = file.replace('.mp3', '');
    const folderIcon = '<span style="font-size: 0.8em; margin-left: 8px; opacity: 0.6; vertical-align: middle;">📁</span>';
    
    // Set text and icon
    DOM.trackTitle.innerHTML = title + folderIcon;
    DOM.trackArtist.textContent = PlayerState.currentStory;
    
    DOM.miniTrackTitle.innerHTML = title + folderIcon;
    DOM.miniTrackArtist.textContent = PlayerState.currentStory;
}

/**
 * Show player view
 */
function showPlayer() {
    DOM.playerView.classList.add('active');
    DOM.miniPlayer.classList.add('active');
}

/**
 * Set playing state and update UI
 * @param {boolean} playing - Whether audio is playing
 */
function setPlayingState(playing) {
    PlayerState.isPlaying = playing;
    const icon = playing ? '⏸' : '▶';

    DOM.playBtn.textContent = icon;
    DOM.miniPlayBtn.textContent = icon;
    DOM.playBtn.classList.toggle('playing', playing);
}

/**
 * Toggle play/pause
 */
function togglePlayPause() {
    if (PlayerState.isPlaying) {
        DOM.audioPlayer.pause();
        setPlayingState(false);
    } else {
        DOM.audioPlayer.play();
        setPlayingState(true);
    }
}

/**
 * Play previous track
 */
function playPrevious() {
    if (PlayerState.currentIndex > 0) {
        playFile(PlayerState.currentIndex - 1);
    }
}

/**
 * Play next track
 */
function playNext() {
    if (PlayerState.isRepeating) {
        DOM.audioPlayer.currentTime = 0;
        DOM.audioPlayer.play();
    } else if (PlayerState.currentIndex + 1 < PlayerState.currentFiles.length) {
        playFile(PlayerState.currentIndex + 1);
    } else {
        setPlayingState(false);
    }
}

// ============================================
// CONTROL FUNCTIONS
// ============================================

/**
 * Toggle shuffle mode
 */
function toggleShuffle() {
    PlayerState.isShuffled = !PlayerState.isShuffled;
    DOM.shuffleBtn.style.color = PlayerState.isShuffled ? 'var(--primary)' : '';
}

/**
 * Toggle repeat mode
 */
function toggleRepeat() {
    PlayerState.isRepeating = !PlayerState.isRepeating;
    DOM.repeatBtn.style.color = PlayerState.isRepeating ? 'var(--primary)' : '';
}

/**
 * Set playback speed
 * @param {number} speed - Playback speed multiplier
 */
function setPlaybackSpeed(speed) {
    PlayerState.currentSpeed = speed;
    DOM.audioPlayer.playbackRate = speed;

    // Update active button
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.classList.toggle('active', parseFloat(btn.dataset.speed) === speed);
    });
}

/**
 * Seek to position in waveform
 * @param {MouseEvent} event - Click event
 */
function seekWaveform(event) {
    const rect = DOM.waveform.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const percentage = x / rect.width;
    DOM.audioPlayer.currentTime = DOM.audioPlayer.duration * percentage;
}

/**
 * Close player on mobile devices
 */
function closePlayerOnMobile() {
    if (window.innerWidth <= 768) {
        DOM.playerView.classList.remove('active');
    }
}

/**
 * Search/filter chapters
 * @param {string} query - Search query
 */
function searchChapters(query) {
    const lowerQuery = query.toLowerCase();

    document.querySelectorAll('.chapter-item').forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(lowerQuery) ? 'flex' : 'none';
    });
}

// ============================================
// MENU & TASK FUNCTIONS
// ============================================

/**
 * Toggle sidebar menu visibility
 */
function toggleSidebar(show) {
    if (show) {
        DOM.sidebar.classList.add('active');
        DOM.sidebarOverlay.classList.add('active');
    } else {
        DOM.sidebar.classList.remove('active');
        DOM.sidebarOverlay.classList.remove('active');
    }
}

/**
 * Poll for active tasks status
 */
/**
 * Trigger an action on the server
 * Real-time feedback is handled by TaskTracker (WebSockets)
 */
async function triggerAction(endpoint, data = {}) {
    try {
        const response = await fetch(CONFIG.API_BASE_URL + endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        console.log(`Action ${endpoint} triggered:`, result);
        
        // Open sidebar to show progress if not already open
        toggleSidebar(true);
        return result;
    } catch (error) {
        logError('triggerAction', error);
        showToast('Action failed to start', 'error');
    }
}


// ============================================
// EVENT LISTENERS
// ============================================

/**
 * Initialize all event listeners
 */
function initializeEventListeners() {
    // Playback controls
    DOM.playBtn.addEventListener('click', togglePlayPause);
    DOM.miniPlayBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        togglePlayPause();
    });

    DOM.prevBtn.addEventListener('click', playPrevious);
    DOM.miniPrevBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        playPrevious();
    });

    DOM.nextBtn.addEventListener('click', playNext);
    DOM.miniNextBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        playNext();
    });

    // Mode toggles
    DOM.shuffleBtn.addEventListener('click', toggleShuffle);
    DOM.repeatBtn.addEventListener('click', toggleRepeat);

    // Speed control
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const speed = parseFloat(btn.dataset.speed);
            setPlaybackSpeed(speed);
        });
    });

    // Waveform seeking
    DOM.waveform.addEventListener('click', seekWaveform);

    // Audio events
    DOM.audioPlayer.addEventListener('timeupdate', () => {
        DOM.currentTimeEl.textContent = formatTime(DOM.audioPlayer.currentTime);
        updateWaveform();

        // Save progress every 5 seconds
        if (Math.floor(DOM.audioPlayer.currentTime) % 5 === 0) {
            ProgressTracker.save();
        }
    });

    DOM.audioPlayer.addEventListener('loadedmetadata', () => {
        DOM.totalTimeEl.textContent = formatTime(DOM.audioPlayer.duration);
    });

    DOM.audioPlayer.addEventListener('ended', () => {
        ProgressTracker.save();
        playNext();
    });

    // Save progress when pausing
    DOM.audioPlayer.addEventListener('pause', () => {
        ProgressTracker.save();
    });

    // Save progress before page unload
    window.addEventListener('beforeunload', () => {
        ProgressTracker.save();
    });

    // UI events (old elements - add null checks)
    if (DOM.storySelect) {
        DOM.storySelect.addEventListener('change', loadChapters);
    }

    if (DOM.miniPlayer) {
        DOM.miniPlayer.addEventListener('click', () => {
            if (PlayerState.currentIndex >= 0) {
                DOM.playerView.classList.add('active');
            }
        });
    }

    // Player Close Button
    if (DOM.playerClose) {
        DOM.playerClose.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            DOM.playerView.classList.remove('active');
            DOM.miniPlayer.classList.add('active');
        });
    }

    // Mini player click - open full player
    if (DOM.miniPlayer) {
        DOM.miniPlayer.addEventListener('click', (e) => {
            // Don't trigger if clicking on control buttons or title (which now has its own listener)
            if (!e.target.closest('.mini-control-btn') && !e.target.closest('.mini-track-title')) {
                DOM.playerView.classList.add('active');
                DOM.miniPlayer.classList.remove('active');
            }
        });
    }

    // Navigation: Click episode title to go to story folder
    if (DOM.trackTitle) {
        DOM.trackTitle.style.cursor = 'pointer';
        DOM.trackTitle.title = 'Go to story folder';
        DOM.trackTitle.addEventListener('click', () => {
            if (PlayerState.currentStory) {
                // Minimize player
                DOM.playerView.classList.remove('active');
                DOM.miniPlayer.classList.add('active');
                // Navigate to chapter list
                if (typeof selectStoryForChapterView === 'function') {
                    selectStoryForChapterView(PlayerState.currentStory);
                } else {
                    console.error('selectStoryForChapterView not found');
                }
            }
        });
    }

    if (DOM.miniTrackTitle) {
        DOM.miniTrackTitle.style.cursor = 'pointer';
        DOM.miniTrackTitle.title = 'Go to story folder';
        DOM.miniTrackTitle.addEventListener('click', (e) => {
            e.stopPropagation(); // Avoid opening full player
            if (PlayerState.currentStory) {
                if (typeof selectStoryForChapterView === 'function') {
                    selectStoryForChapterView(PlayerState.currentStory);
                } else {
                    console.error('selectStoryForChapterView not found');
                }
            }
        });
    }

    if (DOM.searchBar) {
        DOM.searchBar.addEventListener('input', (e) => {
            searchChapters(e.target.value);
        });
    }

    // Menu Controls
    DOM.menuIcon.addEventListener('click', () => toggleSidebar(true));
    DOM.menuClose.addEventListener('click', () => toggleSidebar(false));
    DOM.sidebarOverlay.addEventListener('click', () => toggleSidebar(false));

    DOM.menuScrapeBtn.addEventListener('click', () => {
        toggleSidebar(false);
        openModal('scrapeModal');
    });

    // Modal close & cancel buttons
    if (DOM.scrapeModalClose) {
        DOM.scrapeModalClose.addEventListener('click', () => closeModal('scrapeModal'));
    }
    if (DOM.scrapeModalCancel) {
        DOM.scrapeModalCancel.addEventListener('click', () => closeModal('scrapeModal'));
    }

    DOM.startScrapeBtn.addEventListener('click', async () => {
        const url = DOM.scrapeUrl.value;
        if (!url) {
            alert('Please enter a URL');
            return;
        }
        closeModal('scrapeModal');
        await triggerAction('/api/actions/scrape', {
            url: url,
            fast_mode: DOM.scrapeFast.checked,
            headless: DOM.scrapeHeadless.checked
        });
    });

    DOM.menuConvertBtn.addEventListener('click', async () => {
        if (!PlayerState.currentStory) {
            alert('Please select a story first');
            return;
        }
        toggleSidebar(false);
        await triggerAction('/api/actions/convert', { story_name: PlayerState.currentStory });
    });

    DOM.menuCleanBtn.addEventListener('click', async () => {
        if (!PlayerState.currentStory) {
            alert('Please select a story first');
            return;
        }
        toggleSidebar(false);
        await triggerAction('/api/actions/clean', { story_name: PlayerState.currentStory });
    });

    DOM.menuCheckUpdatesBtn.addEventListener('click', async () => {
        toggleSidebar(false);
        await triggerAction('/api/actions/check-updates');
    });
}

/**
 * Resume from saved progress
 */
async function resumeListening() {
    const progress = await ProgressTracker.load();
    if (!progress) return false;

    console.log('🔄 Resuming from saved progress...');

    // Set the current story
    PlayerState.currentStory = progress.story;

    try {
        // Load chapters for this story
        const response = await fetch(`/api/stories/${encodeURIComponent(progress.story)}`);
        const data = await response.json();

        if (data.files && data.files.length > 0) {
            PlayerState.currentFiles = data.files;
            console.log('📑 Loaded', data.files.length, 'chapters for resume');

            // Find the chapter index
            const chapterIndex = PlayerState.currentFiles.findIndex(f => f === progress.chapterFile);

            if (chapterIndex >= 0) {
                // Restore playback speed
                if (progress.speed) {
                    setPlaybackSpeed(progress.speed);
                }

                // Play from saved position
                playFile(chapterIndex, progress.playbackTime);

                console.log('✅ Resumed successfully');
                return true;
            } else {
                console.warn('⚠️ Chapter not found:', progress.chapterFile);
                alert('Could not find the saved chapter. Starting from beginning.');
                playFile(0);
                return false;
            }
        } else {
            console.error('❌ No chapters found for story:', progress.story);
            alert('No chapters found for this story.');
            return false;
        }
    } catch (error) {
        console.error('❌ Error resuming:', error);
        alert('Failed to resume playback: ' + error.message);
        return false;
    }
}

/**
 * Show continue listening banner
 */
async function showContinueBanner() {
    const progress = await ProgressTracker.load();
    if (!progress) return;

    // Create banner element
    const banner = document.createElement('div');
    banner.id = 'continueBanner';
    banner.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, var(--primary), var(--secondary));
        color: white;
        padding: 15px 25px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        z-index: 9999;
        display: flex;
        align-items: center;
        gap: 15px;
        animation: slideDown 0.3s ease-out;
        cursor: pointer;
        max-width: 90%;
    `;

    banner.innerHTML = `
        <div style="font-size: 24px;">▶️</div>
        <div style="flex: 1;">
            <div style="font-weight: bold; font-size: 14px;">Continue Listening</div>
            <div style="font-size: 12px; opacity: 0.9;">${progress.story} - Chapter ${progress.chapterIndex + 1}</div>
        </div>
        <button id="dismissBanner" style="background: rgba(255,255,255,0.2); border: none; color: white; padding: 8px 12px; border-radius: 6px; cursor: pointer; font-size: 12px;">Dismiss</button>
    `;

    // Add animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideDown {
            from { transform: translateX(-50%) translateY(-100%); opacity: 0; }
            to { transform: translateX(-50%) translateY(0); opacity: 1; }
        }
    `;
    document.head.appendChild(style);

    document.body.appendChild(banner);

    // Click to resume
    banner.addEventListener('click', async (e) => {
        if (e.target.id !== 'dismissBanner') {
            banner.remove();
            await resumeListening();
        }
    });

    // Dismiss button
    document.getElementById('dismissBanner').addEventListener('click', (e) => {
        e.stopPropagation();
        banner.remove();
    });

    // Auto-hide after 10 seconds
    setTimeout(() => {
        if (banner.parentElement) {
            banner.style.animation = 'slideDown 0.3s ease-out reverse';
            setTimeout(() => banner.remove(), 300);
        }
    }, 10000);
}

// ============================================
// TASK WEB SOCKET SYSTEM (Using Shared TaskTracker)
// ============================================

/**
 * Initialize Task Tracking using TaskTracker module
 */
function initializeTaskTracking() {
    if (typeof TaskTracker !== 'undefined') {
        TaskTracker.init('taskStatus');
        
        // Custom callback to reload library when a task finishes
        TaskTracker.onUpdate((task) => {
            if (task && task.status === 'completed') {
                showToast('Processing complete! Refreshing library...', 'success');
                loadLibrary();
            }
        });
    } else {
        console.warn('TaskTracker module not loaded.');
    }
}

// ============================================
// INITIALIZATION
// ============================================

/**
 * Initialize the player application
 */
async function initializePlayer() {
    console.log('🎵 Initializing Audio Player...');

    // Load library grid
    await loadLibrary();
    generateWaveform();

    // Setup event listeners
    initializeEventListeners();
    initializeSearch();
    initializeTaskTracking();

    // Handle initial story from URL
    const urlParams = new URLSearchParams(window.location.search);
    const initialStory = urlParams.get('story');
    if (initialStory) {
        console.log('Loading initial story from URL:', initialStory);
        const storyCard = Array.from(document.querySelectorAll('.story-card'))
            .find(card => card.dataset.name === initialStory);
        if (storyCard) {
            storyCard.click();
        }
    }

    console.log('✅ Audio Player Ready');
}

// Start the application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePlayer);
} else {
    initializePlayer();
}

// ============================================
// EXPORT FOR TESTING (if needed)
// ============================================
// Debug Console Toggle (5 taps on title)
let titleClicks = 0;
document.querySelector('.app-title').addEventListener('click', () => {
    titleClicks++;
    if (titleClicks >= 5) {
        const debugBox = document.getElementById('debugConsole');
        debugBox.style.display = debugBox.style.display === 'none' ? 'block' : 'none';
        debugBox.style.pointerEvents = debugBox.style.display === 'none' ? 'none' : 'auto';
        debugLog('Debug console toggled. Hostname: ' + window.location.hostname);
        titleClicks = 0;
    }
    setTimeout(() => { if (titleClicks > 0) titleClicks--; }, 3000);
});

debugLog('App initialized. Env: ' + (CONFIG.API_BASE_URL ? 'Cloud' : 'Local'));
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        PlayerState,
        formatTime,
        playFile,
        togglePlayPause,
        setPlaybackSpeed
    };
}