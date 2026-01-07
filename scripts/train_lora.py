#!/usr/bin/env python3
"""
AI Council - LoRA Training Script
Fine-tunes a LoRA adapter for a specific persona.

Hardware-aware: Configures batch size, gradient accumulation based on mode.
Uses QLoRA for memory efficiency on consumer hardware.

Requirements:
    pip install unsloth transformers datasets accelerate bitsandbytes

Usage:
    py scripts/train_lora.py --persona architect --mode 16GB
"""

import sys
import argparse
from pathlib import Path

# This is a TEMPLATE - actual training requires additional dependencies
# The script will check for dependencies and provide installation instructions

TRAINING_CONFIG = {
    "16GB": {
        # Conservative settings for 16GB RAM + 8GB VRAM
        "batch_size": 1,
        "gradient_accumulation_steps": 8,
        "max_seq_length": 512,
        "learning_rate": 2e-4,
        "num_epochs": 3,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "use_4bit": True,           # QLoRA - essential for 8GB VRAM
        "use_gradient_checkpointing": True,
        "estimated_time_minutes": 45,
    },
    "32GB": {
        # More aggressive settings for 32GB RAM
        "batch_size": 2,
        "gradient_accumulation_steps": 4,
        "max_seq_length": 1024,
        "learning_rate": 2e-4,
        "num_epochs": 3,
        "lora_r": 32,
        "lora_alpha": 64,
        "lora_dropout": 0.05,
        "use_4bit": True,
        "use_gradient_checkpointing": True,
        "estimated_time_minutes": 30,
    }
}

# Base models suitable for each mode
RECOMMENDED_MODELS = {
    "16GB": [
        "unsloth/Qwen2.5-3B-Instruct-bnb-4bit",  # Recommended - fast
        "unsloth/Phi-3-mini-4k-instruct-bnb-4bit",
        "unsloth/gemma-2-2b-it-bnb-4bit",
    ],
    "32GB": [
        "unsloth/Qwen2.5-3B-Instruct-bnb-4bit",  # Still good
        "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",  # Can try larger
        "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
    ]
}


def check_dependencies():
    """Check if training dependencies are installed."""
    missing = []
    
    try:
        import torch
        print(f"  PyTorch: {torch.__version__}")
        if torch.cuda.is_available():
            print(f"  CUDA: {torch.version.cuda}")
            print(f"  GPU: {torch.cuda.get_device_name(0)}")
            print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            print("  WARNING: CUDA not available - training will be very slow")
    except ImportError:
        missing.append("torch")
    
    try:
        import unsloth
        print(f"  Unsloth: installed")
    except ImportError:
        missing.append("unsloth")
    
    try:
        import transformers
        print(f"  Transformers: {transformers.__version__}")
    except ImportError:
        missing.append("transformers")
    
    try:
        import datasets
        print(f"  Datasets: {datasets.__version__}")
    except ImportError:
        missing.append("datasets")
    
    try:
        import bitsandbytes
        print(f"  BitsAndBytes: installed")
    except ImportError:
        missing.append("bitsandbytes")
    
    return missing


def print_training_plan(persona: str, mode: str, data_file: Path):
    """Print the training plan before execution."""
    config = TRAINING_CONFIG[mode]
    models = RECOMMENDED_MODELS[mode]
    
    print()
    print("=" * 60)
    print(f"  Training Plan: {persona.title()} Persona")
    print("=" * 60)
    print()
    print(f"  Mode: {mode}")
    print(f"  Data: {data_file}")
    print()
    print("  Model options:")
    for i, model in enumerate(models):
        marker = "[RECOMMENDED]" if i == 0 else ""
        print(f"    {i+1}. {model} {marker}")
    print()
    print("  Training configuration:")
    print(f"    Batch size: {config['batch_size']}")
    print(f"    Gradient accumulation: {config['gradient_accumulation_steps']}")
    print(f"    Effective batch: {config['batch_size'] * config['gradient_accumulation_steps']}")
    print(f"    Max sequence length: {config['max_seq_length']}")
    print(f"    Learning rate: {config['learning_rate']}")
    print(f"    Epochs: {config['num_epochs']}")
    print(f"    LoRA rank: {config['lora_r']}")
    print(f"    LoRA alpha: {config['lora_alpha']}")
    print(f"    4-bit quantization: {config['use_4bit']}")
    print(f"    Gradient checkpointing: {config['use_gradient_checkpointing']}")
    print()
    print(f"  Estimated time: ~{config['estimated_time_minutes']} minutes")
    print()


def generate_training_code(persona: str, mode: str, data_file: Path, output_dir: Path) -> str:
    """Generate the actual training code."""
    config = TRAINING_CONFIG[mode]
    model = RECOMMENDED_MODELS[mode][0]
    
    code = f'''
# AI Council - LoRA Training for {persona.title()} Persona
# Generated for {mode} mode
# Run this script after installing dependencies

from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments
import torch

# Configuration
MODEL_NAME = "{model}"
DATA_FILE = "{data_file}"
OUTPUT_DIR = "{output_dir / persona}"
MAX_SEQ_LENGTH = {config['max_seq_length']}

# Load model with 4-bit quantization
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit={config['use_4bit']},
    dtype=None,  # Auto-detect
)

# Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r={config['lora_r']},
    lora_alpha={config['lora_alpha']},
    lora_dropout={config['lora_dropout']},
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    bias="none",
    use_gradient_checkpointing={config['use_gradient_checkpointing']},
    random_state=42,
)

# Load dataset
dataset = load_dataset("json", data_files=DATA_FILE, split="train")

# Format for training
def format_prompt(example):
    return f"""### Instruction:
{{example['instruction']}}

### Input:
{{example['input']}}

### Response:
{{example['output']}}"""

# Training arguments
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size={config['batch_size']},
    gradient_accumulation_steps={config['gradient_accumulation_steps']},
    num_train_epochs={config['num_epochs']},
    learning_rate={config['learning_rate']},
    fp16=not torch.cuda.is_bf16_supported(),
    bf16=torch.cuda.is_bf16_supported(),
    logging_steps=10,
    save_strategy="epoch",
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    optim="adamw_8bit",
)

# Create trainer
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    formatting_func=format_prompt,
    max_seq_length=MAX_SEQ_LENGTH,
    args=training_args,
)

# Train!
print("Starting training...")
trainer.train()

# Save LoRA adapter
print(f"Saving adapter to {{OUTPUT_DIR}}")
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print("Training complete!")
print(f"LoRA adapter saved to: {{OUTPUT_DIR}}")
print()
print("To use in AI Council:")
print(f"  1. Copy {{OUTPUT_DIR}} to loras/{persona}/")
print("  2. Update config to reference the LoRA")
print("  3. Restart AI Council")
'''
    return code


def main():
    parser = argparse.ArgumentParser(description='Train LoRA adapter for persona')
    parser.add_argument('--persona', type=str, required=True,
                       choices=['architect', 'debugger', 'explorer', 'pragmatist'],
                       help='Persona to train')
    parser.add_argument('--mode', choices=['16GB', '32GB'], default='16GB',
                       help='RAM mode')
    parser.add_argument('--data-dir', type=Path,
                       default=Path('data/personas/lora_training'),
                       help='Directory with training data')
    parser.add_argument('--output-dir', type=Path,
                       default=Path('loras'),
                       help='Output directory for LoRA adapters')
    parser.add_argument('--check-only', action='store_true',
                       help='Only check dependencies, do not train')
    parser.add_argument('--generate-script', action='store_true',
                       help='Generate training script instead of running')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  AI Council - LoRA Training")
    print("=" * 60)
    print()
    
    # Check dependencies
    print("Checking dependencies...")
    missing = check_dependencies()
    
    if missing:
        print()
        print("Missing dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print()
        print("Install with:")
        print("  pip install torch --index-url https://download.pytorch.org/whl/cu121")
        print("  pip install unsloth transformers datasets accelerate bitsandbytes")
        print()
        print("Or use the faster unsloth installer:")
        print("  pip install unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git")
        
        if not args.check_only:
            sys.exit(1)
        return
    
    if args.check_only:
        print()
        print("All dependencies installed!")
        return
    
    # Check for training data
    data_file = args.data_dir / f"{args.persona}_train.jsonl"
    if not data_file.exists():
        print()
        print(f"Error: Training data not found: {data_file}")
        print()
        print("Generate training data first:")
        print(f"  py scripts/prepare_lora_data.py --persona {args.persona} --mode {args.mode}")
        sys.exit(1)
    
    # Print training plan
    print_training_plan(args.persona, args.mode, data_file)
    
    if args.generate_script:
        # Generate script file instead of running
        code = generate_training_code(args.persona, args.mode, data_file, args.output_dir)
        script_file = Path(f"train_{args.persona}_lora.py")
        with open(script_file, 'w') as f:
            f.write(code)
        print(f"Generated training script: {script_file}")
        print(f"Run with: python {script_file}")
    else:
        print("To start training, run with --generate-script and execute the generated file")
        print("(Direct training not implemented - use generated script for flexibility)")


if __name__ == '__main__':
    main()

