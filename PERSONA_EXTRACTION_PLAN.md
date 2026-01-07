# Persona Extraction Plan

## Your Data Summary

| Metric | Value |
|--------|-------|
| Conversations | 1,066 |
| Total Messages | 27,885 |
| Your Messages | 9,779 |
| Your Text Volume | ~15.7 MB |
| File Size | 111 MB |

This is a **rich dataset** for persona extraction. Your messages contain your thinking patterns, communication styles, and domain interests.

---

## The Architecture Question: What to Fine-Tune?

### Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI COUNCIL SYSTEM                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐                    │
│   │ Worker  │  │ Worker  │  │ Worker  │  (Same base model) │
│   │ Persona │  │ Persona │  │ Persona │  qwen2.5:3b        │
│   │    A    │  │    B    │  │    C    │                    │
│   └────┬────┘  └────┬────┘  └────┬────┘                    │
│        │            │            │                          │
│        └────────────┼────────────┘                          │
│                     ▼                                       │
│              ┌────────────┐                                 │
│              │Synthesizer │  qwen2.5:7b                     │
│              │ (Reasoner) │                                 │
│              └────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

**Key insight**: Workers share the same BASE MODEL but have different PERSONAS (system prompts). Currently, personas only change the system prompt, not the model weights.

### Options for Personalization

| Approach | What Changes | Effort | Hardware Feasibility |
|----------|--------------|--------|---------------------|
| **1. System Prompts** | Only prompts | Low | ✅ Perfect |
| **2. LoRA per Persona** | Adapter weights | Medium | ⚠️ Challenging |
| **3. Full Fine-tune** | All weights | High | ❌ Not feasible |

---

## Recommendation: Hybrid Approach

### Phase 1: System Prompt Personas (Do This First)
**No fine-tuning needed. Use your data to craft better prompts.**

Extract from your conversations:
- Communication patterns (how you phrase things)
- Reasoning styles (analytical, creative, skeptical)
- Domain interests (tech, business, creative)
- Decision-making patterns

Generate persona prompts that capture distinct "modes" of your thinking.

### Phase 2: LoRA Adapters (Optional, Later)
**Only if Phase 1 isn't enough differentiation.**

Train small LoRA adapters (~10-50MB each) that shift model behavior toward specific personas.

---

## Phase 1: System Prompt Persona Extraction

### Step 1: Parse and Categorize Your Messages

```python
# What we'll extract from each of your messages:
{
    "text": "your message",
    "context": "what you were responding to",
    "topic_category": "coding|business|creative|analysis|etc",
    "tone": "formal|casual|technical|exploratory",
    "reasoning_markers": ["because", "therefore", "but", "alternatively"],
    "question_types": ["how", "why", "what if", "should I"],
    "length_category": "short|medium|long"
}
```

### Step 2: Cluster into Persona Archetypes

Using your message patterns, identify 3-4 distinct "modes":

**Example personas that might emerge:**

| Persona | Trigger Patterns | Characteristics |
|---------|------------------|-----------------|
| **Architect** | System design, planning, "how should I structure" | Long-form, systematic, considers trade-offs |
| **Debugger** | Errors, "not working", troubleshooting | Iterative, asks clarifying questions, tests assumptions |
| **Explorer** | "What if", brainstorming, new ideas | Creative, jumps between concepts, builds on ideas |
| **Pragmatist** | Deadlines, "quick fix", implementation | Concise, solution-focused, values speed |

### Step 3: Generate System Prompts

For each persona, synthesize a system prompt from:
- Your actual phrasing patterns
- Your reasoning style
- Your priorities
- Example exchanges

---

## Phase 2: LoRA Fine-Tuning (If Needed)

### Hardware Reality Check

| Resource | You Have | LoRA Training Needs |
|----------|----------|---------------------|
| VRAM | 8 GB | 6-8 GB (tight but doable) |
| RAM | 16 GB → 32 GB | 16 GB minimum |
| Storage | ? | ~5 GB per LoRA experiment |

**Verdict**: LoRA training IS possible on your hardware, but:
- Use QLoRA (quantized base + LoRA)
- Train one adapter at a time
- Expect ~30-60 min per adapter for a 3B model
- Batch size = 1-2 (VRAM constrained)

### LoRA Strategy

**Train LoRA adapters for WORKERS, not the Synthesizer.**

Why:
1. Workers need persona differentiation → LoRA helps here
2. Synthesizer needs to be neutral/objective → keep it vanilla
3. Smaller worker model (3B) = faster training
4. Multiple LoRAs can share one base model

### Data Format for LoRA Training

```jsonl
{"messages": [{"role": "system", "content": "You are [persona description]"}, {"role": "user", "content": "User prompt"}, {"role": "assistant", "content": "Response in persona style"}]}
```

You'll need to generate "assistant" responses that match each persona. Options:
1. Use a larger model (GPT-4/Claude) to rewrite responses in persona style
2. Filter your conversations for examples that match each persona
3. Have the synthesizer generate training examples

---

## Implementation Pipeline

### Stage 1: Data Extraction (Python Script)

```
conversations.json
       │
       ▼
┌──────────────────┐
│ extract_messages │  Parse JSON, extract your messages with context
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ categorize_msgs  │  Topic, tone, reasoning style classification
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ cluster_personas │  K-means or LLM-based clustering into archetypes
└────────┬─────────┘
         │
         ▼
    personas.json
```

### Stage 2: Prompt Generation

```
personas.json (clustered messages)
       │
       ▼
┌──────────────────┐
│ analyze_patterns │  Extract linguistic patterns per cluster
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ generate_prompts │  LLM writes system prompts from patterns
└────────┬─────────┘
         │
         ▼
   system_prompts.json
```

### Stage 3: (Optional) LoRA Data Prep

```
personas.json + system_prompts.json
       │
       ▼
┌──────────────────┐
│ generate_training│  Create conversation pairs in persona style
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ format_for_lora  │  Convert to training format
└────────┬─────────┘
         │
         ▼
   persona_A_train.jsonl
   persona_B_train.jsonl
   ...
```

### Stage 4: (Optional) LoRA Training

```bash
# Using unsloth (fastest for consumer hardware)
python train_lora.py \
    --base_model qwen2.5:3b \
    --data persona_A_train.jsonl \
    --output loras/persona_A \
    --epochs 3 \
    --batch_size 1 \
    --lora_r 16
```

---

## Time Estimates (Your Hardware)

| Task | Time | Notes |
|------|------|-------|
| Data extraction | 5-10 min | One-time Python script |
| Message categorization | 20-30 min | LLM-assisted, ~10K messages |
| Persona clustering | 10-15 min | Automated |
| Prompt generation | 15-20 min | LLM generates 3-4 prompts |
| **Total Phase 1** | **~1 hour** | No training needed |
| LoRA data prep | 1-2 hours | Generate training pairs |
| LoRA training (per persona) | 30-60 min | 3B model, 1000 examples |
| **Total Phase 2** | **3-5 hours** | For 3-4 personas |

---

## Recommended Implementation Order

### Week 1: System Prompt Personas
1. ✅ Run extraction script on conversations.json
2. ✅ Categorize messages by topic/tone
3. ✅ Identify 3-4 persona clusters
4. ✅ Generate system prompts
5. ✅ Test in AI Council

### Week 2+: Evaluate & Iterate
1. Run multiple sessions with prompt-based personas
2. Collect voting data (which personas win?)
3. Identify where personas are too similar

### Week 3+ (Optional): LoRA Training
Only if prompt-based personas aren't differentiated enough:
1. Prepare training data for weakest personas
2. Train one LoRA at a time
3. A/B test LoRA vs prompt-only

---

## File Structure for Persona Pipeline

```
data/
├── personas/
│   ├── raw_imports/
│   │   └── conversations.json (your file)
│   ├── extracted/
│   │   ├── all_messages.jsonl
│   │   └── categorized_messages.jsonl
│   ├── clusters/
│   │   ├── persona_architect.jsonl
│   │   ├── persona_debugger.jsonl
│   │   └── persona_explorer.jsonl
│   ├── prompts/
│   │   └── generated_prompts.json
│   └── lora_training/ (optional)
│       ├── persona_architect_train.jsonl
│       └── ...
└── loras/ (optional, trained adapters)
    ├── persona_architect/
    └── ...
```

---

## Quick Start - Run These Commands

### Step 1: Move your data file
```powershell
# Create the directory and copy your file
mkdir data\personas\raw_imports -Force
copy conversations.json data\personas\raw_imports\
```

### Step 2: Discover your personas
```powershell
# Auto-discover personas (finds 3-6 natural clusters)
py scripts/extract_personas.py --mode 16GB

# Or force a specific number of personas
py scripts/extract_personas.py --clusters 4 --mode 16GB

# Try different numbers to see what fits your data
py scripts/extract_personas.py --clusters 5 --refresh
```

This will:
1. Parse your conversations
2. Extract your messages with context
3. Categorize by topic, tone, reasoning style
4. **DISCOVER natural clusters** (not predefined archetypes!)
5. Auto-generate names based on cluster characteristics
6. Generate system prompts from YOUR patterns

**Time estimate: ~5-10 minutes**

### Step 3: Review discovered personas
```powershell
# See what was discovered
type data\personas\clusters\cluster_analysis.json

# Review generated prompts
type data\personas\prompts\generated_prompts.json
```

### Step 4: Import into AI Council
```powershell
py scripts/import_personas.py
```

### Step 5: Test your new personas
```powershell
py run.py
# Open http://127.0.0.1:5000
# Your DISCOVERED personas appear in the Persona Manager
```

---

## Phase 2: LoRA Training (Optional, Later)

Only do this if prompt-based personas aren't differentiated enough.

### Step 1: Prepare training data
```powershell
py scripts/prepare_lora_data.py --mode 16GB
```

### Step 2: Generate responses (requires external LLM)
The prepared data has placeholder outputs. You need to fill them:
- Option A: Use GPT-4 API to generate responses
- Option B: Manually write high-quality responses
- Option C: Use Claude to generate in-persona responses

### Step 3: Train LoRA adapter
```powershell
# Check if dependencies are installed
py scripts/train_lora.py --check-only

# Generate training script
py scripts/train_lora.py --persona architect --mode 16GB --generate-script

# Run the generated script
py train_architect_lora.py
```

**Time estimate: ~45 minutes per persona (16GB mode)**

---

## Summary

| Question | Answer |
|----------|--------|
| Fine-tune orchestrator or worker? | **Workers** - they need persona differentiation |
| Multiple workers = multiple models? | **No** - same base model, different personas |
| How do personas differ? | System prompt (Phase 1) or LoRA adapter (Phase 2) |
| Is LoRA feasible on your hardware? | **Yes**, but tight. Use QLoRA, train one at a time |
| What should I do first? | **System prompt personas** - no training, instant results |
| How long will this take? | **~1 hour** for Phase 1, **3-5 hours** for Phase 2 |

---

## Next Steps

1. **Move** `conversations.json` to `data/personas/raw_imports/`
2. **Run** the extraction script (I'll create it)
3. **Review** the suggested persona clusters
4. **Edit** generated system prompts as needed
5. **Test** in AI Council with your new personas

Ready to proceed? I can create the extraction pipeline now.


