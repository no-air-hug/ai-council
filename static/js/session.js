/**
 * AI Council - Session Management
 * Handles session creation, pipeline execution, and session logging.
 */

(function() {
    const { state, api, showView, initializeWorkerCards } = window.aiCouncil;
    
    // Stage progress mapping
    const STAGES = {
        'worker_drafts': { progress: 15, text: 'Workers generating drafts...', logStage: 'draft' },
        'synth_questions': { progress: 25, text: 'Synthesizer generating questions...', logStage: 'questions' },
        'worker_refinement_1': { progress: 35, text: 'Workers refining proposals (round 1)...', logStage: 'refinement' },
        'worker_refinement_2': { progress: 40, text: 'Workers refining proposals (round 2)...', logStage: 'refinement' },
        'worker_refinement_3': { progress: 45, text: 'Workers refining proposals (round 3)...', logStage: 'refinement' },
        'worker_refinement_4': { progress: 48, text: 'Workers refining proposals (round 4)...', logStage: 'refinement' },
        'worker_refinement_5': { progress: 50, text: 'Workers refining proposals (round 5)...', logStage: 'refinement' },
        'diversify': { progress: 42, text: 'Workers diversifying approaches...', logStage: 'refinement' },
        'compatibility_check': { progress: 53, text: 'Checking proposal compatibility...', logStage: 'synthesis' },
        'collaboration_round_1': { progress: 56, text: 'Workers collaborating (round 1)...', logStage: 'collaboration' },
        'collaboration_round_2': { progress: 58, text: 'Workers collaborating (round 2)...', logStage: 'collaboration' },
        'collaboration_round_3': { progress: 60, text: 'Workers collaborating (round 3)...', logStage: 'collaboration' },
        'candidate_synthesis': { progress: 65, text: 'Synthesizing candidates...', logStage: 'synthesis' },
        'argumentation': { progress: 72, text: 'Workers presenting arguments...', logStage: 'argument' },
        'argumentation_round_1': { progress: 74, text: 'Workers presenting arguments (round 1)...', logStage: 'argument' },
        'argumentation_round_2': { progress: 78, text: 'Workers presenting arguments (round 2)...', logStage: 'argument' },
        'argumentation_round_3': { progress: 82, text: 'Workers presenting arguments (round 3)...', logStage: 'argument' },
        'ai_voting': { progress: 88, text: 'AI scoring candidates...', logStage: 'voting' },
        'axiom_analysis': { progress: 92, text: 'Analyzing underlying axioms...', logStage: 'axiom' },
        'final_output': { progress: 98, text: 'Generating final output...', logStage: 'synthesis' },
        'user_voting': { progress: 100, text: 'Ready for your vote!', logStage: 'voting' }
    };
    
    // Session log entries
    let logEntries = [];
    let logCollapsed = false;
    
    // Round feedback state
    let currentRound = 0;
    let totalRounds = 2;
    let roundWorkerFeedback = {};
    
    // Initialize floating log panel
    function initLogPanel() {
        const logToggle = document.getElementById('floating-log-toggle');
        const logPanel = document.getElementById('floating-log');
        const clearBtn = document.getElementById('btn-clear-log');
        const exportBtn = document.getElementById('btn-export-log');
        
        if (logToggle) {
            logToggle.addEventListener('click', (e) => {
                // Don't toggle if clicking on buttons
                if (e.target.closest('.btn-small')) return;
                
                logCollapsed = !logCollapsed;
                logPanel.classList.toggle('collapsed', logCollapsed);
            });
        }
        
        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                clearLog();
            });
        }
        
        if (exportBtn) {
            exportBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                exportLog();
            });
        }
    }
    
    // Update log entry count display
    function updateLogCount() {
        const countEl = document.getElementById('log-entry-count');
        if (countEl) {
            countEl.textContent = `(${logEntries.length})`;
        }
    }
    
    // Content length threshold for expandable entries
    const EXPAND_THRESHOLD = 200;
    
    // Append log entry with optional expandable content
    function appendLog(stage, workerId, personaName, content, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const entry = { timestamp, stage, workerId, personaName, content, type };
        logEntries.push(entry);
        
        renderLogEntry(entry);
        updateLogCount();
    }
    
    // Render a single log entry to the DOM
    function renderLogEntry(entry) {
        const logContainer = document.getElementById('log-entries');
        if (!logContainer) return;
        
        const entryEl = document.createElement('div');
        entryEl.className = `log-entry ${entry.type === 'error' ? 'log-error' : ''} ${entry.type === 'warning' ? 'log-warning' : ''}`;
        
        const stageClass = `stage-${entry.stage}`;
        const displayId = entry.personaName ? `${entry.personaName} (${entry.workerId})` : entry.workerId;
        
        // Check if content is long enough to need expansion
        const isLongContent = entry.content && entry.content.length > EXPAND_THRESHOLD;
        const entryId = `log-entry-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        
        let contentHtml;
        if (isLongContent) {
            contentHtml = `
                <div class="log-content expandable" id="${entryId}">
                    <div class="log-content-preview">${escapeHtml(entry.content.substring(0, EXPAND_THRESHOLD))}...</div>
                    <div class="log-content-full" style="display: none;">${escapeHtml(entry.content)}</div>
                    <button class="log-expand-btn" onclick="window.aiCouncil.session.toggleLogEntry('${entryId}')">
                        <span class="expand-text">Show more</span>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"/>
                        </svg>
                    </button>
                </div>
            `;
        } else {
            contentHtml = `<span class="log-content">${escapeHtml(entry.content)}</span>`;
        }
        
        entryEl.innerHTML = `
            <span class="log-timestamp">${entry.timestamp}</span>
            <span class="log-stage ${stageClass}">${entry.stage}</span>
            ${entry.workerId ? `<span class="log-worker">${escapeHtml(displayId)}</span>` : ''}
            ${contentHtml}
        `;
        
        logContainer.appendChild(entryEl);
        
        // Auto-scroll to bottom
        const logContent = document.getElementById('session-log-content');
        if (logContent) {
            logContent.scrollTop = logContent.scrollHeight;
        }
    }
    
    // Toggle expandable log entry
    function toggleLogEntry(entryId) {
        const entry = document.getElementById(entryId);
        if (!entry) return;
        
        const preview = entry.querySelector('.log-content-preview');
        const full = entry.querySelector('.log-content-full');
        const btn = entry.querySelector('.log-expand-btn');
        const btnText = btn.querySelector('.expand-text');
        
        const isExpanded = full.style.display !== 'none';
        
        if (isExpanded) {
            preview.style.display = 'block';
            full.style.display = 'none';
            btnText.textContent = 'Show more';
            entry.classList.remove('expanded');
        } else {
            preview.style.display = 'none';
            full.style.display = 'block';
            btnText.textContent = 'Show less';
            entry.classList.add('expanded');
        }
    }
    
    // Populate log from entries array (for restore)
    function populateLogFromEntries(entries) {
        const logContainer = document.getElementById('log-entries');
        if (logContainer) {
            logContainer.innerHTML = '';
        }
        logEntries = entries || [];
        logEntries.forEach(entry => renderLogEntry(entry));
        updateLogCount();
        
        // Auto-scroll to bottom
        const logContent = document.getElementById('session-log-content');
        if (logContent) {
            logContent.scrollTop = logContent.scrollHeight;
        }
    }
    
    // Clear log
    function clearLog() {
        logEntries = [];
        const logContainer = document.getElementById('log-entries');
        if (logContainer) {
            logContainer.innerHTML = '';
        }
        updateLogCount();
    }
    
    // Export log
    function exportLog() {
        const logText = logEntries.map(e => {
            const displayId = e.personaName ? `${e.personaName} (${e.workerId})` : e.workerId;
            return `[${e.timestamp}] [${e.stage}]${e.workerId ? ` [${displayId}]` : ''} ${e.content}`;
        }).join('\n');
        
        const blob = new Blob([logText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `session-log-${state.sessionId || 'unknown'}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    
    // Get worker display ID (persona name + worker ID)
    function getWorkerDisplayId(workerId) {
        const worker = state.workers.find(w => w.id === workerId);
        if (worker && worker.persona?.name) {
            return `${worker.persona.name} (${workerId})`;
        }
        return workerId;
    }
    
    // Start session
    async function startSession() {
        const prompt = document.getElementById('prompt-input').value.trim();
        const debateRounds = parseInt(document.getElementById('debate-rounds')?.value) || 2;
        const argumentRounds = parseInt(document.getElementById('argument-rounds')?.value) || 1;
        
        if (!prompt) {
            alert('Please enter a prompt');
            return;
        }
        
        // Build persona assignments
        const personaAssignments = {};
        state.workers.forEach(w => {
            if (w.persona?.id) {
                personaAssignments[w.id] = w.persona.id;
            }
        });
        
        // Clear previous log and initialize chat timeline
        clearLog();
        initChatTimeline();
        updateWorkerRoster();
        appendLog('system', null, null, `Starting new session with ${state.workers.length} workers, ${debateRounds} debate rounds, ${argumentRounds} argument rounds`);
        
        try {
            // Get pipeline settings from state (if configured in settings)
            const pipelineSettings = state.pipelineSettings || {};
            
            // Merge persona assignments - settings overrides session-level
            const finalPersonas = {
                ...personaAssignments,
                ...(pipelineSettings.persona_assignments || {})
            };
            
            // Create session with all pipeline parameters (UI settings override config)
            const session = await api.post('/session/start', {
                prompt: prompt,
                personas: finalPersonas,
                worker_count: pipelineSettings.worker_count || state.workers.length || 2,
                debate_rounds: pipelineSettings.refinement_rounds || debateRounds,
                argument_rounds: pipelineSettings.argument_rounds || argumentRounds,
                collaboration_rounds: pipelineSettings.collaboration_rounds || 1,
                axiom_rounds: pipelineSettings.axiom_rounds || 1,
                worker_max_tokens: pipelineSettings.worker_max_tokens || 400,
                synth_max_tokens: pipelineSettings.synth_max_tokens || 300,
                worker_context_window: pipelineSettings.worker_context_window || 2048,
                synth_context_window: pipelineSettings.synth_context_window || 4096
            });
            
            state.sessionId = session.session_id;
            const workerCountLog = session.worker_count || pipelineSettings.worker_count || state.workers.length;
            appendLog('system', null, null, `Session created: ${session.session_id} with ${workerCountLog} workers`);
            
            // Mark session as active (blocks mode changes, shows End Council button)
            if (window.aiCouncil.setSessionActive) {
                window.aiCouncil.setSessionActive(true, session.session_id);
            }
            
            // Show progress
            document.getElementById('progress-section').style.display = 'block';
            updateProgress(0, 'Starting session...');
            
            // Enable diversify button
            const diversifyBtn = document.getElementById('btn-diversify');
            if (diversifyBtn) {
                diversifyBtn.disabled = false;
            }
            
            // Reset worker outputs
            state.workers.forEach(w => {
                const output = document.getElementById(`output-${w.id}`);
                if (output) {
                    output.innerHTML = '<div class="loading"><div class="spinner"></div><span>Waiting...</span></div>';
                }
            });
            
            // Run pipeline with SSE
            runPipeline();
            
        } catch (error) {
            console.error('Failed to start session:', error);
            appendLog('system', null, null, `Error: ${error.message}`, 'error');
            alert('Failed to start session: ' + error.message);
        }
    }
    
    // Run pipeline with SSE
    function runPipeline() {
        const eventSource = new EventSource(`/api/session/${state.sessionId}/run`);
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handlePipelineEvent(data);
            
            if (data.type === 'complete' || data.type === 'awaiting_user_input') {
                eventSource.close();
            }
        };
        
        eventSource.onerror = () => {
            eventSource.close();
            console.error('Pipeline connection lost');
            updateProgress(0, 'Connection lost. Please try again.');
            appendLog('system', null, null, 'Pipeline connection lost', 'error');
        };
    }
    
    // Diversify workers
    async function diversifyWorkers() {
        if (!state.sessionId) {
            alert('No active session');
            return;
        }
        
        appendLog('system', null, null, 'Triggering diversify action - workers will see each other\'s responses');
        
        const diversifyBtn = document.getElementById('btn-diversify');
        if (diversifyBtn) {
            diversifyBtn.disabled = true;
            diversifyBtn.querySelector('span').textContent = 'Diversifying...';
        }
        
        try {
            // Run diversify with SSE
            const eventSource = new EventSource(`/api/session/${state.sessionId}/diversify`);
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handlePipelineEvent(data);
                
                if (data.type === 'complete' || data.type === 'error') {
                    eventSource.close();
                    if (diversifyBtn) {
                        diversifyBtn.disabled = false;
                        diversifyBtn.querySelector('span').textContent = 'Diversify';
                    }
                }
            };
            
            eventSource.onerror = () => {
                eventSource.close();
                appendLog('system', null, null, 'Diversify connection lost', 'error');
                if (diversifyBtn) {
                    diversifyBtn.disabled = false;
                    diversifyBtn.querySelector('span').textContent = 'Diversify';
                }
            };
            
        } catch (error) {
            console.error('Failed to diversify:', error);
            appendLog('system', null, null, `Diversify error: ${error.message}`, 'error');
            if (diversifyBtn) {
                diversifyBtn.disabled = false;
                diversifyBtn.querySelector('span').textContent = 'Diversify';
            }
        }
    }
    
    // Handle pipeline events
    function handlePipelineEvent(event) {
        console.log('Pipeline event:', event);
        
        // Track token usage if present in event (but NOT for tokens_update which is handled in switch)
        if (event.tokens && window.aiCouncil?.updateTokenStats && event.type !== 'tokens_update') {
            // Determine source from event type or explicit source field
            const source = event.source || (event.worker_id ? 'worker' : 'worker');
            window.aiCouncil.updateTokenStats(event.tokens, source, event.context_limit);
        }
        
        switch (event.type) {
            case 'stage_start':
                const stageInfo = STAGES[event.stage];
                if (stageInfo) {
                    updateProgress(stageInfo.progress, stageInfo.text);
                    appendLog(stageInfo.logStage || 'system', null, null, `Stage started: ${event.stage}`);
                    
                    // Add stage divider to chat
                    const stageLabels = {
                        'worker_drafts': 'Initial Proposals',
                        'synth_questions': 'Synthesizer Questions',
                        'candidate_synthesis': 'Candidate Synthesis',
                        'ai_voting': 'AI Evaluation'
                    };
                    if (event.stage.startsWith('worker_refinement')) {
                        const roundNum = event.stage.replace('worker_refinement_', '');
                        addStageDivider('refinement', `Refinement Round ${roundNum}`);
                    } else if (event.stage.startsWith('collaboration_round')) {
                        const roundNum = event.stage.replace('collaboration_round_', '') || '1';
                        addStageDivider('collaboration', `Collaboration Round ${roundNum}`);
                    } else if (event.stage.startsWith('argumentation')) {
                        const roundNum = event.stage.replace('argumentation_round_', '');
                        addStageDivider('argumentation', `Argumentation Round ${roundNum}`);
                    } else if (event.stage === 'compatibility_check') {
                        addStageDivider('synthesis', 'Compatibility Check');
                    } else if (event.stage === 'axiom_analysis') {
                        addStageDivider('axiom', 'Axiom Analysis');
                    } else if (stageLabels[event.stage]) {
                        addStageDivider(stageInfo.logStage || 'system', stageLabels[event.stage]);
                    }
                }
                break;
                
            case 'worker_start':
                setWorkerLoading(event.worker_id, true);
                const personaName = event.persona || state.workers.find(w => w.id === event.worker_id)?.persona?.name;
                appendLog('draft', event.worker_id, personaName, `Started working on ${event.stage || 'task'}`);
                break;
                
            case 'worker_complete':
                setWorkerLoading(event.worker_id, false);
                const workerPersona = state.workers.find(w => w.id === event.worker_id)?.persona?.name;
                
                if (event.draft) {
                    updateWorkerOutput(event.worker_id, event.draft);
                    appendLog('draft', event.worker_id, workerPersona, `Draft: ${event.draft.summary || ''}`);
                } else if (event.refinement) {
                    appendWorkerRefinement(event.worker_id, event.refinement);
                    appendLog('refinement', event.worker_id, workerPersona, `Refinement: ${event.refinement.updated_summary || event.refinement.raw_text || 'Updated proposal'}`);
                } else if (event.argument) {
                    appendWorkerArgument(event.worker_id, event.argument);
                    appendLog('argument', event.worker_id, workerPersona, `Argument: ${event.argument.main_argument || ''}`);
                } else if (event.diversified) {
                    updateWorkerOutput(event.worker_id, event.diversified);
                    appendLog('refinement', event.worker_id, workerPersona, `Diversified: ${event.diversified.summary || ''}`);
                } else if (event.collaboration) {
                    // Handle collaboration output
                    const collabSummary = event.collaboration.collaborative_summary || event.collaboration.raw_text || 'Collaborated';
                    const messageId = pendingMessages[event.worker_id];
                    if (messageId) {
                        updateChatMessage(messageId, collabSummary, { stage: 'collaboration' });
                        delete pendingMessages[event.worker_id];
                    } else {
                        addChatMessage({
                            workerId: event.worker_id,
                            stage: 'collaboration',
                            content: collabSummary
                        });
                    }
                    appendLog('collaboration', event.worker_id, workerPersona, `Collaboration: ${truncate(collabSummary, 150)}`);
                }
                break;
            
            case 'synth_commentary':
                // Synthesizer weighs in during argumentation
                addChatMessage({
                    isSynthesizer: true,
                    stage: 'commentary',
                    content: event.content || event.message
                });
                appendLog('synthesis', 'synthesizer', null, `Commentary: ${truncate(event.content || event.message, 100)}`);
                break;
                
            case 'stage_complete':
                if (event.questions) {
                    showSynthQuestions(event.questions);
                    appendLog('questions', 'synthesizer', null, `Generated ${Object.keys(event.questions.questions_by_worker || {}).length} sets of questions`);
                }
                if (event.compatibility) {
                    // Display compatibility check results
                    displayCompatibilityResults(event.compatibility);
                    appendLog('synthesis', 'synthesizer', null, `Compatibility: ${event.compatibility.compatibility || 'unknown'}`);
                }
                if (event.candidates) {
                    state.candidates = event.candidates;
                    // Show synthesis message
                    addChatMessage({
                        isSynthesizer: true,
                        stage: 'synthesis',
                        content: `I've synthesized ${event.candidates.length} candidate solutions from the worker proposals. Each represents a different approach to the problem.`
                    });
                    appendLog('synthesis', 'synthesizer', null, `Synthesized ${event.candidates.length} candidates`);
                }
                if (event.scores) {
                    state.aiScores = event.scores;
                    appendLog('voting', 'synthesizer', null, `AI scoring complete`);
                }
                // Clear all worker loading states on stage complete
                if (event.stage === 'compatibility_check' || event.stage?.includes('collaboration')) {
                    Object.keys(window.aiCouncil?.state?.workers || state.workers || {}).forEach((_, idx) => {
                        setWorkerLoading(`worker_${idx + 1}`, false);
                    });
                }
                break;
                
            case 'memory_warning':
                console.warn('Memory warning:', event.message);
                appendLog('system', null, null, `Memory warning: ${event.message}`, 'warning');
                break;
                
            case 'awaiting_user_input':
                if (event.stage === 'user_voting') {
                    state.candidates = event.candidates;
                    state.aiScores = event.ai_scores;
                    state.arguments = event.arguments;
                    state.workerInfo = event.worker_info || {};
                    appendLog('voting', null, null, 'Pipeline complete - awaiting user vote');
                    transitionToVoting();
                }
                break;
                
            case 'awaiting_round_feedback':
                currentRound = event.round;
                totalRounds = event.total_rounds;
                appendLog('refinement', null, null, `Round ${event.round}/${event.total_rounds} complete - awaiting feedback`);
                showRoundFeedbackModal(event);
                break;
            
            case 'awaiting_collab_feedback':
                currentRound = event.round;
                totalRounds = event.total_rounds;
                appendLog('collaboration', null, null, `Collaboration round ${event.round}/${event.total_rounds} complete - awaiting feedback`);
                showCollabFeedbackModal(event);
                break;
            
            case 'awaiting_argument_feedback':
                currentRound = event.round;
                totalRounds = event.total_rounds;
                appendLog('argument', null, null, `Argument round ${event.round}/${event.total_rounds} complete - awaiting feedback`);
                showArgumentFeedbackModal(event);
                break;
                
            case 'tokens_update':
                // Explicit token update event from synthesizer or other sources
                if (event.tokens && window.aiCouncil?.updateTokenStats) {
                    window.aiCouncil.updateTokenStats(event.tokens, event.source || 'synthesizer', event.context_limit);
                }
                break;
                
            case 'error':
                updateProgress(0, `Error: ${event.message}`);
                appendLog('system', null, null, `Error: ${event.message}`, 'error');
                break;
                
            case 'complete':
                appendLog('system', null, null, 'Operation complete');
                break;
        }
    }
    
    // Truncate text
    function truncate(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }
    
    // Track current stage for chat dividers
    let currentChatStage = null;
    
    // ============================================
    // CHAT TIMELINE FUNCTIONS
    // ============================================
    
    // Initialize chat timeline and worker roster
    function initChatTimeline() {
        const timeline = document.getElementById('chat-timeline');
        if (timeline) {
            timeline.innerHTML = '';
        }
        currentChatStage = null;
        
        // Initialize roster toggle
        const rosterToggle = document.getElementById('roster-toggle');
        const roster = document.getElementById('worker-roster');
        if (rosterToggle && roster) {
            rosterToggle.addEventListener('click', () => {
                roster.classList.toggle('collapsed');
            });
        }
    }
    
    // Add a stage divider to the chat
    function addStageDivider(stageName, stageLabel) {
        if (currentChatStage === stageName) return; // Don't add duplicate dividers
        currentChatStage = stageName;
        
        const timeline = document.getElementById('chat-timeline');
        if (!timeline) return;
        
        const divider = document.createElement('div');
        divider.className = 'chat-stage-divider';
        divider.innerHTML = `<span class="chat-stage-label stage-${stageName}">${stageLabel}</span>`;
        timeline.appendChild(divider);
        
        scrollChatToBottom();
    }
    
    // Add a chat message to the timeline
    function addChatMessage(options) {
        const {
            workerId,
            personaName,
            stage,
            content,
            confidence,
            isLoading = false,
            isSynthesizer = false,
            isUser = false,
            metadata = null
        } = options;
        
        const timeline = document.getElementById('chat-timeline');
        if (!timeline) return null;
        
        // Determine avatar class
        let avatarClass = '';
        let avatarText = '';
        let authorName = '';
        
        if (isSynthesizer) {
            avatarClass = 'synthesizer';
            avatarText = 'S';
            authorName = 'Synthesizer';
        } else if (isUser) {
            avatarClass = 'user';
            avatarText = 'U';
            authorName = 'You';
        } else if (workerId) {
            const workerNum = workerId.replace('worker_', '');
            avatarClass = `worker-${workerNum}`;
            avatarText = `W${workerNum}`;
            authorName = `Worker ${workerNum}`;
        }
        
        const messageId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        
        const message = document.createElement('div');
        message.className = `chat-message ${isSynthesizer ? 'synthesizer' : ''} ${isUser ? 'user' : ''} ${isLoading ? 'loading' : ''}`;
        message.id = messageId;
        
        let bodyContent = isLoading 
            ? '<div class="message-loading"><div class="spinner"></div><span>Thinking...</span></div>'
            : `<div class="message-body">${formatMessageContent(content)}</div>`;
        
        let metaHtml = '';
        if (confidence && !isLoading) {
            const confidencePercent = Math.round(confidence * 100);
            metaHtml = `
                <div class="message-meta">
                    <div class="message-confidence">
                        <span>Confidence:</span>
                        <div class="confidence-bar">
                            <div class="confidence-fill" style="width: ${confidencePercent}%"></div>
                        </div>
                        <span>${confidencePercent}%</span>
                    </div>
                </div>
            `;
        }
        
        message.innerHTML = `
            <div class="message-avatar ${avatarClass}">${avatarText}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-author">${escapeHtml(authorName)}</span>
                    ${personaName ? `<span class="message-persona">${escapeHtml(personaName)}</span>` : ''}
                    ${stage ? `<span class="message-stage-tag">${stage}</span>` : ''}
                </div>
                ${bodyContent}
                ${metaHtml}
            </div>
        `;
        
        timeline.appendChild(message);
        scrollChatToBottom();
        
        return messageId;
    }
    
    // Update an existing chat message
    function updateChatMessage(messageId, content, options = {}) {
        const message = document.getElementById(messageId);
        if (!message) return;
        
        message.classList.remove('loading');
        
        const bodyEl = message.querySelector('.message-body') || message.querySelector('.message-loading');
        if (bodyEl) {
            bodyEl.className = 'message-body';
            bodyEl.innerHTML = formatMessageContent(content);
        }
        
        // Add confidence if provided
        if (options.confidence) {
            const confidencePercent = Math.round(options.confidence * 100);
            const metaHtml = `
                <div class="message-meta">
                    <div class="message-confidence">
                        <span>Confidence:</span>
                        <div class="confidence-bar">
                            <div class="confidence-fill" style="width: ${confidencePercent}%"></div>
                        </div>
                        <span>${confidencePercent}%</span>
                    </div>
                </div>
            `;
            const contentEl = message.querySelector('.message-content');
            if (contentEl && !contentEl.querySelector('.message-meta')) {
                contentEl.insertAdjacentHTML('beforeend', metaHtml);
            }
        }

        if (options.stage) {
            const headerEl = message.querySelector('.message-header');
            if (headerEl) {
                const stageEl = headerEl.querySelector('.message-stage-tag');
                if (stageEl) {
                    stageEl.textContent = options.stage;
                } else {
                    headerEl.insertAdjacentHTML('beforeend', `<span class="message-stage-tag">${escapeHtml(options.stage)}</span>`);
                }
            }
        }
    }
    
    // Format message content with paragraphs
    function formatMessageContent(content) {
        if (!content) return '';
        // Split by double newlines for paragraphs
        return content
            .split(/\n\n+/)
            .map(p => `<p>${escapeHtml(p.trim())}</p>`)
            .join('');
    }
    
    // Scroll chat to bottom
    function scrollChatToBottom() {
        const timeline = document.getElementById('chat-timeline');
        if (timeline) {
            setTimeout(() => {
                timeline.scrollTop = timeline.scrollHeight;
            }, 50);
        }
    }
    
    // Update worker roster
    function updateWorkerRoster() {
        const roster = document.getElementById('roster-members');
        if (!roster) return;
        
        roster.innerHTML = '';
        
        // Get workers from window.aiCouncil.state directly to ensure we have latest
        const workers = window.aiCouncil?.state?.workers || state.workers || [];
        
        if (workers.length === 0) {
            // Try to reconstruct from config without warning in normal startup flows.
            const workerCount = window.aiCouncil?.state?.config?.worker_count || 2;
            const fallbackWorkers = Array.from({ length: workerCount }, (_, i) => ({
                id: `worker_${i + 1}`,
                persona: { id: null, name: 'Default' }
            }));
            if (!state.workers || state.workers.length === 0) {
                state.workers = fallbackWorkers;
            }
            fallbackWorkers.forEach((worker, index) => {
                const workerNum = index + 1;
                const card = document.createElement('div');
                card.className = 'roster-member';
                card.innerHTML = `
                    <div class="roster-avatar worker-${workerNum}">W${workerNum}</div>
                    <div class="roster-member-info">
                        <div class="roster-member-name">Worker ${workerNum}</div>
                        <div class="roster-member-persona">${escapeHtml(worker.persona?.name || 'Default')}</div>
                    </div>
                `;
                roster.appendChild(card);
            });
        } else {
            workers.forEach((worker, index) => {
                const workerNum = index + 1;
                const personaName = worker.persona?.name || 'Default';
                
                const card = document.createElement('div');
                card.className = 'roster-member';
                card.innerHTML = `
                    <div class="roster-avatar worker-${workerNum}">W${workerNum}</div>
                    <div class="roster-member-info">
                        <div class="roster-member-name">Worker ${workerNum}</div>
                        <div class="roster-member-persona">${escapeHtml(personaName)}</div>
                    </div>
                `;
                roster.appendChild(card);
            });
        }
        
        // Add synthesizer
        const synthCard = document.createElement('div');
        synthCard.className = 'roster-member';
        synthCard.innerHTML = `
            <div class="roster-avatar synthesizer">S</div>
            <div class="roster-member-info">
                <div class="roster-member-name">Synthesizer</div>
                <div class="roster-member-persona">Coordinator</div>
            </div>
        `;
        roster.appendChild(synthCard);
    }
    
    // Track pending messages for updates
    const pendingMessages = {};
    
    // ============================================
    // UI UPDATES (Legacy + Chat)
    // ============================================
    
    function updateProgress(percent, text) {
        const progressFill = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-text');
        if (progressFill) progressFill.style.width = `${percent}%`;
        if (progressText) progressText.textContent = text;
    }
    
    function setWorkerLoading(workerId, loading) {
        // Update roster member status
        const roster = document.getElementById('roster-members');
        if (roster) {
            const members = roster.querySelectorAll('.roster-member');
            members.forEach(m => m.classList.remove('active'));
            
            if (loading) {
                const workerNum = workerId.replace('worker_', '');
                const member = roster.querySelector(`.roster-avatar.worker-${workerNum}`)?.closest('.roster-member');
                if (member) member.classList.add('active');
            }
        }
        
        // Add loading message to chat
        if (loading) {
            const worker = state.workers.find(w => w.id === workerId);
            const personaName = worker?.persona?.name;
            
            const messageId = addChatMessage({
                workerId,
                personaName,
                isLoading: true
            });
            pendingMessages[workerId] = messageId;
        }
    }
    
    function updateWorkerOutput(workerId, draft) {
        // Update chat message
        const messageId = pendingMessages[workerId];
        if (messageId) {
            updateChatMessage(messageId, draft.summary, { confidence: draft.confidence });
            delete pendingMessages[workerId];
        } else {
            // Add new message if no pending
            const worker = state.workers.find(w => w.id === workerId);
            addChatMessage({
                workerId,
                personaName: worker?.persona?.name,
                stage: 'draft',
                content: draft.summary,
                confidence: draft.confidence
            });
        }
    }
    
    function appendWorkerRefinement(workerId, refinement) {
        const messageId = pendingMessages[workerId];
        const content = refinement.updated_summary || refinement.raw_text || 'Updated proposal';
        
        if (messageId) {
            updateChatMessage(messageId, content);
            delete pendingMessages[workerId];
        } else {
            const worker = state.workers.find(w => w.id === workerId);
            addChatMessage({
                workerId,
                personaName: worker?.persona?.name,
                stage: 'refinement',
                content: content
            });
        }
    }
    
    function appendWorkerArgument(workerId, argument) {
        const messageId = pendingMessages[workerId];
        const content = argument.main_argument || '';
        
        if (messageId) {
            updateChatMessage(messageId, content);
            delete pendingMessages[workerId];
        } else {
            const worker = state.workers.find(w => w.id === workerId);
            addChatMessage({
                workerId,
                personaName: worker?.persona?.name,
                stage: 'argument',
                content: content
            });
        }
    }
    
    function showSynthQuestions(questions) {
        // Add synthesizer message to chat
        let content = '';
        if (questions.overall_observations) {
            content += questions.overall_observations + '\n\n';
        }
        
        if (questions.questions_by_worker) {
            content += 'Questions for each worker:\n\n';
            for (const [workerId, workerQuestions] of Object.entries(questions.questions_by_worker)) {
                const displayId = getWorkerDisplayId(workerId);
                content += `**${displayId}:**\n`;
                
                // Handle both array and non-array cases
                const questionList = Array.isArray(workerQuestions) ? workerQuestions : [workerQuestions];
                questionList.forEach((q, i) => {
                    if (q && q.trim()) {  // Skip empty questions
                        content += `${i + 1}. ${q}\n`;
                    }
                });
                content += '\n';
            }
        }
        
        addChatMessage({
            isSynthesizer: true,
            stage: 'questions',
            content: content.trim()
        });
    }
    
    function displayCompatibilityResults(compatibility) {
        const compatibilityLevel = compatibility.compatibility || 'unknown';
        const overlapAreas = compatibility.overlap_areas || [];
        const conflictAreas = compatibility.conflict_areas || [];
        const compatiblePairs = compatibility.compatible_pairs || [];
        
        let content = `**Compatibility Analysis:** ${compatibilityLevel.replace('_', ' ').toUpperCase()}\n\n`;
        
        if (overlapAreas.length > 0) {
            content += `**Areas of Overlap:**\n`;
            overlapAreas.forEach(area => {
                content += `• ${area}\n`;
            });
            content += '\n';
        }
        
        if (conflictAreas.length > 0) {
            content += `**Potential Conflicts:**\n`;
            conflictAreas.forEach(area => {
                content += `• ${area}\n`;
            });
            content += '\n';
        }
        
        if (compatiblePairs.length > 0) {
            content += `**Compatible Pairs:**\n`;
            compatiblePairs.forEach(pair => {
                const pairStr = pair.map(wid => getWorkerDisplayId(wid)).join(' & ');
                content += `• ${pairStr}\n`;
            });
            content += '\n';
        }
        
        if (compatibilityLevel === 'compatible' || compatibilityLevel === 'partially_compatible') {
            content += '_Workers will now collaborate to build on shared ideas._';
        } else {
            content += '_Proposals have significant differences - proceeding directly to voting._';
        }
        
        addChatMessage({
            isSynthesizer: true,
            stage: 'compatibility',
            content: content.trim()
        });
    }
    
    function transitionToVoting() {
        // Ensure workers are populated from workerInfo if state.workers is empty
        if (!state.workers || state.workers.length === 0) {
            if (state.workerInfo && Object.keys(state.workerInfo).length > 0) {
                state.workers = Object.entries(state.workerInfo).map(([id, w]) => ({
                    id: w.worker_id || id,
                    persona: { 
                        id: w.persona_id || null, 
                        name: w.persona_name || null 
                    }
                }));
            }
        }
        // Build voting UI and switch view
        window.aiCouncil.voting.buildVotingUI(state.candidates, state.aiScores, state.arguments, state.workers);
        showView('voting');
    }

    function renderRefinementList(items, emptyLabel) {
        if (!items || items.length === 0) {
            return `<div class="round-worker-empty">${escapeHtml(emptyLabel)}</div>`;
        }

        const listItems = items
            .map(item => `<li>${escapeHtml(item)}</li>`)
            .join('');
        return `<ul class="round-worker-list">${listItems}</ul>`;
    }

    function renderKeyValueList(items, emptyLabel) {
        const entries = items ? Object.entries(items) : [];
        if (entries.length === 0) {
            return `<div class="round-worker-empty">${escapeHtml(emptyLabel)}</div>`;
        }

        const listItems = entries
            .map(([key, value]) => `<li><strong>${escapeHtml(key)}:</strong> ${escapeHtml(value)}</li>`)
            .join('');
        return `<ul class="round-worker-list">${listItems}</ul>`;
    }

    function renderRefinementAnswers(answers) {
        const entries = answers ? Object.entries(answers) : [];
        if (entries.length === 0) {
            return '<div class="round-worker-empty">No answers provided.</div>';
        }

        return entries
            .map(([question, answer]) => `
                <div class="round-worker-qa">
                    <div class="round-worker-question">Q: ${escapeHtml(question)}</div>
                    <div class="round-worker-answer">A: ${escapeHtml(answer)}</div>
                </div>
            `)
            .join('');
    }

    function renderRefinementSection(title, bodyHtml, isOpen = false) {
        return `
            <details class="round-worker-detail" ${isOpen ? 'open' : ''}>
                <summary>${escapeHtml(title)}</summary>
                <div class="round-worker-detail-body">${bodyHtml}</div>
            </details>
        `;
    }

    function renderArgumentTextSection(title, bodyText, emptyLabel, isOpen = false) {
        const content = bodyText ? `<p>${escapeHtml(bodyText)}</p>` : `<div class="round-worker-empty">${escapeHtml(emptyLabel)}</div>`;
        return renderRefinementSection(title, content, isOpen);
    }
    
    // Show round feedback modal
    function showRoundFeedbackModal(event) {
        const modal = document.getElementById('round-feedback-modal');
        const title = document.getElementById('round-feedback-title');
        const currentRoundEl = modal.querySelector('.current-round');
        const totalRoundsEl = modal.querySelector('.total-rounds');
        const outputsContainer = document.getElementById('round-worker-outputs');
        
        // Update title and progress
        title.textContent = `Round ${event.round} Complete`;
        currentRoundEl.textContent = event.round;
        totalRoundsEl.textContent = event.total_rounds;
        
        // Reset feedback state
        roundWorkerFeedback = {};
        
        // Build worker output cards
        outputsContainer.innerHTML = '';
        for (const [workerId, workerData] of Object.entries(event.worker_outputs)) {
            const card = document.createElement('div');
            card.className = 'round-worker-card';
            
            const summary = workerData.summary || 'No output yet';
            const displayId = workerData.display_id || workerId;
            const refinement = workerData.refinement || {};
            const updatedSummary = refinement.updated_summary || workerData.updated_summary || '';
            const refinementSections = [
                renderRefinementSection('Answers to questions', renderRefinementAnswers(refinement.answers_to_questions), true),
                renderRefinementSection('Patch notes', renderRefinementList(refinement.patch_notes, 'No patch notes recorded.')),
                renderRefinementSection('New risks', renderRefinementList(refinement.new_risks, 'No new risks recorded.')),
                renderRefinementSection('New tradeoffs', renderRefinementList(refinement.new_tradeoffs, 'No new tradeoffs recorded.'))
            ];
            if (updatedSummary) {
                refinementSections.unshift(
                    renderRefinementSection('Updated summary', `<p>${escapeHtml(updatedSummary)}</p>`, true)
                );
            }
            
            card.innerHTML = `
                <div class="round-worker-header">
                    <span class="round-worker-name">${escapeHtml(displayId)}</span>
                </div>
                <div class="round-worker-output">
                    <div class="round-worker-output-label">Summary</div>
                    <div class="round-worker-output-text">${escapeHtml(summary)}</div>
                </div>
                <div class="round-worker-refinements">
                    ${refinementSections.join('')}
                </div>
                <div class="round-worker-feedback">
                    <textarea 
                        data-worker="${workerId}"
                        placeholder="Optional feedback for this worker..."
                        rows="2"
                    ></textarea>
                </div>
            `;
            
            // Add feedback handler
            const textarea = card.querySelector('textarea');
            textarea.addEventListener('input', (e) => {
                roundWorkerFeedback[workerId] = e.target.value;
            });
            
            outputsContainer.appendChild(card);
        }
        
        // Update continue button text based on remaining rounds
        const continueBtn = document.getElementById('btn-continue-round');
        if (event.round >= event.total_rounds - 1) {
            continueBtn.innerHTML = `
                Proceed to Synthesis
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>
            `;
        } else {
            continueBtn.innerHTML = `
                Continue to Round ${event.round + 1}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>
            `;
        }
        
        modal.style.display = 'flex';
    }
    
    // Submit round feedback and continue
    async function submitRoundFeedback(skipToSynthesis = false) {
        const modal = document.getElementById('round-feedback-modal');
        
        try {
            // Submit feedback
            await api.post(`/session/${state.sessionId}/round-feedback`, {
                round: currentRound,
                worker_feedback: roundWorkerFeedback,
                skip_to_synthesis: skipToSynthesis
            });
            
            if (Object.keys(roundWorkerFeedback).length > 0) {
                appendLog('system', null, null, `Round ${currentRound} feedback submitted`);
            }
            
            // Hide modal
            modal.style.display = 'none';
            
            // Continue pipeline
            appendLog('system', null, null, skipToSynthesis ? 'Skipping to synthesis...' : `Continuing to ${currentRound < totalRounds ? `round ${currentRound + 1}` : 'synthesis'}...`);
            continuePipeline();
            
        } catch (error) {
            console.error('Failed to submit round feedback:', error);
            appendLog('system', null, null, `Error: ${error.message}`, 'error');
            alert('Failed to submit feedback: ' + error.message);
        }
    }
    
    // Continue pipeline after feedback
    function continuePipeline() {
        const eventSource = new EventSource(`/api/session/${state.sessionId}/continue`);
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handlePipelineEvent(data);
            
            if (data.type === 'complete' || data.type === 'awaiting_user_input' || data.type === 'awaiting_round_feedback' || data.type === 'awaiting_argument_feedback') {
                eventSource.close();
            }
        };
        
        eventSource.onerror = () => {
            eventSource.close();
            console.error('Pipeline connection lost');
            appendLog('system', null, null, 'Pipeline connection lost', 'error');
        };
    }
    
    // Argument round feedback state
    let argumentWorkerFeedback = {};
    
    // Show argument feedback modal
    // Collaboration feedback state
    let collabWorkerFeedback = {};
    
    function showCollabFeedbackModal(event) {
        const modal = document.getElementById('collab-feedback-modal');
        if (!modal) {
            // If modal doesn't exist, just continue pipeline
            console.warn('Collaboration feedback modal not found, continuing...');
            submitCollabFeedback(true);
            return;
        }
        
        const title = modal.querySelector('h3') || document.getElementById('collab-feedback-title');
        const currentRoundEl = modal.querySelector('.current-round');
        const totalRoundsEl = modal.querySelector('.total-rounds');
        const outputsContainer = document.getElementById('collab-worker-outputs');
        
        // Update title and progress
        if (title) title.textContent = `Collaboration Round ${event.round} Complete`;
        if (currentRoundEl) currentRoundEl.textContent = event.round;
        if (totalRoundsEl) totalRoundsEl.textContent = event.total_rounds;
        
        // Reset feedback state
        collabWorkerFeedback = {};
        
        // Build worker output cards
        if (outputsContainer) {
            outputsContainer.innerHTML = '';
            for (const [workerId, workerData] of Object.entries(event.worker_outputs || {})) {
                const card = document.createElement('div');
                card.className = 'round-worker-card';
                
                const collaboration = workerData.collaboration || {};
                const summary = collaboration.collaborative_summary || workerData.summary || 'Collaboration in progress';
                const displayId = workerData.display_id || workerId;
                const specificImprovements = Array.isArray(collaboration.specific_improvements) ? collaboration.specific_improvements : [];
                const integratedMechanisms = collaboration.integrated_mechanisms && typeof collaboration.integrated_mechanisms === 'object'
                    ? collaboration.integrated_mechanisms
                    : {};
                const resolvedTensions = Array.isArray(collaboration.resolved_tensions) ? collaboration.resolved_tensions : [];
                const newInsights = Array.isArray(collaboration.new_insights) ? collaboration.new_insights : [];
                const confidence = typeof collaboration.confidence === 'number' ? collaboration.confidence : null;
                const collabSections = [renderRefinementSection(
                        'Specific improvements',
                        renderRefinementList(specificImprovements, 'No specific improvements listed.')
                    ),
                    renderRefinementSection(
                        'Integrated mechanisms',
                        renderKeyValueList(integratedMechanisms, 'No integrated mechanisms listed.')
                    ),
                    renderRefinementSection(
                        'Resolved tensions',
                        renderRefinementList(resolvedTensions, 'No resolved tensions listed.')
                    ),
                    renderRefinementSection(
                        'New insights',
                        renderRefinementList(newInsights, 'No new insights listed.')
                    ),
                    renderArgumentTextSection(
                        'Confidence',
                        confidence !== null ? confidence.toFixed(2) : '',
                        'No confidence provided.'
                    )
                ];
                
                card.innerHTML = `
                    <div class="round-worker-header">
                        <span class="round-worker-name">${escapeHtml(displayId)}</span>
                        <span class="message-stage-tag">collaboration</span>
                    </div>

                    <div class="round-worker-output">
                        <div class="round-worker-output-label">Summary</div>
                        <div class="round-worker-output-text">${escapeHtml(summary)}</div>
                    </div>
                    <div class="round-worker-refinements">
                        ${collabSections.join('')}
                    </div>
                    
                    <div class="round-worker-feedback">
                        <textarea 
                            data-worker="${workerId}"
                            placeholder="Guide the collaboration direction..."
                            rows="2"
                        ></textarea>
                    </div>
                `;
                
                const textarea = card.querySelector('textarea');
                textarea.addEventListener('input', (e) => {
                    collabWorkerFeedback[workerId] = e.target.value;
                });
                
                outputsContainer.appendChild(card);
            }
        }
        
        modal.style.display = 'flex';
    }
    
    async function submitCollabFeedback(skip = false) {
        const modal = document.getElementById('collab-feedback-modal');
        if (modal) modal.style.display = 'none';
        
        try {
            await api.post(`/session/${state.sessionId}/collab-feedback`, {
                round: currentRound,
                worker_feedback: collabWorkerFeedback,
                skip_to_synthesis: skip
            });
            
            appendLog('system', null, null, skip ? 'Skipping to synthesis...' : `Collaboration round ${currentRound} feedback submitted`);
            
            // Continue pipeline
            continuePipeline();
        } catch (error) {
            console.error('Failed to submit collaboration feedback:', error);
            alert('Failed to submit feedback: ' + error.message);
        }
    }
    
    function skipCollabFeedback() {
        submitCollabFeedback(true);
    }
    
    function showArgumentFeedbackModal(event) {
        const modal = document.getElementById('argument-feedback-modal');
        const title = document.getElementById('argument-feedback-title');
        const currentRoundEl = modal.querySelector('.current-round');
        const totalRoundsEl = modal.querySelector('.total-rounds');
        const outputsContainer = document.getElementById('argument-worker-outputs');
        
        // Update title and progress
        title.textContent = `Argumentation Round ${event.round} Complete`;
        currentRoundEl.textContent = event.round;
        totalRoundsEl.textContent = event.total_rounds;
        
        // Reset feedback state
        argumentWorkerFeedback = {};
        
        // Build worker argument cards
        outputsContainer.innerHTML = '';
        for (const [workerId, workerData] of Object.entries(event.worker_arguments || {})) {
            const card = document.createElement('div');
            card.className = 'round-worker-card';
            
            const mainArg = workerData.main_argument || 'No argument presented';
            const displayId = workerData.display_id || workerId;
            const keyStrengths = Array.isArray(workerData.key_strengths) ? workerData.key_strengths : [];
            const critique = workerData.critique_of_alternatives || '';
            const rubricAlignment = workerData.rubric_alignment || '';
            const argumentSections = [
                renderRefinementSection('Key strengths', renderRefinementList(keyStrengths, 'No key strengths listed.')),
                renderArgumentTextSection('Critique of alternatives', critique, 'No critique provided.'),
                renderArgumentTextSection('Rubric alignment', rubricAlignment, 'No rubric alignment provided.')
            ];
            
            card.innerHTML = `
                <div class="round-worker-header">
                    <span class="round-worker-name">${escapeHtml(displayId)}</span>
                    <span class="message-stage-tag">argument</span>
                </div>
                <div class="round-worker-output">
                    <div class="round-worker-output-label">Main argument</div>
                    <div class="round-worker-output-text">${escapeHtml(mainArg)}</div>
                </div>
                <div class="round-worker-refinements">
                    ${argumentSections.join('')}
                </div>
                <div class="round-worker-feedback">
                    <textarea 
                        data-worker="${workerId}"
                        placeholder="Optional feedback for this worker's argument..."
                        rows="2"
                    ></textarea>
                </div>
            `;
            
            // Add feedback handler
            const textarea = card.querySelector('textarea');
            textarea.addEventListener('input', (e) => {
                argumentWorkerFeedback[workerId] = e.target.value;
            });
            
            outputsContainer.appendChild(card);
        }
        
        // Update continue button text
        const continueBtn = document.getElementById('btn-continue-argument');
        const roundNumber = Number(event.round) || 0;
        const total = Number(event.total_rounds) || 0;
        if (roundNumber >= total && total > 0) {
            continueBtn.innerHTML = `
                Proceed to Voting
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>
            `;
        } else {
            continueBtn.innerHTML = `
                Continue Argumentation
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>
            `;
        }
        
        modal.style.display = 'flex';
    }
    
    // Submit argument feedback
    async function submitArgumentFeedback(skipToVoting = false) {
        const modal = document.getElementById('argument-feedback-modal');
        
        try {
            await api.post(`/session/${state.sessionId}/argument-feedback`, {
                round: currentRound,
                worker_feedback: argumentWorkerFeedback,
                skip_to_voting: skipToVoting
            });
            
            if (Object.keys(argumentWorkerFeedback).length > 0) {
                appendLog('argument', null, null, `Argument round ${currentRound} feedback submitted`);
            }
            
            // Hide modal
            modal.style.display = 'none';
            
            // Continue pipeline
            appendLog('system', null, null, skipToVoting ? 'Skipping to voting...' : `Continuing argumentation...`);
            continuePipeline();
            
        } catch (error) {
            console.error('Failed to submit argument feedback:', error);
            appendLog('system', null, null, `Error: ${error.message}`, 'error');
            alert('Failed to submit feedback: ' + error.message);
        }
    }
    
    // Utility
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Event listeners
    document.addEventListener('DOMContentLoaded', () => {
        initLogPanel();
        
        document.getElementById('btn-start').addEventListener('click', startSession);
        
        // Diversify button
        const diversifyBtn = document.getElementById('btn-diversify');
        if (diversifyBtn) {
            diversifyBtn.addEventListener('click', diversifyWorkers);
        }
        
        // Enter key in prompt
        document.getElementById('prompt-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                startSession();
            }
        });
        
        // Round feedback modal buttons
        const continueRoundBtn = document.getElementById('btn-continue-round');
        if (continueRoundBtn) {
            continueRoundBtn.addEventListener('click', () => submitRoundFeedback(false));
        }
        
        const skipToSynthesisBtn = document.getElementById('btn-skip-to-synthesis');
        if (skipToSynthesisBtn) {
            skipToSynthesisBtn.addEventListener('click', () => submitRoundFeedback(true));
        }
        
        // Argument feedback modal buttons
        const continueArgumentBtn = document.getElementById('btn-continue-argument');
        if (continueArgumentBtn) {
            continueArgumentBtn.addEventListener('click', () => submitArgumentFeedback(false));
        }
        
        const skipToVotingBtn = document.getElementById('btn-skip-to-voting');
        if (skipToVotingBtn) {
            skipToVotingBtn.addEventListener('click', () => submitArgumentFeedback(true));
        }
        
        // Collaboration modal buttons
        const continueCollabBtn = document.getElementById('btn-continue-collab');
        if (continueCollabBtn) {
            continueCollabBtn.addEventListener('click', () => submitCollabFeedback(false));
        }
        
        const skipCollabBtn = document.getElementById('btn-skip-collab');
        if (skipCollabBtn) {
            skipCollabBtn.addEventListener('click', () => submitCollabFeedback(true));
        }
        
        // Close modal on outside click
        const roundModal = document.getElementById('round-feedback-modal');
        if (roundModal) {
            roundModal.addEventListener('click', (e) => {
                // Don't close on outside click for this modal - require explicit action
            });
        }
    });
    
    // Export
    window.aiCouncil.session = {
        startSession,
        handlePipelineEvent,
        appendLog,
        clearLog,
        getWorkerDisplayId,
        toggleLogEntry,
        populateLogFromEntries,
        getLogEntries: () => logEntries,
        showRoundFeedbackModal,
        submitRoundFeedback,
        showCollabFeedbackModal,
        submitCollabFeedback,
        showArgumentFeedbackModal,
        submitArgumentFeedback,
        continuePipeline,
        initChatTimeline,
        addChatMessage,
        addStageDivider,
        updateWorkerRoster
    };
})();
