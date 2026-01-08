"""
AI Council - Global Context Model
Stores structured deltas for cross-stage state reconstruction.
"""

from dataclasses import dataclass, field
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
    workers: Dict[str, Any] = field(default_factory=dict)
    questions: Dict[str, Any] = field(default_factory=dict)
    compatibility: Dict[str, Any] = field(default_factory=dict)
    collaboration: Dict[str, Any] = field(default_factory=dict)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    voting: Dict[str, Any] = field(default_factory=dict)
    axioms: Dict[str, Any] = field(default_factory=dict)
    user_feedback: Dict[str, Any] = field(default_factory=dict)
    final_output: Dict[str, Any] = field(default_factory=dict)
    patch_notes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "prompt": self.prompt,
            "created_at": self.created_at,
            "workers": self.workers,
            "questions": self.questions,
            "compatibility": self.compatibility,
            "collaboration": self.collaboration,
            "candidates": self.candidates,
            "voting": self.voting,
            "axioms": self.axioms,
            "user_feedback": self.user_feedback,
            "final_output": self.final_output,
            "patch_notes": self.patch_notes,
        }

    def allowed_sections(self) -> set:
        """Return allowed sections for architect updates."""
        return {
            "workers",
            "questions",
            "compatibility",
            "collaboration",
            "candidates",
            "voting",
            "axioms",
            "user_feedback",
            "final_output",
            "patch_notes",
        }

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
        if isinstance(target, list):
            target.append(entry)
            return entry
        if isinstance(target, dict):
            target.update(payload)
            return entry
        setattr(self, section, payload)
        return entry
