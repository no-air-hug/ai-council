"""
AI Council - Synthesizer Agent
Reasoner that generates worker questions and checks compatibility.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from ..models.runtime import OllamaRuntime


@dataclass
class SynthesizerQuestions:
    """Questions generated for workers."""
    questions_by_worker: Dict[str, List[str]]
    overall_observations: str
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, text: str) -> "SynthesizerQuestions":
        """Parse structured JSON output."""
        try:
            data = json.loads(text)
            return cls(
                questions_by_worker=data.get("questions_by_worker", {}),
                overall_observations=data.get("overall_observations", ""),
                raw_text=text
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return cls(
                questions_by_worker={},
                overall_observations=text,
                raw_text=text
            )


class Synthesizer:
    """
    Synthesizer agent that supports worker refinement and compatibility checks.

    Responsibilities:
    - Generate clarifying questions for workers
    - Generate follow-up questions for refinements
    - Check compatibility between proposals
    """

    QUESTIONS_PROMPT = """Review the following worker proposals and generate targeted clarifying questions.

WORKER PROPOSALS:
{proposals}

For each worker, generate 1-2 questions that will help clarify or strengthen their proposal.
Focus on:
- Unclear assumptions
- Missing details
- Potential conflicts between proposals
- Risk mitigation

Respond in JSON format:
{{
    "questions_by_worker": {{
        "worker_1": ["question 1", "question 2"],
        "worker_2": ["question 1"],
        ...
    }},
    "overall_observations": "Brief observation about the proposals as a whole"
}}"""

    FOLLOW_UP_QUESTIONS_PROMPT = """Based on the workers' refinements, generate follow-up questions to help them improve further.

PREVIOUS QUESTIONS ASKED:
{previous_questions}

WORKER REFINEMENTS:
{refinements}

Generate follow-up questions that:
1. Probe areas that were not fully addressed
2. Ask for clarification on new points raised
3. Challenge assumptions or weak arguments
4. Encourage deeper exploration of promising ideas

Respond in JSON format:
{{
    "questions_by_worker": {{
        "worker_id": ["question1", "question2"]
    }},
    "overall_observations": "What patterns or gaps do you see across all refinements?"
}}"""

    COMPATIBILITY_CHECK_PROMPT = """Based on the full discussion history in context above, analyze the following REFINED proposals for compatibility - can they be combined?

PROPOSALS:
{proposals}

Remember: You've seen these proposals evolve through refinement rounds. Consider how they've changed and whether the refinements make them more or less compatible.

Determine if these proposals are:
1. COMPATIBLE - Can be combined into a unified approach
2. PARTIALLY_COMPATIBLE - Have some overlapping elements that can merge
3. INCOMPATIBLE - Fundamentally different approaches that cannot merge

Respond in JSON format:
{{
    "compatibility": "compatible|partially_compatible|incompatible",
    "overlap_areas": ["area 1", "area 2", ...],
    "conflict_areas": ["conflict 1", ...],
    "merge_strategy": "How to combine if compatible (or null if incompatible)",
    "compatible_pairs": [["worker_1", "worker_2"], ...] // which workers can collaborate
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

        self.questions: Optional[SynthesizerQuestions] = None
        self.last_questions: Optional[SynthesizerQuestions] = None
        self._context_messages: List[Dict[str, str]] = []
        self._context_limit: int = context_window
        self._last_token_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "context_used": 0
        }

    @property
    def system_prompt(self) -> str:
        """System prompt for the synthesizer."""
        return """You are a synthesis and reasoning agent. Your role is to:
1. Identify gaps and conflicts in proposals
2. Ask targeted clarifying questions
3. Check compatibility across proposals

Be structured, objective, and thorough. Prioritize clarity over creativity."""

    def get_last_token_usage(self) -> Dict[str, int]:
        return self._last_token_usage.copy()

    def _add_to_context(self, role: str, content: str) -> None:
        self._context_messages.append({"role": role, "content": content})

    def _get_context_for_call(self, include_system: bool = True) -> List[Dict[str, str]]:
        messages = []
        if include_system:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self._context_messages)
        return messages

    def _track_tokens(self, result) -> None:
        prompt_tokens = getattr(result, "prompt_tokens", 0)
        output_tokens = getattr(result, "tokens", 0)
        total = getattr(result, "total_tokens", 0)
        self._last_token_usage = {
            "input_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total,
            "context_used": prompt_tokens,
            "context_limit": self._context_limit
        }

    def generate_questions(self, worker_drafts: Dict[str, Dict[str, Any]]) -> SynthesizerQuestions:
        proposals_text = "\n\n".join(
            f"=== {worker_id} ===\n{draft.get('summary', draft)}"
            for worker_id, draft in worker_drafts.items()
        )

        full_prompt = self.QUESTIONS_PROMPT.format(proposals=proposals_text)
        self._add_to_context("user", full_prompt)

        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.4,
            format_json=True
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)

        try:
            data = json.loads(result.text)
            questions = SynthesizerQuestions(
                questions_by_worker=data.get("questions_by_worker", {}),
                overall_observations=data.get("overall_observations", ""),
                raw_text=result.text
            )
        except (json.JSONDecodeError, KeyError):
            questions = SynthesizerQuestions(
                questions_by_worker={},
                overall_observations=result.text,
                raw_text=result.text
            )

        self.questions = questions
        self.last_questions = questions
        return questions

    def generate_follow_up_questions(
        self,
        refinements: Dict[str, Dict[str, Any]],
        previous_questions: SynthesizerQuestions
    ) -> SynthesizerQuestions:
        refinements_text = "\n\n".join(
            f"=== {worker_id} ===\n"
            f"answers: {ref.get('answers_to_questions', {})}\n"
            f"patch_notes: {ref.get('patch_notes', [])}\n"
            f"new_risks: {ref.get('new_risks', [])}\n"
            f"new_tradeoffs: {ref.get('new_tradeoffs', [])}"
            for worker_id, ref in refinements.items()
        )

        prev_q_text = "\n".join(
            f"{wid}: {', '.join(qs)}"
            for wid, qs in (previous_questions.questions_by_worker.items() if previous_questions else {})
        )

        full_prompt = self.FOLLOW_UP_QUESTIONS_PROMPT.format(
            previous_questions=prev_q_text or "None",
            refinements=refinements_text
        )

        self._add_to_context("user", full_prompt)
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.4,
            format_json=True
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)

        try:
            data = json.loads(result.text)
            questions = SynthesizerQuestions(
                questions_by_worker=data.get("questions_by_worker", {}),
                overall_observations=data.get("overall_observations", ""),
                raw_text=result.text
            )
        except (json.JSONDecodeError, KeyError):
            questions = SynthesizerQuestions(
                questions_by_worker={},
                overall_observations=result.text,
                raw_text=result.text
            )

        self.questions = questions
        self.last_questions = questions
        return questions

    def check_compatibility(self, proposals: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        proposals_text = "\n\n".join(
            f"=== {worker_id} ===\n{proposal.get('summary', proposal)}"
            for worker_id, proposal in proposals.items()
        )

        full_prompt = self.COMPATIBILITY_CHECK_PROMPT.format(proposals=proposals_text)
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
        except json.JSONDecodeError:
            data = {
                "compatibility": "unknown",
                "raw_text": result.text
            }

        return data
