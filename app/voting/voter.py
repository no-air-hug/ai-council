"""
AI Council - Voting System
Handles AI and user voting for candidate selection.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class VoteAction(Enum):
    """Possible user vote actions."""
    SELECT = "select"
    SKIP = "skip"
    OVERRIDE = "override"


@dataclass
class UserVote:
    """A user's vote for a candidate."""
    candidate_id: str
    rank: int  # 1 = first choice, 2 = second, etc. 0 = skip
    feedback: Optional[str] = None
    action: VoteAction = VoteAction.SELECT
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "action": self.action.value
        }


@dataclass
class VotingResult:
    """Combined voting result with comprehensive feedback."""
    winning_candidate_id: str
    ai_scores: Dict[str, float]
    user_votes: Dict[str, UserVote]
    combined_scores: Dict[str, float]
    user_override: bool
    winning_reason: str
    overall_feedback: str = ""
    worker_feedback: Dict[str, str] = None
    synthesizer_feedback: str = ""
    
    def __post_init__(self):
        if self.worker_feedback is None:
            self.worker_feedback = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "winning_candidate_id": self.winning_candidate_id,
            "ai_scores": self.ai_scores,
            "user_votes": {k: v.to_dict() for k, v in self.user_votes.items()},
            "combined_scores": self.combined_scores,
            "user_override": self.user_override,
            "winning_reason": self.winning_reason,
            "overall_feedback": self.overall_feedback,
            "worker_feedback": self.worker_feedback,
            "synthesizer_feedback": self.synthesizer_feedback
        }


class Voter:
    """
    Manages voting between AI and user.
    
    Voting workflow:
    1. AI scores each candidate (from synthesizer)
    2. User reviews candidates and their arguments
    3. User votes (rank, feedback, or skip)
    4. Combine scores to determine winner
    5. User can override final decision
    """
    
    def __init__(
        self,
        ai_weight: float = 0.4,
        user_weight: float = 0.6
    ):
        """
        Initialize voter.
        
        Args:
            ai_weight: Weight for AI scores (0-1).
            user_weight: Weight for user votes (0-1).
        """
        self.ai_weight = ai_weight
        self.user_weight = user_weight
        
        # State
        self.ai_scores: Dict[str, float] = {}
        self.user_votes: Dict[str, UserVote] = {}
        self._candidates: List[str] = []
        
        # Enhanced feedback
        self.overall_feedback: str = ""
        self.worker_feedback: Dict[str, str] = {}
        self.synthesizer_feedback: str = ""
    
    def set_candidates(self, candidate_ids: List[str]):
        """Set the list of candidate IDs to vote on."""
        self._candidates = candidate_ids
    
    def set_ai_scores(self, scores: Dict[str, float]):
        """
        Set AI scores for candidates.
        
        Args:
            scores: Dict mapping candidate_id to score (0-10).
        """
        self.ai_scores = {k: min(10.0, max(0.0, v)) for k, v in scores.items()}
    
    def add_user_vote(
        self,
        candidate_id: str,
        rank: int,
        feedback: Optional[str] = None,
        action: VoteAction = VoteAction.SELECT
    ):
        """
        Add a user vote for a candidate.
        
        Args:
            candidate_id: ID of the candidate.
            rank: Rank (1 = first choice, 2 = second, 0 = skip).
            feedback: Optional feedback text.
            action: Vote action type.
        """
        self.user_votes[candidate_id] = UserVote(
            candidate_id=candidate_id,
            rank=rank,
            feedback=feedback,
            action=action
        )
    
    def submit_user_votes(
        self,
        votes: Dict[str, int],
        candidate_feedback: Dict[str, str] = None,
        overall_feedback: str = "",
        worker_feedback: Dict[str, str] = None,
        synthesizer_feedback: str = ""
    ):
        """
        Submit all user votes with comprehensive feedback.
        
        Args:
            votes: Dict mapping candidate_id to rank.
            candidate_feedback: Optional dict mapping candidate_id to feedback.
            overall_feedback: General feedback on the session.
            worker_feedback: Dict mapping worker_id to feedback text.
            synthesizer_feedback: Feedback on synthesizer performance.
        """
        candidate_feedback = candidate_feedback or {}
        
        for candidate_id, rank in votes.items():
            self.add_user_vote(
                candidate_id=candidate_id,
                rank=rank,
                feedback=candidate_feedback.get(candidate_id),
                action=VoteAction.SELECT if rank > 0 else VoteAction.SKIP
            )
        
        # Store enhanced feedback
        self.overall_feedback = overall_feedback
        self.worker_feedback = worker_feedback or {}
        self.synthesizer_feedback = synthesizer_feedback
    
    def _convert_rank_to_score(self, rank: int, total_candidates: int) -> float:
        """Convert user rank to a 0-10 score."""
        if rank == 0:  # Skip
            return 5.0  # Neutral
        
        # Rank 1 = highest score, rank n = lowest
        max_score = 10.0
        min_score = 4.0
        score_range = max_score - min_score
        
        if total_candidates == 1:
            return max_score if rank == 1 else min_score
        
        # Linear interpolation
        position = (rank - 1) / (total_candidates - 1)
        return max_score - (position * score_range)
    
    def calculate_combined_scores(self) -> Dict[str, float]:
        """
        Calculate combined AI + user scores.
        
        Returns:
            Dict mapping candidate_id to combined score.
        """
        combined = {}
        total_candidates = len(self._candidates)
        
        for candidate_id in self._candidates:
            ai_score = self.ai_scores.get(candidate_id, 5.0)
            
            user_vote = self.user_votes.get(candidate_id)
            if user_vote:
                user_score = self._convert_rank_to_score(
                    user_vote.rank,
                    total_candidates
                )
            else:
                user_score = 5.0  # No vote = neutral
            
            combined[candidate_id] = (
                (ai_score * self.ai_weight) +
                (user_score * self.user_weight)
            )
        
        return combined
    
    def determine_winner(
        self,
        user_override_id: Optional[str] = None
    ) -> VotingResult:
        """
        Determine the winning candidate.
        
        Args:
            user_override_id: Optional candidate ID if user overrides.
        
        Returns:
            VotingResult with complete voting data.
        """
        combined_scores = self.calculate_combined_scores()
        
        # Check for user override
        if user_override_id and user_override_id in self._candidates:
            return VotingResult(
                winning_candidate_id=user_override_id,
                ai_scores=self.ai_scores,
                user_votes=self.user_votes,
                combined_scores=combined_scores,
                user_override=True,
                winning_reason="User override",
                overall_feedback=self.overall_feedback,
                worker_feedback=self.worker_feedback,
                synthesizer_feedback=self.synthesizer_feedback
            )
        
        # Find highest combined score
        if not combined_scores:
            # No candidates - return feedback-only result
            return VotingResult(
                winning_candidate_id="none",
                ai_scores={},
                user_votes=self.user_votes,
                combined_scores={},
                user_override=False,
                winning_reason="No candidates synthesized - feedback only",
                overall_feedback=self.overall_feedback,
                worker_feedback=self.worker_feedback,
                synthesizer_feedback=self.synthesizer_feedback
            )
        
        winner_id = max(combined_scores, key=combined_scores.get)
        
        # Determine reason
        ai_leader = max(self.ai_scores, key=self.ai_scores.get) if self.ai_scores else None
        user_leader = None
        if self.user_votes:
            ranked_votes = [(k, v.rank) for k, v in self.user_votes.items() if v.rank > 0]
            if ranked_votes:
                user_leader = min(ranked_votes, key=lambda x: x[1])[0]
        
        if winner_id == ai_leader == user_leader:
            reason = "AI and user agree"
        elif winner_id == user_leader:
            reason = "User preference (weighted higher)"
        elif winner_id == ai_leader:
            reason = "AI preference (no strong user preference)"
        else:
            reason = "Combined score optimization"
        
        return VotingResult(
            winning_candidate_id=winner_id,
            ai_scores=self.ai_scores,
            user_votes=self.user_votes,
            combined_scores=combined_scores,
            user_override=False,
            winning_reason=reason,
            overall_feedback=self.overall_feedback,
            worker_feedback=self.worker_feedback,
            synthesizer_feedback=self.synthesizer_feedback
        )
    
    def get_voting_state(self) -> Dict[str, Any]:
        """Get current voting state for the UI."""
        return {
            "candidates": self._candidates,
            "ai_scores": self.ai_scores,
            "user_votes": {k: v.to_dict() for k, v in self.user_votes.items()},
            "combined_scores": self.calculate_combined_scores(),
            "ai_weight": self.ai_weight,
            "user_weight": self.user_weight
        }
    
    def get_candidate_summary(self, candidate_id: str) -> Dict[str, Any]:
        """Get summary for a specific candidate."""
        return {
            "candidate_id": candidate_id,
            "ai_score": self.ai_scores.get(candidate_id, 0),
            "user_vote": self.user_votes.get(candidate_id, {}).to_dict() if candidate_id in self.user_votes else None,
            "combined_score": self.calculate_combined_scores().get(candidate_id, 0)
        }


