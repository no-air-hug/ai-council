/**
 * AI Council - Main Application
 * Handles navigation, configuration, global state, and session persistence.
 */

// Global state
const state = {
    currentView: 'session',
    currentMode: '16GB',
    sessionId: null,
    sessionActive: false,  // Track if session is in progress
    personas: [],
    workers: [],
    config: null,
    // Token tracking
    tokenStats: {
        totalTokens: 0,
        inputTokens: 0,
        outputTokens: 0,
        callCount: 0,
        workerContextLimit: 8192,
        synthContextLimit: 20480,
        lastWorkerContextUsed: 0,
        lastSynthContextUsed: 0
    }
};

// Session storage keys
const STORAGE_KEYS = {
    SESSION_ID: 'ai_council_session_id',
    SESSION_ACTIVE: 'ai_council_session_active',
    CURRENT_VIEW: 'ai_council_current_view'
};

// API helper
const api = {
    async get(endpoint) {
        const response = await fetch(`/api${endpoint}`);
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    },
    
    async post(endpoint, data = {}) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `API error: ${response.status}`);
        }
        return response.json();
    },
    
    async put(endpoint, data = {}) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    },
    
    async delete(endpoint) {
        const response = await fetch(`/api${endpoint}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    },
    
    stream(endpoint, onMessage, onError, onComplete) {
        const eventSource = new EventSource(`/api${endpoint}`);
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'complete') {
                eventSource.close();
                if (onComplete) onComplete();
            } else if (data.type === 'error') {
                eventSource.close();
                if (onError) onError(data.message);
            } else {
                onMessage(data);
            }
        };
        
        eventSource.onerror = () => {
            eventSource.close();
            if (onError) onError('Connection lost');
        };
        
        return eventSource;
    }
};

// Session persistence
function saveSessionState() {
    if (state.sessionId) {
        sessionStorage.setItem(STORAGE_KEYS.SESSION_ID, state.sessionId);
        sessionStorage.setItem(STORAGE_KEYS.SESSION_ACTIVE, state.sessionActive ? 'true' : 'false');
        sessionStorage.setItem(STORAGE_KEYS.CURRENT_VIEW, state.currentView);
    } else {
        clearSessionState();
    }
}

function loadSessionState() {
    const sessionId = sessionStorage.getItem(STORAGE_KEYS.SESSION_ID);
    const sessionActive = sessionStorage.getItem(STORAGE_KEYS.SESSION_ACTIVE) === 'true';
    const currentView = sessionStorage.getItem(STORAGE_KEYS.CURRENT_VIEW);
    
    if (sessionId && sessionActive) {
        state.sessionId = sessionId;
        state.sessionActive = sessionActive;
        if (currentView) {
            state.currentView = currentView;
        }
        return true;
    }
    return false;
}

function clearSessionState() {
    sessionStorage.removeItem(STORAGE_KEYS.SESSION_ID);
    sessionStorage.removeItem(STORAGE_KEYS.SESSION_ACTIVE);
    sessionStorage.removeItem(STORAGE_KEYS.CURRENT_VIEW);
}

// View management
function showView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const view = document.getElementById(`view-${viewName}`);
    if (view) {
        view.classList.add('active');
        state.currentView = viewName;
        saveSessionState();
    }
}

// Session state management
function setSessionActive(active, sessionId = null) {
    state.sessionActive = active;
    if (sessionId) {
        state.sessionId = sessionId;
    }
    
    // Update UI elements
    updateSessionUI();
    updateModeBlocker();
    saveSessionState();
}

function updateSessionUI() {
    const banner = document.getElementById('session-banner');
    const sessionIdDisplay = document.getElementById('session-id-display');
    const endCouncilBtn = document.getElementById('btn-end-council');
    const startBtn = document.getElementById('btn-start');
    const promptInput = document.getElementById('prompt-input');
    
    if (state.sessionActive && state.sessionId) {
        // Show active session UI
        if (banner) banner.style.display = 'block';
        if (sessionIdDisplay) sessionIdDisplay.textContent = state.sessionId.substring(0, 8) + '...';
        if (endCouncilBtn) endCouncilBtn.style.display = 'inline-flex';
        if (startBtn) startBtn.disabled = true;
        if (promptInput) promptInput.disabled = true;
    } else {
        // Hide active session UI
        if (banner) banner.style.display = 'none';
        if (endCouncilBtn) endCouncilBtn.style.display = 'none';
        if (startBtn) startBtn.disabled = false;
        if (promptInput) promptInput.disabled = false;
    }
}

function updateModeBlocker() {
    const modeSelector = document.querySelector('.mode-selector');
    const modeRadios = document.querySelectorAll('input[name="ram-mode"]');
    
    if (state.sessionActive) {
        // Block mode changes
        if (modeSelector) modeSelector.classList.add('disabled');
        modeRadios.forEach(radio => radio.disabled = true);
    } else {
        // Allow mode changes
        if (modeSelector) modeSelector.classList.remove('disabled');
        modeRadios.forEach(radio => radio.disabled = false);
    }
}

// End Council functionality
async function endCouncil(showConfirm = true) {
    if (showConfirm) {
        const confirmed = confirm(
            'End this council session?\n\n' +
            'The session log and feedback have been saved.\n' +
            'You can start a new council after ending this one.'
        );
        if (!confirmed) return false;
    }
    
    // Clear session state
    state.sessionId = null;
    state.sessionActive = false;
    clearSessionState();
    
    // Reset UI
    updateSessionUI();
    updateModeBlocker();
    
    // Reset worker outputs
    initializeWorkerCards();

    // Clear chat timeline and logs
    if (window.aiCouncil.session?.clearLog) {
        window.aiCouncil.session.clearLog();
    }
    if (window.aiCouncil.session?.initChatTimeline) {
        window.aiCouncil.session.initChatTimeline();
    }
    if (window.aiCouncil.session?.updateWorkerRoster) {
        window.aiCouncil.session.updateWorkerRoster();
    }
    
    // Reset prompt area
    const promptInput = document.getElementById('prompt-input');
    if (promptInput) {
        promptInput.value = '';
        promptInput.disabled = false;
    }
    
    // Hide progress (with null checks)
    const progressSection = document.getElementById('progress-section');
    const stageOutput = document.getElementById('stage-output');
    if (progressSection) progressSection.style.display = 'none';
    if (stageOutput) stageOutput.style.display = 'none';
    
    // Disable diversify button
    const diversifyBtn = document.getElementById('btn-diversify');
    if (diversifyBtn) diversifyBtn.disabled = true;
    
    // Clear session log (keep log visible but note session ended)
    if (window.aiCouncil.session?.appendLog) {
        window.aiCouncil.session.appendLog('system', null, null, 'Session ended by user');
    }
    
    // Go to session view
    showView('session');
    
    return true;
}

// Mode management
async function setMode(mode) {
    // Block mode change if session is active
    if (state.sessionActive) {
        alert('Cannot change mode while a council session is active.\n\nPlease end the current council first.');
        return;
    }
    
    try {
        const result = await api.post('/config/mode', { mode });
        state.currentMode = result.mode;
        state.config = result;
        updateModeUI();
        initializeWorkerCards();
    } catch (error) {
        console.error('Failed to set mode:', error);
    }
}

function updateModeUI() {
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.id === `mode-${state.currentMode.toLowerCase()}`);
    });
    
    // Update settings radio
    document.querySelectorAll('input[name="ram-mode"]').forEach(radio => {
        radio.checked = radio.value === state.currentMode;
    });
    
    // Update status
    const statusMode = document.getElementById('status-mode');
    if (statusMode) statusMode.textContent = state.currentMode;
    
    const statusWorkers = document.getElementById('status-workers');
    if (statusWorkers && state.config) {
        statusWorkers.textContent = state.config.worker_count;
    }
}

// Memory monitoring
async function updateMemoryStatus() {
    try {
        const memory = await api.get('/system/memory');
        const ramUsage = document.getElementById('ram-usage');
        if (ramUsage) {
            ramUsage.textContent = `${memory.ram.percent.toFixed(1)}%`;
            ramUsage.style.color = memory.ram.percent > 85 ? 'var(--warning)' : 'var(--accent-primary)';
        }
    } catch (error) {
        console.error('Failed to get memory status:', error);
    }
}

// Health check
async function checkHealth() {
    try {
        const health = await api.get('/health');
        const statusOllama = document.getElementById('status-ollama');
        if (statusOllama) {
            statusOllama.textContent = health.ollama;
            statusOllama.className = `status-value ${health.ollama}`;
        }
    } catch (error) {
        const statusOllama = document.getElementById('status-ollama');
        if (statusOllama) {
            statusOllama.textContent = 'error';
            statusOllama.className = 'status-value unhealthy';
        }
    }
}

// Initialize worker cards based on mode
function initializeWorkerCards() {
    const grid = document.getElementById('workers-grid');
    if (!grid) return;
    
    const workerCount = state.config?.worker_count || (state.currentMode === '32GB' ? 3 : 2);
    grid.innerHTML = '';
    
    state.workers = [];
    
    for (let i = 0; i < workerCount; i++) {
        const workerId = `worker_${i + 1}`;
        const persona = state.personas[i] || { name: 'Default', id: null };
        
        state.workers.push({
            id: workerId,
            persona: persona
        });
        
        const card = createWorkerCard(workerId, persona, i + 1);
        grid.appendChild(card);
    }
}

function createWorkerCard(workerId, persona, number) {
    const card = document.createElement('div');
    card.className = 'worker-card';
    card.id = `card-${workerId}`;
    
    card.innerHTML = `
        <div class="worker-header">
            <div>
                <div class="worker-title">Worker ${number}</div>
                <div class="worker-persona" id="persona-${workerId}">${persona.name}</div>
            </div>
        </div>
        <div class="worker-content">
            <div class="worker-output" id="output-${workerId}">
                Waiting for prompt...
            </div>
        </div>
        <div class="worker-footer">
            <button class="btn-swap" data-worker="${workerId}">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M23 4v6h-6"/>
                    <path d="M1 20v-6h6"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                Swap
            </button>
        </div>
    `;
    
    // Add swap button handler
    card.querySelector('.btn-swap').addEventListener('click', () => openSwapModal(workerId));
    
    return card;
}

// Swap modal
let currentSwapWorker = null;

function openSwapModal(workerId) {
    currentSwapWorker = workerId;
    
    const select = document.getElementById('swap-persona-select');
    select.innerHTML = state.personas.map(p => 
        `<option value="${p.id}">${p.name}</option>`
    ).join('');
    
    document.getElementById('swap-modal').style.display = 'flex';
}

function closeSwapModal() {
    currentSwapWorker = null;
    document.getElementById('swap-modal').style.display = 'none';
}

async function confirmSwap() {
    if (!currentSwapWorker || !state.sessionId) {
        // If no session, just update local state
        const newPersonaId = document.getElementById('swap-persona-select').value;
        const persona = state.personas.find(p => p.id === newPersonaId);
        
        const workerIndex = state.workers.findIndex(w => w.id === currentSwapWorker);
        if (workerIndex >= 0 && persona) {
            state.workers[workerIndex].persona = persona;
            document.getElementById(`persona-${currentSwapWorker}`).textContent = persona.name;
        }
        
        closeSwapModal();
        return;
    }
    
    try {
        const newPersonaId = document.getElementById('swap-persona-select').value;
        const action = document.querySelector('input[name="swap-action"]:checked').value;
        
        const result = await api.post(`/session/${state.sessionId}/swap-persona`, {
            worker_id: currentSwapWorker,
            persona_id: newPersonaId,
            action: action
        });
        
        // Update UI
        document.getElementById(`persona-${currentSwapWorker}`).textContent = result.new_persona_name;
        
        if (result.state_cleared) {
            document.getElementById(`output-${currentSwapWorker}`).textContent = 'Persona swapped. Waiting for re-run...';
        }
        
        closeSwapModal();
    } catch (error) {
        console.error('Failed to swap persona:', error);
        alert('Failed to swap persona: ' + error.message);
    }
}

// Check if session still exists on server
async function verifySession() {
    if (!state.sessionId) return false;
    
    try {
        const status = await api.get(`/session/${state.sessionId}/status`);
        return status && status.session_id === state.sessionId;
    } catch (error) {
        // Session doesn't exist on server anymore
        console.warn('Session not found on server, clearing local state');
        return false;
    }
}

// Fetch full session state and restore UI
async function restoreFullSession() {
    if (!state.sessionId) return false;
    
    try {
        const fullState = await api.get(`/session/${state.sessionId}/full-state`);
        
        if (!fullState || fullState.error) {
            console.warn('Failed to get full session state');
            return false;
        }
        
        // Restore session state
        state.prompt = fullState.prompt;
        state.workerInfo = fullState.worker_info || {};
        
        // Restore log entries (wait for session module to be ready)
        setTimeout(() => {
            if (window.aiCouncil?.session?.populateLogFromEntries && fullState.log_entries) {
                window.aiCouncil.session.populateLogFromEntries(fullState.log_entries);
                window.aiCouncil.session.appendLog('system', null, null, 'Session state restored from server');
            }
        }, 100);
        
        // Restore prompt input
        const promptInput = document.getElementById('prompt-input');
        if (promptInput && fullState.prompt) {
            promptInput.value = fullState.prompt;
        }
        
        // Update workers state with restored data
        if (fullState.workers) {
            for (const [workerId, workerData] of Object.entries(fullState.workers)) {
                const workerIndex = state.workers.findIndex(w => w.id === workerId);
                if (workerIndex >= 0) {
                    if (workerData.persona_id) {
                        const persona = state.personas.find(p => p.id === workerData.persona_id);
                        if (persona) {
                            state.workers[workerIndex].persona = persona;
                        }
                    }
                }
            }
        }
        
        // Handle different session stages
        if (fullState.current_stage === 'user_voting') {
            // Restore voting state
            state.candidates = fullState.candidates;
            state.aiScores = fullState.ai_scores;
            state.arguments = fullState.arguments;
            
            // Build and show voting UI
            setTimeout(() => {
                if (window.aiCouncil?.voting?.buildVotingUI) {
                    window.aiCouncil.voting.buildVotingUI(
                        state.candidates,
                        state.aiScores,
                        state.arguments,
                        state.workers
                    );
                    showView('voting');
                }
            }, 150);
        } else if (fullState.awaiting_round_feedback) {
            // Show round feedback modal
            setTimeout(() => {
                if (window.aiCouncil?.session?.showRoundFeedbackModal) {
                    window.aiCouncil.session.showRoundFeedbackModal({
                        round: fullState.current_round,
                        total_rounds: fullState.total_rounds,
                        worker_outputs: fullState.round_worker_outputs || {},
                        follow_up_questions: fullState.follow_up_questions || null
                    });
                }
            }, 150);
        }
        
        // Show progress section if session is active
        const progressSection = document.getElementById('progress-section');
        if (progressSection) {
            progressSection.style.display = 'block';
        }
        
        // Enable diversify button
        const diversifyBtn = document.getElementById('btn-diversify');
        if (diversifyBtn) {
            diversifyBtn.disabled = false;
        }
        
        return true;
    } catch (error) {
        console.error('Failed to restore full session:', error);
        return false;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Load initial config
    try {
        state.config = await api.get('/config');
        state.currentMode = state.config.mode;
        updateModeUI();
    } catch (error) {
        console.error('Failed to load config:', error);
    }
    
    // Load personas
    try {
        const data = await api.get('/personas');
        state.personas = data.personas;
        initializeWorkerCards();
    } catch (error) {
        console.error('Failed to load personas:', error);
        initializeWorkerCards();
    }
    
    // Try to restore session from sessionStorage
    const hasStoredSession = loadSessionState();
    if (hasStoredSession) {
        // Verify session still exists on server
        const sessionValid = await verifySession();
        if (sessionValid) {
            // Restore session UI
            updateSessionUI();
            updateModeBlocker();
            
            // Fetch and restore full session state (including logs, voting data, etc.)
            const restored = await restoreFullSession();
            
            // Show message about restored session
            console.log('Session restored:', state.sessionId, 'Full restore:', restored);
        } else {
            // Session doesn't exist on server, clear local state
            clearSessionState();
            state.sessionId = null;
            state.sessionActive = false;
        }
    }
    
    // Start memory monitoring
    updateMemoryStatus();
    setInterval(updateMemoryStatus, 5000);
    
    // Health check
    checkHealth();
    setInterval(checkHealth, 30000);
    
    // Mode buttons
    document.getElementById('mode-16gb').addEventListener('click', () => setMode('16GB'));
    document.getElementById('mode-32gb').addEventListener('click', () => setMode('32GB'));
    
    // Settings mode radio
    document.querySelectorAll('input[name="ram-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => setMode(e.target.value));
    });
    
    // Navigation
    document.getElementById('btn-council').addEventListener('click', () => {
        showView('session');
    });
    
    document.getElementById('btn-home').addEventListener('click', () => {
        showView('session');
    });
    
    document.getElementById('btn-personas').addEventListener('click', () => {
        showView('personas');
        loadPersonas();
    });
    
    document.getElementById('btn-settings').addEventListener('click', () => {
        showView('settings');
    });
    
    // Swap modal
    document.getElementById('btn-close-swap-modal').addEventListener('click', closeSwapModal);
    document.getElementById('btn-cancel-swap').addEventListener('click', closeSwapModal);
    document.getElementById('btn-confirm-swap').addEventListener('click', confirmSwap);
    
    // End Council button
    const endCouncilBtn = document.getElementById('btn-end-council');
    if (endCouncilBtn) {
        endCouncilBtn.addEventListener('click', () => endCouncil(true));
    }
    
    // New session button (in final view)
    document.getElementById('btn-new-session').addEventListener('click', () => {
        endCouncil(false);  // Don't show confirm, just end
    });
    
    // Close modals on outside click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    });
    
    // Update initial UI state
    updateSessionUI();
    updateModeBlocker();
    
    // Settings handlers
    initializeSettingsHandlers();
    
    // Token tracking
    initializeTokenTracking();
    
    // Load custom personas to settings dropdowns
    loadPersonasToSettings();
    
    // Persona dropdown change listeners
    document.querySelectorAll('.persona-dropdown').forEach(dropdown => {
        dropdown.addEventListener('change', () => {
            updatePipelineSettings();
        });
    });
});

// Initialize settings handlers
function initializeSettingsHandlers() {
    // Token sliders
    const workerTokensSlider = document.getElementById('setting-worker-tokens');
    const workerTokensValue = document.getElementById('worker-tokens-value');
    const synthTokensSlider = document.getElementById('setting-synth-tokens');
    const synthTokensValue = document.getElementById('synth-tokens-value');
    
    if (workerTokensSlider && workerTokensValue) {
        workerTokensSlider.addEventListener('input', (e) => {
            workerTokensValue.textContent = e.target.value;
        });
    }
    
    if (synthTokensSlider && synthTokensValue) {
        synthTokensSlider.addEventListener('input', (e) => {
            synthTokensValue.textContent = e.target.value;
        });
    }
    
    // Worker count and add worker button
    const workerCountInput = document.getElementById('setting-worker-count');
    const addWorkerBtn = document.getElementById('btn-add-worker');
    
    if (addWorkerBtn && workerCountInput) {
        addWorkerBtn.addEventListener('click', () => {
            const currentCount = parseInt(workerCountInput.value) || 2;
            const maxWorkers = state.currentMode === '32GB' ? 4 : 3;
            
            if (currentCount < maxWorkers) {
                workerCountInput.value = currentCount + 1;
                updateWorkerCount(currentCount + 1);
            } else {
                alert(`Maximum ${maxWorkers} workers allowed in ${state.currentMode} mode`);
            }
        });
    }
    
    if (workerCountInput) {
        workerCountInput.addEventListener('change', (e) => {
            const count = parseInt(e.target.value);
            const maxWorkers = state.currentMode === '32GB' ? 4 : 3;
            const clampedCount = Math.min(Math.max(count, 2), maxWorkers);
            e.target.value = clampedCount;
            updateWorkerCount(clampedCount);
        });
    }
    
    // Pipeline settings - store in state for session creation
    ['setting-refinement-rounds', 'setting-argument-rounds', 'setting-collaboration-rounds', 'setting-axiom-rounds'].forEach(id => {
        const input = document.getElementById(id);
        if (input) {
            input.addEventListener('change', () => {
                updatePipelineSettings();
            });
        }
    });
    
    // Chat view pipeline inputs - sync back to settings
    const debateRoundsInput = document.getElementById('debate-rounds');
    if (debateRoundsInput) {
        debateRoundsInput.addEventListener('change', () => {
            const value = parseInt(debateRoundsInput.value) || 2;
            const settingInput = document.getElementById('setting-refinement-rounds');
            if (settingInput) settingInput.value = value;
            updatePipelineSettings();
        });
    }
    
    const argumentRoundsInput = document.getElementById('argument-rounds');
    if (argumentRoundsInput) {
        argumentRoundsInput.addEventListener('change', () => {
            const value = parseInt(argumentRoundsInput.value) || 1;
            const settingInput = document.getElementById('setting-argument-rounds');
            if (settingInput) settingInput.value = value;
            updatePipelineSettings();
        });
    }
    
    // Initialize values from config
    if (state.config) {
        updateSettingsFromConfig(state.config);
    }
}

function updateWorkerCount(count) {
    if (state.config) {
        state.config.worker_count = count;
    }
    
    // Re-initialize worker cards
    initializeWorkerCards();
    
    // Update status display
    const statusWorkers = document.getElementById('status-workers');
    if (statusWorkers) {
        statusWorkers.textContent = count;
    }
    
    // Show/hide persona selector rows based on worker count
    const worker3Row = document.getElementById('worker-3-persona-row');
    const worker4Row = document.getElementById('worker-4-persona-row');
    
    if (worker3Row) {
        worker3Row.style.display = count >= 3 ? 'flex' : 'none';
    }
    if (worker4Row) {
        worker4Row.style.display = count >= 4 ? 'flex' : 'none';
    }
}

function updatePipelineSettings() {
    // Collect pipeline settings from UI - these OVERRIDE config file settings
    const workerCount = parseInt(document.getElementById('setting-worker-count')?.value) || 2;
    
    const settings = {
        worker_count: workerCount,  // From UI, overrides config
        refinement_rounds: parseInt(document.getElementById('setting-refinement-rounds')?.value) || 3,
        argument_rounds: parseInt(document.getElementById('setting-argument-rounds')?.value) || 1,
        collaboration_rounds: parseInt(document.getElementById('setting-collaboration-rounds')?.value) || 1,
        axiom_rounds: parseInt(document.getElementById('setting-axiom-rounds')?.value) || 1,
        worker_max_tokens: parseInt(document.getElementById('setting-worker-tokens')?.value) || 400,
        synth_max_tokens: parseInt(document.getElementById('setting-synth-tokens')?.value) || 300,
        worker_context_window: parseInt(document.getElementById('setting-worker-context')?.value) || 2048,
        synth_context_window: parseInt(document.getElementById('setting-synth-context')?.value) || 4096
    };
    
    // Collect worker persona assignments from settings
    const personaAssignments = {};
    for (let i = 1; i <= workerCount; i++) {
        const select = document.getElementById(`setting-worker-${i}-persona`);
        if (select && select.value !== 'custom') {
            personaAssignments[`worker_${i}`] = select.value;
        }
    }
    settings.persona_assignments = personaAssignments;
    
    // Store in state for use when creating sessions
    state.pipelineSettings = settings;
    
    // Also update token tracking limits
    state.tokenStats.workerContextLimit = settings.worker_context_window;
    state.tokenStats.synthContextLimit = settings.synth_context_window;
    
    // Sync settings to chat view inputs as well
    const debateRoundsInput = document.getElementById('debate-rounds');
    const argumentRoundsInput = document.getElementById('argument-rounds');
    
    if (debateRoundsInput) {
        debateRoundsInput.value = settings.refinement_rounds;
    }
    if (argumentRoundsInput) {
        argumentRoundsInput.value = settings.argument_rounds;
    }
    
    console.log('[Settings] UI settings updated (override config):', settings);
}

function updateSettingsFromConfig(config) {
    // Update UI inputs from config (these are defaults, UI can override)
    const workerCount = config.worker_count || 2;
    const workerCountInput = document.getElementById('setting-worker-count');
    if (workerCountInput) workerCountInput.value = workerCount;
    
    // Context window settings (1K - 32K range)
    const workerContext = config.workers?.context_window || 8192;
    const synthContext = config.synthesizer?.context_window || 20480;
    
    const workerContextSlider = document.getElementById('setting-worker-context');
    const workerContextValue = document.getElementById('worker-context-value');
    const workerContextLimit = document.getElementById('worker-context-limit');
    if (workerContextSlider) workerContextSlider.value = workerContext;
    if (workerContextValue) workerContextValue.textContent = workerContext.toLocaleString();
    if (workerContextLimit) workerContextLimit.textContent = workerContext.toLocaleString();
    state.tokenStats.workerContextLimit = workerContext;
    
    const synthContextSlider = document.getElementById('setting-synth-context');
    const synthContextValue = document.getElementById('synth-context-value');
    const synthContextLimit = document.getElementById('synth-context-limit');
    if (synthContextSlider) synthContextSlider.value = synthContext;
    if (synthContextValue) synthContextValue.textContent = synthContext.toLocaleString();
    if (synthContextLimit) synthContextLimit.textContent = synthContext.toLocaleString();
    state.tokenStats.synthContextLimit = synthContext;
    
    // Max output token settings
    const workerTokens = config.workers?.max_output_tokens || 1500;
    const synthTokens = config.synthesizer?.max_output_tokens || 4000;
    
    const workerTokensSlider = document.getElementById('setting-worker-tokens');
    const workerTokensValue = document.getElementById('worker-tokens-value');
    if (workerTokensSlider) workerTokensSlider.value = workerTokens;
    if (workerTokensValue) workerTokensValue.textContent = workerTokens;
    
    const synthTokensSlider = document.getElementById('setting-synth-tokens');
    const synthTokensValue = document.getElementById('synth-tokens-value');
    if (synthTokensSlider) synthTokensSlider.value = synthTokens;
    if (synthTokensValue) synthTokensValue.textContent = synthTokens;
    
    // Pipeline settings from config
    const pipeline = config.pipeline || {};
    const refinementInput = document.getElementById('setting-refinement-rounds');
    const argInput = document.getElementById('setting-argument-rounds');
    const collabInput = document.getElementById('setting-collaboration-rounds');
    const axiomInput = document.getElementById('setting-axiom-rounds');
    
    if (refinementInput) refinementInput.value = pipeline.refinement_loops || 3;
    if (argInput) argInput.value = pipeline.argumentation_rounds || 1;
    if (collabInput) collabInput.value = pipeline.collaboration_rounds || 1;
    if (axiomInput) axiomInput.value = pipeline.axiom_rounds || 1;
    
    // Initialize pipeline settings state (UI values override config)
    updatePipelineSettings();
    
    console.log('[Config] Loaded defaults - Worker context:', workerContext, 'Synth context:', synthContext);
}

// Token tracking functions
function updateTokenStats(tokenData, source = 'worker', contextLimit = null) {
    if (!tokenData) return;
    
    // Update stats
    if (tokenData.input_tokens) {
        state.tokenStats.inputTokens += tokenData.input_tokens;
    }
    if (tokenData.output_tokens) {
        state.tokenStats.outputTokens += tokenData.output_tokens;
    }
    if (tokenData.total_tokens) {
        state.tokenStats.totalTokens += tokenData.total_tokens;
    } else {
        state.tokenStats.totalTokens = state.tokenStats.inputTokens + state.tokenStats.outputTokens;
    }
    
    // Update context limit if provided (from backend or token payload)
    const effectiveContextLimit = contextLimit || tokenData.context_limit;
    if (effectiveContextLimit) {
        if (source === 'synthesizer' || source === 'synth') {
            state.tokenStats.synthContextLimit = effectiveContextLimit;
        } else {
            state.tokenStats.workerContextLimit = effectiveContextLimit;
        }
    }
    
    // Track context usage by source (use context_used from token data)
    const contextUsed = tokenData.context_used || tokenData.total_tokens || 0;
    if (source === 'synthesizer' || source === 'synth') {
        state.tokenStats.lastSynthContextUsed = contextUsed;
    } else {
        // For workers, track cumulative context (should grow with each round)
        state.tokenStats.lastWorkerContextUsed = contextUsed;
    }
    
    state.tokenStats.callCount++;
    
    // Update UI
    updateTokenDisplay();
    
    // Log to console for debugging
    const limit = (source === 'synthesizer' || source === 'synth') 
        ? state.tokenStats.synthContextLimit 
        : state.tokenStats.workerContextLimit;
    const used = (source === 'synthesizer' || source === 'synth')
        ? state.tokenStats.lastSynthContextUsed 
        : state.tokenStats.lastWorkerContextUsed;
    console.log(`[Tokens] ${source} - Input: ${tokenData.input_tokens || 0}, Output: ${tokenData.output_tokens || 0}, Context: ${used}/${limit}`);
}

function updateTokenDisplay() {
    const stats = state.tokenStats;
    
    // Update worker context bar
    const workerBar = document.getElementById('worker-context-bar');
    const workerUsed = document.getElementById('worker-context-used');
    const workerLimit = document.getElementById('worker-context-limit');
    
    if (workerBar && workerUsed && workerLimit) {
        const percentage = Math.min((stats.lastWorkerContextUsed / stats.workerContextLimit) * 100, 100);
        workerBar.style.width = `${percentage}%`;
        workerUsed.textContent = stats.lastWorkerContextUsed.toLocaleString();
        workerLimit.textContent = stats.workerContextLimit.toLocaleString();
    }
    
    // Update synthesizer context bar
    const synthBar = document.getElementById('synth-context-bar');
    const synthUsed = document.getElementById('synth-context-used');
    const synthLimit = document.getElementById('synth-context-limit');
    
    if (synthBar && synthUsed && synthLimit) {
        const percentage = Math.min((stats.lastSynthContextUsed / stats.synthContextLimit) * 100, 100);
        synthBar.style.width = `${percentage}%`;
        synthUsed.textContent = stats.lastSynthContextUsed.toLocaleString();
        synthLimit.textContent = stats.synthContextLimit.toLocaleString();
    }
    
    // Update stats grid
    const tokensTotal = document.getElementById('tokens-total');
    const tokensInput = document.getElementById('tokens-input');
    const tokensOutput = document.getElementById('tokens-output');
    const tokensAvg = document.getElementById('tokens-avg');
    
    if (tokensTotal) tokensTotal.textContent = stats.totalTokens.toLocaleString();
    if (tokensInput) tokensInput.textContent = stats.inputTokens.toLocaleString();
    if (tokensOutput) tokensOutput.textContent = stats.outputTokens.toLocaleString();
    if (tokensAvg && stats.callCount > 0) {
        tokensAvg.textContent = Math.round(stats.totalTokens / stats.callCount).toLocaleString();
    }
}

function resetTokenStats() {
    state.tokenStats = {
        totalTokens: 0,
        inputTokens: 0,
        outputTokens: 0,
        callCount: 0,
        workerContextLimit: state.tokenStats.workerContextLimit,
        synthContextLimit: state.tokenStats.synthContextLimit,
        lastWorkerContextUsed: 0,
        lastSynthContextUsed: 0
    };
    updateTokenDisplay();
    console.log('[Tokens] Stats reset');
}

// Load and populate persona dropdowns with custom personas
async function loadPersonasToSettings() {
    try {
        const response = await api.get('/personas');
        const personasList = response.personas || response || [];
        
        if (!Array.isArray(personasList) || personasList.length === 0) {
            console.log('[Personas] No custom personas found');
            return;
        }
        
        // Get all persona dropdowns
        const dropdowns = document.querySelectorAll('.persona-dropdown');
        
        dropdowns.forEach(dropdown => {
            // Check if custom options already added
            if (dropdown.querySelector('option[data-custom="true"]')) return;
            
            // Add custom personas after the "-- Custom Personas --" option
            const customOption = Array.from(dropdown.options).find(opt => opt.value === 'custom');
            if (customOption) {
                personasList.forEach(persona => {
                    // Skip default personas (already in dropdown)
                    if (['analyst', 'creative', 'skeptic'].includes(persona.id)) return;
                    
                    const option = document.createElement('option');
                    option.value = persona.id;
                    option.textContent = `${persona.name} (${persona.reasoning_style || 'custom'})`;
                    option.setAttribute('data-custom', 'true');
                    dropdown.insertBefore(option, customOption);
                });
            }
        });
    } catch (error) {
        console.error('Failed to load personas for settings:', error);
    }
}

// Initialize token display on settings
function initializeTokenTracking() {
    const resetBtn = document.getElementById('btn-reset-token-stats');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetTokenStats);
    }
    
    // Temperature slider
    const tempSlider = document.getElementById('setting-temperature');
    const tempValue = document.getElementById('temperature-value');
    if (tempSlider && tempValue) {
        tempSlider.addEventListener('input', () => {
            tempValue.textContent = tempSlider.value;
        });
    }
    
    // Worker context window slider
    const workerContextSlider = document.getElementById('setting-worker-context');
    const workerContextValue = document.getElementById('worker-context-value');
    if (workerContextSlider && workerContextValue) {
        workerContextSlider.addEventListener('input', () => {
            const value = parseInt(workerContextSlider.value);
            workerContextValue.textContent = value.toLocaleString();
            state.tokenStats.workerContextLimit = value;
            // Update the limit display
            const limitEl = document.getElementById('worker-context-limit');
            if (limitEl) limitEl.textContent = value.toLocaleString();
            updatePipelineSettings();
        });
    }
    
    // Synthesizer context window slider
    const synthContextSlider = document.getElementById('setting-synth-context');
    const synthContextValue = document.getElementById('synth-context-value');
    if (synthContextSlider && synthContextValue) {
        synthContextSlider.addEventListener('input', () => {
            const value = parseInt(synthContextSlider.value);
            synthContextValue.textContent = value.toLocaleString();
            state.tokenStats.synthContextLimit = value;
            // Update the limit display
            const limitEl = document.getElementById('synth-context-limit');
            if (limitEl) limitEl.textContent = value.toLocaleString();
            updatePipelineSettings();
        });
    }
    
    updateTokenDisplay();
}

// Export for other modules
window.aiCouncil = {
    state,
    api,
    showView,
    initializeWorkerCards,
    setSessionActive,
    endCouncil,
    restoreFullSession,
    updateSettingsFromConfig,
    updateTokenStats,
    resetTokenStats
};
