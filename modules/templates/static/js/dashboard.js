/**
 * CYBERPUNK TTS - DASHBOARD LOGIC v2.0
 * Fully integrated with TaskTracker for real-time status.
 */

const CONFIG = {
    // If running on local network (IP), hostname (localhost), or development, use relative paths.
    API_BASE_URL: (
        window.location.hostname.includes('onrender.com') || 
        window.location.hostname.includes('firebaseapp.com')
    ) ? 'https://sixaudio-backend.onrender.com' : ''
};

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
    dashMenuClose: document.getElementById('dashMenuClose'),
    sidebarClose: document.getElementById('sidebarClose')
};

/**
 * INITIALIZATION
 */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Task Tracking
    if (typeof TaskTracker !== 'undefined') {
        TaskTracker.init('taskStatus');
        TaskTracker.onUpdate((id, data) => {
            if (data && data.status === 'completed') {
                console.log('✅ Task finished:', id);
                setTimeout(fetchLibrary, 1500); // Reload library when a task finishes
            }
        });
    }

    fetchLibrary();

    // Event Listeners
    if (DOM.startScrapeBtn) DOM.startScrapeBtn.addEventListener('click', startScraping);
    if (DOM.scrapeNewBtn) DOM.scrapeNewBtn.addEventListener('click', () => openModal('scrapeModal'));
    if (DOM.refreshAllBtn) DOM.refreshAllBtn.addEventListener('click', checkUpdates);

    // Modal close/cancel
    [DOM.dashScrapeModalClose, DOM.dashScrapeModalCancel].forEach(el => {
        if (el) el.addEventListener('click', () => closeModal('scrapeModal'));
    });

    // Sidebar close
    [DOM.dashMenuClose, DOM.sidebarClose, DOM.sidebarOverlay].forEach(el => {
        if (el) el.addEventListener('click', () => toggleSidebar(false));
    });
});

/**
 * FETCH LIBRARY DATA
 */
async function fetchLibrary() {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/library/status`);
        const data = await response.json();

        if (data.error) throw new Error(data.error);
        renderLibrary(data);
    } catch (error) {
        console.error('Failed to fetch library:', error);
        DOM.libraryGrid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; background: rgba(255,0,0,0.1); border: 1px solid red; border-radius: 10px;">
                <h3 style="color: #ff4444;">DATABASE ERROR</h3>
                <p style="color: var(--text-secondary); margin-top: 10px;">${error.message}</p>
                <button class="action-btn" style="margin-top: 15px;" onclick="fetchLibrary()">RETRY SCAN</button>
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
                <button class="action-btn" onclick="triggerAction('fix-empty', '${story.name}')" title="Fix empty chapters">🔧 FIX</button>
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
    if (url) DOM.scrapeUrl.value = url;
    openModal('scrapeModal');
}

async function triggerAction(action, storyName) {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/actions/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ story_name: storyName })
        });
        const result = await response.json();
        console.log(`Action ${action} triggered:`, result);
        toggleSidebar(true); // Open sidebar to show progress
    } catch (error) {
        console.error(`Action ${action} failed:`, error);
        alert('Action failed. See console.');
    }
}

async function startScraping() {
    const url = DOM.scrapeUrl.value;
    if (!url) return alert('Please enter a story URL');

    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/api/actions/scrape`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                fast_mode: DOM.scrapeFast.checked,
                headless: DOM.scrapeHeadless.checked
            })
        });
        const result = await response.json();
        console.log("Scrape triggered:", result);
        closeModal('scrapeModal');
        toggleSidebar(true);
    } catch (error) {
        console.error('Scraping request failed:', error);
        alert('Request failed.');
    }
}

async function checkUpdates() {
    try {
        await fetch(`${CONFIG.API_BASE_URL}/api/actions/check-updates`, { method: 'POST' });
        toggleSidebar(true);
    } catch (error) {
        console.error('Update check failed:', error);
    }
}

/**
 * UI HELPERS
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

function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('active');
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('active');
}
