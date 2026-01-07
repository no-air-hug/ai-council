/**
 * AI Council - Persona Management
 * Handles persona CRUD operations and UI.
 */

(function() {
    const { state, api } = window.aiCouncil;
    
    let editingPersonaId = null;
    
    // Load and display personas
    async function loadPersonas() {
        try {
            const data = await api.get('/personas');
            state.personas = data.personas;
            renderPersonasGrid();
        } catch (error) {
            console.error('Failed to load personas:', error);
        }
    }
    
    function renderPersonasGrid() {
        const grid = document.getElementById('personas-grid');
        grid.innerHTML = '';
        
        state.personas.forEach(persona => {
            const card = createPersonaCard(persona);
            grid.appendChild(card);
        });
    }
    
    function createPersonaCard(persona) {
        const card = document.createElement('div');
        card.className = `persona-card ${persona.is_default ? 'default' : ''}`;
        
        // Truncate system prompt for display
        const shortPrompt = persona.system_prompt?.substring(0, 150) + 
            (persona.system_prompt?.length > 150 ? '...' : '');
        
        card.innerHTML = `
            <div class="persona-name">${escapeHtml(persona.name)}</div>
            <div class="persona-style">${persona.reasoning_style} / ${persona.tone}</div>
            <div class="persona-description">${escapeHtml(shortPrompt)}</div>
            <div class="persona-stats">
                <span>Used: ${persona.usage_count || 0}x</span>
                <span>Win rate: ${((persona.win_rate || 0) * 100).toFixed(0)}%</span>
            </div>
            ${!persona.is_default ? `
            <div class="persona-actions">
                <button class="btn-secondary btn-edit" data-id="${persona.id}">Edit</button>
                <button class="btn-secondary btn-delete" data-id="${persona.id}">Delete</button>
            </div>
            ` : `
            <div class="persona-actions">
                <span style="font-size: 0.75rem; color: var(--text-muted);">Default persona (read-only)</span>
            </div>
            `}
        `;
        
        // Event handlers
        const editBtn = card.querySelector('.btn-edit');
        if (editBtn) {
            editBtn.addEventListener('click', () => editPersona(persona));
        }
        
        const deleteBtn = card.querySelector('.btn-delete');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => deletePersona(persona.id));
        }
        
        return card;
    }
    
    // Open new persona modal
    function openNewPersonaModal() {
        editingPersonaId = null;
        
        document.getElementById('persona-modal-title').textContent = 'New Persona';
        document.getElementById('persona-name').value = '';
        document.getElementById('persona-prompt').value = '';
        document.getElementById('persona-style').value = 'structured';
        document.getElementById('persona-tone').value = 'formal';
        
        document.getElementById('persona-modal').style.display = 'flex';
    }
    
    // Edit existing persona
    function editPersona(persona) {
        editingPersonaId = persona.id;
        
        document.getElementById('persona-modal-title').textContent = 'Edit Persona';
        document.getElementById('persona-name').value = persona.name;
        document.getElementById('persona-prompt').value = persona.system_prompt;
        document.getElementById('persona-style').value = persona.reasoning_style;
        document.getElementById('persona-tone').value = persona.tone;
        
        document.getElementById('persona-modal').style.display = 'flex';
    }
    
    // Save persona
    async function savePersona() {
        const name = document.getElementById('persona-name').value.trim();
        const systemPrompt = document.getElementById('persona-prompt').value.trim();
        const reasoningStyle = document.getElementById('persona-style').value;
        const tone = document.getElementById('persona-tone').value;
        
        if (!name || !systemPrompt) {
            alert('Name and system prompt are required');
            return;
        }
        
        try {
            if (editingPersonaId) {
                // Update existing
                await api.put(`/personas/${editingPersonaId}`, {
                    name,
                    system_prompt: systemPrompt,
                    reasoning_style: reasoningStyle,
                    tone
                });
            } else {
                // Create new
                await api.post('/personas', {
                    name,
                    system_prompt: systemPrompt,
                    reasoning_style: reasoningStyle,
                    tone
                });
            }
            
            closePersonaModal();
            loadPersonas();
            
        } catch (error) {
            console.error('Failed to save persona:', error);
            alert('Failed to save persona: ' + error.message);
        }
    }
    
    // Delete persona
    async function deletePersona(personaId) {
        if (!confirm('Are you sure you want to delete this persona?')) {
            return;
        }
        
        try {
            await api.delete(`/personas/${personaId}`);
            loadPersonas();
        } catch (error) {
            console.error('Failed to delete persona:', error);
            alert('Failed to delete persona: ' + error.message);
        }
    }
    
    // Close modal
    function closePersonaModal() {
        editingPersonaId = null;
        document.getElementById('persona-modal').style.display = 'none';
    }
    
    // Import text modal (placeholder for Phase 5)
    function openImportModal() {
        alert('Raw text import will be available in a future update.');
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
        document.getElementById('btn-new-persona').addEventListener('click', openNewPersonaModal);
        document.getElementById('btn-import-text').addEventListener('click', openImportModal);
        document.getElementById('btn-close-persona-modal').addEventListener('click', closePersonaModal);
        document.getElementById('btn-cancel-persona').addEventListener('click', closePersonaModal);
        document.getElementById('btn-save-persona').addEventListener('click', savePersona);
    });
    
    // Export
    window.aiCouncil.personas = {
        loadPersonas,
        renderPersonasGrid
    };
    
    // Also expose loadPersonas globally for navigation
    window.loadPersonas = loadPersonas;
})();


