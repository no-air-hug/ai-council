"""
AI Council - Candidate Models
Structured representations for synthesized candidates and scores.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, List


@dataclass
class Candidate:
    """A synthesized candidate solution."""

    id: str
    source_workers: List[str]
    summary: str
    best_use_case: str
    trade_offs: List[str]
    failure_modes: List[str]
    decision_criteria: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateScore:
    """AI score for a candidate."""

    candidate_id: str
    score: float  # 0-10
    reasoning: str
    rubric_scores: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
