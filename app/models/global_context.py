"""
AI Council - Global Context Model
Stores structured deltas for cross-stage state reconstruction.
"""

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Dict, List, Optional


def _utc_timestamp() -> str:
    return datetime.utcnow().isoformat()


@dataclass
class GlobalContext:
    """Global JSON schema for session-wide deltas."""

    session_id: Optional[str] = None
    prompt: Optional[str] = None
    created_at: str = field(default_factory=_utc_timestamp)
    proposals: List[Dict[str, Any]] = field(default_factory=list)
    refinements: List[Dict[str, Any]] = field(default_factory=list)
    critiques: List[Dict[str, Any]] = field(default_factory=list)
    rebuttals: List[Dict[str, Any]] = field(default_factory=list)
    collaboration_deltas: List[Dict[str, Any]] = field(default_factory=list)
    axioms: List[Dict[str, Any]] = field(default_factory=list)
    user_feedback: List[Dict[str, Any]] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    candidate_voting: List[Dict[str, Any]] = field(default_factory=list)
    final_output: Dict[str, Any] = field(default_factory=dict)
    patch_notes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "prompt": self.prompt,
            "created_at": self.created_at,
            "proposals": self.proposals,
            "refinements": self.refinements,
            "critiques": self.critiques,
            "rebuttals": self.rebuttals,
            "collaboration_deltas": self.collaboration_deltas,
            "axioms": self.axioms,
            "user_feedback": self.user_feedback,
            "candidates": self.candidates,
            "candidate_voting": self.candidate_voting,
            "final_output": self.final_output,
            "patch_notes": self.patch_notes,
        }

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update the global context from a dict, preserving known keys."""
        for field_info in fields(self):
            key = field_info.name
            if key in data:
                setattr(self, key, data[key])

    def add_entry(
        self,
        section: str,
        payload: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append a structured entry to a section and return it."""
        entry = {
            "timestamp": timestamp or _utc_timestamp(),
            "provenance": provenance or {},
            "payload": payload,
        }
        target = getattr(self, section)
        target.append(entry)
        return entry

    def add_proposal(self, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.add_entry("proposals", payload, provenance)

    def add_refinement(self, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.add_entry("refinements", payload, provenance)

    def add_critique(self, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.add_entry("critiques", payload, provenance)

    def add_rebuttal(self, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.add_entry("rebuttals", payload, provenance)

    def add_collaboration_delta(
        self, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self.add_entry("collaboration_deltas", payload, provenance)

    def add_axiom(self, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.add_entry("axioms", payload, provenance)

    def add_user_feedback(
        self, payload: Dict[str, Any], provenance: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self.add_entry("user_feedback", payload, provenance)
