#!/usr/bin/env python3
"""
AI Council - Import Generated Personas
Imports generated system prompts into the AI Council persona system.

Usage:
    py scripts/import_personas.py [--prompts-file path/to/prompts.json]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def infer_style_from_analysis(cluster_analysis: Dict) -> tuple:
    """Infer reasoning style and tone from cluster analysis."""
    
    dominant_reasoning = cluster_analysis.get('dominant_reasoning', [])
    dominant_tones = cluster_analysis.get('dominant_tones', [])
    
    # Map dominant characteristics to AI Council style categories
    if 'analytical' in dominant_reasoning:
        reasoning_style = 'structured'
    elif 'exploratory' in dominant_reasoning:
        reasoning_style = 'lateral'
    elif 'conditional' in dominant_reasoning or 'comparative' in dominant_reasoning:
        reasoning_style = 'critical'
    else:
        reasoning_style = 'intuitive'
    
    if 'formal' in dominant_tones:
        tone = 'formal'
    elif 'technical' in dominant_tones:
        tone = 'technical'
    elif 'exploratory' in dominant_tones:
        tone = 'conversational'
    elif 'casual' in dominant_tones:
        tone = 'casual'
    else:
        tone = 'formal'
    
    return reasoning_style, tone


def import_personas(prompts_file: Path, personas_file: Path):
    """Import DISCOVERED personas into the AI Council system."""
    
    print("=" * 60)
    print("  AI Council - Import Discovered Personas")
    print("=" * 60)
    print()
    
    # Load generated prompts
    with open(prompts_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    prompts = data.get('prompts', {})
    cluster_analyses = data.get('cluster_analyses', {})
    discovery_method = data.get('discovery_method', 'unknown')
    
    print(f"Discovery method: {discovery_method}")
    print(f"Found {len(prompts)} personas to import")
    print()
    
    # Load existing personas
    if personas_file.exists():
        with open(personas_file, 'r', encoding='utf-8') as f:
            personas_data = json.load(f)
    else:
        personas_data = {'personas': [], 'version': '1.0', 'last_updated': None}
    
    existing_personas = personas_data.get('personas', [])
    existing_names = {p['name'].lower() for p in existing_personas}
    
    # Import each persona
    imported = 0
    skipped = 0
    
    for persona_name, system_prompt in prompts.items():
        # Convert name for display (e.g., "curious_explorer" -> "Curious Explorer")
        display_name = persona_name.replace('_', ' ').title()
        
        # Check if already exists
        if display_name.lower() in existing_names:
            print(f"  Skipping {display_name} (already exists)")
            skipped += 1
            continue
        
        # Get cluster analysis for this persona
        cluster_analysis = cluster_analyses.get(persona_name, {})
        
        # Infer style and tone from analysis
        reasoning_style, tone = infer_style_from_analysis(cluster_analysis)
        
        # Create persona entry
        import uuid
        persona = {
            'id': str(uuid.uuid4()),
            'name': display_name,
            'system_prompt': system_prompt,
            'reasoning_style': reasoning_style,
            'tone': tone,
            'source_text_id': None,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'usage_count': 0,
            'win_rate': 0.0,
            'is_default': False,
            # Store discovery metadata
            'discovery_metadata': {
                'method': discovery_method,
                'dominant_topics': cluster_analysis.get('dominant_topics', []),
                'dominant_tones': cluster_analysis.get('dominant_tones', []),
                'message_count': cluster_analysis.get('size', 0),
            }
        }
        
        existing_personas.append(persona)
        
        # Show what was discovered
        topics = cluster_analysis.get('dominant_topics', [])
        print(f"  Imported: {display_name}")
        print(f"    Style: {reasoning_style}, Tone: {tone}")
        if topics:
            print(f"    Focus: {', '.join(topics[:3])}")
        imported += 1
    
    # Save updated personas
    personas_data['personas'] = existing_personas
    personas_data['last_updated'] = datetime.utcnow().isoformat() + 'Z'
    
    with open(personas_file, 'w', encoding='utf-8') as f:
        json.dump(personas_data, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"Imported: {imported}")
    print(f"Skipped: {skipped}")
    print(f"Total personas: {len(existing_personas)}")
    print()
    print(f"Personas saved to: {personas_file}")
    print()
    print("Start AI Council to use your new personas:")
    print("  py run.py")


def main():
    parser = argparse.ArgumentParser(description='Import generated personas')
    parser.add_argument('--prompts-file', type=Path, 
                       default=Path('data/personas/prompts/generated_prompts.json'),
                       help='Path to generated prompts JSON')
    parser.add_argument('--personas-file', type=Path,
                       default=Path('data/personas/personas.json'),
                       help='Path to personas storage file')
    args = parser.parse_args()
    
    if not args.prompts_file.exists():
        print(f"Error: Prompts file not found: {args.prompts_file}")
        print("Run extract_personas.py first to generate prompts")
        sys.exit(1)
    
    import_personas(args.prompts_file, args.personas_file)


if __name__ == '__main__':
    main()

