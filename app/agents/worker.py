"""
AI Council - Worker Agent
Fast agents that generate diverse candidate solutions with persona support.
"""

import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

from ..models.runtime import OllamaRuntime, GenerationResult
from ..personas.manager import Persona


@dataclass
class WorkerDraft:
    """Structured output from a worker draft."""
    summary: str
    key_assumptions: list
    strengths: list
    risks: list
    confidence: float
    raw_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_json(cls, text: str) -> "WorkerDraft":
        """Parse structured JSON output."""
        try:
            data = json.loads(text)
            return cls(
                summary=data.get("summary", ""),
                key_assumptions=data.get("key_assumptions", []),
                strengths=data.get("strengths", []),
                risks=data.get("risks", []),
                confidence=float(data.get("confidence", 0.5)),
                raw_text=text
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            # Fallback: treat as unstructured text
            return cls(
                summary=text[:1500],
                key_assumptions=[],
                strengths=[],
                risks=[],
                confidence=0.5,
                raw_text=text
            )


@dataclass
class WorkerRefinement:
    """Structured output from a worker refinement."""
    answers_to_questions: Dict[str, str]
    patch_notes: list
    new_risks: list
    new_tradeoffs: list
    updated_summary: Optional[str] = None
    raw_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, text: str) -> "WorkerRefinement":
        """Parse structured JSON output from refinement."""
        try:
            data = json.loads(text)
            return cls(
                answers_to_questions=data.get("answers_to_questions", {}),
                patch_notes=data.get("patch_notes", []),
                new_risks=data.get("new_risks", []),
                new_tradeoffs=data.get("new_tradeoffs", []),
                updated_summary=data.get("updated_summary"),
                raw_text=text
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return cls(
                answers_to_questions={},
                patch_notes=[],
                new_risks=[],
                new_tradeoffs=[],
                updated_summary=None,
                raw_text=text
            )


@dataclass
class WorkerArgument:
    """Worker's argument for why their proposal is best."""
    main_argument: str
    key_strengths: list
    critique_of_alternatives: str
    rubric_alignment: str
    raw_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Worker:
    """
    A persona-driven worker agent that generates candidate solutions.
    
    Workers are fast agents (small models) that explore different
    thinking styles and perspectives on the user's problem.
    """
    
    DRAFT_PROMPT = """You are tasked with providing a thoughtful response to the following prompt.

USER PROMPT:
{prompt}

{constraints}

Provide your response in the following JSON format:
{{
    "summary": "Your main proposal/answer (max 150 words)",
    "key_assumptions": ["assumption 1", "assumption 2", ...],
    "strengths": ["strength 1", "strength 2", ...],
    "risks": ["risk 1", "risk 2", ...],
    "confidence": 0.0 to 1.0
}}

Be concise and structured. Focus on your unique perspective."""

    REFINEMENT_PROMPT = """Review your previous work and answer the synthesizer's questions with ONLY deltas.

{conversation_history}

CURRENT PROPOSAL:
{previous_summary}

NEW QUESTIONS TO ADDRESS:
{questions}
{user_guidance}
Build on your previous thinking. Evolve your proposal - don't start from scratch. Reference insights from earlier rounds.

Respond in JSON format (delta-only):
{{
    "answers_to_questions": {{"question": "direct answer building on previous insights", ...}},
    "patch_notes": ["Concrete change 1 and why", "Concrete change 2 and why"],
    "new_risks": ["New risk introduced by changes (if any)"],
    "new_tradeoffs": ["New tradeoff introduced by changes (if any)"]
}}

Do NOT rewrite the full proposal. Be specific about what changed and why. Show continuity of thought across rounds."""

    ARGUMENT_PROMPT = """Make your case for why your proposal is the best solution.

YOUR PROPOSAL:
{proposal}

OTHER PROPOSALS (summarized):
{alternatives}

{rubric}

Argue why your proposal should be selected. Be specific and reference the evaluation criteria.

Respond in JSON format:
{{
    "main_argument": "Your core argument (2-3 sentences)",
    "key_strengths": ["strength 1", "strength 2", ...],
    "critique_of_alternatives": "Brief critique of other proposals",
    "rubric_alignment": "How your proposal aligns with evaluation criteria"
}}"""

    COUNTER_ARGUMENT_PROMPT = """Continue the argumentation. Other workers have presented their arguments.

YOUR PROPOSAL:
{proposal}

OTHER PROPOSALS (summarized):
{alternatives}

PREVIOUS ARGUMENTS FROM OTHER WORKERS:
{counter_arguments}
{user_guidance}
{rubric}

Respond to the other workers' arguments. Address their criticisms, counter their points, and reinforce why your proposal is superior. Be respectful but firm.

Respond in JSON format:
{{
    "main_argument": "Your counter-argument (2-3 sentences addressing their points)",
    "key_strengths": ["strength 1", "strength 2", ...],
    "critique_of_alternatives": "Response to their arguments and critiques",
    "rubric_alignment": "How your proposal still aligns best with evaluation criteria",
    "user_feedback_addressed": "How you addressed the user's feedback (if any)"
}}"""

    DIVERSIFY_PROMPT = """You are part of a council of workers. Here are the other workers' proposals:

OTHER WORKERS' PROPOSALS:
{other_proposals}

YOUR CURRENT PROPOSAL:
{your_proposal}

Your task: Differentiate your approach. Look for gaps, alternative perspectives, or unique angles that others haven't explored. Don't just repeat what others said - find your own unique contribution.

Respond in JSON format:
{{
    "summary": "Your revised/differentiated proposal (max 150 words)",
    "key_assumptions": ["assumption 1", "assumption 2", ...],
    "strengths": ["strength 1", "strength 2", ...],
    "risks": ["risk 1", "risk 2", ...],
    "confidence": 0.0 to 1.0,
    "differentiation": "How your approach differs from others (1-2 sentences)"
}}

Be creative and explore a different angle!"""

    AXIOM_PROMPT = """After all debate and refinement, reflect on the AXIOMS underlying your final position.

YOUR FINAL PROPOSAL:
{proposal}

YOUR PERSONA: {persona_info}

CONVERSATION SUMMARY:
{conversation_summary}

Identify the AXIOMS - the fundamental assumptions and principles that underpin your proposal. Every statement approximates truth but never IS truth. Be rigorous about what you're assuming.

Respond in JSON format:
{{
    "axioms": [
        {{
            "statement": "The axiom text - a fundamental principle or assumption",
            "axiom_type": "core|derived|assumption|parameter",
            "confidence": 0.0 to 1.0,
            "depends_on": ["Brief description of other axioms this builds on"],
            "enables": ["What conclusions this axiom enables"],
            "vulnerability": "What would invalidate this axiom",
            "evidence": "Supporting evidence from the discussion",
            "potential_biases": ["Biases that might affect this axiom"]
        }}
    ],
    "theory_contribution": "How your axioms contribute to building a general theory"
}}

Be honest about your assumptions and their limitations. Tag each with your confidence."""

    COLLABORATION_PROMPT = """[COLLABORATION PHASE]

Your refined proposal and the full discussion history are in the context above.

COMPATIBLE PROPOSALS FROM OTHER WORKERS:
{compatible_proposals}

AREAS OF OVERLAP:
{overlap_areas}

MERGE STRATEGY: {merge_strategy}
{user_guidance}

The synthesizer identified compatibility. Now ACTIVELY COLLABORATE - don't just restate the same merged text.

Think critically:
- What specific mechanisms from others can strengthen YOUR proposal?
- What trade-offs need resolution?
- What NEW insights emerge from combining approaches?
- How do you resolve remaining tensions?

Respond in JSON. Required keys (include them even if empty):
- collaborative_summary (string)
- specific_improvements (array)
- integrated_mechanisms (object mapping worker -> mechanism)
- resolved_tensions (array)
- new_insights (array)
- confidence (number 0.0 to 1.0)

Respond in JSON:
{{
    "collaborative_summary": "Your EVOLVED proposal with specific improvements from collaboration (be concrete!)",
    "specific_improvements": ["Specific change 1 with reasoning", "Specific change 2"],
    "integrated_mechanisms": {{"from_worker_X": "Concrete mechanism/idea integrated"}},
    "resolved_tensions": ["How we resolved conflict/trade-off X"],
    "new_insights": ["Insight 1 that emerged from collaboration"],
    "confidence": 0.0 to 1.0
}}

Be specific and concrete. Show real collaboration, not just agreement."""

    def __init__(
        self,
        worker_id: str,
        runtime: OllamaRuntime,
        model: str,
        max_tokens: int = 300,
        persona: Optional[Persona] = None
    ):
        """
        Initialize a worker agent.
        
        Args:
            worker_id: Unique identifier for this worker.
            runtime: Ollama runtime instance.
            model: Model name to use.
            max_tokens: Maximum output tokens.
            persona: Optional persona to apply.
        """
        self.worker_id = worker_id
        self.runtime = runtime
        self.model = model
        self.max_tokens = max_tokens
        self.persona = persona
        
        # State
        self.current_draft: Optional[WorkerDraft] = None
        self.refinements: list = []
        self.argument: Optional[WorkerArgument] = None
        self._history: list = []
        
        # Context management - accumulated messages for this worker
        self._context_messages: List[Dict[str, str]] = []
        self._context_limit: int = 4096  # Will be set from config
        
        # Token tracking
        self._last_token_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "context_used": 0
        }
        self._total_tokens: int = 0
        self._cumulative_context: int = 0  # Running total of context used
    
    def set_context_limit(self, limit: int) -> None:
        """Set the context window limit for this worker."""
        self._context_limit = limit
    
    def get_last_token_usage(self) -> Dict[str, int]:
        """Get token usage from the last operation."""
        return self._last_token_usage.copy()
    
    def _add_to_context(self, role: str, content: str) -> None:
        """Add a message to the worker's accumulated context."""
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
        
        # Update cumulative context (this is the actual context size being used)
        self._cumulative_context = prompt_tokens + output_tokens
        
        self._last_token_usage = {
            "input_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total,
            "context_used": self._cumulative_context,
            "context_limit": self._context_limit
        }
        self._total_tokens += self._last_token_usage.get("total_tokens", 0)
    
    @property
    def system_prompt(self) -> str:
        """Get the system prompt for this worker."""
        if self.persona:
            return self.persona.system_prompt
        return "You are a helpful assistant that provides thoughtful, structured responses."
    
    @property
    def display_id(self) -> str:
        """Get display ID combining persona name and worker ID."""
        if self.persona and self.persona.name:
            return f"{self.persona.name} ({self.worker_id})"
        return self.worker_id
    
    def set_persona(self, persona: Persona):
        """Set or update the worker's persona."""
        self.persona = persona
    
    def clear_state(self):
        """Clear all state for this worker (for persona swap restart)."""
        self.current_draft = None
        self.refinements = []
        self.argument = None
        self._history = []
    
    def generate_draft(
        self,
        prompt: str,
        constraints: Optional[str] = None
    ) -> WorkerDraft:
        """
        Generate initial draft proposal.
        
        Args:
            prompt: User's prompt.
            constraints: Optional constraints or rubric.
        
        Returns:
            WorkerDraft with structured response.
        """
        constraints_text = f"\nCONSTRAINTS/CRITERIA:\n{constraints}" if constraints else ""
        
        full_prompt = self.DRAFT_PROMPT.format(
            prompt=prompt,
            constraints=constraints_text
        )
        
        # Clear context and start fresh for this session
        self._context_messages = []
        
        # Add the draft prompt to context
        self._add_to_context("user", full_prompt)
        
        # Use chat with accumulated context
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.7,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add assistant response to context for continuity
        self._add_to_context("assistant", result.text)
        
        draft = WorkerDraft.from_json(result.text)
        self.current_draft = draft
        self._history.append({
            "stage": "draft",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return draft
    
    def _build_conversation_history(self) -> str:
        """Build a summary of conversation history from previous rounds."""
        if not self.refinements:
            return "CONVERSATION HISTORY:\n(This is your first refinement round)"
        
        history_parts = ["CONVERSATION HISTORY:"]
        
        # Add original draft summary
        if self.current_draft:
            history_parts.append(f"\n=== ROUND 1 (Initial Draft) ===")
            history_parts.append(f"Key assumptions: {', '.join(self.current_draft.key_assumptions[:3])}" if self.current_draft.key_assumptions else "")
        
        # Add each refinement round
        for i, ref in enumerate(self.refinements, start=2):
            history_parts.append(f"\n=== ROUND {i} ===")
            if ref.patch_notes:
                history_parts.append(f"Patch notes: {'; '.join(ref.patch_notes[:3])}")
            if ref.answers_to_questions:
                answers = list(ref.answers_to_questions.items())[:2]
                for q, a in answers:
                    history_parts.append(f"Q: {q[:50]}... A: {a[:100]}...")
        
        return "\n".join(history_parts)
    
    def refine(
        self,
        questions: list,
        user_guidance: str = None
    ) -> WorkerRefinement:
        """
        Refine proposal based on synthesizer questions and user feedback.
        Context accumulates: each refinement builds on the full conversation.
        
        Args:
            questions: List of questions to address.
            user_guidance: Optional direct feedback from the user to incorporate.
        
        Returns:
            WorkerRefinement with updates.
        """
        if not self.current_draft:
            raise ValueError("No draft to refine. Call generate_draft first.")
        
        questions_text = "\n".join(f"- {q}" for q in questions)
        
        # Build the refinement prompt - explicitly include current draft
        guidance_section = ""
        if user_guidance:
            guidance_section = f"\n\nUSER FEEDBACK (address this directly):\n{user_guidance}"
        
        # Get current proposal summary (from draft or latest refinement)
        current_proposal = self.current_draft.summary if self.current_draft else "No previous proposal"
        
        # Build conversation history summary
        conversation_history = self._build_conversation_history()
        
        round_num = len(self.refinements) + 1
        refine_prompt = f"""[REFINEMENT ROUND {round_num}]

{conversation_history}

YOUR CURRENT PROPOSAL:
{current_proposal}

SYNTHESIZER QUESTIONS TO ADDRESS:
{questions_text}
{guidance_section}

Build on your previous proposal above. Address these questions and evolve your proposal - don't start from scratch. Reference your original assumptions and previous insights.

Respond in JSON:
{{
    "answers_to_questions": {{"question": "direct answer building on previous insights", ...}},
    "patch_notes": ["Concrete change 1 and why", "Concrete change 2 and why"],
    "new_risks": ["New risk introduced by changes (if any)"],
    "new_tradeoffs": ["New tradeoff introduced by changes (if any)"]
}}"""
        
        # Add questions to context (this maintains conversation history)
        self._add_to_context("user", refine_prompt)
        
        # Use chat with accumulated context
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.5,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context for next round
        self._add_to_context("assistant", result.text)
        
        refinement = WorkerRefinement.from_json(result.text)
        
        self.refinements.append(refinement)
        
        self._history.append({
            "stage": "refinement",
            "input": refine_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return refinement
    
    def inject_shared_context(self, shared_context: str) -> None:
        """Inject shared context from other workers (for argumentation/collaboration)."""
        if shared_context:
            self._add_to_context("user", f"[SHARED CONTEXT FROM OTHER WORKERS]\n{shared_context}\n[END SHARED CONTEXT]")
    
    def argue(
        self,
        alternatives: list,
        rubric: Optional[str] = None,
        counter_arguments: Optional[list] = None,
        user_guidance: str = None,
        shared_context: Optional[str] = None
    ) -> WorkerArgument:
        """
        Argue why this worker's proposal is best.
        Context is shared during argumentation - workers see each other's positions.
        
        Args:
            alternatives: Summaries of other workers' proposals.
            rubric: Optional evaluation rubric.
            counter_arguments: Optional list of previous arguments to respond to.
            user_guidance: Optional direct feedback from the user to incorporate.
            shared_context: Optional shared context from other workers.
        
        Returns:
            WorkerArgument with the case.
        """
        if not self.current_draft:
            raise ValueError("No draft to argue for. Call generate_draft first.")
        
        # Inject shared context if provided (marks transition to shared phase)
        if shared_context:
            self.inject_shared_context(shared_context)
        
        alternatives_text = "\n".join(f"- {alt}" for alt in alternatives)
        rubric_text = f"\nEVALUATION RUBRIC:\n{rubric}" if rubric else ""
        
        # Build user guidance section if provided
        guidance_section = ""
        if user_guidance:
            guidance_section = f"\n\nUSER GUIDANCE:\n{user_guidance}"
        
        # Build argument prompt
        if counter_arguments:
            counter_args_text = "\n\n".join(
                f"**{arg.get('worker', 'Worker')}**: {arg.get('argument', '')}"
                for arg in counter_arguments
            )
            argue_prompt = f"""[ARGUMENTATION PHASE]

Your refined proposal is in the context above. Now argue for it.

OTHER PROPOSALS:
{alternatives_text}

PREVIOUS ARGUMENTS TO RESPOND TO:
{counter_args_text}
{guidance_section}
{rubric_text}

Make your case. Respond in JSON:
{{
    "main_argument": "Your counter-argument (2-3 sentences)",
    "key_strengths": ["strength 1", "strength 2"],
    "critique_of_alternatives": "Brief critique",
    "rubric_alignment": "How you align with criteria"
}}"""
        else:
            argue_prompt = f"""[ARGUMENTATION PHASE]

Your refined proposal is in the context above. Now argue for it.

OTHER PROPOSALS:
{alternatives_text}
{guidance_section}
{rubric_text}

Make your case for why your proposal should be selected.

Respond in JSON:
{{
    "main_argument": "Your core argument (2-3 sentences)",
    "key_strengths": ["strength 1", "strength 2"],
    "critique_of_alternatives": "Brief critique of other proposals",
    "rubric_alignment": "How your proposal aligns with criteria"
}}"""
        
        # Add to context
        self._add_to_context("user", argue_prompt)
        
        # Use chat with accumulated context
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.6,
            format_json=True
        )
        self._track_tokens(result)
        
        # Add response to context
        self._add_to_context("assistant", result.text)
        
        try:
            data = json.loads(result.text)
            argument = WorkerArgument(
                main_argument=data.get("main_argument", ""),
                key_strengths=data.get("key_strengths", []),
                critique_of_alternatives=data.get("critique_of_alternatives", ""),
                rubric_alignment=data.get("rubric_alignment", ""),
                raw_text=result.text
            )
        except (json.JSONDecodeError, KeyError):
            argument = WorkerArgument(
                main_argument=result.text,
                key_strengths=[],
                critique_of_alternatives="",
                rubric_alignment="",
                raw_text=result.text
            )
        
        self.argument = argument
        self._history.append({
            "stage": "argument",
            "input": argue_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return argument
    
    def diversify(
        self,
        other_proposals: list
    ) -> WorkerDraft:
        """
        Diversify approach based on seeing other workers' proposals.
        
        Args:
            other_proposals: List of dicts with 'worker_id' and 'summary'.
        
        Returns:
            WorkerDraft with differentiated approach.
        """
        if not self.current_draft:
            raise ValueError("No draft to diversify. Call generate_draft first.")
        
        other_text = "\n".join(
            f"- {p.get('worker_id', 'Worker')}: {p.get('summary', '')}"
            for p in other_proposals
        )
        
        diversify_prompt = f"""[DIVERSIFICATION PHASE]

OTHER WORKERS' PROPOSALS:
{other_text}

Your current proposal is in the context above. Differentiate your approach.

Respond in JSON:
{{
    "summary": "Your differentiated proposal",
    "key_assumptions": ["assumption 1", "assumption 2"],
    "strengths": ["unique strength 1", "unique strength 2"],
    "risks": ["risk 1", "risk 2"],
    "confidence": 0.0 to 1.0
}}"""
        
        self._add_to_context("user", diversify_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.8,
            format_json=True
        )
        self._track_tokens(result)
        
        self._add_to_context("assistant", result.text)
        
        draft = WorkerDraft.from_json(result.text)
        self.current_draft = draft
        self._history.append({
            "stage": "diversify",
            "input": diversify_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return draft
    
    def collaborate(
        self,
        compatible_proposals: List[Dict[str, Any]],
        overlap_areas: List[str],
        merge_strategy: str,
        user_guidance: str = None
    ) -> Dict[str, Any]:
        """
        Collaborate with compatible workers to build a unified approach.
        Context is fully shared during collaboration.
        
        Args:
            compatible_proposals: List of dicts with worker_id and proposal from compatible workers.
            overlap_areas: Areas of overlap identified by synthesizer.
            merge_strategy: Suggested merge strategy.
            user_guidance: Optional user feedback to incorporate.
        
        Returns:
            Dict with collaborative output.
        """
        if not self.current_draft:
            raise ValueError("No draft to collaborate on. Call generate_draft first.")
        
        proposals_text = "\n\n".join(
            f"=== {p.get('worker_id', 'Worker')} ===\n{p.get('summary', p)}"
            for p in compatible_proposals
        )
        
        overlap_text = "\n".join(f"- {area}" for area in overlap_areas) if overlap_areas else "General compatibility"
        
        guidance_section = ""
        if user_guidance:
            guidance_section = f"\n\nUSER FEEDBACK: {user_guidance}"
        
        collab_prompt = self.COLLABORATION_PROMPT.format(
            compatible_proposals=proposals_text,
            overlap_areas=overlap_text,
            merge_strategy=merge_strategy or "Find common ground and build together",
            user_guidance=guidance_section
        )
        
        self._add_to_context("user", collab_prompt)
        
        result = self.runtime.chat(
            model=self.model,
            messages=self._get_context_for_call(),
            max_tokens=self.max_tokens,
            temperature=0.5,
            format_json=True
        )
        self._track_tokens(result)
        
        self._add_to_context("assistant", result.text)
        
        defaults = {
            "collaborative_summary": "",
            "specific_improvements": [],
            "integrated_mechanisms": {},
            "resolved_tensions": [],
            "new_insights": [],
            "confidence": 0.5
        }

        try:
            data = json.loads(result.text)
        except json.JSONDecodeError:
            data = defaults.copy()
            data["collaborative_summary"] = result.text

        normalized = defaults.copy()
        if isinstance(data, dict):
            normalized.update(data)

        if not isinstance(normalized.get("specific_improvements"), list):
            normalized["specific_improvements"] = [str(normalized.get("specific_improvements"))] if normalized.get("specific_improvements") else []
        if not isinstance(normalized.get("resolved_tensions"), list):
            normalized["resolved_tensions"] = [str(normalized.get("resolved_tensions"))] if normalized.get("resolved_tensions") else []
        if not isinstance(normalized.get("new_insights"), list):
            normalized["new_insights"] = [str(normalized.get("new_insights"))] if normalized.get("new_insights") else []
        if not isinstance(normalized.get("integrated_mechanisms"), dict):
            normalized["integrated_mechanisms"] = {}

        try:
            normalized["confidence"] = float(normalized.get("confidence", defaults["confidence"]))
        except (TypeError, ValueError):
            normalized["confidence"] = defaults["confidence"]

        normalized["raw_text"] = result.text
        
        self._history.append({
            "stage": "collaboration",
            "input": collab_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return normalized
    
    def analyze_axioms(
        self,
        conversation_summary: str
    ) -> Dict[str, Any]:
        """
        Analyze the axioms underlying this worker's final proposal.
        
        Args:
            conversation_summary: Summary of the full discussion.
        
        Returns:
            Dict with axioms and theory contribution.
        """
        if not self.current_draft:
            raise ValueError("No draft to analyze. Call generate_draft first.")
        
        persona_info = f"{self.persona.name} ({self.persona.reasoning_style}, {self.persona.tone})" if self.persona else "Default worker persona"
        
        full_prompt = self.AXIOM_PROMPT.format(
            proposal=self.current_draft.summary,
            persona_info=persona_info,
            conversation_summary=conversation_summary
        )
        
        result = self.runtime.generate(
            model=self.model,
            prompt=full_prompt,
            system=self.system_prompt,
            max_tokens=self.max_tokens,
            temperature=0.4,  # Lower temperature for analytical thinking
            format_json=True
        )
        self._track_tokens(result)
        
        try:
            data = json.loads(result.text)
            
            # Handle nested JSON - sometimes the model puts JSON inside a string field
            # This often happens with escaped JSON strings (e.g., "{\\n    \"axioms\": ...")
            if isinstance(data.get("theory_contribution"), str):
                theory_str = data["theory_contribution"].strip()
                if theory_str.startswith("{") or theory_str.startswith('"') and theory_str.startswith('"{'):
                    try:
                        # Try parsing directly
                        nested = json.loads(theory_str)
                        # If the nested JSON has axioms, use those
                        if nested.get("axioms") and (not data.get("axioms") or len(data.get("axioms", [])) == 0):
                            data["axioms"] = nested["axioms"]
                        if nested.get("theory_contribution") and isinstance(nested.get("theory_contribution"), str):
                            data["theory_contribution"] = nested["theory_contribution"]
                    except json.JSONDecodeError:
                        # Try unescaping first (handle \\n -> \n)
                        try:
                            import codecs
                            unescaped = codecs.decode(theory_str, 'unicode_escape')
                            nested = json.loads(unescaped)
                            if nested.get("axioms") and (not data.get("axioms") or len(data.get("axioms", [])) == 0):
                                data["axioms"] = nested["axioms"]
                            if nested.get("theory_contribution") and isinstance(nested.get("theory_contribution"), str):
                                data["theory_contribution"] = nested["theory_contribution"]
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            # Try regex extraction as last resort
                            import re
                            json_match = re.search(r'\{[\s\S]*?"axioms"[\s\S]*?\}', theory_str)
                            if json_match:
                                try:
                                    parsed = json.loads(json_match.group())
                                    if parsed.get("axioms") and (not data.get("axioms") or len(data.get("axioms", [])) == 0):
                                        data["axioms"] = parsed["axioms"]
                                except json.JSONDecodeError:
                                    pass
                    
            # Also check raw_text for axioms if axioms is still empty
            if not data.get("axioms") or len(data.get("axioms", [])) == 0:
                # Check if raw_text contains axioms (sometimes it's stored there)
                raw_text_str = str(result.text)
                if '"axioms"' in raw_text_str:
                    try:
                        # Try parsing the entire raw text
                        nested = json.loads(raw_text_str)
                        if nested.get("axioms"):
                            data["axioms"] = nested["axioms"]
                    except json.JSONDecodeError:
                        # Try regex extraction from raw text
                        import re
                        json_match = re.search(r'\{[\s\S]*?"axioms"[\s\S]*?\}', raw_text_str)
                        if json_match:
                            try:
                                parsed = json.loads(json_match.group())
                                if parsed.get("axioms"):
                                    data["axioms"] = parsed["axioms"]
                            except json.JSONDecodeError:
                                pass
                        
        except json.JSONDecodeError:
            # Try to extract axioms from raw text anyway
            data = {
                "axioms": [],
                "theory_contribution": result.text,
                "raw_text": result.text
            }
            
            # Try to find JSON in the raw text using regex
            import re
            json_match = re.search(r'\{[\s\S]*?"axioms"[\s\S]*?\}', result.text)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    if parsed.get("axioms"):
                        data["axioms"] = parsed["axioms"]
                    if parsed.get("theory_contribution"):
                        data["theory_contribution"] = parsed["theory_contribution"]
                except json.JSONDecodeError:
                    # Last resort: try unescaping and parsing
                    try:
                        import codecs
                        unescaped = codecs.decode(json_match.group(), 'unicode_escape')
                        parsed = json.loads(unescaped)
                        if parsed.get("axioms"):
                            data["axioms"] = parsed["axioms"]
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
        
        # Ensure raw_text is always set
        if "raw_text" not in data:
            data["raw_text"] = result.text
        
        self._history.append({
            "stage": "axiom_analysis",
            "input": full_prompt,
            "output": result.text,
            "tokens": result.tokens
        })
        
        return data
    
    def get_state(self) -> Dict[str, Any]:
        """Get current worker state for serialization."""
        return {
            "worker_id": self.worker_id,
            "persona_id": self.persona.id if self.persona else None,
            "persona_name": self.persona.name if self.persona else None,
            "display_id": self.display_id,
            "model": self.model,
            "current_draft": self.current_draft.to_dict() if self.current_draft else None,
            "refinements": [r.to_dict() for r in self.refinements],
            "argument": self.argument.to_dict() if self.argument else None
        }
