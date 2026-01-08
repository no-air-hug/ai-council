"""
AI Council - Engineer Agent
Generates final practical output from the global JSON context.
"""

import json
from typing import Dict, Any

from ..models.runtime import OllamaRuntime


class Engineer:
    """
    Engineer agent that converts global JSON nuance into practical output.
    """

    FINAL_OUTPUT_PROMPT = """You are the Engineer responsible for final output.

Goals:
- Translate the compact global JSON into practical guidance.
- Present multiple options with their key strengths and weaknesses.
- Use axioms from the global JSON, but do not repeat all axioms verbatim.
- Assume detailed axioms are already rendered in id="final-meta".

GLOBAL JSON CONTEXT (summarized, not raw logs):
{global_context}

WINNING CANDIDATE (if applicable):
{candidate}

USER FEEDBACK & DIRECTION:
{feedback}

VOTING RESULTS:
- AI Score: {ai_score}
- User Selection: {user_selection}

Respond with a clear, actionable write-up that includes:
1) A concise recommendation tied to the winning candidate (if any)
2) 2-4 alternative options with strengths and weaknesses
3) Practical next steps
4) Key risks or watch-outs

Write the final response directly (no JSON)."""

    def __init__(
        self,
        runtime: OllamaRuntime,
        model: str,
        max_tokens: int = 1200,
        context_window: int = 8192
    ):
        self.runtime = runtime
        self.model = model
        self.max_tokens = max_tokens
        self._context_limit = context_window
        self._last_token_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "context_used": 0
        }

    @property
    def system_prompt(self) -> str:
        return """You are the Engineer agent.
Focus on practical, actionable guidance with options and trade-offs.
Leverage axioms from the global JSON without exhaustive repetition."""

    def get_last_token_usage(self) -> Dict[str, int]:
        return self._last_token_usage.copy()

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

    def generate_final_output(
        self,
        global_context: Dict[str, Any],
        winning_candidate: str,
        user_feedback: str,
        ai_score: float,
        user_selection: str
    ) -> str:
        full_prompt = self.FINAL_OUTPUT_PROMPT.format(
            global_context=json.dumps(global_context, indent=2),
            candidate=winning_candidate or "No winning candidate selected",
            feedback=user_feedback or "No specific feedback provided",
            ai_score=ai_score,
            user_selection=user_selection or "Not specified"
        )

        result = self.runtime.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            max_tokens=max(self.max_tokens, 800),
            temperature=0.5
        )
        self._track_tokens(result)
        return result.text
