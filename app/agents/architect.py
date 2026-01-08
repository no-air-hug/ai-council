"""
AI Council - Architect Agent
Maintains global JSON updates, candidate synthesis, and voting analysis.
"""

import json
from typing import Dict, Any, List, Optional

from ..models.runtime import OllamaRuntime
from ..models.candidate import Candidate, CandidateScore


class Architect:
    """
    Architect agent that updates the global JSON and drives candidate selection.
    """

    UPDATE_PROMPT = """You are the Architect for the council session.

Primary objectives:
- Maintain a compact, useful global JSON for the Engineer.
- Update worker-specific summaries (refinement, argumentation, collaboration).
- Preserve nuance without dumping full raw logs or repeats.
- Provide patch notes that highlight what changed since the prior snapshot.
- Ensure candidate voting phase data is captured.

You receive:
1) The current global JSON snapshot.
2) The stage name and stage payload.

Return JSON ONLY in this exact format:
{
  "entries": [
    {
      "section": "workers|questions|compatibility|collaboration|candidates|voting|axioms|user_feedback|final_output|patch_notes",
      "payload": { "..." : "..." },
      "provenance": { "stage": "stage_name", "source": "architect" }
    }
  ],
  "patch_notes": ["note 1", "note 2"]
}

Schema guidance:
- workers: { "worker_id": { "display_id": "...", "proposal_summary": "...", "refinement_notes": [...], "argumentation_highlights": [...], "collaboration_notes": [...] } }
- questions: { "overall": "...", "by_worker": { "worker_id": ["q1", "q2"] } }
- compatibility: { "compatibility": "...", "overlap_areas": [...], "conflict_areas": [...], "merge_strategy": "..." }
- collaboration: { "rounds": { "1": { "by_worker": { "worker_id": "summary" } } } }
- candidates: [ { "id": "...", "summary": "...", "strengths": [...], "weaknesses": [...], "best_use_case": "..." } ]
- voting: { "ai_scores": {...}, "winning_candidate_id": "...", "winning_reason": "..." }
- axioms: { "shared": [...], "conflicts": [...], "theories": [...] }
- user_feedback: { "overall": "...", "by_worker": {...}, "by_candidate": {...} }
- final_output: { "summary": "...", "key_actions": [...], "risks": [...] }

Rules:
- Do NOT repeat entries already present in the global JSON.
- Update or replace summaries rather than appending raw logs.
- Use consistent keys and structure across entries.
- If nothing new should be added, return an empty entries array and empty patch_notes.
"""

    SYNTHESIS_PROMPT = """Based on the refined worker proposals, synthesize 3-4 distinct candidate solutions.

REFINED PROPOSALS:
{proposals}

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
}}
"""

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
}}
"""

    COMMENTARY_PROMPT = """As the council coordinator, provide DIRECTIVE feedback to guide the next argumentation round.

ARGUMENTS PRESENTED:
{arguments_summary}
{user_feedback_section}
ROUND: {round_num}

Don't just observe - DIRECT the workers. Tell them specifically:
1. What arguments need more evidence or support
2. What assumptions should be challenged or defended
3. Which points need clarification or expansion
4. How to strengthen their case for the next round
5. If user provided feedback, incorporate their direction

Be specific, actionable, and constructive. Give workers concrete guidance on what to do next."""

    EXTRACT_USER_AXIOMS_PROMPT = """Analyze the user's feedback to identify implicit AXIOMS - fundamental assumptions and beliefs.

USER FEEDBACK HISTORY:
{feedback_history}

CONTEXT (what the user was responding to):
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
}}
"""

    AXIOM_NETWORK_PROMPT = """Analyze the collected axioms and build a coherent network.

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
}}
"""

    def __init__(
        self,
        runtime: OllamaRuntime,
        model: str,
        max_tokens: int = 600,
        context_window: int = 8192
    ):
        self.runtime = runtime
        self.model = model
        self.max_tokens = max_tokens
        self._context_limit = context_window

        self.candidates: List[Candidate] = []
        self.scores: Dict[str, CandidateScore] = {}
        self._context_messages: List[Dict[str, str]] = []
        self._last_token_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "context_used": 0
        }

    @property
    def system_prompt(self) -> str:
        return """You are the Architect agent.
Maintain the global JSON, track candidate selection, and avoid redundant updates.
Be structured, precise, and consistent in JSON formatting."""

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

    def update_global_context(
        self,
        stage: str,
        stage_payload: Dict[str, Any],
        current_context: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Update the global JSON with the latest stage payload."""
        full_prompt = (
            f"CURRENT GLOBAL JSON:\n{json.dumps(current_context, indent=2)}\n\n"
            f"STAGE: {stage}\n"
            f"STAGE PAYLOAD:\n{json.dumps(stage_payload, indent=2)}\n"
            f"PROVENANCE:\n{json.dumps(provenance or {}, indent=2)}"
        )

        self._add_to_context("user", self.UPDATE_PROMPT + "\n\n" + full_prompt)
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
            data = {"entries": [], "patch_notes": []}
        data.setdefault("entries", [])
        data.setdefault("patch_notes", [])
        return data

    def synthesize_candidates(
        self,
        refined_proposals: Dict[str, Dict[str, Any]]
    ) -> List[Candidate]:
        proposals_text = "\n\n".join(
            f"=== {worker_id} ===\n"
            f"Summary: {proposal.get('summary', '')}\n"
            f"Patch notes: {proposal.get('patch_notes', [])}\n"
            f"Answers: {proposal.get('answers_to_questions', {})}\n"
            f"New risks: {proposal.get('new_risks', [])}\n"
            f"New tradeoffs: {proposal.get('new_tradeoffs', [])}"
            for worker_id, proposal in refined_proposals.items()
        )

        full_prompt = self.SYNTHESIS_PROMPT.format(proposals=proposals_text)
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

        candidates: List[Candidate] = []
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

        self.candidates = candidates
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
            max_tokens=300,
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

        self.scores[candidate.id] = score
        return score

    def score_all_candidates(
        self,
        arguments: Dict[str, str],
        rubric: Optional[str] = None
    ) -> Dict[str, CandidateScore]:
        for candidate in self.candidates:
            argument = arguments.get(candidate.id, "")
            self.score_candidate(candidate, argument, rubric)
        return self.scores

    def generate_argumentation_commentary(
        self,
        arguments_summary: str,
        round_num: int,
        user_feedback: str = None
    ) -> str:
        user_section = ""
        if user_feedback:
            user_section = f"""

USER FEEDBACK (incorporate this into your commentary):
{user_feedback}
"""
        full_prompt = self.COMMENTARY_PROMPT.format(
            arguments_summary=arguments_summary,
            user_feedback_section=user_section,
            round_num=round_num
        )
        self._add_to_context("user", full_prompt)
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=200,
            temperature=0.6
        )
        self._track_tokens(result)
        self._add_to_context("assistant", result.text)
        return result.text

    def extract_user_axioms(
        self,
        feedback_history: List[Dict[str, str]],
        context: str
    ) -> Dict[str, Any]:
        feedback_text = "\n\n".join(
            f"Round {f.get('round', '?')}: {f.get('feedback', f)}"
            for f in feedback_history
        ) if feedback_history else "No feedback yet"

        full_prompt = self.EXTRACT_USER_AXIOMS_PROMPT.format(
            feedback_history=feedback_text,
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
            max_tokens=600,
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
