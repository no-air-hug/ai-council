#!/usr/bin/env python3
"""
AI Council - Persona Extraction Pipeline
Extracts personas from ChatGPT conversation exports.

Hardware-aware: Works within 16GB/32GB RAM constraints.
Processes data in chunks to avoid memory issues.

Usage:
    py scripts/extract_personas.py [--mode 16GB|32GB]
"""

import os
import sys
import json
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional, Generator
import re

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Configuration based on RAM mode
# ============================================================================

MODE_CONFIG = {
    "16GB": {
        "chunk_size": 50,           # Conversations per chunk
        "max_messages_in_memory": 5000,
        "clustering_sample_size": 2000,
        "use_streaming": True,
    },
    "32GB": {
        "chunk_size": 200,
        "max_messages_in_memory": 20000,
        "clustering_sample_size": 5000,
        "use_streaming": False,
    }
}


# ============================================================================
# Message Extraction
# ============================================================================

def extract_messages_streaming(filepath: Path, mode: str = "16GB") -> Generator[Dict, None, None]:
    """
    Extract user messages from conversations.json in a memory-efficient way.
    
    Yields one message at a time instead of loading all into memory.
    """
    config = MODE_CONFIG[mode]
    
    print(f"[1/4] Extracting messages from {filepath.name}...")
    print(f"      Mode: {mode} (chunk_size={config['chunk_size']})")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total_convos = len(data)
    processed = 0
    
    for conv in data:
        conv_id = conv.get('conversation_id', conv.get('id', 'unknown'))
        title = conv.get('title', 'Untitled')
        model = conv.get('default_model_slug', 'unknown')
        create_time = conv.get('create_time')
        
        mapping = conv.get('mapping', {})
        
        # Build parent-child relationships for context
        node_parents = {}
        for node_id, node in mapping.items():
            parent = node.get('parent')
            if parent:
                node_parents[node_id] = parent
        
        for node_id, node in mapping.items():
            msg = node.get('message')
            if not msg:
                continue
                
            author = msg.get('author', {})
            role = author.get('role', 'unknown')
            
            # Only extract user messages
            if role != 'user':
                continue
            
            content = msg.get('content', {})
            parts = content.get('parts', [])
            
            # Extract text from parts
            text = ''
            for part in parts:
                if isinstance(part, str):
                    text += part
                elif isinstance(part, dict) and 'text' in part:
                    text += part['text']
            
            if not text or len(text.strip()) < 10:
                continue
            
            # Get context (what user was responding to)
            context = ''
            parent_id = node_parents.get(node_id)
            if parent_id and parent_id in mapping:
                parent_node = mapping[parent_id]
                parent_msg = parent_node.get('message')
                if parent_msg:
                    parent_content = parent_msg.get('content', {})
                    parent_parts = parent_content.get('parts', [])
                    for part in parent_parts:
                        if isinstance(part, str):
                            context += part[:500]  # Limit context length
                            break
            
            yield {
                'id': hashlib.md5(f"{conv_id}:{node_id}".encode()).hexdigest()[:12],
                'conversation_id': conv_id,
                'conversation_title': title,
                'text': text.strip(),
                'context': context.strip(),
                'model': model,
                'timestamp': create_time,
                'word_count': len(text.split()),
                'char_count': len(text)
            }
        
        processed += 1
        if processed % 100 == 0:
            print(f"      Processed {processed}/{total_convos} conversations...")
    
    print(f"      Done! Processed {total_convos} conversations")


def save_messages_chunked(messages: Generator, output_path: Path, mode: str = "16GB") -> int:
    """Save messages to JSONL file, returning count."""
    config = MODE_CONFIG[mode]
    count = 0
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + '\n')
            count += 1
            
            if count % 1000 == 0:
                print(f"      Saved {count} messages...")
    
    return count


# ============================================================================
# Message Categorization
# ============================================================================

# Topic patterns (regex-based, no LLM needed)
TOPIC_PATTERNS = {
    'coding': [
        r'\b(code|function|variable|class|method|api|bug|error|debug|python|javascript|typescript|sql|html|css)\b',
        r'\b(import|export|async|await|try|catch|if|else|for|while|return)\b',
        r'```',  # Code blocks
    ],
    'system_design': [
        r'\b(architecture|design|system|database|server|client|microservice|api|endpoint)\b',
        r'\b(scale|performance|cache|queue|load.?balanc|deploy)\b',
    ],
    'analysis': [
        r'\b(analyze|analysis|compare|evaluate|assess|review|examine)\b',
        r'\b(pros|cons|trade.?off|advantage|disadvantage|benefit|drawback)\b',
    ],
    'creative': [
        r'\b(idea|creative|brainstorm|imagine|story|write|draft|compose)\b',
        r'\b(design|style|aesthetic|visual|ui|ux)\b',
    ],
    'planning': [
        r'\b(plan|strategy|roadmap|timeline|milestone|goal|objective)\b',
        r'\b(step|phase|stage|priority|schedule)\b',
    ],
    'troubleshooting': [
        r'\b(error|issue|problem|bug|fix|solve|debug|not.?working|broken|fail)\b',
        r'\b(why|how.?come|what.?went.?wrong)\b',
    ],
    'learning': [
        r'\b(explain|understand|learn|what.?is|how.?does|tell.?me.?about)\b',
        r'\b(concept|theory|principle|basics|fundamentals)\b',
    ],
}

# Tone patterns
TONE_PATTERNS = {
    'formal': [
        r'\b(please|kindly|would you|could you|i would appreciate)\b',
        r'\b(regarding|concerning|with respect to|in reference to)\b',
    ],
    'casual': [
        r'\b(hey|hi|yo|cool|awesome|great|nice|thanks|thx)\b',
        r'\b(gonna|wanna|gotta|kinda|sorta|dunno)\b',
    ],
    'technical': [
        r'\b(implementation|configuration|parameter|instance|interface)\b',
        r'\b(initialize|instantiate|serialize|deserialize|compile)\b',
    ],
    'exploratory': [
        r'\b(what if|maybe|perhaps|could|might|possibly|wonder)\b',
        r'\b(alternative|option|different|another way|other approach)\b',
    ],
}

# Reasoning markers
REASONING_MARKERS = {
    'analytical': ['because', 'therefore', 'thus', 'hence', 'since', 'given that'],
    'comparative': ['compared to', 'versus', 'vs', 'rather than', 'instead of', 'better than'],
    'conditional': ['if', 'unless', 'provided that', 'assuming', 'in case'],
    'exploratory': ['what if', 'suppose', 'imagine', 'alternatively', 'on the other hand'],
}


def categorize_message(msg: Dict) -> Dict:
    """
    Categorize a message by topic, tone, and reasoning style.
    Uses regex patterns - no LLM needed, very fast.
    """
    text = msg['text'].lower()
    
    # Detect topics
    topics = []
    topic_scores = {}
    for topic, patterns in TOPIC_PATTERNS.items():
        score = sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)
        if score > 0:
            topic_scores[topic] = score
            topics.append(topic)
    
    primary_topic = max(topic_scores, key=topic_scores.get) if topic_scores else 'general'
    
    # Detect tone
    tones = []
    tone_scores = {}
    for tone, patterns in TONE_PATTERNS.items():
        score = sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)
        if score > 0:
            tone_scores[tone] = score
            tones.append(tone)
    
    primary_tone = max(tone_scores, key=tone_scores.get) if tone_scores else 'neutral'
    
    # Detect reasoning style
    reasoning_scores = {}
    for style, markers in REASONING_MARKERS.items():
        score = sum(text.count(marker) for marker in markers)
        if score > 0:
            reasoning_scores[style] = score
    
    primary_reasoning = max(reasoning_scores, key=reasoning_scores.get) if reasoning_scores else 'direct'
    
    # Length category
    word_count = msg['word_count']
    if word_count < 30:
        length_cat = 'short'
    elif word_count < 100:
        length_cat = 'medium'
    elif word_count < 300:
        length_cat = 'long'
    else:
        length_cat = 'very_long'
    
    # Question type detection
    question_types = []
    if '?' in text:
        if re.search(r'\bhow\b', text):
            question_types.append('how')
        if re.search(r'\bwhy\b', text):
            question_types.append('why')
        if re.search(r'\bwhat\b', text):
            question_types.append('what')
        if re.search(r'\bshould\b', text):
            question_types.append('should')
        if re.search(r'\bcan\b|\bcould\b', text):
            question_types.append('can')
    
    return {
        **msg,
        'primary_topic': primary_topic,
        'topics': topics,
        'primary_tone': primary_tone,
        'tones': tones,
        'primary_reasoning': primary_reasoning,
        'reasoning_scores': reasoning_scores,
        'length_category': length_cat,
        'question_types': question_types,
        'has_code': '```' in msg['text'] or bool(re.search(r'`[^`]+`', msg['text'])),
    }


def categorize_messages_file(input_path: Path, output_path: Path) -> Dict[str, Any]:
    """
    Categorize all messages from a JSONL file.
    Returns statistics about the categorization.
    """
    print(f"[2/4] Categorizing messages...")
    
    stats = {
        'total': 0,
        'topics': Counter(),
        'tones': Counter(),
        'reasoning': Counter(),
        'lengths': Counter(),
    }
    
    with open(input_path, 'r', encoding='utf-8') as f_in, \
         open(output_path, 'w', encoding='utf-8') as f_out:
        
        for line in f_in:
            msg = json.loads(line)
            categorized = categorize_message(msg)
            f_out.write(json.dumps(categorized, ensure_ascii=False) + '\n')
            
            stats['total'] += 1
            stats['topics'][categorized['primary_topic']] += 1
            stats['tones'][categorized['primary_tone']] += 1
            stats['reasoning'][categorized['primary_reasoning']] += 1
            stats['lengths'][categorized['length_category']] += 1
            
            if stats['total'] % 1000 == 0:
                print(f"      Categorized {stats['total']} messages...")
    
    print(f"      Done! Categorized {stats['total']} messages")
    return stats


# ============================================================================
# Feature Extraction for Clustering
# ============================================================================

# All possible features for clustering
ALL_TOPICS = ['coding', 'system_design', 'analysis', 'creative', 'planning', 
              'troubleshooting', 'learning', 'general']
ALL_TONES = ['formal', 'casual', 'technical', 'exploratory', 'neutral']
ALL_REASONING = ['analytical', 'comparative', 'conditional', 'exploratory', 'direct']
ALL_LENGTHS = ['short', 'medium', 'long', 'very_long']


def message_to_feature_vector(msg: Dict) -> List[float]:
    """
    Convert a categorized message to a numerical feature vector for clustering.
    This enables unsupervised discovery of natural persona groupings.
    """
    features = []
    
    # Topic features (one-hot style, but with scores)
    for topic in ALL_TOPICS:
        if topic == msg.get('primary_topic'):
            features.append(1.0)
        elif topic in msg.get('topics', []):
            features.append(0.5)
        else:
            features.append(0.0)
    
    # Tone features
    for tone in ALL_TONES:
        if tone == msg.get('primary_tone'):
            features.append(1.0)
        elif tone in msg.get('tones', []):
            features.append(0.5)
        else:
            features.append(0.0)
    
    # Reasoning features
    reasoning_scores = msg.get('reasoning_scores', {})
    max_reasoning = max(reasoning_scores.values()) if reasoning_scores else 1
    for reasoning in ALL_REASONING:
        score = reasoning_scores.get(reasoning, 0)
        features.append(score / max_reasoning if max_reasoning > 0 else 0)
    
    # Length features
    for length in ALL_LENGTHS:
        features.append(1.0 if msg.get('length_category') == length else 0.0)
    
    # Additional features
    features.append(1.0 if msg.get('has_code') else 0.0)
    features.append(len(msg.get('question_types', [])) / 5.0)  # Normalized
    features.append(min(msg.get('word_count', 0) / 500.0, 1.0))  # Normalized length
    
    return features


def simple_kmeans(data: List[List[float]], k: int, max_iters: int = 100) -> tuple:
    """
    Simple K-means implementation (no numpy/sklearn dependency).
    Returns (labels, centroids).
    """
    import random
    
    n = len(data)
    dim = len(data[0])
    
    # Initialize centroids randomly
    indices = random.sample(range(n), min(k, n))
    centroids = [data[i][:] for i in indices]
    
    labels = [0] * n
    
    for iteration in range(max_iters):
        # Assign points to nearest centroid
        new_labels = []
        for point in data:
            distances = []
            for centroid in centroids:
                dist = sum((a - b) ** 2 for a, b in zip(point, centroid)) ** 0.5
                distances.append(dist)
            new_labels.append(distances.index(min(distances)))
        
        # Check convergence
        if new_labels == labels:
            break
        labels = new_labels
        
        # Update centroids
        for c in range(k):
            cluster_points = [data[i] for i in range(n) if labels[i] == c]
            if cluster_points:
                centroids[c] = [
                    sum(p[d] for p in cluster_points) / len(cluster_points)
                    for d in range(dim)
                ]
    
    return labels, centroids


def analyze_cluster(messages: List[Dict]) -> Dict[str, Any]:
    """
    Analyze a cluster to understand its characteristics.
    Returns descriptive statistics that help name and describe the persona.
    """
    if not messages:
        return {}
    
    # Count distributions
    topic_counts = Counter(m.get('primary_topic', 'general') for m in messages)
    tone_counts = Counter(m.get('primary_tone', 'neutral') for m in messages)
    reasoning_counts = Counter(m.get('primary_reasoning', 'direct') for m in messages)
    length_counts = Counter(m.get('length_category', 'medium') for m in messages)
    
    # Calculate percentages
    total = len(messages)
    
    # Find dominant characteristics (>20% of cluster)
    dominant_topics = [t for t, c in topic_counts.most_common() if c/total > 0.2]
    dominant_tones = [t for t, c in tone_counts.most_common() if c/total > 0.2]
    dominant_reasoning = [r for r, c in reasoning_counts.most_common() if c/total > 0.2]
    dominant_lengths = [l for l, c in length_counts.most_common() if c/total > 0.2]
    
    # Code usage
    code_ratio = sum(1 for m in messages if m.get('has_code')) / total
    
    # Question patterns
    question_types = Counter()
    for m in messages:
        for qt in m.get('question_types', []):
            question_types[qt] += 1
    
    # Average message length
    avg_words = sum(m.get('word_count', 0) for m in messages) / total
    
    return {
        'size': total,
        'dominant_topics': dominant_topics,
        'dominant_tones': dominant_tones,
        'dominant_reasoning': dominant_reasoning,
        'dominant_lengths': dominant_lengths,
        'topic_distribution': dict(topic_counts.most_common()),
        'tone_distribution': dict(tone_counts.most_common()),
        'code_ratio': code_ratio,
        'question_types': dict(question_types.most_common()),
        'avg_word_count': avg_words,
    }


def generate_cluster_name(analysis: Dict) -> str:
    """
    Generate a descriptive name for a cluster based on its characteristics.
    """
    topics = analysis.get('dominant_topics', [])
    tones = analysis.get('dominant_tones', [])
    reasoning = analysis.get('dominant_reasoning', [])
    code_ratio = analysis.get('code_ratio', 0)
    avg_words = analysis.get('avg_word_count', 50)
    
    # Build name based on most distinctive characteristics
    name_parts = []
    
    # Primary characteristic from topic
    if 'system_design' in topics or 'planning' in topics:
        name_parts.append('Strategist')
    elif 'troubleshooting' in topics:
        name_parts.append('Solver')
    elif 'creative' in topics:
        name_parts.append('Innovator')
    elif 'coding' in topics and code_ratio > 0.3:
        name_parts.append('Builder')
    elif 'analysis' in topics:
        name_parts.append('Analyst')
    elif 'learning' in topics:
        name_parts.append('Learner')
    else:
        name_parts.append('Thinker')
    
    # Modifier from tone/style
    if 'exploratory' in reasoning or 'exploratory' in tones:
        name_parts.insert(0, 'Curious')
    elif 'analytical' in reasoning and 'formal' in tones:
        name_parts.insert(0, 'Methodical')
    elif 'casual' in tones and avg_words < 50:
        name_parts.insert(0, 'Direct')
    elif avg_words > 150:
        name_parts.insert(0, 'Thorough')
    elif 'critical' in reasoning or 'conditional' in reasoning:
        name_parts.insert(0, 'Careful')
    
    return '_'.join(name_parts).lower()


def cluster_messages(input_path: Path, output_dir: Path, mode: str = "16GB", 
                     num_clusters: int = None, min_cluster_size: int = 50) -> Dict[str, Any]:
    """
    Cluster messages using unsupervised learning to DISCOVER natural personas.
    
    Instead of fitting into predefined archetypes, this finds the natural
    groupings in YOUR data and names them based on their characteristics.
    """
    print(f"[3/4] Discovering persona clusters from your data...")
    
    config = MODE_CONFIG[mode]
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load messages
    print(f"      Loading messages...")
    messages = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            messages.append(json.loads(line))
    
    print(f"      Loaded {len(messages)} messages")
    
    # Convert to feature vectors
    print(f"      Extracting features...")
    features = [message_to_feature_vector(m) for m in messages]
    
    # Determine number of clusters if not specified
    if num_clusters is None:
        # Heuristic: aim for clusters of ~500-2000 messages each
        # But cap between 3-6 personas
        suggested = max(3, min(6, len(messages) // 1000))
        num_clusters = suggested
    
    print(f"      Clustering into {num_clusters} groups...")
    
    # Run K-means clustering
    labels, centroids = simple_kmeans(features, num_clusters, max_iters=50)
    
    # Group messages by cluster
    clusters = defaultdict(list)
    for i, label in enumerate(labels):
        messages[i]['cluster_id'] = label
        clusters[label].append(messages[i])
    
    # Analyze each cluster and generate names
    print(f"      Analyzing clusters...")
    cluster_info = {}
    
    for cluster_id, cluster_messages in clusters.items():
        analysis = analyze_cluster(cluster_messages)
        
        # Skip tiny clusters
        if analysis['size'] < min_cluster_size:
            print(f"      Cluster {cluster_id}: too small ({analysis['size']} messages), merging to 'other'")
            continue
        
        # Generate name
        name = generate_cluster_name(analysis)
        
        # Ensure unique names
        base_name = name
        counter = 1
        while name in cluster_info:
            name = f"{base_name}_{counter}"
            counter += 1
        
        cluster_info[name] = {
            'cluster_id': cluster_id,
            'analysis': analysis,
            'message_count': len(cluster_messages),
        }
        
        print(f"      Discovered: {name.upper()} ({len(cluster_messages)} messages)")
        print(f"        Topics: {analysis['dominant_topics']}")
        print(f"        Tones: {analysis['dominant_tones']}")
        print(f"        Reasoning: {analysis['dominant_reasoning']}")
    
    # Save cluster files
    print(f"      Saving cluster files...")
    persona_counts = {}
    
    for name, info in cluster_info.items():
        cluster_id = info['cluster_id']
        filepath = output_dir / f"persona_{name}.jsonl"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for msg in clusters[cluster_id]:
                msg['assigned_persona'] = name
                f.write(json.dumps(msg, ensure_ascii=False) + '\n')
        
        persona_counts[name] = info['message_count']
    
    # Save unclustered/small cluster messages
    unclustered = []
    for cluster_id, cluster_messages in clusters.items():
        if not any(info['cluster_id'] == cluster_id for info in cluster_info.values()):
            unclustered.extend(cluster_messages)
    
    if unclustered:
        with open(output_dir / "unclustered.jsonl", 'w', encoding='utf-8') as f:
            for msg in unclustered:
                msg['assigned_persona'] = None
                f.write(json.dumps(msg, ensure_ascii=False) + '\n')
    
    # Save cluster analysis
    analysis_file = output_dir / "cluster_analysis.json"
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump({
            'num_clusters': num_clusters,
            'total_messages': len(messages),
            'clusters': {name: info['analysis'] for name, info in cluster_info.items()},
        }, f, indent=2)
    
    print(f"      Done! Found {len(cluster_info)} distinct personas")
    print(f"      Distribution: {persona_counts}")
    if unclustered:
        print(f"      Unclustered: {len(unclustered)}")
    
    return cluster_info


# ============================================================================
# System Prompt Generation
# ============================================================================

def extract_linguistic_patterns(messages: List[Dict]) -> Dict[str, Any]:
    """Extract linguistic patterns from a set of messages."""
    
    # Collect statistics
    all_text = ' '.join(m['text'] for m in messages)
    words = all_text.lower().split()
    word_freq = Counter(words)
    
    # Find characteristic phrases (2-3 word combinations)
    bigrams = Counter()
    trigrams = Counter()
    for msg in messages:
        msg_words = msg['text'].lower().split()
        for i in range(len(msg_words) - 1):
            bigrams[f"{msg_words[i]} {msg_words[i+1]}"] += 1
        for i in range(len(msg_words) - 2):
            trigrams[f"{msg_words[i]} {msg_words[i+1]} {msg_words[i+2]}"] += 1
    
    # Find common sentence starters
    starters = Counter()
    for msg in messages:
        sentences = re.split(r'[.!?]\s+', msg['text'])
        for sent in sentences:
            words = sent.strip().split()[:3]
            if words:
                starters[' '.join(words).lower()] += 1
    
    # Question patterns
    question_patterns = Counter()
    for msg in messages:
        questions = re.findall(r'[^.!?]*\?', msg['text'])
        for q in questions:
            # Extract pattern (first few words)
            words = q.strip().split()[:4]
            if words:
                question_patterns[' '.join(words).lower()] += 1
    
    return {
        'common_words': word_freq.most_common(50),
        'common_bigrams': bigrams.most_common(30),
        'common_trigrams': trigrams.most_common(20),
        'sentence_starters': starters.most_common(20),
        'question_patterns': question_patterns.most_common(15),
        'avg_message_length': sum(m['word_count'] for m in messages) / len(messages) if messages else 0,
        'code_frequency': sum(1 for m in messages if m.get('has_code', False)) / len(messages) if messages else 0,
    }


def generate_system_prompt(persona_name: str, patterns: Dict, cluster_analysis: Dict, sample_messages: List[Dict]) -> str:
    """
    Generate a system prompt based on DISCOVERED cluster characteristics.
    This uses the actual patterns found in YOUR data, not predefined archetypes.
    """
    
    # Get cluster characteristics
    topics = cluster_analysis.get('dominant_topics', [])
    tones = cluster_analysis.get('dominant_tones', [])
    reasoning = cluster_analysis.get('dominant_reasoning', [])
    lengths = cluster_analysis.get('dominant_lengths', [])
    code_ratio = cluster_analysis.get('code_ratio', 0)
    avg_words = cluster_analysis.get('avg_word_count', 50)
    question_types = cluster_analysis.get('question_types', {})
    
    # Build prompt sections
    prompt_parts = []
    
    # Generate description from characteristics
    description_parts = []
    if 'system_design' in topics or 'planning' in topics:
        description_parts.append("strategic and structured")
    if 'troubleshooting' in topics:
        description_parts.append("problem-solving oriented")
    if 'creative' in topics:
        description_parts.append("creative and innovative")
    if 'coding' in topics:
        description_parts.append("implementation-focused")
    if 'analysis' in topics:
        description_parts.append("analytical")
    if 'learning' in topics:
        description_parts.append("curious and learning-oriented")
    if 'exploratory' in reasoning or 'exploratory' in tones:
        description_parts.append("exploratory")
    if avg_words > 150:
        description_parts.append("thorough and detailed")
    elif avg_words < 50:
        description_parts.append("direct and concise")
    
    description = ", ".join(description_parts[:3]) if description_parts else "thoughtful"
    
    # Core identity
    display_name = persona_name.replace('_', ' ').title()
    prompt_parts.append(f"You are the {display_name} - a {description} thinker.")
    prompt_parts.append("")
    
    # Thinking style (derived from actual data)
    prompt_parts.append("## Your Thinking Style")
    
    if 'analytical' in reasoning:
        prompt_parts.append("- You think systematically, breaking down problems into components")
        prompt_parts.append("- You use logical connectors like 'because', 'therefore', 'thus'")
    if 'exploratory' in reasoning:
        prompt_parts.append("- You explore multiple possibilities before converging")
        prompt_parts.append("- You frequently ask 'what if' and consider alternatives")
    if 'comparative' in reasoning:
        prompt_parts.append("- You compare options explicitly, weighing trade-offs")
        prompt_parts.append("- You consider pros and cons before recommending")
    if 'conditional' in reasoning:
        prompt_parts.append("- You think in terms of conditions and edge cases")
        prompt_parts.append("- You consider 'if X then Y' scenarios")
    if 'direct' in reasoning and not any(r in reasoning for r in ['analytical', 'exploratory', 'comparative']):
        prompt_parts.append("- You get straight to the point")
        prompt_parts.append("- You focus on actionable solutions")
    
    # Add question style if relevant
    if question_types:
        top_questions = sorted(question_types.items(), key=lambda x: -x[1])[:2]
        q_styles = [q[0] for q in top_questions]
        if 'why' in q_styles:
            prompt_parts.append("- You dig into root causes and motivations")
        if 'how' in q_styles:
            prompt_parts.append("- You focus on implementation and process")
        if 'what' in q_styles and 'should' in q_styles:
            prompt_parts.append("- You seek clarity and direction")
    
    prompt_parts.append("")
    
    # Communication style (from actual data)
    prompt_parts.append("## Your Communication Style")
    
    if avg_words > 150:
        prompt_parts.append("- You provide detailed, comprehensive responses")
        prompt_parts.append("- You don't shy away from thorough explanations")
    elif avg_words > 75:
        prompt_parts.append("- You balance detail with conciseness")
        prompt_parts.append("- You elaborate when needed but stay focused")
    else:
        prompt_parts.append("- You are direct and concise")
        prompt_parts.append("- You get to the point quickly")
    
    if 'formal' in tones:
        prompt_parts.append("- You maintain a professional, structured tone")
    if 'casual' in tones:
        prompt_parts.append("- You use a conversational, approachable tone")
    if 'technical' in tones:
        prompt_parts.append("- You use precise technical terminology when appropriate")
    if 'exploratory' in tones:
        prompt_parts.append("- You think out loud and explore ideas openly")
    
    if code_ratio > 0.3:
        prompt_parts.append("- You frequently include code examples and snippets")
    elif code_ratio > 0.1:
        prompt_parts.append("- You include code when it clarifies your point")
    
    prompt_parts.append("")
    
    # Focus areas (from actual data)
    prompt_parts.append("## Your Focus Areas")
    topic_descriptions = {
        'system_design': "System architecture and design patterns",
        'planning': "Strategic planning and roadmapping",
        'analysis': "Analytical evaluation and assessment",
        'coding': "Code implementation and programming",
        'troubleshooting': "Problem diagnosis and debugging",
        'creative': "Creative solutions and ideation",
        'learning': "Explanation and knowledge sharing",
        'general': "General problem-solving and discussion",
    }
    for topic in topics[:4]:  # Top 4 topics
        prompt_parts.append(f"- {topic_descriptions.get(topic, topic.replace('_', ' ').title())}")
    prompt_parts.append("")
    
    # Characteristic phrases (from actual user's data)
    common_starters = patterns.get('sentence_starters', [])
    common_bigrams = patterns.get('common_bigrams', [])
    
    if common_starters or common_bigrams:
        prompt_parts.append("## Characteristic Expressions")
        prompt_parts.append("You naturally use phrases like:")
        
        # Add sentence starters
        added = 0
        for phrase, count in common_starters[:10]:
            if len(phrase) > 5 and count > 2 and added < 5:
                prompt_parts.append(f'- "{phrase}..."')
                added += 1
        
        # Add common phrases
        for phrase, count in common_bigrams[:5]:
            if count > 3 and len(phrase) > 5:
                prompt_parts.append(f'- Uses "{phrase}" frequently')
                break
        
        prompt_parts.append("")
    
    # Sample actual messages for context
    if sample_messages:
        prompt_parts.append("## Example of Your Style")
        prompt_parts.append("Here's how you typically express yourself:")
        
        # Find a good representative message (medium length, not too short)
        good_samples = [m for m in sample_messages 
                       if 50 < m.get('word_count', 0) < 200 
                       and not m.get('has_code')]
        if good_samples:
            sample = good_samples[0]
            sample_text = sample['text'][:300]
            if len(sample['text']) > 300:
                sample_text += "..."
            prompt_parts.append(f'> "{sample_text}"')
        prompt_parts.append("")
    
    # Output format guidance
    prompt_parts.append("## Output Format")
    prompt_parts.append("When responding to prompts:")
    prompt_parts.append("1. Provide a clear summary of your approach")
    prompt_parts.append("2. List key assumptions you're making")
    prompt_parts.append("3. Identify strengths of your approach")
    prompt_parts.append("4. Acknowledge potential risks or limitations")
    prompt_parts.append("5. Rate your confidence (0.0 to 1.0)")
    
    return '\n'.join(prompt_parts)


def generate_all_prompts(clusters_dir: Path, output_path: Path, mode: str = "16GB") -> Dict[str, str]:
    """Generate system prompts for all DISCOVERED persona clusters."""
    print(f"[4/4] Generating system prompts from discovered patterns...")
    
    config = MODE_CONFIG[mode]
    prompts = {}
    
    # Load cluster analysis
    analysis_file = clusters_dir / "cluster_analysis.json"
    if analysis_file.exists():
        with open(analysis_file, 'r', encoding='utf-8') as f:
            cluster_data = json.load(f)
        cluster_analyses = cluster_data.get('clusters', {})
    else:
        cluster_analyses = {}
    
    # Find all persona files (dynamically discovered)
    persona_files = list(clusters_dir.glob("persona_*.jsonl"))
    
    if not persona_files:
        print("      No persona clusters found!")
        return prompts
    
    for cluster_file in persona_files:
        # Extract persona name from filename
        persona_name = cluster_file.stem.replace('persona_', '')
        
        # Load sample messages (limited by mode)
        messages = []
        with open(cluster_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= config['clustering_sample_size']:
                    break
                messages.append(json.loads(line))
        
        if len(messages) < 10:
            print(f"      Skipping {persona_name} (too few messages: {len(messages)})")
            continue
        
        # Get cluster analysis (or generate basic one)
        cluster_analysis = cluster_analyses.get(persona_name, {})
        if not cluster_analysis:
            # Generate basic analysis if not available
            cluster_analysis = analyze_cluster(messages)
        
        # Extract linguistic patterns
        patterns = extract_linguistic_patterns(messages)
        
        # Generate prompt using discovered characteristics
        prompt = generate_system_prompt(
            persona_name, 
            patterns, 
            cluster_analysis,
            messages[:100]
        )
        prompts[persona_name] = prompt
        
        display_name = persona_name.replace('_', ' ').title()
        print(f"      Generated prompt for {display_name} ({len(messages)} messages)")
    
    # Save prompts with metadata
    output_data = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'mode': mode,
        'discovery_method': 'unsupervised_clustering',
        'cluster_analyses': cluster_analyses,
        'prompts': prompts
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"      Saved {len(prompts)} prompts to {output_path}")
    return prompts


# ============================================================================
# Main Pipeline
# ============================================================================

def run_pipeline(input_file: Path, mode: str = "16GB", num_clusters: int = None, 
                 force_refresh: bool = False):
    """
    Run the full persona extraction pipeline.
    
    Args:
        input_file: Path to conversations.json
        mode: RAM mode (16GB or 32GB)
        num_clusters: Number of personas to discover (None = auto-detect)
        force_refresh: If True, regenerate even if cached files exist
    """
    
    print("=" * 60)
    print("  AI Council - Persona Discovery Pipeline")
    print(f"  Mode: {mode}")
    print(f"  Clusters: {num_clusters or 'auto-detect'}")
    print("=" * 60)
    print()
    
    base_dir = input_file.parent.parent  # data/personas/raw_imports -> data/personas
    extracted_dir = base_dir / "extracted"
    clusters_dir = base_dir / "clusters"
    prompts_dir = base_dir / "prompts"
    
    # Step 1: Extract messages
    messages_file = extracted_dir / "all_messages.jsonl"
    if not messages_file.exists() or force_refresh:
        messages = extract_messages_streaming(input_file, mode)
        count = save_messages_chunked(messages, messages_file, mode)
        print(f"      Extracted {count} user messages")
    else:
        print(f"[1/4] Using cached messages from {messages_file}")
        count = sum(1 for _ in open(messages_file, 'r', encoding='utf-8'))
    print()
    
    # Step 2: Categorize messages
    categorized_file = extracted_dir / "categorized_messages.jsonl"
    if not categorized_file.exists() or force_refresh:
        stats = categorize_messages_file(messages_file, categorized_file)
        print(f"      Topic distribution: {dict(stats['topics'])}")
        print(f"      Tone distribution: {dict(stats['tones'])}")
    else:
        print(f"[2/4] Using cached categorized messages from {categorized_file}")
    print()
    
    # Step 3: Cluster into personas (always re-run to allow different num_clusters)
    cluster_info = cluster_messages(categorized_file, clusters_dir, mode, num_clusters)
    print()
    
    # Step 4: Generate system prompts
    prompts_file = prompts_dir / "generated_prompts.json"
    prompts = generate_all_prompts(clusters_dir, prompts_file, mode)
    print()
    
    # Summary
    print("=" * 60)
    print("  Pipeline Complete!")
    print("=" * 60)
    print()
    print("DISCOVERED PERSONAS:")
    for name in prompts.keys():
        display_name = name.replace('_', ' ').title()
        if name in cluster_info:
            analysis = cluster_info[name].get('analysis', {})
            topics = analysis.get('dominant_topics', [])
            msg_count = cluster_info[name].get('message_count', 0)
            print(f"  {display_name}")
            print(f"    Messages: {msg_count}")
            print(f"    Focus: {', '.join(topics[:3])}")
        else:
            print(f"  {display_name}")
    print()
    print(f"Output files:")
    print(f"  - Messages: {messages_file}")
    print(f"  - Categorized: {categorized_file}")
    print(f"  - Clusters: {clusters_dir}/")
    print(f"  - Analysis: {clusters_dir}/cluster_analysis.json")
    print(f"  - Prompts: {prompts_file}")
    print()
    print("Next steps:")
    print("  1. Review discovered personas in cluster_analysis.json")
    print("  2. Review/edit prompts in generated_prompts.json")
    print("  3. Import into AI Council: py scripts/import_personas.py")
    print()
    print("To try different number of clusters:")
    print(f"  py scripts/extract_personas.py --clusters 5 --mode {mode}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Discover personas from your conversation data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py scripts/extract_personas.py                    # Auto-detect clusters
  py scripts/extract_personas.py --clusters 4      # Force 4 personas
  py scripts/extract_personas.py --mode 32GB       # Use 32GB mode
  py scripts/extract_personas.py --refresh         # Re-extract everything
        """
    )
    parser.add_argument('input', nargs='?', default=None, 
                       help='Input JSON file (default: data/personas/raw_imports/conversations.json)')
    parser.add_argument('--mode', choices=['16GB', '32GB'], default='16GB',
                       help='RAM mode - affects memory usage and batch sizes')
    parser.add_argument('--clusters', '-c', type=int, default=None,
                       help='Number of personas to discover (default: auto-detect 3-6)')
    parser.add_argument('--refresh', '-r', action='store_true',
                       help='Force re-extraction even if cached files exist')
    args = parser.parse_args()
    
    # Find input file
    if args.input:
        input_file = Path(args.input)
    else:
        # Look for conversations.json in expected locations
        candidates = [
            Path('data/personas/raw_imports/conversations.json'),
            Path('conversations.json'),
        ]
        input_file = None
        for candidate in candidates:
            if candidate.exists():
                input_file = candidate
                break
        
        if not input_file:
            print("Error: No input file specified and conversations.json not found")
            print()
            print("Usage:")
            print("  py scripts/extract_personas.py [conversations.json] [options]")
            print()
            print("First, copy your conversations.json to data/personas/raw_imports/")
            print("  mkdir data\\personas\\raw_imports")
            print("  copy conversations.json data\\personas\\raw_imports\\")
            sys.exit(1)
    
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    run_pipeline(input_file, args.mode, args.clusters, args.refresh)


if __name__ == '__main__':
    main()

