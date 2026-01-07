# AI Council - Complete Setup & Run Guide

This guide covers everything from installation to running your first council session.

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Install Ollama](#2-install-ollama)
3. [Download Models](#3-download-models)
4. [Install Python Dependencies](#4-install-python-dependencies)
5. [Configure RAM Mode](#5-configure-ram-mode)
6. [Run AI Council](#6-run-ai-council)
7. [Extract Your Personas](#7-extract-your-personas)
8. [Using the UI](#8-using-the-ui)
9. [Troubleshooting](#9-troubleshooting)
10. [Advanced: LoRA Fine-Tuning](#10-advanced-lora-fine-tuning)

---

## 1. Prerequisites

### System Requirements

| Component | 16GB Mode | 32GB Mode |
|-----------|-----------|-----------|
| RAM | 16 GB | 32 GB |
| VRAM | 6+ GB | 8+ GB |
| Disk Space | 10 GB | 20 GB |
| OS | Windows 10/11, Linux, macOS | Same |
| Python | 3.11+ | 3.11+ |

### Check Your System

```powershell
# Check Python version
python --version
# or
py --version

# Check available RAM (Windows)
systeminfo | findstr "Total Physical Memory"

# Check GPU (NVIDIA)
nvidia-smi
```

---

## 2. Install Ollama

Ollama runs the LLM models locally. It's the engine behind AI Council.

### Windows

1. **Download** from [ollama.com/download](https://ollama.com/download)
2. **Run the installer** (OllamaSetup.exe)
3. **Verify installation**:
   ```powershell
   ollama --version
   ```

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### macOS

```bash
brew install ollama
# or download from ollama.com/download
```

### Start Ollama Service

Ollama runs as a background service. On Windows, it starts automatically after installation.

```powershell
# Check if Ollama is running
ollama list

# If not running, start it
ollama serve
```

The Ollama API runs at `http://localhost:11434`.

---

## 3. Download Models

AI Council uses two models:
- **Worker model** (3B) - Fast, runs multiple instances
- **Synthesizer model** (7B) - Smarter, runs once per stage

### Recommended Models

```powershell
# Worker model (required) - ~2GB download
ollama pull qwen2.5:3b

# Synthesizer model (required) - ~4.5GB download  
ollama pull qwen2.5:7b
```

### Alternative Models

If you prefer different models:

```powershell
# Smaller workers (for very limited VRAM)
ollama pull phi3:mini          # 2.3B
ollama pull gemma2:2b          # 2B

# Alternative synthesizers
ollama pull llama3.1:8b        # 8B
ollama pull mistral:7b         # 7B
```

### Verify Models

```powershell
# List downloaded models
ollama list

# Test a model
ollama run qwen2.5:3b "Hello, who are you?"
# Press Ctrl+D to exit
```

### Model Storage Location

- **Windows**: `C:\Users\<username>\.ollama\models`
- **Linux/macOS**: `~/.ollama/models`

---

## 4. Install Python Dependencies

### Create Virtual Environment (Recommended)

```powershell
# Navigate to project directory
cd "C:\Users\<username>\OneDrive\Desktop\AI Council"

# Create virtual environment
python -m venv venv

# Activate it (Windows)
.\venv\Scripts\Activate.ps1

# Activate it (Linux/macOS)
source venv/bin/activate
```

### Install Dependencies

```powershell
# Install all required packages
pip install -r requirements.txt
```

This installs:
- Flask (web server)
- PyYAML (configuration)
- psutil (memory monitoring)
- requests (Ollama API client)
- pydantic (data validation)

---

## 5. Configure RAM Mode

AI Council has two modes optimized for different hardware:

### 16GB Mode (Default)
- 2-3 workers
- Smaller context windows
- Aggressive model unloading
- Best for: Laptops, budget systems

### 32GB Mode
- 3-4 workers
- Larger context windows
- Moderate model unloading
- Best for: Desktops, workstations

### Set Mode

**Option 1: Environment Variable (Persistent)**
```powershell
# Windows (current session)
$env:AI_COUNCIL_RAM_MODE = "16GB"

# Windows (permanent - run as admin)
[System.Environment]::SetEnvironmentVariable("AI_COUNCIL_RAM_MODE", "16GB", "User")

# Linux/macOS
export AI_COUNCIL_RAM_MODE=16GB
```

**Option 2: UI Toggle**
Click the 16GB/32GB button in the top-left of the web interface.

**Option 3: Edit Config**
Modify `config/modes/16gb.yaml` or `config/modes/32gb.yaml`.

---

## 6. Run AI Council

### Start the Server

```powershell
# Make sure you're in the project directory
cd "C:\Users\<username>\OneDrive\Desktop\AI Council"

# Activate virtual environment (if using)
.\venv\Scripts\Activate.ps1

# Start AI Council
python run.py
```

You should see:
```
==================================================
  AI Council - Local Multi-Agent LLM System
==================================================
  Server: http://127.0.0.1:5000
  Debug Mode: True
==================================================
```

### Open the UI

Open your browser to: **http://127.0.0.1:5000**

### Verify Everything Works

1. Check the RAM mode indicator (top-left)
2. Check memory status (top-right)
3. Click Settings → System Status should show:
   - Ollama: healthy
   - Mode: 16GB or 32GB
   - Workers: 2-3

---

## 7. Extract Your Personas

If you have a ChatGPT conversation export (`conversations.json`), you can extract your personal thinking styles.

### Step 1: Prepare Your Data

```powershell
# Create directory
mkdir data\personas\raw_imports -Force

# Copy your ChatGPT export
copy conversations.json data\personas\raw_imports\
```

### Step 2: Run Extraction

```powershell
# Basic extraction (auto-detects 3-6 personas)
python scripts/extract_personas.py --mode 16GB

# Force specific number of personas
python scripts/extract_personas.py --clusters 4 --mode 16GB

# Re-run with fresh extraction
python scripts/extract_personas.py --refresh --clusters 5
```

### Step 3: Review Results

The script outputs:
```
DISCOVERED PERSONAS:
  Methodical Strategist
    Messages: 2,341
    Focus: system_design, planning, analysis
  
  Direct Builder
    Messages: 3,102
    Focus: coding, troubleshooting
```

Check the analysis:
```powershell
# View cluster analysis
type data\personas\clusters\cluster_analysis.json

# View generated prompts
type data\personas\prompts\generated_prompts.json
```

### Step 4: Import into AI Council

```powershell
python scripts/import_personas.py
```

### Step 5: Use Your Personas

Restart AI Council and your discovered personas appear in the Persona Manager.

---

## 8. Using the UI

### Main Session View

1. **Enter your prompt** in the text area
2. **Review worker personas** - click "Swap" to change before starting
3. **Click "Start Council"** to begin

### During Execution

Watch the pipeline progress:
1. **Worker Drafts** - Each worker generates initial proposal
2. **Synth Questions** - Synthesizer asks clarifying questions
3. **Refinement** - Workers refine based on questions
4. **Argumentation** - Workers argue for their proposals
5. **AI Voting** - Synthesizer scores candidates

### Voting Phase

1. Review each candidate's **argument** (why they think it's best)
2. Review the actual **output**
3. See the **AI Score** (0-10)
4. **Cast your vote** (1st, 2nd, 3rd, or Skip)
5. Add optional **feedback**
6. **Submit** to generate final output

### Persona Manager

- **View** all personas and their stats
- **Create** new personas manually
- **Edit** existing personas
- **Import** from text (future feature)

---

## 9. Troubleshooting

### Ollama Not Running

```powershell
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If error, start Ollama
ollama serve
```

### Out of Memory (OOM)

```powershell
# Switch to 16GB mode
$env:AI_COUNCIL_RAM_MODE = "16GB"

# Or use smaller models
# Edit config/modes/16gb.yaml:
#   workers:
#     model: "phi3:mini"  # Smaller than qwen2.5:3b
```

### Model Not Found

```powershell
# List available models
ollama list

# Pull missing model
ollama pull qwen2.5:3b
```

### Port Already in Use

```powershell
# Use different port
$env:AI_COUNCIL_PORT = "5001"
python run.py
```

### Slow Performance

1. **Close other applications** using GPU
2. **Check VRAM usage**: `nvidia-smi`
3. **Use 16GB mode** even on 32GB systems
4. **Reduce worker count** in config

### Python Module Errors

```powershell
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Or recreate virtual environment
rm -r venv
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 10. Advanced: LoRA Fine-Tuning

If prompt-based personas aren't differentiated enough, you can train LoRA adapters.

### Requirements

- NVIDIA GPU with 8GB+ VRAM
- Additional ~10GB disk space
- 30-60 minutes per persona

### Step 1: Install Training Dependencies

```powershell
# Install PyTorch with CUDA
pip install torch --index-url https://download.pytorch.org/whl/cu121

# Install training libraries
pip install unsloth transformers datasets accelerate bitsandbytes
```

### Step 2: Prepare Training Data

```powershell
python scripts/prepare_lora_data.py --mode 16GB
```

This creates `data/personas/lora_training/` with training files for each persona.

**Important**: The output fields contain placeholders. You need to generate actual responses using GPT-4/Claude or manually.

### Step 3: Generate Training Script

```powershell
# Check dependencies
python scripts/train_lora.py --check-only

# Generate training script for a persona
python scripts/train_lora.py --persona curious_explorer --mode 16GB --generate-script
```

### Step 4: Train

```powershell
# Run the generated script
python train_curious_explorer_lora.py
```

Training takes ~45 minutes on 16GB mode (batch_size=1).

### Step 5: Use LoRA in AI Council

(Future feature - LoRA loading not yet implemented in runtime)

---

## Quick Reference

### Commands

| Task | Command |
|------|---------|
| Start AI Council | `python run.py` |
| Extract personas | `python scripts/extract_personas.py --mode 16GB` |
| Import personas | `python scripts/import_personas.py` |
| Check Ollama | `ollama list` |
| Pull model | `ollama pull qwen2.5:3b` |

### Environment Variables

| Variable | Values | Default |
|----------|--------|---------|
| `AI_COUNCIL_RAM_MODE` | `16GB`, `32GB` | `16GB` |
| `AI_COUNCIL_HOST` | IP address | `127.0.0.1` |
| `AI_COUNCIL_PORT` | Port number | `5000` |
| `AI_COUNCIL_DEBUG` | `true`, `false` | `true` |

### Key Files

| File | Purpose |
|------|---------|
| `config/modes/16gb.yaml` | 16GB mode settings |
| `config/modes/32gb.yaml` | 32GB mode settings |
| `data/personas/personas.json` | Stored personas |
| `data/sessions/*.jsonl` | Session logs |

---

## Getting Help

1. Check the [Troubleshooting](#9-troubleshooting) section
2. Review [PERSONA_EXTRACTION_PLAN.md](PERSONA_EXTRACTION_PLAN.md) for persona details
3. Check Ollama docs: [ollama.com/docs](https://ollama.com/docs)

