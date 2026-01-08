"""
AI Council - Architect Agent
Maintains global JSON context and synthesizes candidates for voting.
"""

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from ..models.runtime import OllamaRuntime


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


class Architect:
    """
    Architect agent that manages the global JSON context and candidate selection.
    """

    UPDATE_GLOBAL_CONTEXT_PROMPT = """You are the Architect. Update the GLOBAL JSON context based on the latest stage.

Rules:
- Maintain a consistent JSON format. Preserve all existing keys.
- Expand nuance: incorporate new details rather than repeating existing entries.
- Prevent repetition: if the payload duplicates existing content, summarize the delta and avoid re-adding identical entries.
- Always append patch notes describing the delta for this stage.
- Ensure candidate voting phases are captured under `candidate_voting` with scores, votes, and winner.

CURRENT GLOBAL JSON:
{global_context}

STAGE NAME:
{stage}

STAGE PAYLOAD:
{payload}

Return JSON only in this format:
{{
  "global_context": {{
    "session_id": "...",
    "prompt": "...",
    "created_at": "...",
    "proposals": [...],
    "refinements": [...],
    "critiques": [...],
    "rebuttals": [...],
    "collaboration_deltas": [...],
    "axioms": [...],
    "user_feedback": [...],
    "candidates": [...],
    "candidate_voting": [...],
    "final_output": {{}},
    "patch_notes": [...]
  }}
}}"""

    CANDIDATE_SYNTHESIS_PROMPT = """Based on the refined worker proposals, synthesize distinct candidate solutions.

REFINED PROPOSALS:
{proposals}

Create 3-4 distinct candidates that represent the best approaches. Each candidate can combine ideas from multiple workers.

Respond in JSON format:
{{
    "candidates": [
        {{
            "id": "candidate_1",
            "source_workers": ["worker_1", "worker_2"],
            "summary": "Clear summary of this approach",
            "best_use_case": "When this approach works best",
            "trade_offs": ["trade-off 1", "trade-off 2"],
            "failure_modes": ["failure mode 1"],
            "decision_criteria": "Choose this if..."
        }}
    ]
}}"""

    SCORING_PROMPT = """Score the following candidate based on the evaluation criteria.

CANDIDATE:
{candidate}

WORKER'S ARGUMENT FOR THIS CANDIDATE:
{argument}

{rubric}

Score this candidate on a scale of 0-10. Be objective and specific.

Respond in JSON format:
{{
    "score": Number between 0 and 10,
    "reasoning": "Explanation for the score",
    "rubric_scores": {{
        "criteria_1": 8.0,
        "criteria_2": 7.0
    }}
}}"""

    def __init__(
        self,
        runtime: OllamaRuntime,
        model: str,
        max_tokens: int = 400,
        context_window: int = 8192
    ):
        self.runtime = runtime
        self.model = model
        self.max_tokens = max_tokens

        self._context_messages: List[Dict[str, str]] = []
        self._context_limit: int = context_window
        self._cumulative_context: int = 0

        self._last_token_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "context_used": 0
        }
        self._total_tokens: int = 0

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Architect. You maintain the global JSON context, produce patch notes, "
            "and ensure candidate selection data is captured precisely."
        )

    def _add_to_context(self, role: str, content: str) -> None:
        self._context_messages.append({"role": role, "content": content})

    def _get_context_for_call(self, include_system: bool = True) -> List[Dict[str, str]]:
        messages = []
        if include_system:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self._context_messages)
        return messages

    def _track_tokens(self, result) -> None:
        prompt_tokens = getattr(result, 'prompt_tokens', 0)
        output_tokens = getattr(result, 'tokens', 0)
        total = getattr(result, 'total_tokens', 0)

        self._cumulative_context = prompt_tokens
        self._last_token_usage = {
            "input_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total,
            "context_used": prompt_tokens,
            "context_limit": self._context_limit
        }
        self._total_tokens += total

    def get_last_token_usage(self) -> Dict[str, int]:
        return self._last_token_usage.copy()

    def update_global_context(
        self,
        stage: str,
        current_context: Dict[str, Any],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        full_prompt = self.UPDATE_GLOBAL_CONTEXT_PROMPT.format(
            global_context=json.dumps(current_context, ensure_ascii=False),
            stage=stage,
            payload=json.dumps(payload, ensure_ascii=False)
        )

        self._add_to_context("user", full_prompt)
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.3,
            format_json=True
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)

        try:
            data = json.loads(result.text)
            return data
        except json.JSONDecodeError:
            return {
                "global_context": current_context,
                "raw_text": result.text
            }

    def synthesize_candidates(self, refined_proposals: Dict[str, Dict[str, Any]]) -> List[Candidate]:
        proposals_text = "\n\n".join(
            f"=== {worker_id} ===\n"
            f"Summary: {proposal.get('summary', '')}\n"
            f"Patch notes: {proposal.get('patch_notes', [])}\n"
            f"Answers: {proposal.get('answers_to_questions', {})}\n"
            f"New risks: {proposal.get('new_risks', [])}\n"
            f"New tradeoffs: {proposal.get('new_tradeoffs', [])}"
            for worker_id, proposal in refined_proposals.items()
        )

        full_prompt = self.CANDIDATE_SYNTHESIS_PROMPT.format(proposals=proposals_text)
        self._add_to_context("user", full_prompt)

        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.5,
            format_json=True
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)

        try:
            data = json.loads(result.text)
            candidates = [
                Candidate(
                    id=c.get("id", f"candidate_{i}"),
                    source_workers=c.get("source_workers", []),
                    summary=c.get("summary", ""),
                    best_use_case=c.get("best_use_case", ""),
                    trade_offs=c.get("trade_offs", []),
                    failure_modes=c.get("failure_modes", []),
                    decision_criteria=c.get("decision_criteria", "")
                )
                for i, c in enumerate(data.get("candidates", []))
            ]
        except (json.JSONDecodeError, KeyError):
            candidates = []

        if not candidates and refined_proposals:
            for i, (worker_id, proposal) in enumerate(refined_proposals.items()):
                summary = proposal.get("summary", str(proposal))
                candidates.append(Candidate(
                    id=f"candidate_{i + 1}",
                    source_workers=[worker_id],
                    summary=summary[:500] if len(summary) > 500 else summary,
                    best_use_case="Based on this worker's refined proposal",
                    trade_offs=["Derived from single worker's perspective"],
                    failure_modes=["May not incorporate other workers' insights"],
                    decision_criteria=f"Choose if you prefer {worker_id}'s approach"
                ))

        return candidates

    def score_candidate(
        self,
        candidate: Candidate,
        argument: str,
        rubric: Optional[str] = None
    ) -> CandidateScore:
        rubric_text = f"\nEVALUATION RUBRIC:\n{rubric}" if rubric else ""
        full_prompt = self.SCORING_PROMPT.format(
            candidate=candidate.summary,
            argument=argument,
            rubric=rubric_text
        )

        self._add_to_context("user", full_prompt)
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=min(self.max_tokens, 800),
            temperature=0.3,
            format_json=True
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)

        try:
            data = json.loads(result.text)
            score = CandidateScore(
                candidate_id=candidate.id,
                score=float(data.get("score", 5.0)),
                reasoning=data.get("reasoning", ""),
                rubric_scores=data.get("rubric_scores", {})
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            score = CandidateScore(
                candidate_id=candidate.id,
                score=5.0,
                reasoning=result.text,
                rubric_scores={}
            )

        return score

    def score_all_candidates(
        self,
        candidates: List[Candidate],
        arguments: Dict[str, str],
        rubric: Optional[str] = None
    ) -> Dict[str, CandidateScore]:
        scores: Dict[str, CandidateScore] = {}
        for candidate in candidates:
            argument = arguments.get(candidate.id, "")
            scores[candidate.id] = self.score_candidate(candidate, argument, rubric)
        return scores
