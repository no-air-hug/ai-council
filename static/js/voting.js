/**
 * AI Council - Voting System
 * Handles candidate display, voting, and comprehensive feedback submission.
 */

(function() {
    const { state, api, showView } = window.aiCouncil;
    
    // Voting state
    const votingState = {
        votes: {},  // candidate_id -> rank
        candidateFeedback: {},  // candidate_id -> text
        workerFeedback: {},  // worker_id -> text
        overallFeedback: "",
        synthesizerFeedback: "",
        promptRating: 0,  // 0 = skip, 1-5 = rating
        promptFeedback: ""
    };
    
    // Store worker info for display
    let workerInfo = {};
    
    // Build voting UI
    function buildVotingUI(candidates, aiScores, arguments, workers) {
        const container = document.getElementById('candidates-container');
        container.innerHTML = '';
        
        // Reset voting state
        votingState.votes = {};
        votingState.candidateFeedback = {};
        votingState.workerFeedback = {};
        votingState.overallFeedback = "";
        votingState.synthesizerFeedback = "";
        votingState.promptRating = 0;
        votingState.promptFeedback = "";
        
        // Display original prompt
        displayPrompt();
        
        // Store worker info
        workerInfo = {};
        if (workers) {
            workers.forEach(w => {
                workerInfo[w.id] = {
                    id: w.id,
                    personaName: w.persona?.name || null,
                    displayId: w.persona?.name ? `${w.persona.name} (${w.id})` : w.id
                };
            });
        }
        
        // Build conversation history from session log
        buildConversationHistory();
        
        // Handle case when no candidates were synthesized
        if (!candidates || candidates.length === 0) {
            container.innerHTML = `
                <div class="no-candidates-warning">
                    <h3>⚠️ No Candidates Synthesized</h3>
                    <p>The synthesizer was unable to generate distinct candidates from the worker proposals.</p>
                    <p>This can happen when:</p>
                    <ul>
                        <li>Worker proposals were too similar</li>
                        <li>The model returned an invalid response</li>
                        <li>Token limits were exceeded</li>
                    </ul>
                    <p>You can still provide feedback on workers and the synthesizer below.</p>
                </div>
            `;
            // Enable submit button for feedback-only submission
            const submitBtn = document.getElementById('btn-submit-votes');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Feedback';
            }
        } else {
            // Build candidate cards
            candidates.forEach((candidate, index) => {
                const card = createCandidateCard(candidate, aiScores, arguments, index);
                container.appendChild(card);
            });
        }
        
        // Build worker feedback grid
        buildWorkerFeedbackGrid(workers);
        
        // Reset overall and synthesizer feedback textareas
        const overallTextarea = document.getElementById('overall-feedback');
        if (overallTextarea) overallTextarea.value = '';
        
        const synthTextarea = document.getElementById('synthesizer-feedback');
        if (synthTextarea) synthTextarea.value = '';
        
        // Update submit button state
        updateSubmitButton();
        
        // Add event listeners for feedback textareas
        setupFeedbackListeners();
        
        // Setup conversation toggle
        setupConversationToggle();
    }
    
    // Build conversation history from session log entries
    function buildConversationHistory() {
        const container = document.getElementById('voting-conversation');
        if (!container) return;
        
        container.innerHTML = '';
        
        // Get log entries from session module
        const logEntries = window.aiCouncil.session?.getLogEntries?.() || [];
        
        // Filter and format relevant entries
        let currentStage = null;
        
        logEntries.forEach(entry => {
            // Skip system entries and brief entries
            if (entry.stage === 'system' || !entry.content || entry.content.length < 20) return;
            
            // Add stage divider when stage changes
            const stageLabel = getStageLabel(entry.stage);
            if (stageLabel && entry.stage !== currentStage && entry.workerId) {
                currentStage = entry.stage;
                const divider = document.createElement('div');
                divider.className = 'conversation-msg stage-divider';
                divider.innerHTML = `<span class="conversation-stage-label">${stageLabel}</span>`;
                container.appendChild(divider);
            }
            
            // Create message based on entry type
            if (entry.workerId || entry.stage === 'questions' || entry.stage === 'synthesis' || entry.stage === 'commentary') {
                const msg = createConversationMessage(entry);
                if (msg) container.appendChild(msg);
            }
        });
        
        // Add final arguments for each worker from state
        if (state.arguments) {
            const argDivider = document.createElement('div');
            argDivider.className = 'conversation-msg stage-divider';
            argDivider.innerHTML = `<span class="conversation-stage-label">Final Arguments</span>`;
            container.appendChild(argDivider);
            
            for (const [workerId, arg] of Object.entries(state.arguments)) {
                const worker = workerInfo[workerId];
                const workerNum = workerId.replace('worker_', '');
                
                const msg = document.createElement('div');
                msg.className = 'conversation-msg';
                msg.innerHTML = `
                    <div class="msg-avatar worker-${workerNum}">W${workerNum}</div>
                    <div class="msg-content">
                        <div class="msg-header">
                            <span class="msg-author">${escapeHtml(worker?.displayId || workerId)}</span>
                            <span class="msg-stage">argument</span>
                        </div>
                        <div class="msg-body">${escapeHtml(arg.main_argument || '')}</div>
                    </div>
                `;
                container.appendChild(msg);
            }
        }
    }
    
    // Create a conversation message element
    function createConversationMessage(entry) {
        const msg = document.createElement('div');
        
        const isSynthesizer = entry.stage === 'questions' || entry.stage === 'synthesis' || entry.stage === 'commentary' || entry.workerId === 'synthesizer';
        
        if (isSynthesizer) {
            msg.className = 'conversation-msg synthesizer';
            msg.innerHTML = `
                <div class="msg-avatar synthesizer">S</div>
                <div class="msg-content">
                    <div class="msg-header">
                        <span class="msg-author">Synthesizer</span>
                        <span class="msg-stage">${entry.stage}</span>
                    </div>
                    <div class="msg-body">${createExpandableContent(entry.content)}</div>
                </div>
            `;
        } else if (entry.workerId) {
            const worker = workerInfo[entry.workerId];
            const workerNum = entry.workerId.replace('worker_', '');
            const displayId = worker?.displayId || entry.workerId;
            
            msg.className = 'conversation-msg';
            msg.innerHTML = `
                <div class="msg-avatar worker-${workerNum}">W${workerNum}</div>
                <div class="msg-content">
                    <div class="msg-header">
                        <span class="msg-author">${escapeHtml(displayId)}</span>
                        <span class="msg-stage">${entry.stage}</span>
                    </div>
                    <div class="msg-body">${createExpandableContent(entry.content)}</div>
                </div>
            `;
        } else {
            return null;  // Skip entries without worker or synthesizer
        }
        
        return msg;
    }
    
    // Get human-readable stage label
    function getStageLabel(stage) {
        const labels = {
            'draft': 'Initial Proposals',
            'questions': 'Clarifying Questions',
            'refinement': 'Refinement',
            'synthesis': 'Candidate Synthesis',
            'argument': 'Arguments',
            'argumentation': 'Argumentation',
            'commentary': 'Synthesizer Commentary'
        };
        return labels[stage] || null;
    }
    
    // Create expandable content for long messages
    function createExpandableContent(text) {
        if (!text) return '';
        const maxLength = 500;
        if (text.length <= maxLength) {
            return `<div class="msg-body-text">${escapeHtml(text)}</div>`;
        }
        const uniqueId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        return `
            <div class="msg-body-text">
                <div class="msg-preview" id="${uniqueId}-preview">${escapeHtml(text.substring(0, maxLength))}...</div>
                <div class="msg-full" id="${uniqueId}-full" style="display:none">${escapeHtml(text)}</div>
                <button class="btn-expand-msg" onclick="
                    document.getElementById('${uniqueId}-preview').style.display='none';
                    document.getElementById('${uniqueId}-full').style.display='block';
                    this.style.display='none';
                ">Show full message</button>
            </div>
        `;
    }
    
    // Setup conversation toggle functionality
    function setupConversationToggle() {
        const toggle = document.getElementById('conversation-toggle');
        const content = document.getElementById('conversation-content');
        
        if (toggle && content) {
            toggle.addEventListener('click', () => {
                content.classList.toggle('collapsed');
            });
        }
    }
    
    function createCandidateCard(candidate, aiScores, arguments, index) {
        const card = document.createElement('div');
        card.className = 'candidate-card';
        card.id = `candidate-${candidate.id}`;
        
        // Get AI score
        const scoreData = aiScores[candidate.id] || {};
        const score = typeof scoreData === 'object' ? scoreData.score : scoreData;
        
        // Get source worker display info
        let sourceDisplay = 'synthesized';
        if (candidate.source_workers && candidate.source_workers.length > 0) {
            sourceDisplay = candidate.source_workers.map(wid => {
                const info = workerInfo[wid];
                return info ? info.displayId : wid;
            }).join(', ');
        }
        
        // Get argument from source worker
        let argumentText = '';
        if (candidate.source_workers && candidate.source_workers.length > 0) {
            const sourceWorker = candidate.source_workers[0];
            if (arguments && arguments[sourceWorker]) {
                argumentText = arguments[sourceWorker].main_argument || '';
            }
        }
        
        card.innerHTML = `
            <div class="candidate-header">
                <div>
                    <div class="candidate-title">Candidate ${index + 1}</div>
                    <div class="candidate-source">From: ${escapeHtml(sourceDisplay)}</div>
                </div>
                <div class="ai-score">
                    <span class="ai-score-label">AI Score:</span>
                    <span class="ai-score-value">${score?.toFixed(1) || '--'}/10</span>
                </div>
            </div>
            <div class="candidate-body">
                ${argumentText ? `
                <div class="candidate-argument">
                    <div class="argument-label">Why this is best</div>
                    <div class="argument-text">${escapeHtml(argumentText)}</div>
                </div>
                ` : ''}
                <div class="candidate-output">
                    <div class="output-summary">${escapeHtml(candidate.summary)}</div>
                    ${candidate.best_use_case ? `
                    <div class="output-meta">
                        <strong>Best for:</strong> ${escapeHtml(candidate.best_use_case)}
                    </div>
                    ` : ''}
                    ${candidate.trade_offs?.length ? `
                    <div class="output-meta">
                        <strong>Trade-offs:</strong> ${candidate.trade_offs.map(t => escapeHtml(t)).join(', ')}
                    </div>
                    ` : ''}
                </div>
            </div>
            <div class="candidate-footer">
                <div class="vote-options">
                    <button class="vote-btn" data-candidate="${candidate.id}" data-rank="1">1st</button>
                    <button class="vote-btn" data-candidate="${candidate.id}" data-rank="2">2nd</button>
                    <button class="vote-btn" data-candidate="${candidate.id}" data-rank="3">3rd</button>
                    <button class="vote-btn" data-candidate="${candidate.id}" data-rank="0">Skip</button>
                </div>
                <div class="feedback-input">
                    <input type="text" 
                           placeholder="Feedback on this candidate (optional)..." 
                           data-candidate="${candidate.id}"
                           class="candidate-feedback-text">
                </div>
            </div>
        `;
        
        // Add vote button handlers
        card.querySelectorAll('.vote-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const candidateId = btn.dataset.candidate;
                const rank = parseInt(btn.dataset.rank);
                setVote(candidateId, rank);
            });
        });
        
        // Add feedback handler
        card.querySelector('.candidate-feedback-text').addEventListener('input', (e) => {
            votingState.candidateFeedback[candidate.id] = e.target.value;
        });
        
        return card;
    }
    
    function buildWorkerFeedbackGrid(workers) {
        const grid = document.getElementById('worker-feedback-grid');
        if (!grid) return;
        
        grid.innerHTML = '';
        
        if (!workers || workers.length === 0) {
            grid.innerHTML = '<p class="text-muted">No worker information available</p>';
            return;
        }
        
        workers.forEach(w => {
            const card = document.createElement('div');
            card.className = 'worker-feedback-card';
            
            const displayId = w.persona?.name ? `${w.persona.name} (${w.id})` : w.id;
            const personaName = w.persona?.name || 'No persona';
            
            card.innerHTML = `
                <div class="worker-feedback-header">
                    <span class="worker-feedback-name">${escapeHtml(w.id)}</span>
                    <span class="worker-feedback-persona">${escapeHtml(personaName)}</span>
                </div>
                <textarea 
                    data-worker="${w.id}"
                    placeholder="Feedback on ${escapeHtml(displayId)}..."
                    class="worker-feedback-text"
                ></textarea>
            `;
            
            // Add feedback handler
            card.querySelector('.worker-feedback-text').addEventListener('input', (e) => {
                votingState.workerFeedback[w.id] = e.target.value;
            });
            
            grid.appendChild(card);
        });
    }
    
    function setupFeedbackListeners() {
        const overallTextarea = document.getElementById('overall-feedback');
        if (overallTextarea) {
            overallTextarea.addEventListener('input', (e) => {
                votingState.overallFeedback = e.target.value;
            });
        }
        
        const synthTextarea = document.getElementById('synthesizer-feedback');
        if (synthTextarea) {
            synthTextarea.addEventListener('input', (e) => {
                votingState.synthesizerFeedback = e.target.value;
            });
        }
        
        // Prompt feedback listeners
        const promptFeedbackTextarea = document.getElementById('prompt-feedback');
        if (promptFeedbackTextarea) {
            promptFeedbackTextarea.addEventListener('input', (e) => {
                votingState.promptFeedback = e.target.value;
            });
        }
        
        // Prompt rating buttons
        const ratingButtons = document.querySelectorAll('#prompt-rating-buttons .rating-btn');
        ratingButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const rating = parseInt(btn.dataset.rating);
                setPromptRating(rating);
            });
        });
    }
    
    // Display original prompt in voting view
    function displayPrompt() {
        const promptDisplay = document.getElementById('prompt-display');
        const promptInput = document.getElementById('prompt-input');
        
        if (promptDisplay) {
            // Get prompt from state or input
            const prompt = state.prompt || (promptInput ? promptInput.value : '');
            promptDisplay.textContent = prompt || 'No prompt available';
        }
        
        // Reset prompt feedback UI
        const promptFeedbackTextarea = document.getElementById('prompt-feedback');
        if (promptFeedbackTextarea) {
            promptFeedbackTextarea.value = '';
        }
        
        // Reset rating buttons
        const ratingButtons = document.querySelectorAll('#prompt-rating-buttons .rating-btn');
        ratingButtons.forEach(btn => btn.classList.remove('active'));
    }
    
    // Set prompt rating
    function setPromptRating(rating) {
        votingState.promptRating = rating;
        
        // Update button states
        const ratingButtons = document.querySelectorAll('#prompt-rating-buttons .rating-btn');
        ratingButtons.forEach(btn => {
            const btnRating = parseInt(btn.dataset.rating);
            btn.classList.toggle('active', btnRating === rating);
        });
    }
    
    function setVote(candidateId, rank) {
        // If selecting a rank > 0, check if another candidate has this rank
        if (rank > 0) {
            for (const [cid, r] of Object.entries(votingState.votes)) {
                if (cid !== candidateId && r === rank) {
                    // Clear that rank from other candidate
                    votingState.votes[cid] = 0;
                    updateCandidateVoteUI(cid, 0);
                }
            }
        }
        
        votingState.votes[candidateId] = rank;
        updateCandidateVoteUI(candidateId, rank);
        updateSubmitButton();
    }
    
    function updateCandidateVoteUI(candidateId, rank) {
        const card = document.getElementById(`candidate-${candidateId}`);
        if (!card) return;
        
        // Update button states
        card.querySelectorAll('.vote-btn').forEach(btn => {
            const btnRank = parseInt(btn.dataset.rank);
            btn.classList.toggle('active', btnRank === rank);
        });
        
        // Update card selection state
        card.classList.toggle('selected', rank > 0);
    }
    
    function updateSubmitButton() {
        const submitBtn = document.getElementById('btn-submit-votes');
        if (!submitBtn) return;
        
        // Enable if any interaction has occurred:
        // - At least one vote cast (rank > 0)
        // - OR any feedback provided
        // - OR prompt rating given
        // - OR just candidates exist (allow submission without ranking)
        const hasVotes = Object.values(votingState.votes).some(r => r > 0);
        const hasCandidateFeedback = Object.values(votingState.candidateFeedback || {}).some(f => f && f.trim());
        const hasOverallFeedback = votingState.overallFeedback && votingState.overallFeedback.trim();
        const hasWorkerFeedback = Object.values(votingState.workerFeedback || {}).some(f => f && f.trim());
        const hasPromptFeedback = votingState.promptFeedback && votingState.promptFeedback.trim();
        const hasPromptRating = votingState.promptRating !== null && votingState.promptRating !== undefined;
        const hasCandidates = state.candidates && state.candidates.length > 0;
        
        // Enable button if there are candidates (even without explicit ranking)
        // This allows users to proceed with default values or just feedback
        const canSubmit = hasCandidates || hasVotes || hasCandidateFeedback || hasOverallFeedback || 
                          hasWorkerFeedback || hasPromptFeedback || hasPromptRating;
        
        submitBtn.disabled = !canSubmit;
    }
    
    // Submit votes
    async function submitVotes() {
        try {
            // Check if there are candidates to vote on
            if (!state.candidates || state.candidates.length === 0) {
                alert('No candidates available to vote on. The synthesis may have failed.');
                return;
            }
            
            // Collect all feedback
            const submitData = {
                votes: votingState.votes,
                candidate_feedback: votingState.candidateFeedback,
                overall_feedback: votingState.overallFeedback,
                worker_feedback: votingState.workerFeedback,
                synthesizer_feedback: votingState.synthesizerFeedback,
                prompt_rating: votingState.promptRating,
                prompt_feedback: votingState.promptFeedback
            };
            
            // Submit votes
            const result = await api.post(`/session/${state.sessionId}/vote`, submitData);
            
            // Store voting result
            state.votingResult = result;
            
            // Finalize using SSE stream for axiom analysis + final output
            await runFinalizeStream();
            
        } catch (error) {
            console.error('Failed to submit votes:', error);
            alert('Failed to submit votes: ' + error.message);
        }
    }
    
    // State for axiom analysis
    let axiomData = {
        workerAxioms: {},
        networkAxioms: null
    };
    
    async function runFinalizeStream() {
        return new Promise((resolve, reject) => {
            const eventSource = new EventSource(`/api/session/${state.sessionId}/finalize`);
            
            let finalOutput = null;
            let winningCandidate = null;
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'stage_start') {
                        console.log(`Finalize stage: ${data.stage}`);
                        // Show loading indicator in final view
                        showFinalizeProgress(data.stage);
                    } else if (data.type === 'axiom_extracted') {
                        const axiomCount = data.axioms?.length || 0;
                        console.log(`Axioms from ${data.source}:`, axiomCount);
                        if (data.source === 'user') {
                            axiomData.userAxioms = data.axioms || [];
                        } else if (data.source && data.source.startsWith('worker_')) {
                            axiomData.workerAxioms[data.source] = {
                                axioms: data.axioms || [],
                                displayId: data.worker_display_id || data.source,
                                theoryContribution: data.theory_contribution || ''
                            };
                        }
                        // Update progress display
                        updateAxiomProgress(data.source, axiomCount);
                    } else if (data.type === 'stage_complete' && data.stage === 'axiom_analysis') {
                        // Handle axiom network from stage_complete event
                        if (data.axiom_network) {
                            axiomData.networkSummary = data.axiom_network;
                        }
                    } else if (data.type === 'final_output') {
                        finalOutput = data.output;
                        winningCandidate = data.winning_candidate;
                        // Also capture session_summary if provided
                        if (data.session_summary) {
                            axiomData.sessionSummary = data.session_summary;
                        }
                    } else if (data.type === 'error') {
                        console.error('Finalize error:', data.message);
                        eventSource.close();
                        reject(new Error(data.message));
                    } else if (data.type === 'info') {
                        console.log('Finalize info:', data.message);
                    }
                } catch (e) {
                    console.error('Parse error:', e);
                }
            };
            
            eventSource.onerror = (err) => {
                eventSource.close();
                
                // If we have a final output, show it
                if (finalOutput) {
                    showFinalOutput({
                        final_output: finalOutput,
                        winning_candidate: winningCandidate
                    });
                    resolve();
                } else {
                    // Try submitting final feedback anyway to complete
                    submitFinalFeedback('').then(() => {
                        resolve();
                    }).catch(reject);
                }
            };
        });
    }
    
    async function submitFinalFeedback(feedback) {
        try {
            const result = await api.post(`/session/${state.sessionId}/final-feedback`, { feedback });
            showFinalOutput(result);
        } catch (error) {
            console.error('Failed to submit final feedback:', error);
        }
    }
    
    function showFinalizeProgress(stage) {
        const finalContent = document.getElementById('final-content');
        if (!finalContent) return;
        
        const stageLabels = {
            'axiom_analysis': 'Analyzing axioms...',
            'final_output': 'Generating final output...'
        };
        
        const label = stageLabels[stage] || `Processing: ${stage}`;
        finalContent.innerHTML = `<div class="finalize-progress"><div class="spinner"></div><span>${label}</span></div>`;
        showView('final');
    }
    
    function updateAxiomProgress(source, count) {
        const finalContent = document.getElementById('final-content');
        if (!finalContent) return;
        
        // Append to progress display
        const progressEl = finalContent.querySelector('.finalize-progress');
        if (progressEl) {
            const sourceLabel = source === 'user' ? 'User feedback' : source.replace('_', ' ');
            const msg = document.createElement('div');
            msg.className = 'axiom-progress-item';
            msg.textContent = `✓ ${sourceLabel}: ${count} axiom${count !== 1 ? 's' : ''} extracted`;
            progressEl.appendChild(msg);
        }
    }
    
    function displayAxiomNetwork(network) {
        const axiomSection = document.getElementById('axiom-section');
        const sharedAxiomsEl = document.getElementById('shared-axioms');
        const conflictsEl = document.getElementById('axiom-conflicts');
        const theoriesEl = document.getElementById('derived-theories');
        
        if (!axiomSection) return;
        
        axiomSection.style.display = 'block';
        
        // Display shared axioms
        if (network.shared_axioms && network.shared_axioms.length > 0) {
            let html = '<h4>Shared Axioms</h4><ul class="axiom-list">';
            network.shared_axioms.forEach(axiom => {
                const sources = axiom.sources ? axiom.sources.join(', ') : 'Unknown';
                html += `<li class="axiom-item">
                    <div class="axiom-statement">${escapeHtml(axiom.statement)}</div>
                    <div class="axiom-meta">
                        <span class="axiom-confidence">Confidence: ${(axiom.confidence * 100).toFixed(0)}%</span>
                        <span class="axiom-sources">Sources: ${sources}</span>
                    </div>
                </li>`;
            });
            html += '</ul>';
            sharedAxiomsEl.innerHTML = html;
        }
        
        // Display conflicts
        if (network.conflicts && network.conflicts.length > 0) {
            let html = '<h4>Axiom Conflicts</h4><ul class="conflict-list">';
            network.conflicts.forEach(conflict => {
                html += `<li class="conflict-item">
                    <div class="conflict-axioms">
                        <div class="axiom-a"><strong>A:</strong> ${escapeHtml(conflict.axiom_a)}</div>
                        <div class="axiom-b"><strong>B:</strong> ${escapeHtml(conflict.axiom_b)}</div>
                    </div>
                    <div class="conflict-nature">Nature: ${conflict.nature || 'Unspecified'}</div>
                </li>`;
            });
            html += '</ul>';
            conflictsEl.innerHTML = html;
        }
        
        // Display theories
        if (network.theories && network.theories.length > 0) {
            let html = '<h4>Derived Theories</h4><ul class="theory-list">';
            network.theories.forEach(theory => {
                const proponents = theory.proponents ? theory.proponents.join(', ') : 'Unknown';
                html += `<li class="theory-item">
                    <div class="theory-name">${escapeHtml(theory.name)}</div>
                    <div class="theory-summary">${escapeHtml(theory.summary)}</div>
                    <div class="theory-meta">
                        <span class="theory-proponents">Proponents: ${proponents}</span>
                    </div>
                </li>`;
            });
            html += '</ul>';
            theoriesEl.innerHTML = html;
        }
    }
    
    function showFinalOutput(result) {
        const finalContent = document.getElementById('final-content');
        const finalMeta = document.getElementById('final-meta');
        
        // Display final output with formatting
        let outputHtml = '<div class="final-response">';
        outputHtml += '<h4>Final Response:</h4>';
        outputHtml += `<div class="response-text">${formatOutputText(result.final_output || 'No final output generated.')}</div>`;
        outputHtml += '</div>';
        
        finalContent.innerHTML = outputHtml;
        
        // Display session summary
        let metaHtml = '<h4>Session Summary</h4>';
        metaHtml += '<div class="meta-grid">';
        
        if (result.voting_result) {
            metaHtml += `<div class="meta-item">
                <span class="meta-label">Winning Candidate:</span>
                <span class="meta-value">${result.voting_result.winning_candidate_id || 'N/A'}</span>
            </div>`;
            if (result.voting_result.winning_reason) {
                metaHtml += `<div class="meta-item full-width">
                    <span class="meta-label">Selection Reason:</span>
                    <span class="meta-value">${escapeHtml(result.voting_result.winning_reason)}</span>
                </div>`;
            }
            
            // Show feedback summary if provided
            if (result.voting_result.overall_feedback) {
                metaHtml += `<div class="meta-item full-width">
                    <span class="meta-label">Your Feedback:</span>
                    <span class="meta-value">${escapeHtml(result.voting_result.overall_feedback)}</span>
                </div>`;
            }
        }
        
        // Session statistics
        const sessionSummary = result.session_summary || axiomData.sessionSummary;
        if (sessionSummary) {
            metaHtml += `<div class="meta-item">
                <span class="meta-label">Total Pipeline Entries:</span>
                <span class="meta-value">${sessionSummary.total_entries || 'N/A'}</span>
            </div>`;
            if (sessionSummary.stages_completed) {
                metaHtml += `<div class="meta-item">
                    <span class="meta-label">Stages Completed:</span>
                    <span class="meta-value">${sessionSummary.stages_completed}</span>
                </div>`;
            }
        }
        
        metaHtml += '</div>';
        
        // Display axiom summary in meta section
        const axiomSummary = result.axiom_network || axiomData.networkSummary;
        if (axiomSummary) {
            metaHtml += '<h4>Axiom Analysis Summary</h4>';
            metaHtml += '<div class="axiom-summary-grid">';
            
            if (typeof axiomSummary.user_axioms === 'number') {
                metaHtml += `<div class="axiom-stat">
                    <span class="stat-value">${axiomSummary.user_axioms}</span>
                    <span class="stat-label">User Axioms</span>
                </div>`;
            }
            
            if (axiomSummary.worker_axioms) {
                const totalWorkerAxioms = Object.values(axiomSummary.worker_axioms).reduce((a, b) => a + b, 0);
                metaHtml += `<div class="axiom-stat">
                    <span class="stat-value">${totalWorkerAxioms}</span>
                    <span class="stat-label">Worker Axioms</span>
                </div>`;
            }
            
            if (typeof axiomSummary.meta_axioms === 'number') {
                metaHtml += `<div class="axiom-stat">
                    <span class="stat-value">${axiomSummary.meta_axioms}</span>
                    <span class="stat-label">Meta Axioms</span>
                </div>`;
            }
            
            if (typeof axiomSummary.shared_axioms === 'number') {
                metaHtml += `<div class="axiom-stat">
                    <span class="stat-value">${axiomSummary.shared_axioms}</span>
                    <span class="stat-label">Shared Axioms</span>
                </div>`;
            }
            
            if (typeof axiomSummary.conflicts === 'number') {
                metaHtml += `<div class="axiom-stat">
                    <span class="stat-value">${axiomSummary.conflicts}</span>
                    <span class="stat-label">Conflicts</span>
                </div>`;
            }
            
            metaHtml += '</div>';
            
            // Display theories if available
            if (axiomSummary.theories && axiomSummary.theories.length > 0) {
                metaHtml += '<div class="theories-section">';
                metaHtml += '<h5>Derived Theories:</h5>';
                axiomSummary.theories.forEach(theory => {
                    const theoryName = theory.name || 'Unnamed Theory';
                    const theorySummary = theory.summary || '';
                    metaHtml += `<div class="theory-card">
                        <div class="theory-name">${escapeHtml(theoryName)}</div>
                        <div class="theory-summary">${escapeHtml(theorySummary)}</div>
                    </div>`;
                });
                metaHtml += '</div>';
            }
        }
        
        // Display collected worker axioms if we have them
        if (Object.keys(axiomData.workerAxioms).length > 0) {
            metaHtml += '<h4>Worker Axiom Contributions</h4>';
            metaHtml += '<div class="worker-axioms-section">';
            
            for (const [workerId, workerData] of Object.entries(axiomData.workerAxioms)) {
                const displayId = workerData.displayId || workerId;
                const axiomList = workerData.axioms || [];
                
                metaHtml += `<div class="worker-axiom-card">
                    <div class="worker-axiom-header">${escapeHtml(displayId)} (${axiomList.length} axiom${axiomList.length !== 1 ? 's' : ''})</div>`;
                
                if (axiomList.length > 0) {
                    metaHtml += '<ul class="axiom-full-list">';
                    axiomList.forEach((axiom, idx) => {
                        const statement = axiom.statement || JSON.stringify(axiom);
                        const axiomType = axiom.axiom_type || 'unknown';
                        const confidence = axiom.confidence ? `${Math.round(axiom.confidence * 100)}%` : 'N/A';
                        metaHtml += `<li class="axiom-item">
                            <div class="axiom-statement">${escapeHtml(statement)}</div>
                            <div class="axiom-meta">
                                <span class="axiom-type">${axiomType}</span>
                                <span class="axiom-confidence">Confidence: ${confidence}</span>
                            </div>`;
                        if (axiom.vulnerability) {
                            metaHtml += `<div class="axiom-vulnerability">⚠ Vulnerability: ${escapeHtml(axiom.vulnerability)}</div>`;
                        }
                        if (axiom.potential_biases && axiom.potential_biases.length > 0) {
                            metaHtml += `<div class="axiom-biases">Biases: ${axiom.potential_biases.map(b => escapeHtml(b)).join(', ')}</div>`;
                        }
                        metaHtml += `</li>`;
                    });
                    metaHtml += '</ul>';
                }
                
                // Show theory contribution if available
                if (workerData.theoryContribution) {
                    metaHtml += `<div class="theory-contribution">${escapeHtml(workerData.theoryContribution)}</div>`;
                }
                
                metaHtml += '</div>';
            }
            
            metaHtml += '</div>';
        }
        
        finalMeta.innerHTML = metaHtml;
        
        // Show final feedback section
        const feedbackSection = document.getElementById('final-feedback-section');
        if (feedbackSection) {
            feedbackSection.style.display = 'block';
        }
        
        showView('final');
    }
    
    function formatOutputText(text) {
        if (!text) return '';
        // Convert line breaks to <br> and preserve formatting
        return text
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/^/, '<p>')
            .replace(/$/, '</p>');
    }
    
    async function submitFinalFeedbackUI() {
        const feedbackInput = document.getElementById('final-feedback-input');
        const feedback = feedbackInput ? feedbackInput.value.trim() : '';
        
        try {
            await submitFinalFeedback(feedback);
            alert('Final feedback submitted! Council session complete.');
            
            // Disable the button
            const btn = document.getElementById('btn-submit-final-feedback');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Feedback Submitted';
            }
        } catch (error) {
            console.error('Failed to submit final feedback:', error);
        }
    }
    
    // Go back to session view
    function backToSession() {
        showView('session');
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
        const submitVotesBtn = document.getElementById('btn-submit-votes');
        if (submitVotesBtn) {
            submitVotesBtn.addEventListener('click', submitVotes);
        }
        
        const finalFeedbackBtn = document.getElementById('btn-submit-final-feedback');
        if (finalFeedbackBtn) {
            finalFeedbackBtn.addEventListener('click', submitFinalFeedbackUI);
        }
        
        const backBtn = document.getElementById('btn-back-to-session');
        if (backBtn) {
            backBtn.addEventListener('click', backToSession);
        }
    });
    
    // Export
    window.aiCouncil.voting = {
        buildVotingUI,
        submitVotes,
        workerInfo
    };
})();
