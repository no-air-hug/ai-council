"""
AI Council - Engineer Agent
Turns global JSON context and axioms into practical, user-facing outputs.
"""

import json
from typing import Any, Dict, List, Optional

from ..models.runtime import OllamaRuntime


class Engineer:
    """
    Engineer agent that interprets global context and axioms for final output.
    """

    EXTRACT_USER_AXIOMS_PROMPT = """Analyze the global JSON context to identify implicit AXIOMS from user feedback.

GLOBAL JSON:
{global_context}

CONVERSATION SUMMARY:
{context}

Extract the underlying axioms from the user's feedback. Even short feedback reveals assumptions.

Respond in JSON format:
{{
    "axioms": [
        {{
            "statement": "The axiom implied by the user's feedback",
            "axiom_type": "core|derived|assumption|parameter",
            "confidence": 0.0 to 1.0,
            "source_feedback": "The specific feedback this was derived from",
            "reasoning": "Why this is an underlying axiom"
        }}
    ],
    "user_priorities": "What the user seems to prioritize based on their feedback"
}}"""

    AXIOM_NETWORK_PROMPT = """As the engineer, analyze the collected axioms and build a coherent network.

USER AXIOMS:
{user_axioms}

WORKER AXIOMS:
{worker_axioms}

DISCUSSION SUMMARY:
{discussion_summary}

Analyze the axioms for:
1. Shared axioms across sources
2. Conflicts and contradictions
3. Dependencies (which axioms build on others)
4. Clusters/themes
5. META-AXIOMS: What assumptions did YOU make when synthesizing?

Respond in JSON format:
{{
    "meta_axioms": [
        {{
            "statement": "Your own meta-axiom about the discussion",
            "axiom_type": "meta",
            "confidence": 0.0 to 1.0,
            "applies_to": "What this assumption governed"
        }}
    ],
    "shared_axioms": [
        {{"statement": "...", "sources": ["user", "worker_1"], "confidence": 0.9}}
    ],
    "conflicts": [
        {{"axiom_a": "...", "axiom_b": "...", "nature": "contradiction|scope|emphasis", "sources_a": [...], "sources_b": [...]}}
    ],
    "dependencies": [
        {{"from": "axiom text", "to": "axiom text", "type": "enables|derives|supports"}}
    ],
    "theories": [
        {{
            "name": "Theory name",
            "summary": "What this theory represents",
            "core_axioms": ["axiom 1", "axiom 2"],
            "proponents": ["worker_1", "user"]
        }}
    ]
}}"""

    FINAL_OUTPUT_PROMPT = """You are the Engineer. Translate the global JSON into a practical, user-facing response.

GLOBAL JSON CONTEXT:
{global_context}

WINNING CANDIDATE:
{candidate}

USER FEEDBACK & DIRECTION:
{feedback}

VOTING RESULTS:
- AI Score: {ai_score}
- User Selection: {user_selection}

AXIOM SUMMARY:
{axiom_summary}

Hard constraints:
- Use the selected candidate as the primary recommendation.
- Present multiple options with key strengths and weaknesses.
- You do NOT need to list every axiom; only those relevant to the final response.
- Avoid unnecessary repetition; focus on actionable, practical guidance.

Generate a comprehensive final response with:
1. Recommended approach (rooted in the winning candidate)
2. 2-3 alternative options with strengths and weaknesses
3. Trade-offs and risks grounded in the axioms and feedback
4. Clear next steps and decision criteria

Write the final response directly, not in JSON format."""

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
            "You are the Engineer. You translate nuanced context and axioms into practical, "
            "actionable guidance with clear options and trade-offs."
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

    def extract_user_axioms(
        self,
        global_context: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        full_prompt = self.EXTRACT_USER_AXIOMS_PROMPT.format(
            global_context=json.dumps(global_context, ensure_ascii=False),
            context=context
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
        except json.JSONDecodeError:
            data = {
                "axioms": [],
                "user_priorities": result.text
            }

        data["raw_text"] = result.text
        return data

    def analyze_axiom_network(
        self,
        user_axioms: List[Dict],
        worker_axioms: Dict[str, List[Dict]],
        discussion_summary: str
    ) -> Dict[str, Any]:
        user_axioms_text = "\n".join(
            f"- {a.get('statement', a)}"
            for a in user_axioms
        ) if user_axioms else "No user axioms extracted"

        worker_axioms_text = "\n\n".join(
            f"=== {worker_id} ===\n" + "\n".join(
                f"- {a.get('statement', a)}"
                for a in axioms
            )
            for worker_id, axioms in worker_axioms.items()
        ) if worker_axioms else "No worker axioms"

        full_prompt = self.AXIOM_NETWORK_PROMPT.format(
            user_axioms=user_axioms_text,
            worker_axioms=worker_axioms_text,
            discussion_summary=discussion_summary
        )

        self._add_to_context("user", full_prompt)
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=max(self.max_tokens, 600),
            temperature=0.4,
            format_json=True
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)

        try:
            data = json.loads(result.text)
        except json.JSONDecodeError:
            data = {
                "meta_axioms": [],
                "shared_axioms": [],
                "conflicts": [],
                "dependencies": [],
                "theories": [],
                "raw_text": result.text
            }

        data["raw_text"] = result.text
        return data

    def generate_final_output(
        self,
        global_context: Dict[str, Any],
        winning_candidate_summary: str,
        user_feedback: str = "",
        ai_score: float = 0.0,
        user_selection: Optional[str] = None,
        axiom_summary: Optional[str] = None
    ) -> str:
        full_prompt = self.FINAL_OUTPUT_PROMPT.format(
            global_context=json.dumps(global_context, ensure_ascii=False),
            candidate=winning_candidate_summary,
            feedback=user_feedback or "No specific feedback provided",
            ai_score=ai_score,
            user_selection=user_selection or "Not specified",
            axiom_summary=axiom_summary or "(Axiom analysis not performed)"
        )

        final_max_tokens = max(self.max_tokens * 2, 800)
        self._add_to_context("user", full_prompt)
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=final_max_tokens,
            temperature=0.5
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)

        return result.text
