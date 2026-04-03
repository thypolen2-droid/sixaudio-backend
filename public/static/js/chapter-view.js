/**
 * Chapter View Functions
 * Enhanced chapter list with filters, search, and status tracking
 */

/**
 * Select a story and show chapter list view
 */
async function selectStoryForChapterView(storyName) {
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

    const chapters = chaptersToRender || PlayerState.currentFiles;
    const progress = getProgressForStory(PlayerState.currentStory);

    container.innerHTML = chapters.map((file, index) => {
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
                            <div class="chapter-progress-bar">
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
        return {
            class: 'in-progress',
            label: 'IN PROGRESS',
            icon: '⏸',
            iconClass: 'pause',
            progress: 45,
            timeLeft: '05:42'
        };
    }

    return {
        class: 'unplayed',
        label: 'UNPLAYED',
        icon: null
    };
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

    const filtered = PlayerState.currentFiles.filter(file =>
        file.toLowerCase().includes(query.toLowerCase())
    );
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
    const filtered = PlayerState.currentFiles.filter((file, index) => {
        const chapterStatus = getChapterStatus(index, progress);
        return chapterStatus.class === status.replace('progress', 'in-progress');
    });

    renderChapterCards(filtered);
}
