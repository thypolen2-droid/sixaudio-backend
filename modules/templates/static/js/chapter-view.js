/**
 * Chapter View Functions
 * Enhanced chapter list with filters, search, and status tracking
 */

/**
 * Select a story and show chapter list view
 */
async function selectStoryForChapterView(storyName) {
    console.log('📚 Navigating to story:', storyName);

    // If already playing this story, just show the view
    if (PlayerState.currentStory === storyName && PlayerState.currentFiles.length > 0) {
        showChapterView(storyName);
        return;
    }

    try {
        const response = await fetch(`/api/stories/${encodeURIComponent(storyName)}`);
        const data = await response.json();

        if (data.files && data.files.length > 0) {
            // Update the state ONLY if we are starting a clean navigation 
            // OR if the player is currently idle for another story.
            // If the user wants to play this new story, the click on a CHAPTER card 
            // should handle the actual playback start.
            
            // For now, load files into state to render them
            PlayerState.currentStory = storyName;
            PlayerState.currentFiles = data.files;
            
            // If we are NOT already playing the current file, reset index
            if (!PlayerState.isPlaying) {
                PlayerState.currentIndex = -1;
            }
            
            console.log('📑 Loaded', data.files.length, 'chapters');
            showChapterView(storyName);
        } else {
            alert(`No chapters found for "${storyName}"`);
        }
    } catch (error) {
        console.error('Error loading chapters:', error);
        alert('Failed to load chapters');
    }
}

/**
 * Show the chapter list view
 */
function showChapterView(storyName) {
    const chapterView = document.getElementById('chapterView');
    const libraryContainer = document.querySelector('.library-container');
    const chapterViewTitle = document.getElementById('chapterViewTitle');

    if (!chapterView || !libraryContainer) return;

    // Update title
    if (chapterViewTitle) {
        chapterViewTitle.textContent = storyName;
    }

    // Hide library, show chapter view
    libraryContainer.style.display = 'none';
    chapterView.style.display = 'block';

    // Render chapters
    renderChapterCards();

    // Setup back button
    const backBtn = document.getElementById('chapterBackBtn');
    if (backBtn) {
        backBtn.onclick = () => {
            chapterView.style.display = 'none';
            libraryContainer.style.display = 'block';
        };
    }

    // Setup search
    const searchInput = document.getElementById('chapterSearch');
    if (searchInput) {
        searchInput.value = '';
        searchInput.oninput = (e) => {
            filterChapters(e.target.value);
        };
    }

    // Setup filter pills
    document.querySelectorAll('.filter-pill').forEach(pill => {
        pill.onclick = function () {
            document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
            this.classList.add('active');
            filterChaptersByStatus(this.dataset.filter);
        };
    });
}

/**
 * Render chapter cards
 */
function renderChapterCards(chaptersToRender = null) {
    const container = document.getElementById('chaptersContainer');
    if (!container) return;

    // Preserve original indexes when rendering a filtered list.
    const chapters = chaptersToRender || PlayerState.currentFiles.map((file, index) => ({ file, index }));
    const progress = getProgressForStory(PlayerState.currentStory);

    container.innerHTML = chapters.map(({ file, index }) => {
        const status = getChapterStatus(index, progress);

        return `
            <div class="chapter-card ${status.class}" data-index="${index}" onclick="playChapterFromList(${index})">
                <div class="chapter-number-badge ${status.class}">
                    ${index + 1}
                    ${status.icon ? `<div class="chapter-status-icon ${status.iconClass}">${status.icon}</div>` : ''}
                </div>
                <div class="chapter-card-content">
                    <div class="chapter-status-label ${status.class}">${status.label}</div>
                    <div class="chapter-card-title">${getChapterName(file)}</div>
                    ${status.progress !== undefined ? `
                        <div class="chapter-progress-container">
                            <div class="chapter-progress-bar" role="slider" tabindex="0"
                                 aria-label="Seek within chapter" aria-valuemin="0" aria-valuemax="100"
                                 aria-valuenow="${Math.round(status.progress)}" data-seek-index="${index}">
                                <div class="chapter-progress-fill" style="width: ${status.progress}%"></div>
                            </div>
                            <span class="chapter-time-left">${status.timeLeft || '0:00'} left</span>
                        </div>
                    ` : `
                        <div class="chapter-duration">0:00</div>
                    `}
                </div>
                <div class="chapter-actions">
                    ${status.class === 'unplayed' || status.class === 'in-progress' ?
                '<button class="chapter-action-btn chapter-play-btn">▶</button>' :
                '<button class="chapter-action-btn">⋮</button>'
            }
                </div>
            </div>
        `;
    }).join('');

    // Prevent a seek click from bubbling to the card and restarting the chapter.
    container.querySelectorAll('[data-seek-index]').forEach(bar => {
        const seek = event => seekChapterProgress(event, Number(bar.dataset.seekIndex));
        bar.addEventListener('click', seek);
        bar.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                seek(event);
            }
        });
    });

    ensureSavedProgressDuration(progress);

    // Scroll into view if there's an in-progress chapter
    setTimeout(() => {
        const activeCard = container.querySelector('.chapter-card.in-progress');
        if (activeCard) {
            activeCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, 300);
}

/**
 * Get chapter status (played, in-progress, unplayed)
 */
function getChapterStatus(index, progress) {
    if (!progress || progress.chapterIndex === undefined) {
        return {
            class: 'unplayed',
            label: 'UNPLAYED',
            icon: null
        };
    }

    if (index < progress.chapterIndex) {
        return {
            class: 'played',
            label: '✓ PLAYED',
            icon: '✓',
            iconClass: ''
        };
    }

    if (index === progress.chapterIndex) {
        const audio = document.getElementById('audioPlayer');
        const isCurrentChapter = PlayerState.currentIndex === index;
        const duration = isCurrentChapter && Number.isFinite(audio?.duration)
            ? audio.duration
            : Number(progress.duration);
        const elapsed = isCurrentChapter && Number.isFinite(audio?.currentTime)
            ? audio.currentTime
            : Number(progress.playbackTime) || 0;
        const progressPercent = Number.isFinite(duration) && duration > 0
            ? Math.min(100, Math.max(0, (elapsed / duration) * 100))
            : 0;

        return {
            class: 'in-progress',
            label: 'IN PROGRESS',
            icon: '⏸',
            iconClass: 'pause',
            progress: progressPercent,
            timeLeft: Number.isFinite(duration) && duration > 0
                ? formatTime(Math.max(0, duration - elapsed))
                : '—'
        };
    }

    return {
        class: 'unplayed',
        label: 'UNPLAYED',
        icon: null
    };
}

// A saved listening position does not include media metadata from older page
// versions. Load metadata for only the saved chapter, without playing it, so
// the chapter card can show an accurate percentage and remaining time.
let pendingDurationLookup = null;
function ensureSavedProgressDuration(progress) {
    if (!progress || Number.isFinite(Number(progress.duration)) || !progress.chapterFile) return;

    const lookupKey = `${progress.story}:${progress.chapterFile}`;
    if (pendingDurationLookup === lookupKey) return;
    pendingDurationLookup = lookupKey;

    const metadataAudio = new Audio();
    metadataAudio.preload = 'metadata';
    metadataAudio.addEventListener('loadedmetadata', () => {
        pendingDurationLookup = null;
        if (!Number.isFinite(metadataAudio.duration) || metadataAudio.duration <= 0) return;

        const saved = getProgressForStory(progress.story);
        if (!saved || saved.chapterFile !== progress.chapterFile) return;

        saved.duration = metadataAudio.duration;
        localStorage.setItem('tts_listening_progress', JSON.stringify(saved));
        refreshChapterProgress();
    }, { once: true });
    metadataAudio.addEventListener('error', () => { pendingDurationLookup = null; }, { once: true });
    metadataAudio.src = `/stream/${encodeURIComponent(progress.story)}/${encodeURIComponent(progress.chapterFile)}`;
}

/** Seek the current chapter from its progress track. */
function seekChapterProgress(event, index) {
    event.stopPropagation();
    const audio = document.getElementById('audioPlayer');
    if (PlayerState.currentIndex !== index || !Number.isFinite(audio?.duration) || audio.duration <= 0) return;

    const rect = event.currentTarget.getBoundingClientRect();
    const percentage = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    audio.currentTime = audio.duration * percentage;
    refreshChapterProgress();
}

/** Keep the open chapter view in sync while its audio plays. */
function refreshChapterProgress() {
    const chapterView = document.getElementById('chapterView');
    if (!chapterView || chapterView.style.display === 'none') return;

    const progress = getProgressForStory(PlayerState.currentStory);
    if (!progress || PlayerState.currentIndex !== progress.chapterIndex) return;

    const status = getChapterStatus(progress.chapterIndex, progress);
    const card = document.querySelector(`.chapter-card[data-index="${progress.chapterIndex}"]`);
    if (!card || status.progress === undefined) return;

    const fill = card.querySelector('.chapter-progress-fill');
    const time = card.querySelector('.chapter-time-left');
    const bar = card.querySelector('[data-seek-index]');
    if (fill) fill.style.width = `${status.progress}%`;
    if (time) time.textContent = `${status.timeLeft} left`;
    if (bar) bar.setAttribute('aria-valuenow', Math.round(status.progress));
}

/**
 * Get progress for current story
 */
function getProgressForStory(storyName) {
    try {
        const saved = localStorage.getItem('tts_listening_progress');
        if (saved) {
            const progress = JSON.parse(saved);
            if (progress.story === storyName) {
                return progress;
            }
        }
    } catch (error) {
        console.error('Error getting progress:', error);
    }
    return null;
}

/**
 * Play chapter from list
 */
function playChapterFromList(index) {
    playFile(index);

    // Close chapter view, show library
    const chapterView = document.getElementById('chapterView');
    if (chapterView) {
        chapterView.style.display = 'none';
    }

    const libraryContainer = document.querySelector('.library-container');
    if (libraryContainer) {
        libraryContainer.style.display = 'block';
    }
}

/**
 * Filter chapters by search query
 */
function filterChapters(query) {
    if (!query) {
        renderChapterCards();
        return;
    }

    const filtered = PlayerState.currentFiles
        .map((file, index) => ({ file, index }))
        .filter(({ file }) => file.toLowerCase().includes(query.toLowerCase()));
    renderChapterCards(filtered);
}

/**
 * Filter chapters by status
 */
function filterChaptersByStatus(status) {
    if (status === 'all') {
        renderChapterCards();
        return;
    }

    const progress = getProgressForStory(PlayerState.currentStory);
    const filtered = PlayerState.currentFiles.map((file, index) => ({ file, index })).filter(({ index }) => {
        const chapterStatus = getChapterStatus(index, progress);
        return chapterStatus.class === status.replace('progress', 'in-progress');
    });

    renderChapterCards(filtered);
}
