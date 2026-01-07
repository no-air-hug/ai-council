"""
AI Council - Axiom Data Models
Richly attributed axiom network for mind map visualization.

Axioms are collected LAST in the pipeline (after all debate/refinement)
because every statement approximates truth but never IS truth.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import json
import hashlib


class AxiomSourceType(Enum):
    """Who contributed an axiom."""
    USER = "user"
    WORKER = "worker"
    SYNTHESIZER = "synthesizer"


@dataclass
class AxiomSource:
    """Attribution for who contributed an axiom."""
    source_type: AxiomSourceType     # user | worker | synthesizer
    source_id: str                   # "user", "synthesizer", or worker_id
    
    # Worker-specific attribution
    persona_id: Optional[str] = None       # Persona ID if worker has one
    persona_name: Optional[str] = None     # "Analyst", "Creative", etc.
    is_default_persona: bool = True        # True if no custom persona assigned
    
    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "is_default_persona": self.is_default_persona
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AxiomSource":
        return cls(
            source_type=AxiomSourceType(data["source_type"]),
            source_id=data["source_id"],
            persona_id=data.get("persona_id"),
            persona_name=data.get("persona_name"),
            is_default_persona=data.get("is_default_persona", True)
        )
    
    @classmethod
    def user(cls) -> "AxiomSource":
        """Create a user source."""
        return cls(
            source_type=AxiomSourceType.USER,
            source_id="user"
        )
    
    @classmethod
    def worker(cls, worker_id: str, persona_id: str = None, persona_name: str = None) -> "AxiomSource":
        """Create a worker source with optional persona."""
        return cls(
            source_type=AxiomSourceType.WORKER,
            source_id=worker_id,
            persona_id=persona_id,
            persona_name=persona_name,
            is_default_persona=(persona_id is None)
        )
    
    @classmethod
    def synthesizer(cls) -> "AxiomSource":
        """Create a synthesizer source."""
        return cls(
            source_type=AxiomSourceType.SYNTHESIZER,
            source_id="synthesizer"
        )


@dataclass
class SessionContext:
    """Session metadata for cross-session analysis."""
    session_id: str
    prompt: str                      # Original user prompt
    prompt_hash: str                 # For grouping similar prompts
    timestamp: str
    ram_mode: str                    # "16GB" | "32GB"
    worker_count: int
    personas_used: List[dict]        # [{id, name}, ...]
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "prompt": self.prompt,
            "prompt_hash": self.prompt_hash,
            "timestamp": self.timestamp,
            "ram_mode": self.ram_mode,
            "worker_count": self.worker_count,
            "personas_used": self.personas_used
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SessionContext":
        return cls(
            session_id=data["session_id"],
            prompt=data["prompt"],
            prompt_hash=data["prompt_hash"],
            timestamp=data["timestamp"],
            ram_mode=data["ram_mode"],
            worker_count=data["worker_count"],
            personas_used=data.get("personas_used", [])
        )
    
    @classmethod
    def create(cls, session_id: str, prompt: str, ram_mode: str, 
               worker_count: int, personas: List[dict]) -> "SessionContext":
        """Create a new session context."""
        return cls(
            session_id=session_id,
            prompt=prompt,
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:8],
            timestamp=datetime.utcnow().isoformat() + "Z",
            ram_mode=ram_mode,
            worker_count=worker_count,
            personas_used=personas
        )


@dataclass
class ConnectedStatement:
    """A statement connected to an axiom."""
    text: str
    relationship: str  # "supports" | "extends" | "derives" | "contradicts"
    source: Optional[AxiomSource] = None
    
    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "relationship": self.relationship,
            "source": self.source.to_dict() if self.source else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ConnectedStatement":
        return cls(
            text=data["text"],
            relationship=data["relationship"],
            source=AxiomSource.from_dict(data["source"]) if data.get("source") else None
        )


@dataclass
class AxiomNode:
    """Single axiom in the global knowledge graph."""
    # IDENTITY
    axiom_id: str                    # Global unique: "ax_{session_short}_{source}_{num}"
    statement: str                   # The axiom text
    axiom_type: str                  # "core" | "derived" | "assumption" | "parameter"
    
    # ATTRIBUTION (who contributed this)
    source: AxiomSource              # User, Worker+Persona, or Synthesizer
    
    # SESSION CONTEXT
    session: SessionContext          # Which session, what prompt, what config
    round_num: int                   # Which round of axiom analysis
    
    # CONFIDENCE & STRENGTH
    confidence: float                # Source's confidence (0-1)
    evidence_strength: float = 0.5   # How well supported by statements (0-1)
    
    # NETWORK RELATIONSHIPS (for mind map edges)
    depends_on: List[str] = field(default_factory=list)      # Axiom IDs required
    enables: List[str] = field(default_factory=list)         # Axiom IDs that follow
    conflicts_with: List[str] = field(default_factory=list)  # Contradicting axioms
    supports: List[str] = field(default_factory=list)        # Axioms this reinforces
    
    # THEORY BUILDING
    connected_statements: List[ConnectedStatement] = field(default_factory=list)
    theory_contribution: str = ""    # How this builds the general theory
    theory_id: Optional[str] = None  # Which theory cluster this belongs to
    
    # BIAS & VULNERABILITY DETECTION
    potential_biases: List[str] = field(default_factory=list)
    vulnerability: str = ""          # What would invalidate this
    counter_evidence: List[str] = field(default_factory=list)
    
    # GRAPH METADATA (calculated by synthesizer)
    centrality_score: float = 0.0    # How central to the network
    cluster_id: Optional[str] = None # Thematic cluster
    is_shared: bool = False          # Agreed by multiple sources
    shared_by: List[str] = field(default_factory=list)  # Source IDs that share this
    
    def to_dict(self) -> dict:
        return {
            "axiom_id": self.axiom_id,
            "statement": self.statement,
            "axiom_type": self.axiom_type,
            "source": self.source.to_dict(),
            "session": self.session.to_dict() if self.session else None,
            "round_num": self.round_num,
            "confidence": self.confidence,
            "evidence_strength": self.evidence_strength,
            "depends_on": self.depends_on,
            "enables": self.enables,
            "conflicts_with": self.conflicts_with,
            "supports": self.supports,
            "connected_statements": [s.to_dict() for s in self.connected_statements],
            "theory_contribution": self.theory_contribution,
            "theory_id": self.theory_id,
            "potential_biases": self.potential_biases,
            "vulnerability": self.vulnerability,
            "counter_evidence": self.counter_evidence,
            "centrality_score": self.centrality_score,
            "cluster_id": self.cluster_id,
            "is_shared": self.is_shared,
            "shared_by": self.shared_by
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AxiomNode":
        return cls(
            axiom_id=data["axiom_id"],
            statement=data["statement"],
            axiom_type=data["axiom_type"],
            source=AxiomSource.from_dict(data["source"]),
            session=SessionContext.from_dict(data["session"]) if data.get("session") else None,
            round_num=data.get("round_num", 1),
            confidence=data.get("confidence", 0.5),
            evidence_strength=data.get("evidence_strength", 0.5),
            depends_on=data.get("depends_on", []),
            enables=data.get("enables", []),
            conflicts_with=data.get("conflicts_with", []),
            supports=data.get("supports", []),
            connected_statements=[ConnectedStatement.from_dict(s) for s in data.get("connected_statements", [])],
            theory_contribution=data.get("theory_contribution", ""),
            theory_id=data.get("theory_id"),
            potential_biases=data.get("potential_biases", []),
            vulnerability=data.get("vulnerability", ""),
            counter_evidence=data.get("counter_evidence", []),
            centrality_score=data.get("centrality_score", 0.0),
            cluster_id=data.get("cluster_id"),
            is_shared=data.get("is_shared", False),
            shared_by=data.get("shared_by", [])
        )


@dataclass
class AxiomEdge:
    """Edge in the axiom network."""
    from_axiom: str
    to_axiom: str
    edge_type: str  # "depends_on" | "enables" | "conflicts" | "supports" | "extends"
    strength: float = 1.0  # Edge weight for visualization
    
    def to_dict(self) -> dict:
        return {
            "from": self.from_axiom,
            "to": self.to_axiom,
            "type": self.edge_type,
            "strength": self.strength
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AxiomEdge":
        return cls(
            from_axiom=data["from"],
            to_axiom=data["to"],
            edge_type=data["type"],
            strength=data.get("strength", 1.0)
        )


@dataclass
class Theory:
    """A cluster of related axioms forming a coherent theory."""
    theory_id: str
    name: str                        # "Efficiency-First Approach"
    summary: str
    core_axioms: List[str]           # Central axiom IDs
    supporting_axioms: List[str] = field(default_factory=list)  # Peripheral axiom IDs
    proponents: List[AxiomSource] = field(default_factory=list)  # Who champions this theory
    competing_theories: List[str] = field(default_factory=list)  # Theory IDs that conflict
    session_id: str = ""
    
    def to_dict(self) -> dict:
        return {
            "theory_id": self.theory_id,
            "name": self.name,
            "summary": self.summary,
            "core_axioms": self.core_axioms,
            "supporting_axioms": self.supporting_axioms,
            "proponents": [p.to_dict() for p in self.proponents],
            "competing_theories": self.competing_theories,
            "session_id": self.session_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Theory":
        return cls(
            theory_id=data["theory_id"],
            name=data["name"],
            summary=data["summary"],
            core_axioms=data.get("core_axioms", []),
            supporting_axioms=data.get("supporting_axioms", []),
            proponents=[AxiomSource.from_dict(p) for p in data.get("proponents", [])],
            competing_theories=data.get("competing_theories", []),
            session_id=data.get("session_id", "")
        )


@dataclass
class AxiomNetwork:
    """Full axiom graph for a session - ready for mind map export."""
    # SESSION INFO
    session: SessionContext
    
    # NODES (all axioms from all sources)
    nodes: Dict[str, AxiomNode] = field(default_factory=dict)
    
    # EDGES (relationships)
    edges: List[AxiomEdge] = field(default_factory=list)
    
    # THEORIES (clustered axioms)
    theories: List[Theory] = field(default_factory=list)
    
    # CROSS-SOURCE ANALYSIS
    shared_axioms: List[dict] = field(default_factory=list)
    # Each: {"axiom_ids": [...], "merged_statement": "...", "sources": [...]}
    
    conflict_clusters: List[dict] = field(default_factory=list)
    # Each: {"axiom_ids": [...], "nature": "contradiction|scope|emphasis", "sources": [...]}
    
    # SOURCE STATISTICS (for mind map coloring)
    axioms_by_source: Dict[str, List[str]] = field(default_factory=dict)
    # {"user": ["ax_001"], "worker_1": ["ax_002"], "synthesizer": ["ax_003"]}
    
    axioms_by_persona: Dict[str, List[str]] = field(default_factory=dict)
    # {"Analyst": ["ax_002"], "Creative": ["ax_004"], "default": ["ax_005"]}
    
    def add_axiom(self, axiom: AxiomNode):
        """Add an axiom and update tracking indices."""
        self.nodes[axiom.axiom_id] = axiom
        
        # Update source tracking
        source_key = axiom.source.source_id
        if source_key not in self.axioms_by_source:
            self.axioms_by_source[source_key] = []
        self.axioms_by_source[source_key].append(axiom.axiom_id)
        
        # Update persona tracking
        persona_key = axiom.source.persona_name or "default"
        if persona_key not in self.axioms_by_persona:
            self.axioms_by_persona[persona_key] = []
        self.axioms_by_persona[persona_key].append(axiom.axiom_id)
    
    def add_edge(self, from_id: str, to_id: str, edge_type: str, strength: float = 1.0):
        """Add an edge between axioms."""
        self.edges.append(AxiomEdge(from_id, to_id, edge_type, strength))
    
    def build_edges_from_nodes(self):
        """Build edges from node relationship fields."""
        for axiom in self.nodes.values():
            for dep_id in axiom.depends_on:
                self.add_edge(axiom.axiom_id, dep_id, "depends_on")
            for enable_id in axiom.enables:
                self.add_edge(axiom.axiom_id, enable_id, "enables")
            for conflict_id in axiom.conflicts_with:
                self.add_edge(axiom.axiom_id, conflict_id, "conflicts")
            for support_id in axiom.supports:
                self.add_edge(axiom.axiom_id, support_id, "supports")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "session": self.session.to_dict() if self.session else None,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "theories": [t.to_dict() for t in self.theories],
            "shared_axioms": self.shared_axioms,
            "conflict_clusters": self.conflict_clusters,
            "axioms_by_source": self.axioms_by_source,
            "axioms_by_persona": self.axioms_by_persona
        }
    
    def to_mindmap_json(self) -> dict:
        """Export format optimized for mind map visualization."""
        return {
            "session": self.session.to_dict() if self.session else None,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "theories": [t.to_dict() for t in self.theories],
            "analysis": {
                "shared_axioms": self.shared_axioms,
                "conflict_clusters": self.conflict_clusters,
                "by_source": self.axioms_by_source,
                "by_persona": self.axioms_by_persona
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AxiomNetwork":
        """Create from dictionary."""
        network = cls(
            session=SessionContext.from_dict(data["session"]) if data.get("session") else None
        )
        
        # Load nodes
        for axiom_data in data.get("nodes", {}).values() if isinstance(data.get("nodes"), dict) else data.get("nodes", []):
            if isinstance(axiom_data, dict):
                network.nodes[axiom_data["axiom_id"]] = AxiomNode.from_dict(axiom_data)
        
        # Load edges
        for edge_data in data.get("edges", []):
            network.edges.append(AxiomEdge.from_dict(edge_data))
        
        # Load theories
        for theory_data in data.get("theories", []):
            network.theories.append(Theory.from_dict(theory_data))
        
        # Load analysis data
        network.shared_axioms = data.get("shared_axioms", [])
        network.conflict_clusters = data.get("conflict_clusters", [])
        network.axioms_by_source = data.get("axioms_by_source", data.get("analysis", {}).get("by_source", {}))
        network.axioms_by_persona = data.get("axioms_by_persona", data.get("analysis", {}).get("by_persona", {}))
        
        return network
    
    def save(self, filepath: str):
        """Save network to JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_mindmap_json(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, filepath: str) -> "AxiomNetwork":
        """Load network from JSON file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


def generate_axiom_id(session_id: str, source: AxiomSource, index: int) -> str:
    """Generate a unique axiom ID."""
    session_short = session_id[:8] if session_id else "unknown"
    source_prefix = {
        AxiomSourceType.USER: "user",
        AxiomSourceType.WORKER: source.source_id.replace("worker_", "w"),
        AxiomSourceType.SYNTHESIZER: "syn"
    }[source.source_type]
    return f"ax_{session_short}_{source_prefix}_{index:03d}"

