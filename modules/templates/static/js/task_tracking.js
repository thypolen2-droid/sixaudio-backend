/**
 * Shared Task Tracking Module v2.0
 * Handles WebSocket connection and task status rendering across different views.
 * Cyberpunk Aesthetic Integration.
 */

const TaskTracker = {
    socket: null,
    onTaskUpdate: null,
    activeTasks: {},
    containerId: null,

    /**
     * Initialize WebSocket for task tracking
     * @param {string} containerId - The ID of the container to render tasks into
     */
    init(containerId) {
        this.containerId = containerId;
        this.renderContainer = document.getElementById(containerId);
        if (!this.renderContainer) {
            console.warn(`TaskTracker: Container #${containerId} not found.`);
            return;
        }

        // Apply styles to container
        this.renderContainer.classList.add('task-status-container');
        
        this.connect();
    },

    /**
     * Connect to the WebSocket
     */
    connect() {
        console.log('🔌 Connecting to Task WebSocket...');
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Use the same host as the current page
        const wsUrl = `${protocol}//${window.location.host}/ws/tasks`;
        
        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            console.log('✅ Task WebSocket Connected');
        };

        this.socket.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this.handleSocketMessage(msg);
            } catch (e) {
                console.error('TaskTracker WS Message Error:', e);
            }
        };

        this.socket.onerror = (error) => {
            console.warn('TaskTracker WS Error:', error);
        };

        this.socket.onclose = () => {
            console.log('🔌 Task WebSocket Disconnected. Reconnecting in 5s...');
            setTimeout(() => this.connect(), 5000);
        };
    },

    /**
     * Handle incoming socket messages based on backend protocol
     */
    handleSocketMessage(msg) {
        switch (msg.type) {
            case 'sync':
                this.activeTasks = msg.tasks || {};
                this.renderAll();
                break;
            case 'task_update':
            case 'task_finish':
                this.activeTasks[msg.task_id] = msg.data;
                this.updateTaskCardUI(msg.task_id, msg.data);
                if (this.onTaskUpdate) this.onTaskUpdate(msg.task_id, msg.data);
                break;
            case 'task_remove':
                delete this.activeTasks[msg.task_id];
                this.renderAll();
                break;
        }
    },

    /**
     * Render all active tasks
     */
    renderAll() {
        if (!this.renderContainer) return;
        
        const taskIds = Object.keys(this.activeTasks);
        if (taskIds.length === 0) {
            this.renderContainer.innerHTML = '<div style="font-size: 11px; opacity: 0.5; text-align: center; padding: 20px;">No active tasks</div>';
            return;
        }

        this.renderContainer.innerHTML = '';
        taskIds.forEach(id => {
            this.updateTaskCardUI(id, this.activeTasks[id]);
        });
    },

    /**
     * Update or create a single task card in the UI
     */
    updateTaskCardUI(taskId, task) {
        if (!this.renderContainer) return;

        let card = document.getElementById(`task-${taskId}`);
        if (!card) {
            card = document.createElement('div');
            card.id = `task-${taskId}`;
            card.className = 'task-card';
            this.renderContainer.appendChild(card);
        }

        // Apply status class
        card.className = `task-card status-${task.status || 'active'}`;

        const progress = task.progress || 0;
        const logs = task.logs || [];
        const logsHtml = logs.slice(-3).map((log, i) => 
            `<div class="log-entry ${i === logs.slice(-3).length - 1 ? 'active' : ''}">${log}</div>`
        ).join('');

        const type = taskId.split('_')[0].toUpperCase();

        card.innerHTML = `
            <div class="task-title">
                <span>${type} SYNC</span>
                <span>${task.status === 'completed' ? 'DONE' : (Math.round(progress) + '%')}</span>
            </div>
            <div class="task-msg">${task.message || 'Processing...'}</div>
            <div class="task-progress-bar">
                <div class="task-progress-fill" style="width: ${progress}%"></div>
            </div>
            <div class="task-logs">
                ${logsHtml || '<div class="log-entry">Waiting for logs...</div>'}
            </div>
        `;

        // If completed or failed, remove after delay
        if (task.status === 'completed' || task.status === 'failed') {
            setTimeout(() => {
                if (card.parentElement) {
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.95)';
                    card.style.transition = 'all 0.5s ease';
                    setTimeout(() => {
                        delete this.activeTasks[taskId];
                        card.remove();
                    }, 500);
                }
            }, 5000);
        }
    },

    /**
     * Set a callback for task updates
     */
    onUpdate(callback) {
        this.onTaskUpdate = callback;
    }
};
