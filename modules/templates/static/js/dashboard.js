/**
 * CYBERPUNK TTS - DASHBOARD LOGIC
 */

const DOM = {
    libraryGrid: document.getElementById('libraryGrid'),
    taskStatus: document.getElementById('taskStatus'),
    sidebar: document.getElementById('sidebar'),
    sidebarOverlay: document.getElementById('sidebarOverlay'),
    scrapeModal: document.getElementById('scrapeModal'),
    scrapeUrl: document.getElementById('scrapeUrl'),
    scrapeFast: document.getElementById('scrapeFast'),
    scrapeHeadless: document.getElementById('scrapeHeadless'),
    startScrapeBtn: document.getElementById('startScrapeBtn'),
    scrapeNewBtn: document.getElementById('scrapeNewBtn'),
    refreshAllBtn: document.getElementById('refreshAllBtn'),
    dashScrapeModalClose: document.getElementById('dashScrapeModalClose'),
    dashScrapeModalCancel: document.getElementById('dashScrapeModalCancel'),
    dashMenuClose: document.getElementById('dashMenuClose')
};

/**
 * INITIALIZATION
 */
document.addEventListener('DOMContentLoaded', () => {
    fetchLibrary();
    pollTasks();

    DOM.startScrapeBtn.addEventListener('click', startScraping);

    // Header buttons
    if (DOM.scrapeNewBtn) DOM.scrapeNewBtn.addEventListener('click', () => openModal('scrapeModal'));
    if (DOM.refreshAllBtn) DOM.refreshAllBtn.addEventListener('click', checkUpdates);

    // Modal close/cancel
    if (DOM.dashScrapeModalClose) DOM.dashScrapeModalClose.addEventListener('click', () => closeModal('scrapeModal'));
    if (DOM.dashScrapeModalCancel) DOM.dashScrapeModalCancel.addEventListener('click', () => closeModal('scrapeModal'));

    // Sidebar close
    if (DOM.dashMenuClose) DOM.dashMenuClose.addEventListener('click', () => toggleSidebar(false));
    if (DOM.sidebarOverlay) DOM.sidebarOverlay.addEventListener('click', () => toggleSidebar(false));
});

/**
 * FETCH LIBRARY DATA
 */
async function fetchLibrary() {
    try {
        const response = await fetch('/api/library/status');
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        renderLibrary(data);
    } catch (error) {
        console.error('Failed to fetch library:', error);
        DOM.libraryGrid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; background: rgba(255,0,0,0.1); border: 1px solid red; border-radius: 10px;">
                <h3 style="color: #ff4444;">DATABASE ERROR</h3>
                <p style="color: var(--text-secondary); margin-top: 10px;">${error.message}</p>
                <button class="btn btn-secondary" style="margin-top: 15px;" onclick="fetchLibrary()">RETRY SCAN</button>
            </div>
        `;
    }
}

/**
 * RENDER LIBRARY GRID
 */
function renderLibrary(stories) {
    if (!Array.isArray(stories) || stories.length === 0) {
        DOM.libraryGrid.innerHTML = '<div class="stat-item" style="grid-column: 1/-1; text-align: center; padding: 40px; opacity: 0.5;">LIBRARY IS EMPTY OR DATABASE IS INITIALIZING...</div>';
        return;
    }

    DOM.libraryGrid.innerHTML = '';
    stories.forEach(story => {
        const ttsProgress = (story.mp3_count / story.txt_count * 100) || 0;
        const statusClass = story.status === 'completed' ? 'status-completed' : 'status-active';

        const card = document.createElement('div');
        card.className = 'story-card';
        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div class="story-title" title="${story.name}">${story.name}</div>
                <span class="status-badge ${statusClass}">${story.status}</span>
            </div>
            
            <div class="story-stats">
                <div class="stat-item">
                    <span class="stat-label">SCRAPED</span>
                    <span class="stat-value">${story.txt_count} Chapters</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">AUDIO</span>
                    <span class="stat-value">${story.mp3_count} Files</span>
                </div>
            </div>

            <div style="margin-top: 10px;">
                <div style="display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 3px;">
                    <span class="stat-label">SCRAPING PROGRESS</span>
                    <span class="stat-value">${story.progress.scraping.last_chapter_number || 0} / ${story.progress.scraping.total_chapters || story.txt_count} Chapters</span>
                </div>
                <div class="progress-mini">
                    <div class="progress-fill-mini" style="width: ${((story.progress.scraping.last_chapter_number || 0) / (story.progress.scraping.total_chapters || story.txt_count || 1)) * 100}%; background: #00f2ff;"></div>
                </div>
            </div>

            <div style="margin-top: 5px;">
                <div style="display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 3px;">
                    <span class="stat-label">TTS PROGRESS</span>
                    <span class="stat-value">${Math.round(ttsProgress)}%</span>
                </div>
                <div class="progress-mini">
                    <div class="progress-fill-mini" style="width: ${ttsProgress}%"></div>
                </div>
            </div>

            <div class="card-actions">
                <button class="action-btn" onclick="openScrapeForStory('${story.progress.metadata.story_url}')">🕷️ SCRAPE</button>
                <button class="action-btn" onclick="triggerAction('fix-empty', '${story.name}')" title="Fix chapters with no content">🔧 FIX</button>
                <button class="action-btn" onclick="triggerAction('clean', '${story.name}')">🧹 CLEAN</button>
                <button class="action-btn primary" onclick="triggerAction('convert', '${story.name}')">🎧 CONVERT</button>
                <button class="action-btn" style="grid-column: span 4;" onclick="window.location.href='/?story=${encodeURIComponent(story.name)}'">▶️ PLAY IN PLAYER</button>
            </div>
        `;
        DOM.libraryGrid.appendChild(card);
    });
}

/**
 * ACTIONS
 */
function openScrapeForStory(url) {
    if (url) {
        DOM.scrapeUrl.value = url;
    } else {
        DOM.scrapeUrl.value = '';
    }
    openModal('scrapeModal');
}
async function triggerAction(action, storyName) {
    try {
        const response = await fetch(`/api/actions/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ story_name: storyName })
        });
        const result = await response.json();
        toggleSidebar(true);
        pollTasks();
    } catch (error) {
        alert('Action failed: ' + error.message);
    }
}

async function startScraping() {
    const url = DOM.scrapeUrl.value;
    if (!url) return alert('Enter URL');

    try {
        const response = await fetch('/api/actions/scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                fast_mode: DOM.scrapeFast.checked,
                headless: DOM.scrapeHeadless.checked
            })
        });
        closeModal('scrapeModal');
        toggleSidebar(true);
        pollTasks();
    } catch (error) {
        alert('Scraping failed');
    }
}

async function checkUpdates() {
    try {
        await fetch('/api/actions/check-updates');
        toggleSidebar(true);
        pollTasks();
    } catch (error) {
        alert('Update check failed');
    }
}

/**
 * TASK POLLING (Shared logic)
 */
async function pollTasks() {
    try {
        const response = await fetch('/api/tasks/status');
        const tasks = await response.json();

        // Update global task state for card rendering
        currentTasks = tasks;

        const taskIds = Object.keys(tasks);
        if (taskIds.length === 0) {
            DOM.taskStatus.innerHTML = '<div style="font-size: 11px; opacity: 0.5; text-align: center; padding: 20px;">No active tasks</div>';
            // If tasks were just cleared, refresh the grid one last time
            if (Object.keys(currentTasks).length > 0) {
                currentTasks = {};
                fetchLibrary();
            }
            return;
        }

        DOM.taskStatus.innerHTML = '';
        let hasJustFinished = false;

        taskIds.forEach(id => {
            const task = tasks[id];
            const card = document.createElement('div');
            card.className = 'task-card';
            card.innerHTML = `
                <div class="task-title">
                    <span>${id.split('_')[0].toUpperCase()}</span>
                    <span>${task.status}</span>
                </div>
                <div class="task-msg">${task.message}</div>
                <div class="task-progress-bar">
                    <div class="task-progress-fill" style="width: ${task.progress}%"></div>
                </div>
            `;
            DOM.taskStatus.appendChild(card);

            // If any task finished, mark for refresh
            if (task.status === 'completed' || task.status === 'failed') {
                hasJustFinished = true;
            }
        });

        // Dynamic update of library cards while tasks are running
        renderLibraryGridOnly();

        if (hasJustFinished) {
            setTimeout(fetchLibrary, 1000);
        }

        const hasActive = taskIds.some(id => tasks[id].status !== 'completed' && tasks[id].status !== 'failed');
        if (hasActive) setTimeout(pollTasks, 2000);
    } catch (error) { }
}

/**
 * RE-RENDER ONLY THE GRID WITHOUT FETCHING (for live updates)
 */
async function renderLibraryGridOnly() {
    // We actually need the story data to render correctly, 
    // but the task progress updates independently.
    // For now, pollTasks calls fetchLibrary on finish, 
    // and renderLibrary uses currentTasks for live progress.
    // To make it truly live, we'd need to cache stories.
    // Let's just call fetchLibrary every few polls if tasks are active.
}

/**
 * UI HELPERS
 */
function toggleSidebar(show) {
    if (show) {
        DOM.sidebar.style.transform = 'translateX(0)';
        DOM.sidebarOverlay.style.display = 'block';
        setTimeout(() => DOM.sidebarOverlay.style.opacity = '1', 10);
    } else {
        DOM.sidebar.style.transform = 'translateX(100%)';
        DOM.sidebarOverlay.style.opacity = '0';
        setTimeout(() => DOM.sidebarOverlay.style.display = 'none', 300);
    }
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
