# AI Council - Project Overview

## Vision

**Replace single-model prompting with structured multi-agent debate.**

Instead of asking one AI for an answer and hoping for the best, AI Council runs multiple AI "workers" with distinct thinking styles. They generate solutions, get challenged by a synthesizer, refine their ideas, argue their positions, and compete for your approval.

The result: better outputs through diversity, structure, and human oversight.

---

## Core Philosophy

```
Small models + structure + debate
        beats
  big models + vibes
```

| Traditional Approach | AI Council Approach |
|---------------------|---------------------|
| One model, one answer | Multiple models, competing answers |
| Hope it's good | Evaluate and vote on quality |
| Model decides everything | You have final say |
| Generic responses | Persona-driven perspectives |
| No learning | Logs enable fine-tuning |

---

## System Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AI COUNCIL PIPELINE                           │
└─────────────────────────────────────────────────────────────────────────┘

     ┌──────────────┐
     │  Your Prompt │
     └──────┬───────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: WORKER DRAFTS                                                 │
│  ─────────────────────                                                  │
│                                                                         │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐ │
│  │  Worker 1   │   │  Worker 2   │   │  Worker 3   │   │  Worker 4   │ │
│  │  Persona A  │   │  Persona B  │   │  Persona C  │   │  Persona D  │ │
│  │             │   │             │   │             │   │  (32GB only)│ │
│  │  Draft #1   │   │  Draft #2   │   │  Draft #3   │   │  Draft #4   │ │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘ │
│         │                 │                 │                 │        │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────┘
          │                 │                 │                 │
          └────────────────┬┴─────────────────┴─────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: SYNTHESIZER QUESTIONS                                         │
│  ──────────────────────────────                                         │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        SYNTHESIZER                               │   │
│  │                                                                  │   │
│  │  • Reviews all drafts                                           │   │
│  │  • Identifies gaps, conflicts, unclear assumptions              │   │
│  │  • Generates 1-2 targeted questions per worker                  │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
          ┌──────────────────────────┴──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: WORKER REFINEMENT (Configurable rounds + User feedback)       │
│  ────────────────────────────────────────────────────────────           │
│                                                                         │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                   │
│  │  Worker 1   │   │  Worker 2   │   │  Worker 3   │                   │
│  │             │   │             │   │             │                   │
│  │  Answers    │   │  Answers    │   │  Answers    │                   │
│  │  questions  │   │  questions  │   │  questions  │                   │
│  │             │   │             │   │             │                   │
│  │  Refines    │   │  Refines    │   │  Refines    │                   │
│  │  proposal   │   │  proposal   │   │  proposal   │                   │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                   │
│         │                 │                 │                          │
└─────────┼─────────────────┼─────────────────┼──────────────────────────┘
          │                 │                 │
          └────────────────┬┴─────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: CANDIDATE SYNTHESIS                                           │
│  ────────────────────────────                                           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        SYNTHESIZER                               │   │
│  │                                                                  │   │
│  │  Produces 3-4 distinct candidates:                              │   │
│  │  • Each with best use-case                                      │   │
│  │  • Trade-offs identified                                        │   │
│  │  • Failure modes noted                                          │   │
│  │  • Decision criteria explained                                  │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 5: MULTI-ROUND ARGUMENTATION (Configurable + User feedback)     │
│  ─────────────────────────────────────────────────────────────          │
│                                                                         │
│  Workers argue for their proposals in configurable rounds:              │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ROUND 1: Initial Arguments                                     │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐           │   │
│  │  │  Worker 1   │   │  Worker 2   │   │  Worker 3   │           │   │
│  │  │  "Mine is   │   │  "Mine is   │   │  "Mine is   │           │   │
│  │  │   best..."  │   │   best..."  │   │   best..."  │           │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘           │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  SYNTHESIZER COMMENTARY: "Key disagreements are... Worker 2    │   │
│  │  should address... Consider this angle..."                      │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  USER FEEDBACK (optional): Can provide guidance or skip         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ROUND 2+: Counter-Arguments                                    │   │
│  │  Workers respond to each other's arguments, refine positions    │   │
│  │  Synthesizer continues providing commentary                      │   │
│  │  Process repeats for configured number of rounds                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 6: VOTING                                                        │
│  ──────────────                                                         │
│                                                                         │
│  ┌────────────────────────────┐   ┌────────────────────────────┐       │
│  │        AI VOTE             │   │        YOUR VOTE           │       │
│  │                            │   │                            │       │
│  │  Synthesizer scores each   │   │  • Review arguments        │       │
│  │  candidate on rubric       │   │  • Review outputs          │       │
│  │                            │   │  • Rank candidates         │       │
│  │  Score: 0-10              │   │  • Feedback per candidate  │       │
│  │                            │   │  • Feedback per worker     │       │
│  │                            │   │  • Synthesizer feedback    │       │
│  │                            │   │  • Overall session notes   │       │
│  └────────────────────────────┘   └────────────────────────────┘       │
│                                                                         │
│  Combined score = (AI × 0.4) + (User × 0.6)                            │
│                                                                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 7: FINAL OUTPUT                                                  │
│  ─────────────────────                                                  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        SYNTHESIZER                               │   │
│  │                                                                  │   │
│  │  • Takes winning candidate                                      │   │
│  │  • Incorporates your feedback                                   │   │
│  │  • Produces clean final response                                │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      SESSION LOG (JSONL)                         │   │
│  │                                                                  │   │
│  │  All stages logged for fine-tuning:                             │   │
│  │  • Inputs, outputs, token counts                                │   │
│  │  • Persona assignments                                          │   │
│  │  • User votes and feedback                                      │   │
│  │  • AI scores                                                    │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Goals

### Primary Goals

| Goal | Description | Status |
|------|-------------|--------|
| **Multi-Agent Debate** | Run multiple AI workers with different perspectives | ✅ Implemented |
| **Hardware Efficient** | Work on consumer hardware (16GB RAM, 8GB VRAM) | ✅ Implemented |
| **Human-in-the-Loop** | User participates in voting, not just receiving output | ✅ Implemented |
| **Persona-Driven** | Workers have distinct thinking styles | ✅ Implemented |
| **Learn From Use** | Log everything for future fine-tuning | ✅ Implemented |

### Secondary Goals

| Goal | Description | Status |
|------|-------------|--------|
| **Persona Discovery** | Extract personas from user's own conversation data | ✅ Implemented |
| **LoRA Training** | Fine-tune personas based on voting history | 🔧 Scripts Ready |
| **Flexible Modes** | Easy switching between 16GB and 32GB modes | ✅ Implemented |
| **Real-time UI** | Watch pipeline execute with live updates | ✅ Implemented |
| **Persona Swapping** | Change worker personas mid-session | ✅ Implemented |

### Non-Goals

| Non-Goal | Why Not |
|----------|---------|
| Giant monolithic models | Doesn't fit on consumer hardware |
| Real-time parallel inference | VRAM limitations prevent concurrent model loading |
| Cloud dependency | Designed for local-only operation |
| Fully autonomous AI | User oversight is a feature, not a bug |

---

## Features

### Core Features

#### 1. Multi-Worker Architecture
- 2-4 worker agents (mode-dependent)
- Each worker uses distinct persona
- Sequential execution (time-sliced)
- Shared base model, different system prompts

#### 2. Synthesis & Refinement
- Synthesizer asks clarifying questions
- Workers must respond to challenges
- **Configurable debate rounds** (1-5, set in UI)
- Conflicts and gaps explicitly addressed
- **Diversify action**: Workers see each other's proposals and differentiate their approaches

#### 3. Argumentation Phase
- Each worker argues their case
- References evaluation criteria
- Critiques alternative proposals
- Builds case for selection

#### 4. Collaborative Voting
- AI scores (0-10) with reasoning
- User ranks candidates (1st, 2nd, 3rd, Skip)
- **Multi-level feedback**:
  - Per-candidate feedback
  - Per-worker feedback (tied to persona + worker ID)
  - Synthesizer feedback
  - Overall session feedback
- Weighted combination (AI 40%, User 60%)
- Override capability

#### 5. Structured Logging
- JSONL format (append-only)
- Every stage logged with metadata
- **Comprehensive feedback capture**:
  - User votes and rankings
  - Per-candidate feedback
  - Per-worker feedback (with persona ID)
  - Synthesizer feedback
  - Overall session notes
- Ready for fine-tuning export
- **Session log panel** in UI for real-time visibility

### Hardware Features

#### 6. RAM Mode Switching
| Feature | 16GB Mode | 32GB Mode |
|---------|-----------|-----------|
| Worker Count | 2-3 | 3-4 |
| Worker Model | 3B (4-bit) | 3-4B (4-bit) |
| Synthesizer | 5-6B (4-bit) | 7-8B (4-bit) |
| Context Window | 2K / 4K | 4K / 8K |
| Model Unloading | Aggressive | Moderate |

#### 7. Memory Monitoring
- Real-time RAM/VRAM tracking
- Automatic model unloading under pressure
- Mode-specific thresholds
- UI display of current usage

### Persona Features

#### 8. Persona Discovery
- Import ChatGPT conversation exports
- Unsupervised clustering (K-means)
- Auto-generated names from characteristics
- System prompts from YOUR patterns

#### 9. Persona Management
- Create, edit, delete personas
- View usage stats and win rates
- Assign personas to workers
- Swap personas mid-session

#### 10. Persona Swapping Options
When swapping a persona mid-session:
- **Keep All**: Previous outputs remain visible, marked with old persona
- **Archive**: Previous outputs hidden but logged
- **Restart**: Clear worker state, start fresh with new persona

### UI Features

#### 11. Session View - Chat Timeline
- **Chat-style Message Timeline**: Worker outputs displayed as a chat conversation
  - Stage dividers show progression (Drafts → Questions → Refinement → etc.)
  - Worker avatars with color-coded identities
  - Real-time message animation as workers respond
- Prompt input with Ctrl+Enter shortcut
- **Configurable Rounds**:
  - Refinement rounds (1-5): Number of refinement iterations
  - Argument rounds (1-3): Number of argumentation back-and-forth rounds
- **Worker Roster Panel**: Collapsible sidebar showing all council members
- Progress bar with stage indicator
- Real-time updates via SSE
- **Floating Session Log**: Persistent, expandable log panel visible across all views
- **Diversify Button**: Let workers see each other's responses and differentiate
- **Interactive Round Feedback**: Modal prompts after each round to provide guidance
- **End Council Button**: Properly end session to start fresh

#### 12. Voting View
- **Conversation History Panel**: Collapsible view of the full council discussion
  - Shows all drafts, refinements, and arguments in chat format
  - Helps inform voting decisions
- Candidate cards with arguments and worker identity (persona + ID)
- AI scores displayed
- Ranked voting (1st, 2nd, 3rd, Skip)
- **Multi-level Feedback**:
  - Prompt quality rating (1-5 stars)
  - Prompt improvement feedback
  - Overall session feedback
  - Per-candidate feedback
  - Per-worker feedback
  - Synthesizer feedback
- Back to session navigation
- Submit to finalize

#### 13. Persona Manager
- Grid of persona cards
- Stats: usage count, win rate
- Edit modal for prompt customization
- Import from extracted data

#### 14. Settings
- RAM mode toggle (blocked during active session)
- System health status
- Ollama connection status
- Log export

### Session Management Features

#### 15. Session Persistence
- Session ID stored in browser sessionStorage
- Survives page refresh within same tab
- Auto-restores session state on reload
- Verifies session exists on server before restoring

#### 16. Mode Protection
- Mode switching blocked during active sessions
- Visual indicator (lock icon) when blocked
- Must end council before changing modes
- Prevents inconsistencies between frontend and backend

#### 17. End Council
- Confirmation dialog before ending
- Cleans up UI state properly
- Re-enables mode switching
- Logs are preserved in JSONL files for fine-tuning

### Future Features (Roadmap)

#### Phase 2: LoRA Fine-Tuning
- [ ] Training data preparation scripts ✅
- [ ] Training script templates ✅
- [ ] LoRA adapter loading in runtime
- [ ] A/B testing LoRA vs prompt-only

#### Phase 3: Advanced
- [ ] RAG integration for context
- [ ] Custom evaluation rubrics
- [ ] Batch processing mode
- [ ] API endpoints for programmatic use

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                            AI COUNCIL                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐  ┌─────────────────────────────────────────────┐  │
│  │   Web UI    │  │              Flask Backend                  │  │
│  │ (Vanilla JS)│◄─┤                                             │  │
│  └─────────────┘  │  ┌───────────┐  ┌────────────┐              │  │
│                   │  │Orchestrator│  │Config Mgr  │              │  │
│                   │  └─────┬─────┘  └────────────┘              │  │
│                   │        │                                     │  │
│                   │  ┌─────┴─────┐                               │  │
│                   │  │           │                               │  │
│                   │  ▼           ▼                               │  │
│                   │ Workers   Synthesizer                        │  │
│                   │  │           │                               │  │
│                   │  └─────┬─────┘                               │  │
│                   │        │                                     │  │
│                   │        ▼                                     │  │
│                   │  ┌───────────┐                               │  │
│                   │  │  Ollama   │◄── qwen2.5:3b, qwen2.5:7b    │  │
│                   │  │  Runtime  │                               │  │
│                   │  └───────────┘                               │  │
│                   │                                             │  │
│                   │  ┌───────────┐  ┌───────────┐               │  │
│                   │  │  Persona  │  │  Session  │               │  │
│                   │  │  Manager  │  │  Logger   │               │  │
│                   │  └───────────┘  └───────────┘               │  │
│                   │                                             │  │
│                   └─────────────────────────────────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Data: personas.json, sessions/*.jsonl, config/*.yaml              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Pipeline completion | < 3 minutes | Timer from start to final output |
| System responsiveness | No freezing | UI remains interactive during inference |
| Output quality | Better than single-pass | User preference in voting |
| Log cleanliness | Train-ready | No manual cleanup for fine-tuning |
| Memory stability | No OOM | Complete sessions without crashes |

---

## Design Principles

1. **Time-Sliced, Not Concurrent**
   - One model in GPU at a time
   - Sequential worker execution
   - Explicit model loading/unloading

2. **Token Discipline**
   - Hard limits per stage
   - Context summarization between stages
   - Reject and retry on limit violation

3. **Human Oversight**
   - User votes matter (60% weight)
   - Override capability
   - Feedback captured for learning

4. **Inspectable & Debuggable**
   - JSONL logs for every stage
   - Clear stage progression in UI
   - Memory stats visible

5. **Persona Diversity**
   - Different thinking styles produce different outputs
   - Personas discovered from YOUR data
   - Swappable without losing session

---

## Quick Reference

### Start the System
```powershell
python run.py
# Open: http://127.0.0.1:5000
```

### Discover Your Personas
```powershell
python scripts/extract_personas.py --mode 16GB
python scripts/import_personas.py
```

### Switch RAM Mode
```powershell
$env:AI_COUNCIL_RAM_MODE = "32GB"
```

### Key Files
| File | Purpose |
|------|---------|
| `run.py` | Entry point |
| `config/modes/*.yaml` | Mode configurations |
| `data/personas/personas.json` | Stored personas |
| `data/sessions/*.jsonl` | Session logs |
| `scripts/extract_personas.py` | Persona discovery |


