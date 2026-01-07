#!/usr/bin/env python3
"""
AI Council - Prepare LoRA Training Data
Prepares conversation data for LoRA fine-tuning (Phase 2).

Hardware-aware: Uses appropriate batch sizes for 16GB/32GB modes.
Generates training data in Alpaca/ShareGPT format.

Usage:
    py scripts/prepare_lora_data.py [--mode 16GB|32GB] [--persona architect]
"""

import sys
import json
import argparse
import random
from pathlib import Path
from typing import List, Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Configuration
# ============================================================================

MODE_CONFIG = {
    "16GB": {
        "max_examples_per_persona": 500,    # Limit training data size
        "max_input_tokens": 512,             # Shorter sequences
        "max_output_tokens": 256,
        "validation_split": 0.1,
    },
    "32GB": {
        "max_examples_per_persona": 2000,
        "max_input_tokens": 1024,
        "max_output_tokens": 512,
        "validation_split": 0.1,
    }
}

def load_persona_templates(prompts_file: Path) -> Dict[str, str]:
    """Load discovered persona templates from generated prompts file."""
    if not prompts_file.exists():
        return {}
    
    with open(prompts_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get('prompts', {})


# ============================================================================
# Data Preparation
# ============================================================================

def estimate_tokens(text: str) -> int:
    """Rough token estimation (~4 chars per token)."""
    return len(text) // 4


def load_cluster_messages(cluster_file: Path, max_count: int) -> List[Dict]:
    """Load messages from a persona cluster file."""
    messages = []
    with open(cluster_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= max_count:
                break
            msg = json.loads(line)
            messages.append(msg)
    return messages


def create_training_example_alpaca(
    instruction: str,
    input_text: str,
    output: str,
    persona_name: str
) -> Dict[str, str]:
    """Create a training example in Alpaca format."""
    return {
        "instruction": instruction,
        "input": input_text,
        "output": output,
        "persona": persona_name,
    }


def create_training_example_sharegpt(
    messages: List[Dict[str, str]],
    persona_name: str
) -> Dict[str, Any]:
    """Create a training example in ShareGPT format."""
    return {
        "conversations": messages,
        "persona": persona_name,
    }


def prepare_persona_data(
    cluster_file: Path,
    persona_name: str,
    mode: str = "16GB",
    output_format: str = "alpaca",
    persona_template: str = None
) -> List[Dict]:
    """
    Prepare training data for a single discovered persona.
    
    Since we don't have AI responses in the original data,
    we'll create instruction-following examples from the user messages.
    """
    config = MODE_CONFIG[mode]
    
    display_name = persona_name.replace('_', ' ').title()
    print(f"  Preparing {display_name} data...")
    
    messages = load_cluster_messages(
        cluster_file, 
        config['max_examples_per_persona'] * 2  # Load extra for filtering
    )
    
    if not messages:
        print(f"    No messages found for {display_name}")
        return []
    
    # Use provided template or create a generic one
    if not persona_template:
        persona_template = f"You are the {display_name}. Respond in your characteristic style."
    
    examples = []
    
    for msg in messages:
        text = msg['text']
        context = msg.get('context', '')
        
        # Skip messages that are too short or too long
        text_tokens = estimate_tokens(text)
        if text_tokens < 20 or text_tokens > config['max_input_tokens']:
            continue
        
        # Create instruction based on message characteristics
        if msg.get('question_types'):
            # It's a question - create a Q&A style example
            instruction = "Respond to the following question in your characteristic style."
            input_text = text
        elif msg.get('has_code'):
            # Contains code - create a code review/discussion example
            instruction = "Review and respond to the following code-related message."
            input_text = text
        elif context:
            # Has context - create a contextual response example
            instruction = f"Given this context:\n{context[:300]}\n\nRespond to:"
            input_text = text
        else:
            # General message - create a discussion example
            instruction = "Respond to the following message in your characteristic style."
            input_text = text
        
        if output_format == "alpaca":
            # For Alpaca format, we need to generate/simulate an output
            # In practice, you'd use a larger model to generate these
            # For now, we'll create a template that indicates the persona's style
            output_hint = f"[{persona_name.upper()} RESPONSE - Generate during training or use LLM to create]"
            
            example = create_training_example_alpaca(
                instruction=instruction,
                input_text=input_text,
                output=output_hint,
                persona_name=persona_name
            )
        else:  # sharegpt
            example = create_training_example_sharegpt(
                messages=[
                    {"from": "system", "value": persona_template},
                    {"from": "human", "value": f"{instruction}\n\n{input_text}"},
                    {"from": "gpt", "value": f"[{persona_name.upper()} RESPONSE]"},
                ],
                persona_name=persona_name
            )
        
        examples.append(example)
        
        if len(examples) >= config['max_examples_per_persona']:
            break
    
    print(f"    Created {len(examples)} training examples")
    return examples


def split_train_val(examples: List[Dict], val_ratio: float = 0.1) -> tuple:
    """Split examples into training and validation sets."""
    random.shuffle(examples)
    split_idx = int(len(examples) * (1 - val_ratio))
    return examples[:split_idx], examples[split_idx:]


def save_jsonl(examples: List[Dict], filepath: Path):
    """Save examples to JSONL file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')


# ============================================================================
# Main
# ============================================================================

def prepare_all_personas(
    clusters_dir: Path,
    output_dir: Path,
    mode: str = "16GB",
    personas: List[str] = None,
    output_format: str = "alpaca"
):
    """Prepare LoRA training data for discovered personas."""
    
    print("=" * 60)
    print("  AI Council - LoRA Data Preparation")
    print(f"  Mode: {mode}")
    print(f"  Format: {output_format}")
    print("=" * 60)
    print()
    
    config = MODE_CONFIG[mode]
    
    # Load persona templates from generated prompts
    prompts_file = clusters_dir.parent / "prompts" / "generated_prompts.json"
    persona_templates = load_persona_templates(prompts_file)
    
    if not persona_templates:
        print("Error: No persona templates found!")
        print(f"Expected file: {prompts_file}")
        print("Run extract_personas.py first")
        return
    
    print(f"Found {len(persona_templates)} discovered personas")
    
    # Find all available personas from cluster files
    available_personas = []
    for f in clusters_dir.glob("persona_*.jsonl"):
        name = f.stem.replace("persona_", "")
        available_personas.append(name)
    
    # Default to all discovered personas
    if personas is None:
        personas = available_personas
    else:
        # Filter to only requested personas that exist
        personas = [p for p in personas if p in available_personas]
    
    if not personas:
        print("No personas to process!")
        return
    
    all_examples = {}
    
    for persona_name in personas:
        cluster_file = clusters_dir / f"persona_{persona_name}.jsonl"
        
        if not cluster_file.exists():
            print(f"  Skipping {persona_name} (no cluster file)")
            continue
        
        # Get the template for this persona
        template = persona_templates.get(persona_name, "")
        
        examples = prepare_persona_data(
            cluster_file,
            persona_name,
            mode,
            output_format,
            template
        )
        
        if examples:
            all_examples[persona_name] = examples
    
    print()
    print("Saving training data...")
    
    for persona_name, examples in all_examples.items():
        train, val = split_train_val(examples, config['validation_split'])
        
        train_file = output_dir / f"{persona_name}_train.jsonl"
        val_file = output_dir / f"{persona_name}_val.jsonl"
        
        save_jsonl(train, train_file)
        save_jsonl(val, val_file)
        
        display_name = persona_name.replace('_', ' ').title()
        print(f"  {display_name}: {len(train)} train, {len(val)} val")
    
    print()
    print("=" * 60)
    print("  Data Preparation Complete!")
    print("=" * 60)
    print()
    print("Output files:")
    for persona_name in all_examples:
        print(f"  - {output_dir / f'{persona_name}_train.jsonl'}")
        print(f"  - {output_dir / f'{persona_name}_val.jsonl'}")
    print()
    print("IMPORTANT: The 'output' fields contain placeholders.")
    print("You need to generate actual responses using a larger model.")
    print()
    print("Options:")
    print("  1. Use GPT-4/Claude API to generate responses for each input")
    print("  2. Use the AI Council's synthesizer to generate in-persona responses")
    print("  3. Manually review and write responses for high-quality data")
    print()
    print("After generating responses, train with:")
    first_persona = list(all_examples.keys())[0] if all_examples else "your_persona"
    print(f"  py scripts/train_lora.py --persona {first_persona} --mode {mode}")


def main():
    parser = argparse.ArgumentParser(description='Prepare LoRA training data')
    parser.add_argument('--mode', choices=['16GB', '32GB'], default='16GB',
                       help='RAM mode (affects data size)')
    parser.add_argument('--persona', type=str, default=None,
                       help='Specific persona to prepare (default: all)')
    parser.add_argument('--clusters-dir', type=Path,
                       default=Path('data/personas/clusters'),
                       help='Directory with cluster files')
    parser.add_argument('--output-dir', type=Path,
                       default=Path('data/personas/lora_training'),
                       help='Output directory for training data')
    parser.add_argument('--format', choices=['alpaca', 'sharegpt'], default='alpaca',
                       help='Output format')
    
    args = parser.parse_args()
    
    if not args.clusters_dir.exists():
        print(f"Error: Clusters directory not found: {args.clusters_dir}")
        print("Run extract_personas.py first")
        sys.exit(1)
    
    personas = [args.persona] if args.persona else None
    
    prepare_all_personas(
        args.clusters_dir,
        args.output_dir,
        args.mode,
        personas,
        args.format
    )


if __name__ == '__main__':
    main()

