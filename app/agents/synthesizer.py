"""
AI Council - Synthesizer Agent
Reasoner that synthesizes worker outputs, generates questions, and scores candidates.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from ..models.runtime import OllamaRuntime, GenerationResult


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


class Synthesizer:
    """
    Synthesizer agent that coordinates worker outputs.
    
    Responsibilities:
    - Generate clarifying questions for workers
    - Synthesize refined candidates
    - Score candidates for AI voting
    - Generate final output
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

    SYNTHESIS_PROMPT = """Based on the previous questions and analysis in context above, synthesize the following REFINED worker proposals into distinct candidate solutions.

REFINED PROPOSALS:
{proposals}

Remember: You've already seen the initial proposals and asked questions about them. These include delta-only refinements (patch notes, new risks, new tradeoffs) that address your questions. Use those deltas to update each worker's proposal when synthesizing candidates.

Create 3-4 distinct candidates that represent the best approaches. Each candidate can combine ideas from multiple workers. Consider how the refinements address the concerns you raised earlier.

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
        }},
        ...
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
        "criteria_2": 7.0,
        ...
    }}
}}"""

    FINAL_OUTPUT_PROMPT = """Generate the comprehensive final response for the WINNING candidate ONLY.

=== FULL CONVERSATION CONTEXT ===
{conversation_context}

=== WINNING CANDIDATE ===
{candidate}

=== USER FEEDBACK & DIRECTION ===
{feedback}

=== VOTING RESULTS ===
- AI Score: {ai_score}
- User Selection: {user_selection}

=== AXIOM ANALYSIS SUMMARY ===
{axiom_summary}

Hard constraints:
- Use ONLY the selected candidate's approach in the final solution.
- Do NOT merge in ideas from other candidates unless explicitly instructed to operate in merge mode.
- If mentioning alternatives, add a brief "Alternatives not chosen" section (1-2 lines each) without blending them into the final plan.

Generate a comprehensive final response that:
1. Implements the selected candidate's approach faithfully
2. Addresses relevant argumentation points without changing the selected approach
3. Reflects collaboration outcomes only if they are already part of the selected candidate
4. Integrates user feedback and direction throughout
5. Acknowledges key axioms and assumptions
6. Provides clear, actionable conclusions

Be thorough - use your full context window to create a well-reasoned synthesis.
Write the final response directly, not in JSON format."""

    def __init__(
        self,
        runtime: OllamaRuntime,
        model: str,
        max_tokens: int = 400,
        context_window: int = 8192
    ):
        """
        Initialize synthesizer agent.
        
        Args:
            runtime: Ollama runtime instance.
            model: Model name to use.
            max_tokens: Maximum output tokens (from UI config).
            context_window: Maximum context window size (from UI config).
        """
        self.runtime = runtime
        self.model = model
        self.max_tokens = max_tokens
        
        # State
        self.questions: Optional[SynthesizerQuestions] = None
        self.candidates: List[Candidate] = []
        self.scores: Dict[str, CandidateScore] = {}
        self.final_output: Optional[str] = None
        self._history: list = []
        
        # Context management - accumulated messages for synthesizer
        self._context_messages: List[Dict[str, str]] = []
        self._context_limit: int = context_window  # FROM UI CONFIG!
        self._cumulative_context: int = 0
        
        # Token tracking
        self._last_token_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "context_used": 0
        }
        self._total_tokens: int = 0
    
    def get_last_token_usage(self) -> Dict[str, int]:
        """Get token usage from the last operation."""
        return self._last_token_usage.copy()
    
    def _add_to_context(self, role: str, content: str) -> None:
        """Add a message to the synthesizer's accumulated context."""
        self._context_messages.append({"role": role, "content": content})
    
    def _get_context_for_call(self, include_system: bool = True) -> List[Dict[str, str]]:
        """Get the accumulated context for an API call."""
        messages = []
        if include_system:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self._context_messages)
        return messages
    
    def _track_tokens(self, result) -> None:
        """Track token usage from a generation result."""
        prompt_tokens = getattr(result, 'prompt_tokens', 0)
        output_tokens = getattr(result, 'tokens', 0)
        total = getattr(result, 'total_tokens', 0)
        
        # Calculate cumulative context size (all messages accumulated so far)
        # This includes system prompt + all user/assistant messages in context
        cumulative_size = 0
        if self.system_prompt:
            cumulative_size += len(self.system_prompt) // 4  # Rough token estimate (4 chars per token)
        
        for msg in self._context_messages:
            content = str(msg.get('content', ''))
            cumulative_size += len(content) // 4  # Rough token estimate
        
        # Update cumulative context - use the actual prompt_tokens from Ollama (which includes full context)
        # But also track our own estimate for verification
        self._cumulative_context = prompt_tokens  # This is the actual context size sent to Ollama
        
        self._last_token_usage = {
            "input_tokens": prompt_tokens,  # Actual prompt tokens (includes full accumulated context)
            "output_tokens": output_tokens,
            "total_tokens": total,
            "context_used": prompt_tokens,  # This is the actual cumulative context size
            "context_estimated": cumulative_size,  # Our estimate for verification
            "context_limit": self._context_limit
        }
        self._total_tokens += total
    
    @property
    def system_prompt(self) -> str:
        """System prompt for the synthesizer."""
        return """You are a synthesis and reasoning agent. Your role is to:
1. Identify gaps and conflicts in proposals
2. Ask targeted clarifying questions
3. Combine ideas into coherent candidates
4. Evaluate objectively against criteria
5. Generate clear, actionable outputs

Be structured, objective, and thorough. Prioritize clarity over creativity."""

    def generate_questions(
        self,
        worker_drafts: Dict[str, Dict[str, Any]]
    ) -> SynthesizerQuestions:
        """
        Generate clarifying questions for workers.
        
        Args:
            worker_drafts: Dict mapping worker_id to their draft output.
        
        Returns:
            SynthesizerQuestions with questions per worker.
        """
        proposals_text = "\n\n".join(
            f"=== {worker_id} ===\n{draft.get('summary', draft)}"
            for worker_id, draft in worker_drafts.items()
        )
        
        full_prompt = self.QUESTIONS_PROMPT.format(proposals=proposals_text)
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.4,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
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
        self._history.append({
            "stage": "questions",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return questions
    
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
    
    def generate_follow_up_questions(
        self,
        refinements: Dict[str, Dict[str, Any]],
        previous_questions: 'SynthesizerQuestions'
    ) -> SynthesizerQuestions:
        """
        Generate follow-up questions based on worker refinements.
        
        Args:
            refinements: Dict mapping worker_id to their refinement output.
            previous_questions: Previous questions that were asked.
        
        Returns:
            SynthesizerQuestions with follow-up questions per worker.
        """
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
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.4,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
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
        self._history.append({
            "stage": "follow_up_questions",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return questions
    
    def synthesize_candidates(
        self,
        refined_proposals: Dict[str, Dict[str, Any]]
    ) -> List[Candidate]:
        """
        Synthesize refined proposals into candidates.
        
        Args:
            refined_proposals: Dict mapping worker_id to refined proposal.
        
        Returns:
            List of synthesized candidates.
        """
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
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.5,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
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
        
        # Fallback: if no candidates were synthesized, create candidates from worker proposals
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
        self._history.append({
            "stage": "synthesis",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return candidates
    
    def score_candidate(
        self,
        candidate: Candidate,
        argument: str,
        rubric: Optional[str] = None
    ) -> CandidateScore:
        """
        Score a single candidate.
        
        Args:
            candidate: Candidate to score.
            argument: Worker's argument for this candidate.
            rubric: Optional evaluation rubric.
        
        Returns:
            CandidateScore with detailed scoring.
        """
        rubric_text = f"\nEVALUATION RUBRIC:\n{rubric}" if rubric else ""
        
        full_prompt = self.SCORING_PROMPT.format(
            candidate=candidate.summary,
            argument=argument,
            rubric=rubric_text
        )
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=300,
            temperature=0.3,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
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
        self._history.append({
            "stage": "scoring",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return score
    
    def score_all_candidates(
        self,
        arguments: Dict[str, str],
        rubric: Optional[str] = None
    ) -> Dict[str, CandidateScore]:
        """
        Score all candidates.
        
        Args:
            arguments: Dict mapping candidate_id to worker argument.
            rubric: Optional evaluation rubric.
        
        Returns:
            Dict mapping candidate_id to score.
        """
        for candidate in self.candidates:
            argument = arguments.get(candidate.id, "")
            self.score_candidate(candidate, argument, rubric)
        
        return self.scores
    
    def generate_final_output(
        self,
        winning_candidate: Candidate,
        user_feedback: str = "",
        ai_score: float = 0.0,
        user_selection: Optional[str] = None,
        conversation_context: Optional[str] = None,
        axiom_summary: Optional[str] = None
    ) -> str:
        """
        Generate the final output with full conversation context.
        
        Args:
            winning_candidate: The selected candidate.
            user_feedback: Optional user feedback.
            ai_score: AI score for the winning candidate.
            user_selection: User's selection reason.
            conversation_context: Full context from refinement, argumentation, collaboration.
            axiom_summary: Summary of axiom analysis.
        
        Returns:
            Final output text.
        """
        full_prompt = self.FINAL_OUTPUT_PROMPT.format(
            conversation_context=conversation_context or "(No conversation context provided)",
            candidate=winning_candidate.summary,
            feedback=user_feedback or "No specific feedback provided",
            ai_score=ai_score,
            user_selection=user_selection or "Not specified",
            axiom_summary=axiom_summary or "(Axiom analysis not performed)"
        )
        
        # Use larger max_tokens for final output - this is the most important output
        final_max_tokens = max(self.max_tokens * 2, 800)
        
        # Add to context and use accumulated messages (FULL context for final synthesis!)
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=final_max_tokens,
            temperature=0.5
        )
        self._track_tokens(result)
        
        # Add response to context
        self._add_to_context("assistant", result.text)
        
        self.final_output = result.text
        self._history.append({
            "stage": "final",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return result.text
    
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

    AXIOM_NETWORK_PROMPT = """As the synthesizer, analyze the collected axioms and build a coherent network.

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

    def generate_argumentation_commentary(
        self,
        arguments_summary: str,
        round_num: int,
        user_feedback: str = None
    ) -> str:
        """
        Generate commentary on the argumentation round, incorporating user feedback.
        
        Args:
            arguments_summary: Summary of worker arguments.
            round_num: Current round number.
            user_feedback: Optional user feedback to incorporate.
        
        Returns:
            Commentary text.
        """
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
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=200,
            temperature=0.6
        )
        self._track_tokens(result)
        
        # Add response to context
        self._add_to_context("assistant", result.text)
        
        self._history.append({
            "stage": "commentary",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return result.text
    
    def extract_user_axioms(
        self,
        feedback_history: List[Dict[str, str]],
        context: str
    ) -> Dict[str, Any]:
        """
        Extract implicit axioms from user feedback.
        
        Args:
            feedback_history: List of user feedback entries.
            context: The discussion context.
        
        Returns:
            Dict with extracted axioms and priorities.
        """
        feedback_text = "\n\n".join(
            f"Round {f.get('round', '?')}: {f.get('feedback', f)}"
            for f in feedback_history
        ) if feedback_history else "No feedback yet"
        
        full_prompt = self.EXTRACT_USER_AXIOMS_PROMPT.format(
            feedback_history=feedback_text,
            context=context
        )
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.4,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
        self._add_to_context("assistant", result.text)
        
        try:
            data = json.loads(result.text)
        except json.JSONDecodeError:
            data = {
                "axioms": [],
                "user_priorities": result.text
            }
        
        data["raw_text"] = result.text
        
        self._history.append({
            "stage": "extract_user_axioms",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return data
    
    def check_compatibility(
        self,
        proposals: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Check if worker proposals are compatible for collaboration.
        
        Args:
            proposals: Dict mapping worker_id to proposal.
        
        Returns:
            Compatibility analysis.
        """
        proposals_text = "\n\n".join(
            f"=== {worker_id} ===\n{proposal.get('summary', proposal)}"
            for worker_id, proposal in proposals.items()
        )
        
        full_prompt = self.COMPATIBILITY_CHECK_PROMPT.format(proposals=proposals_text)
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.3,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
        self._add_to_context("assistant", result.text)
        
        try:
            data = json.loads(result.text)
        except json.JSONDecodeError:
            data = {
                "compatibility": "unknown",
                "raw_text": result.text
            }
        
        self._history.append({
            "stage": "compatibility_check",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return data
    
    def analyze_axiom_network(
        self,
        user_axioms: List[Dict],
        worker_axioms: Dict[str, List[Dict]],
        discussion_summary: str
    ) -> Dict[str, Any]:
        """
        Build a coherent axiom network from all sources.
        
        Args:
            user_axioms: Axioms extracted from user feedback.
            worker_axioms: Dict mapping worker_id to their axioms.
            discussion_summary: Summary of the full discussion.
        
        Returns:
            Full axiom network analysis.
        """
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
        
        # Add to context and use accumulated messages
        self._add_to_context("user", full_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=600,  # Larger for complex analysis
            temperature=0.4,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
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
        
        self._history.append({
            "stage": "axiom_network",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return data
    
    def get_state(self) -> Dict[str, Any]:
        """Get current synthesizer state for serialization."""
        return {
            "questions": self.questions.to_dict() if self.questions else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "scores": {k: v.to_dict() for k, v in self.scores.items()},
            "final_output": self.final_output
        }
