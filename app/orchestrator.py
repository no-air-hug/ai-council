"""
AI Council - Orchestrator
Coordinates the full multi-agent pipeline execution.
"""

import uuid
import difflib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator
from enum import Enum

from .config import AppConfig
from .models.runtime import OllamaRuntime
from .models.registry import ModelRegistry
from .models.global_context import GlobalContext
from .agents.worker import Worker, WorkerRefinement
from .agents.synthesizer import Synthesizer, SynthesizerQuestions
from .agents.architect import Architect
from .agents.engineer import Engineer
from .models.candidate import Candidate
from .personas.manager import PersonaManager
from .voting.voter import Voter
from .utils.memory import MemoryMonitor
from .utils.logging import SessionLogger


class PipelineStage(Enum):
    """Pipeline execution stages."""
    SETUP = "setup"
    WORKER_DRAFTS = "worker_drafts"
    SYNTH_QUESTIONS = "synth_questions"
    WORKER_REFINEMENT = "worker_refinement"
    AWAITING_ROUND_FEEDBACK = "awaiting_round_feedback"
    COMPATIBILITY_CHECK = "compatibility_check"
    COLLABORATION = "collaboration"
    AWAITING_COLLAB_FEEDBACK = "awaiting_collab_feedback"
    CANDIDATE_SYNTHESIS = "candidate_synthesis"
    ARGUMENTATION = "argumentation"
    AWAITING_ARGUMENT_FEEDBACK = "awaiting_argument_feedback"
    AI_VOTING = "ai_voting"
    USER_VOTING = "user_voting"
    AXIOM_ANALYSIS = "axiom_analysis"
    FINAL_OUTPUT = "final_output"
    AWAITING_FINAL_FEEDBACK = "awaiting_final_feedback"
    COMPLETE = "complete"


class Orchestrator:
    """
    Orchestrates the full AI Council pipeline.
    
    Pipeline stages:
    1. Setup - Initialize workers with personas
    2. Worker Drafts - Each worker generates initial proposal
    3. Synth Questions - Synthesizer generates clarifying questions
    4. Worker Refinement - Workers answer questions and refine
    5. Candidate Synthesis - Architect creates refined candidates
    6. Argumentation - Workers argue for their proposals
    7. AI Voting - Architect scores candidates
    8. User Voting - User votes and provides feedback
    9. Final Output - Engineer generates final response
    """
    
    def __init__(
        self, 
        base_path: Path, 
        config: AppConfig,
        worker_max_tokens: Optional[int] = None,
        synth_max_tokens: Optional[int] = None,
        worker_context_window: Optional[int] = None,
        synth_context_window: Optional[int] = None,
        architect_max_tokens: Optional[int] = None,
        engineer_max_tokens: Optional[int] = None,
        architect_context_window: Optional[int] = None,
        engineer_context_window: Optional[int] = None
    ):
        """
        Initialize orchestrator.
        
        Args:
            base_path: Base path for data storage.
            config: Application configuration.
            worker_max_tokens: Optional override for worker max tokens.
            synth_max_tokens: Optional override for synthesizer max tokens.
            worker_context_window: Optional override for worker context window (1K-32K).
            synth_context_window: Optional override for synthesizer context window (1K-32K).
        """
        self.base_path = Path(base_path)
        self.config = config
        
        # Store token and context overrides (UI settings override config)
        self.worker_max_tokens = worker_max_tokens or config.mode_config.workers.max_output_tokens
        self.synth_max_tokens = synth_max_tokens or config.mode_config.synthesizer.max_output_tokens
        self.worker_context_window = worker_context_window or config.mode_config.workers.context_window
        self.synth_context_window = synth_context_window or config.mode_config.synthesizer.context_window
        self.architect_max_tokens = architect_max_tokens or config.mode_config.architect.max_output_tokens
        self.engineer_max_tokens = engineer_max_tokens or config.mode_config.engineer.max_output_tokens
        self.architect_context_window = architect_context_window or config.mode_config.architect.context_window
        self.engineer_context_window = engineer_context_window or config.mode_config.engineer.context_window
        
        # Initialize components
        self.runtime = OllamaRuntime(config.ollama)
        self.registry = ModelRegistry(config)
        self.persona_manager = PersonaManager(base_path)
        self.persona_manager.set_default_personas(config.default_personas)
        self.memory_monitor = MemoryMonitor(
            config.mode_config.memory.max_ram_usage_percent
        )
        
        # Session state
        self.session_id: Optional[str] = None
        self.prompt: Optional[str] = None
        self.constraints: Optional[str] = None
        self.rubric: Optional[str] = None
        self.debate_rounds: int = 2  # Configurable debate rounds
        self.argument_rounds: int = 1  # Configurable argumentation rounds
        self.collaboration_rounds: int = 1  # Configurable collaboration rounds
        self.axiom_rounds: int = 1  # Configurable axiom analysis rounds
        self.refinement_similarity_threshold: float = getattr(
            self.config.mode_config.pipeline, "refinement_similarity_threshold", 0.92
        )
        
        # Agents
        self.workers: Dict[str, Worker] = {}
        self.synthesizer: Optional[Synthesizer] = None
        self.architect: Optional[Architect] = None
        self.engineer: Optional[Engineer] = None
        self.voter: Optional[Voter] = None
        
        # Logger
        self.logger: Optional[SessionLogger] = None
        
        # State tracking
        self.current_stage = PipelineStage.SETUP
        self._stage_outputs: Dict[str, Any] = {}
        self._archived_outputs: Dict[str, List[Dict]] = {}  # For persona swaps
        
        # Round feedback tracking
        self._current_round: int = 0
        self._round_feedback: Dict[int, Dict[str, Any]] = {}  # round_num -> feedback
        self._awaiting_round_feedback: bool = False
        self._skip_to_synthesis: bool = False
        
        # Argumentation round tracking
        self._current_arg_round: int = 0
        self._arg_round_feedback: Dict[int, Dict[str, Any]] = {}
        self._awaiting_argument_feedback: bool = False
        self._skip_to_voting: bool = False
        
        # Collaboration tracking
        self._current_collab_round: int = 0
        self._collab_feedback: Dict[int, Dict[str, Any]] = {}
        self._awaiting_collab_feedback: bool = False
        self._compatibility_result: Dict[str, Any] = {}
        
        # Axiom collection
        self._user_feedback_history: List[Dict[str, str]] = []
        self._user_axioms: List[Dict] = []
        self._worker_axioms: Dict[str, List[Dict]] = {}
        self._axiom_network: Optional[Dict[str, Any]] = None
        
        # Final output feedback
        self._awaiting_final_feedback: bool = False
        self._final_output_feedback: str = ""

        self._candidates: List[Candidate] = []

        # Global context tracking
        self.global_context: Optional[GlobalContext] = None
        self._last_global_snapshot: Optional[Dict[str, Any]] = None
    
    def create_session(
        self,
        prompt: str,
        persona_assignments: Dict[str, str] = None,
        constraints: str = None,
        rubric: str = None,
        debate_rounds: int = None,
        argument_rounds: int = None,
        collaboration_rounds: int = None,
        axiom_rounds: int = None,
        worker_count: int = None
    ) -> str:
        """
        Create a new council session.
        
        Args:
            prompt: User's prompt.
            persona_assignments: Optional dict mapping worker_id to persona_id.
            constraints: Optional constraints.
            rubric: Optional evaluation rubric.
            debate_rounds: Optional number of refinement loops (default from config).
            argument_rounds: Optional number of argumentation rounds (default from config).
            collaboration_rounds: Optional number of collaboration rounds (default from config).
            axiom_rounds: Optional number of axiom analysis rounds (default from config).
            worker_count: Optional number of workers (UI override, default from config).
        
        Returns:
            Session ID.
        """
        self.session_id = str(uuid.uuid4())
        self.prompt = prompt
        self.constraints = constraints
        self.rubric = rubric
        self.debate_rounds = debate_rounds or self.config.mode_config.pipeline.refinement_loops
        self.argument_rounds = argument_rounds or getattr(self.config.mode_config.pipeline, 'argumentation_rounds', 1)
        self.collaboration_rounds = collaboration_rounds or getattr(self.config.mode_config.pipeline, 'collaboration_rounds', 1)
        self.axiom_rounds = axiom_rounds or getattr(self.config.mode_config.pipeline, 'axiom_rounds', 1)
        self.refinement_similarity_threshold = getattr(
            self.config.mode_config.pipeline, "refinement_similarity_threshold", 0.92
        )
        
        # Initialize logger
        self.logger = SessionLogger(
            self.config.sessions_dir,
            self.session_id,
            self.config.mode.value
        )
        
        # Initialize workers (UI override takes precedence)
        worker_count = worker_count or self.config.mode_config.workers.count
        worker_model = self.registry.get_worker_model()
        
        persona_assignments = persona_assignments or {}
        all_personas = self.persona_manager.get_all_personas()
        default_persona_ids = [p["id"] for p in all_personas[:worker_count]]
        
        for i in range(worker_count):
            worker_id = f"worker_{i + 1}"
            persona_id = persona_assignments.get(worker_id, default_persona_ids[i] if i < len(default_persona_ids) else None)
            persona = self.persona_manager.get_persona(persona_id) if persona_id else None
            
            worker = Worker(
                worker_id=worker_id,
                runtime=self.runtime,
                model=worker_model.name,
                max_tokens=self.worker_max_tokens,  # Use override or config
                persona=persona
            )
            worker.set_context_limit(self.worker_context_window)  # Set context limit
            self.workers[worker_id] = worker
        
        # Initialize synthesizer with UI config values
        synth_model = self.registry.get_synthesizer_model()
        self.synthesizer = Synthesizer(
            runtime=self.runtime,
            model=synth_model.name,
            max_tokens=self.synth_max_tokens,  # From UI config
            context_window=self.synth_context_window  # From UI config
        )

        # Initialize architect with UI config values
        architect_model = self.registry.get_architect_model()
        self.architect = Architect(
            runtime=self.runtime,
            model=architect_model.name,
            max_tokens=self.architect_max_tokens,
            context_window=self.architect_context_window
        )

        # Initialize engineer with UI config values
        engineer_model = self.registry.get_engineer_model()
        self.engineer = Engineer(
            runtime=self.runtime,
            model=engineer_model.name,
            max_tokens=self.engineer_max_tokens,
            context_window=self.engineer_context_window
        )
        
        # Initialize voter
        self.voter = Voter(ai_weight=0.4, user_weight=0.6)
        
        self.current_stage = PipelineStage.SETUP

        self.global_context = GlobalContext(
            session_id=self.session_id,
            prompt=self.prompt
        )
        self._last_global_snapshot = self.global_context.to_dict()
        
        return self.session_id
    
    def run_pipeline(self) -> Generator[Dict[str, Any], None, None]:
        """
        Run the full pipeline with SSE events.
        
        Yields:
            Event dicts with stage progress and outputs.
        """
        if not self.session_id:
            raise ValueError("No active session. Call create_session first.")
        
        # Stage 1: Worker Drafts
        self.current_stage = PipelineStage.WORKER_DRAFTS
        yield {"type": "stage_start", "stage": "worker_drafts"}
        
        drafts = {}
        for worker_id, worker in self.workers.items():
            yield {"type": "worker_start", "worker_id": worker_id, "persona": worker.persona.name if worker.persona else "Default"}
            
            # Check memory before each worker
            if self.memory_monitor.should_unload_model():
                yield {"type": "memory_warning", "message": "High memory usage detected"}
            
            draft = worker.generate_draft(self.prompt, self.constraints)
            drafts[worker_id] = draft.to_dict()
            
            # Log
            self.logger.log(
                stage="worker_draft",
                agent_id=worker_id,
                input_text=self.prompt,
                output_text=draft.summary,
                persona_id=worker.persona.id if worker.persona else None,
                persona_name=worker.persona.name if worker.persona else None,
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )
            
            yield {
                "type": "worker_complete",
                "worker_id": worker_id,
                "draft": draft.to_dict(),
                "tokens": worker.get_last_token_usage(),
                "context_patch": self._emit_context_patch()
            }
        
        self._stage_outputs["drafts"] = drafts
        draft_payload = {
            "prompt": self.prompt,
            "constraints": self.constraints,
            "drafts": [
                {
                    "worker_id": worker_id,
                    "display_id": self.workers[worker_id].display_id,
                    "persona_id": self.workers[worker_id].persona.id if self.workers[worker_id].persona else None,
                    "persona_name": self.workers[worker_id].persona.name if self.workers[worker_id].persona else None,
                    "draft": draft
                }
                for worker_id, draft in drafts.items()
            ]
        }
        self._apply_architect_update("worker_drafts", draft_payload, {"stage": "worker_draft"})
        yield {
            "type": "stage_complete",
            "stage": "worker_drafts",
            "context_patch": self._emit_context_patch()
        }
        
        # Unload worker model if aggressive unloading
        if self.config.mode_config.memory.model_unloading == "aggressive":
            self.runtime.unload_model()
        
        # Stage 2: Synthesizer Questions
        self.current_stage = PipelineStage.SYNTH_QUESTIONS
        yield {"type": "stage_start", "stage": "synth_questions"}
        
        synth_input_text = str(drafts)
        synth_input_hash = self.logger.compute_hash(synth_input_text)
        cached_questions_entry = self.logger.find_entry(
            stage="synth_questions",
            agent_id="synthesizer",
            input_hash=synth_input_hash
        )
        if cached_questions_entry:
            questions = SynthesizerQuestions.from_json(cached_questions_entry.output_text)
        else:
            questions = self.synthesizer.generate_questions(drafts)
        
        # Emit synthesizer token usage
        synth_tokens = self.synthesizer.get_last_token_usage()
        yield {
            "type": "tokens_update",
            "source": "synthesizer",
            "tokens": synth_tokens,
            "context_limit": self.synth_context_window
        }
        
        if not cached_questions_entry:
            self.logger.log(
                stage="synth_questions",
                agent_id="synthesizer",
                input_text=synth_input_text,
                output_text=questions.raw_text,
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )
        
        self._stage_outputs["questions"] = questions.to_dict()
        self._apply_architect_update(
            "synth_questions",
            {
                "questions": questions.to_dict(),
                "drafts": drafts
            },
            {"stage": "synth_questions"}
        )
        yield {
            "type": "stage_complete",
            "stage": "synth_questions",
            "questions": questions.to_dict(),
            "context_patch": self._emit_context_patch()
        }
        
        # Stage 3: Worker Refinement with interactive rounds
        refinement_loops = self.debate_rounds
        
        for loop in range(refinement_loops):
            self._current_round = loop + 1
            self.current_stage = PipelineStage.WORKER_REFINEMENT
            yield {"type": "stage_start", "stage": f"worker_refinement_{loop + 1}"}
            
            refinements = {}
            similarity_hits = []
            for worker_id, worker in self.workers.items():
                worker_questions = questions.questions_by_worker.get(worker_id, [])
                
                # If no questions for this worker, give them a default refinement prompt
                if not worker_questions:
                    worker_questions = ["Based on the synthesizer's overall observations, how can you improve or clarify your proposal?"]
                
                yield {"type": "worker_start", "worker_id": worker_id, "stage": "refinement"}
                
                # Get user guidance from previous round feedback (if any)
                user_guidance = None
                prev_round_feedback = self._round_feedback.get(loop, {})
                if prev_round_feedback:
                    user_guidance = prev_round_feedback.get("worker_feedback", {}).get(worker_id)
                
                current_draft_summary = worker.current_draft.summary if worker.current_draft else "No draft"
                full_input_text = f"CURRENT PROPOSAL:\n{current_draft_summary}\n\nSYNTHESIZER QUESTIONS:\n" + "\n".join(f"- {q}" for q in worker_questions)
                if user_guidance:
                    full_input_text += f"\n\nUSER FEEDBACK:\n{user_guidance}"

                input_hash = self.logger.compute_hash(full_input_text)
                cached_refinement_entry = self.logger.find_entry(
                    stage="refinement",
                    agent_id=worker_id,
                    input_hash=input_hash
                )
                if cached_refinement_entry:
                    refinement = WorkerRefinement.from_json(cached_refinement_entry.output_text)
                    if not worker.refinements or worker.refinements[-1].raw_text != refinement.raw_text:
                        worker.refinements.append(refinement)
                    self.logger.log(
                        stage="refinement",
                        agent_id=worker_id,
                        input_text=full_input_text,
                        output_text=refinement.raw_text,
                        persona_id=worker.persona.id if worker.persona else None,
                        persona_name=worker.persona.name if worker.persona else None,
                        memory_usage_mb=self.memory_monitor.get_memory_mb(),
                        metadata={
                            "round": loop + 1,
                            "stage_label": f"worker_refinement_{loop + 1}",
                            "cache_hit": True
                        }
                    )
                else:
                    refinement = worker.refine(worker_questions, user_guidance=user_guidance)
                    self.logger.log(
                        stage="refinement",
                        agent_id=worker_id,
                        input_text=full_input_text,
                        output_text=refinement.raw_text,
                        persona_id=worker.persona.id if worker.persona else None,
                        persona_name=worker.persona.name if worker.persona else None,
                        memory_usage_mb=self.memory_monitor.get_memory_mb(),
                        metadata={
                            "round": loop + 1,
                            "stage_label": f"worker_refinement_{loop + 1}",
                            "cache_hit": False
                        }
                    )

                refinements[worker_id] = refinement.to_dict()
                
                yield {
                    "type": "worker_complete",
                    "worker_id": worker_id,
                    "refinement": refinement.to_dict(),
                    "tokens": worker.get_last_token_usage(),
                    "context_patch": self._emit_context_patch()
                }

                if len(worker.refinements) > 1:
                    previous = worker.refinements[-2].raw_text
                    current = worker.refinements[-1].raw_text
                    similarity = difflib.SequenceMatcher(a=previous, b=current).ratio()
                    similarity_hits.append(similarity >= self.refinement_similarity_threshold)
            
            self._stage_outputs[f"refinements_{loop + 1}"] = refinements
            self._apply_architect_update(
                "worker_refinement",
                {
                    "round": loop + 1,
                    "refinements": refinements,
                    "questions": questions.to_dict() if questions else None
                },
                {"stage": "worker_refinement"}
            )
            yield {
                "type": "stage_complete",
                "stage": f"worker_refinement_{loop + 1}",
                "context_patch": self._emit_context_patch()
            }

            if similarity_hits and all(similarity_hits):
                yield {
                    "type": "info",
                    "message": "Refinement halted due to high similarity with previous outputs."
                }
                break
            
            # After each round, pause for optional user feedback
            # Only pause if there are more rounds to go
            if loop < refinement_loops - 1:
                self._awaiting_round_feedback = True
                self.current_stage = PipelineStage.AWAITING_ROUND_FEEDBACK
                
                # Generate follow-up questions from synthesizer for next round
                yield {"type": "synth_commentary", "content": "Analyzing refinements for follow-up questions..."}
                
                follow_up_questions = self.synthesizer.generate_follow_up_questions(refinements, questions)
                
                # Emit synthesizer token usage
                synth_tokens = self.synthesizer.get_last_token_usage()
                yield {
                    "type": "tokens_update",
                    "source": "synthesizer",
                    "tokens": synth_tokens,
                    "context_limit": self.synth_context_window
                }
                
                if follow_up_questions:
                    questions = follow_up_questions  # Update questions for next round
                    yield {"type": "synth_commentary", "content": follow_up_questions.overall_observations or "Follow-up questions generated."}

                if follow_up_questions:
                    self._apply_architect_update(
                        "follow_up_questions",
                        {
                            "round": loop + 1,
                            "questions": follow_up_questions.to_dict()
                        },
                        {"stage": "synth_follow_up_questions"}
                    )
                
                yield {
                    "type": "awaiting_round_feedback",
                    "round": loop + 1,
                    "total_rounds": refinement_loops,
                    "worker_outputs": {
                        wid: {
                            "display_id": w.display_id,
                            "summary": w.current_draft.summary if w.current_draft else None,
                            "refinement": self._build_refinement_payload(refinements.get(wid))
                        }
                        for wid, w in self.workers.items()
                    },
                    "follow_up_questions": follow_up_questions.to_dict() if follow_up_questions else None,
                    "context_patch": self._emit_context_patch()
                }
                # Pipeline will resume when continue_pipeline is called
                return
        
        # All refinement rounds complete, continue with synthesis and voting
        for event in self._run_synthesis_and_voting():
            yield event
    
    def submit_user_votes(
        self,
        votes: Dict[str, int],
        candidate_feedback: Dict[str, str] = None,
        overall_feedback: str = "",
        worker_feedback: Dict[str, str] = None,
        synthesizer_feedback: str = "",
        prompt_rating: int = 0,
        prompt_feedback: str = ""
    ) -> Dict[str, Any]:
        """
        Submit user votes and comprehensive feedback.
        
        Args:
            votes: Dict mapping candidate_id to rank (1 = best).
            candidate_feedback: Optional dict mapping candidate_id to feedback text.
            overall_feedback: General feedback on the session.
            worker_feedback: Dict mapping worker_id to feedback text.
            synthesizer_feedback: Feedback on synthesizer performance.
            prompt_rating: Optional rating of the original prompt (1-5, 0=skip).
            prompt_feedback: Optional feedback on the prompt quality.
        
        Returns:
            Voting result with all feedback.
        """
        self.voter.submit_user_votes(
            votes=votes, 
            candidate_feedback=candidate_feedback or {},
            overall_feedback=overall_feedback,
            worker_feedback=worker_feedback or {},
            synthesizer_feedback=synthesizer_feedback
        )
        
        # Determine winner
        result = self.voter.determine_winner()
        
        # Log candidate votes
        for candidate_id, vote in self.voter.user_votes.items():
            self.logger.log(
                stage="user_voting",
                agent_id="user",
                input_text=candidate_id,
                output_text=f"rank={vote.rank}, feedback={vote.feedback}",
                user_vote=vote.rank,
                user_feedback=vote.feedback,
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )
        
        # Log overall feedback
        if overall_feedback:
            self.logger.log(
                stage="user_voting",
                agent_id="user",
                input_text="overall_feedback",
                output_text=overall_feedback,
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )
        
        # Log worker feedback
        for worker_id, feedback in (worker_feedback or {}).items():
            if feedback:
                worker = self.workers.get(worker_id)
                self.logger.log(
                    stage="user_voting",
                    agent_id="user",
                    input_text=f"worker_feedback:{worker_id}",
                    output_text=feedback,
                    persona_id=worker.persona.id if worker and worker.persona else None,
                    persona_name=worker.persona.name if worker and worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
        
        # Log synthesizer feedback
        if synthesizer_feedback:
            self.logger.log(
                stage="user_voting",
                agent_id="user",
                input_text="synthesizer_feedback",
                output_text=synthesizer_feedback,
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )
        
        # Log prompt feedback
        if prompt_rating > 0 or prompt_feedback:
            self.logger.log(
                stage="prompt_feedback",
                agent_id="user",
                input_text=self.prompt,
                output_text=f"rating={prompt_rating}, feedback={prompt_feedback}",
                metadata={
                    "prompt_rating": prompt_rating,
                    "prompt_feedback": prompt_feedback
                },
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )

        self._apply_architect_update(
            "user_voting",
            {
                "votes": votes,
                "candidate_feedback": candidate_feedback or {},
                "overall_feedback": overall_feedback,
                "worker_feedback": worker_feedback or {},
                "synthesizer_feedback": synthesizer_feedback,
                "prompt_rating": prompt_rating,
                "prompt_feedback": prompt_feedback,
                "voting_result": result.to_dict()
            },
            {"stage": "user_voting"}
        )
        
        self._stage_outputs["voting_result"] = result.to_dict()
        
        return result.to_dict()
    
    def finalize(self, run_axioms: bool = True) -> Generator[Dict[str, Any], None, None]:
        """
        Generate final output with optional axiom analysis.
        
        Args:
            run_axioms: Whether to run axiom analysis (default True).
        
        Yields:
            Event dicts with final output progress.
        """
        if not self._stage_outputs.get("voting_result"):
            raise ValueError("User voting not complete")
        
        # Run axiom analysis first (LAST analytical stage, before final output)
        if run_axioms and self.axiom_rounds > 0:
            for event in self.run_axiom_analysis():
                yield event
        
        self.current_stage = PipelineStage.FINAL_OUTPUT
        yield {"type": "stage_start", "stage": "final_output"}
        
        voting_result = self._stage_outputs["voting_result"]
        winning_id = voting_result["winning_candidate_id"]
        
        # Find winning candidate
        winning_candidate = None
        if winning_id and winning_id != "none":
            for candidate in self._candidates:
                if candidate.id == winning_id:
                    winning_candidate = candidate
                    break
        
        # Handle no candidates case - generate summary from worker proposals
        if not winning_candidate:
            # Create a pseudo-candidate from worker proposals
            worker_summaries = [
                w.current_draft.summary[:200] 
                for w in self.workers.values() 
                if w.current_draft
            ]
            winning_candidate = Candidate(
                id="feedback_only",
                source_workers=list(self.workers.keys()),
                summary="Combined worker proposals: " + " | ".join(worker_summaries),
                best_use_case="Feedback collection only",
                trade_offs=[],
                failure_modes=[],
                decision_criteria="No synthesis was performed"
            )
        
        # Get user feedback for winner
        user_feedback = voting_result.get("overall_feedback", "")
        user_votes = voting_result.get("user_votes", {})
        if winning_id in user_votes:
            user_feedback = user_votes[winning_id].get("feedback", "") or user_feedback

        # Generate final output using global JSON context
        global_context = self.global_context.to_dict() if self.global_context else {}
        final_output = self.engineer.generate_final_output(
            global_context=global_context,
            winning_candidate=winning_candidate.summary if winning_candidate else "",
            user_feedback=user_feedback,
            ai_score=voting_result["ai_scores"].get(winning_id, 0),
            user_selection=voting_result["winning_reason"]
        )

        engineer_tokens = self.engineer.get_last_token_usage()
        yield {
            "type": "tokens_update",
            "source": "engineer",
            "tokens": engineer_tokens,
            "context_limit": self.engineer_context_window
        }
        
        self.logger.log(
            stage="final_output",
            agent_id="engineer",
            input_text=str(winning_candidate.to_dict()),
            output_text=final_output,
            memory_usage_mb=self.memory_monitor.get_memory_mb()
        )
        
        self._stage_outputs["final_output"] = final_output

        self._apply_architect_update(
            "final_output",
            {
                "final_output": final_output,
                "winning_candidate": winning_candidate.to_dict(),
                "ai_score": voting_result["ai_scores"].get(winning_id, 0),
                "user_selection": voting_result["winning_reason"]
            },
            {"stage": "final_output", "source": "engineer"}
        )
        
        # Yield final output and await optional feedback
        self._awaiting_final_feedback = True
        self.current_stage = PipelineStage.AWAITING_FINAL_FEEDBACK
        yield {
            "type": "final_output",
            "output": final_output,
            "winning_candidate": winning_candidate.to_dict(),
            "awaiting_feedback": True,
            "context_patch": self._emit_context_patch()
        }
    
    def submit_final_feedback(self, feedback: str) -> Dict[str, Any]:
        """
        Submit feedback on the final output (for logging only).
        
        Args:
            feedback: User feedback on the final output.
        
        Returns:
            Summary of the completed session.
        """
        self._final_output_feedback = feedback
        self._awaiting_final_feedback = False
        
        # Log feedback
        if feedback:
            self.logger.log(
                stage="final_output_feedback",
                agent_id="user",
                input_text=self._stage_outputs.get("final_output", ""),
                output_text=feedback,
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )

            self._apply_architect_update(
                "final_output_feedback",
                {
                    "round": "final",
                    "feedback": feedback
                },
                {"stage": "final_output_feedback"}
            )
            
            # Add to feedback history for future analysis
            self._user_feedback_history.append({
                "round": "final",
                "feedback": feedback,
                "worker_id": None
            })
        
        self.current_stage = PipelineStage.COMPLETE
        
        # Update persona stats
        voting_result = self._stage_outputs.get("voting_result", {})
        winning_id = voting_result.get("winning_candidate_id")
        
        for worker_id, worker in self.workers.items():
            if worker.persona:
                self.persona_manager.increment_usage(worker.persona.id)
                # Check if this worker's persona won
                won = winning_id in [c.id for c in self._candidates 
                                     if worker_id in c.source_workers]
                self.persona_manager.update_win_rate(worker.persona.id, won)
        
        return {
            "session_id": self.session_id,
            "final_output": self._stage_outputs.get("final_output"),
            "voting_result": voting_result,
            "axiom_network": self._stage_outputs.get("axiom_network"),
            "session_summary": self.logger.get_session_summary(),
            "status": "complete"
        }
    
    def swap_worker_persona(
        self,
        worker_id: str,
        new_persona_id: str,
        action: str = "restart"
    ) -> Dict[str, Any]:
        """
        Swap a worker's persona mid-session.
        
        Args:
            worker_id: ID of worker to update.
            new_persona_id: ID of new persona.
            action: One of "keep_all", "archive", "restart".
        
        Returns:
            Updated worker state.
        """
        if worker_id not in self.workers:
            raise ValueError(f"Worker not found: {worker_id}")
        
        worker = self.workers[worker_id]
        new_persona = self.persona_manager.get_persona(new_persona_id)
        
        if not new_persona:
            raise ValueError(f"Persona not found: {new_persona_id}")
        
        # Handle previous outputs
        if action == "archive" and worker.current_draft:
            if worker_id not in self._archived_outputs:
                self._archived_outputs[worker_id] = []
            self._archived_outputs[worker_id].append({
                "persona_id": worker.persona.id if worker.persona else None,
                "persona_name": worker.persona.name if worker.persona else None,
                "draft": worker.current_draft.to_dict() if worker.current_draft else None,
                "archived_at": datetime.utcnow().isoformat()
            })
        
        if action == "restart":
            worker.clear_state()
        
        # Set new persona
        worker.set_persona(new_persona)
        
        return {
            "worker_id": worker_id,
            "new_persona_id": new_persona_id,
            "new_persona_name": new_persona.name,
            "action": action,
            "state_cleared": action == "restart"
        }
    
    def submit_round_feedback(
        self,
        round_num: int,
        worker_feedback: Dict[str, str] = None,
        skip_to_synthesis: bool = False
    ) -> Dict[str, Any]:
        """
        Submit feedback for a specific debate round.
        
        Args:
            round_num: The round number (1-indexed).
            worker_feedback: Dict mapping worker_id to feedback text.
            skip_to_synthesis: If True, skip remaining rounds and go to synthesis.
        
        Returns:
            Summary of feedback submitted.
        """
        if not self._awaiting_round_feedback:
            raise ValueError("Not awaiting round feedback")
        
        self._round_feedback[round_num] = {
            "worker_feedback": worker_feedback or {},
            "skip_to_synthesis": skip_to_synthesis,
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        # Log round feedback and track for axiom extraction
        for worker_id, feedback in (worker_feedback or {}).items():
            if feedback:
                worker = self.workers.get(worker_id)
                self._user_feedback_history.append({
                    "round": f"refinement_{round_num}",
                    "feedback": feedback,
                    "worker_id": worker_id
                })
                self.logger.log(
                    stage=f"round_feedback_{round_num}",
                    agent_id="user",
                    input_text=f"worker_feedback:{worker_id}",
                    output_text=feedback,
                    persona_id=worker.persona.id if worker and worker.persona else None,
                    persona_name=worker.persona.name if worker and worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
        
        self._skip_to_synthesis = skip_to_synthesis
        self._awaiting_round_feedback = False

        self._apply_architect_update(
            "round_feedback",
            {
                "round": round_num,
                "worker_feedback": worker_feedback or {},
                "skip_to_synthesis": skip_to_synthesis
            },
            {"stage": "round_feedback"}
        )
        
        return {
            "round": round_num,
            "feedback_count": len(worker_feedback or {}),
            "skip_to_synthesis": skip_to_synthesis
        }
    
    def submit_collab_feedback(
        self,
        round_num: int,
        worker_feedback: Dict[str, str] = None,
        skip_to_synthesis: bool = False
    ) -> Dict[str, Any]:
        """
        Submit feedback for a specific collaboration round.
        
        Args:
            round_num: The collaboration round number (1-indexed).
            worker_feedback: Dict mapping worker_id to feedback text.
            skip_to_synthesis: If True, skip remaining rounds and go to synthesis.
        
        Returns:
            Summary of feedback submitted.
        """
        if not self._awaiting_collab_feedback:
            raise ValueError("Not awaiting collaboration feedback")
        
        self._collab_feedback[round_num] = {
            "worker_feedback": worker_feedback or {},
            "skip_to_synthesis": skip_to_synthesis,
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        # Track feedback for axiom extraction
        for worker_id, feedback in (worker_feedback or {}).items():
            if feedback:
                worker = self.workers.get(worker_id)
                self._user_feedback_history.append({
                    "round": f"collab_{round_num}",
                    "feedback": feedback,
                    "worker_id": worker_id
                })
                self.logger.log(
                    stage=f"collab_feedback_{round_num}",
                    agent_id="user",
                    input_text=f"worker_feedback:{worker_id}",
                    output_text=feedback,
                    persona_id=worker.persona.id if worker and worker.persona else None,
                    persona_name=worker.persona.name if worker and worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
        
        self._skip_to_synthesis = skip_to_synthesis
        self._awaiting_collab_feedback = False

        self._apply_architect_update(
            "collab_feedback",
            {
                "round": round_num,
                "worker_feedback": worker_feedback or {},
                "skip_to_synthesis": skip_to_synthesis
            },
            {"stage": "collab_feedback"}
        )
        
        return {
            "round": round_num,
            "feedback_count": len(worker_feedback or {}),
            "skip_to_synthesis": skip_to_synthesis
        }
    
    def submit_argument_feedback(
        self,
        round_num: int,
        worker_feedback: Dict[str, str] = None,
        skip_to_voting: bool = False
    ) -> Dict[str, Any]:
        """
        Submit feedback for a specific argumentation round.
        
        Args:
            round_num: The argumentation round number (1-indexed).
            worker_feedback: Dict mapping worker_id to feedback text.
            skip_to_voting: If True, skip remaining rounds and go to voting.
        
        Returns:
            Summary of feedback submitted.
        """
        if not self._awaiting_argument_feedback:
            raise ValueError("Not awaiting argument feedback")
        
        self._arg_round_feedback[round_num] = {
            "worker_feedback": worker_feedback or {},
            "skip_to_voting": skip_to_voting,
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        # Log argument round feedback and track for axiom extraction
        for worker_id, feedback in (worker_feedback or {}).items():
            if feedback:
                worker = self.workers.get(worker_id)
                self._user_feedback_history.append({
                    "round": f"argument_{round_num}",
                    "feedback": feedback,
                    "worker_id": worker_id
                })
                self.logger.log(
                    stage=f"argument_feedback_{round_num}",
                    agent_id="user",
                    input_text=f"worker_feedback:{worker_id}",
                    output_text=feedback,
                    persona_id=worker.persona.id if worker and worker.persona else None,
                    persona_name=worker.persona.name if worker and worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
        
        self._skip_to_voting = skip_to_voting
        self._awaiting_argument_feedback = False

        self._apply_architect_update(
            "argument_feedback",
            {
                "round": round_num,
                "worker_feedback": worker_feedback or {},
                "skip_to_voting": skip_to_voting
            },
            {"stage": "argument_feedback"}
        )
        
        return {
            "round": round_num,
            "feedback_count": len(worker_feedback or {}),
            "skip_to_voting": skip_to_voting
        }
    
    def continue_pipeline(self) -> Generator[Dict[str, Any], None, None]:
        """
        Continue the pipeline after round feedback, collaboration feedback, or argument feedback.
        
        Yields:
            Event dicts with stage progress and outputs.
        """
        if not self.session_id:
            raise ValueError("No active session")
        
        # Check if we're continuing from collaboration feedback
        if self._awaiting_collab_feedback:
            self._awaiting_collab_feedback = False
            for event in self._continue_collaboration():
                yield event
            return
        
        # Check if we're continuing from argumentation feedback
        if self._current_arg_round > 0 and self.current_stage == PipelineStage.ARGUMENTATION:
            for event in self._continue_argumentation():
                yield event
            return
        
        # Check if we're continuing from final output feedback
        if self._awaiting_final_feedback:
            self._awaiting_final_feedback = False
            yield {"type": "stage_complete", "stage": "final_output_feedback_received"}
            return
        
        # Get where we left off
        current_round = self._current_round
        total_rounds = self.debate_rounds
        
        # If user chose to skip to synthesis
        if self._skip_to_synthesis:
            yield {"type": "info", "message": f"Skipping remaining rounds, proceeding to synthesis"}
            # Fall through to synthesis stage
        else:
            # Continue with remaining refinement rounds
            questions = self.synthesizer.last_questions if hasattr(self.synthesizer, 'last_questions') else None
            
            # Get questions from stage outputs
            if not questions and "questions" in self._stage_outputs:
                from .agents.synthesizer import SynthesizerQuestions
                q_data = self._stage_outputs["questions"]
                # Reconstruct questions object for remaining rounds
                class QuestionsHolder:
                    def __init__(self, data):
                        self.questions_by_worker = data.get("questions_by_worker", {})
                        self.overall_observations = data.get("overall_observations", "")
                questions = QuestionsHolder(q_data)
            
            for loop in range(current_round, total_rounds):
                self._current_round = loop + 1
                self.current_stage = PipelineStage.WORKER_REFINEMENT
                yield {"type": "stage_start", "stage": f"worker_refinement_{loop + 1}"}
                
                refinements = {}
                similarity_hits = []
                for worker_id, worker in self.workers.items():
                    worker_questions = questions.questions_by_worker.get(worker_id, []) if questions else []
                    
                    # If no questions for this worker, give them a default refinement prompt
                    if not worker_questions:
                        worker_questions = ["Based on the synthesizer's overall observations, how can you improve or clarify your proposal?"]
                    
                    yield {"type": "worker_start", "worker_id": worker_id, "stage": "refinement"}
                    
                    # Get user guidance from previous round feedback
                    user_guidance = None
                    prev_round_feedback = self._round_feedback.get(loop, {})  # Round `loop` feedback for round `loop+1`
                    if prev_round_feedback:
                        user_guidance = prev_round_feedback.get("worker_feedback", {}).get(worker_id)
                    
                    current_draft_summary = worker.current_draft.summary if worker.current_draft else "No draft"
                    full_input_text = f"CURRENT PROPOSAL:\n{current_draft_summary}\n\nSYNTHESIZER QUESTIONS:\n" + "\n".join(f"- {q}" for q in worker_questions)
                    if user_guidance:
                        full_input_text += f"\n\nUSER FEEDBACK:\n{user_guidance}"

                    input_hash = self.logger.compute_hash(full_input_text)
                    cached_refinement_entry = self.logger.find_entry(
                        stage="refinement",
                        agent_id=worker_id,
                        input_hash=input_hash
                    )
                    if cached_refinement_entry:
                        refinement = WorkerRefinement.from_json(cached_refinement_entry.output_text)
                        if not worker.refinements or worker.refinements[-1].raw_text != refinement.raw_text:
                            worker.refinements.append(refinement)
                        self.logger.log(
                            stage="refinement",
                            agent_id=worker_id,
                            input_text=full_input_text,
                            output_text=refinement.raw_text,
                            persona_id=worker.persona.id if worker.persona else None,
                            persona_name=worker.persona.name if worker.persona else None,
                            memory_usage_mb=self.memory_monitor.get_memory_mb(),
                            metadata={
                                "round": loop + 1,
                                "stage_label": f"worker_refinement_{loop + 1}",
                                "cache_hit": True
                            }
                        )
                    else:
                        refinement = worker.refine(worker_questions, user_guidance=user_guidance)
                        self.logger.log(
                            stage="refinement",
                            agent_id=worker_id,
                            input_text=full_input_text,
                            output_text=refinement.raw_text,
                            persona_id=worker.persona.id if worker.persona else None,
                            persona_name=worker.persona.name if worker.persona else None,
                            memory_usage_mb=self.memory_monitor.get_memory_mb(),
                            metadata={
                                "round": loop + 1,
                                "stage_label": f"worker_refinement_{loop + 1}",
                                "cache_hit": False
                            }
                        )

                    refinements[worker_id] = refinement.to_dict()
                    
                    yield {
                        "type": "worker_complete",
                        "worker_id": worker_id,
                        "refinement": refinement.to_dict(),
                        "tokens": worker.get_last_token_usage(),
                        "context_patch": self._emit_context_patch()
                    }

                    if len(worker.refinements) > 1:
                        previous = worker.refinements[-2].raw_text
                        current = worker.refinements[-1].raw_text
                        similarity = difflib.SequenceMatcher(a=previous, b=current).ratio()
                        similarity_hits.append(similarity >= self.refinement_similarity_threshold)
                
                self._stage_outputs[f"refinements_{loop + 1}"] = refinements
                self._apply_architect_update(
                    "worker_refinement",
                    {
                        "round": loop + 1,
                        "refinements": refinements,
                        "questions": questions.to_dict() if questions else None
                    },
                    {"stage": "worker_refinement"}
                )
                yield {
                    "type": "stage_complete",
                    "stage": f"worker_refinement_{loop + 1}",
                    "context_patch": self._emit_context_patch()
                }

                if similarity_hits and all(similarity_hits):
                    yield {
                        "type": "info",
                        "message": "Refinement halted due to high similarity with previous outputs."
                    }
                    break
                
                # Pause for feedback between rounds (not after last)
                if loop < total_rounds - 1:
                    self._awaiting_round_feedback = True
                    self.current_stage = PipelineStage.AWAITING_ROUND_FEEDBACK
                    
                    # Generate follow-up questions from synthesizer for next round
                    yield {"type": "synth_commentary", "content": "Analyzing refinements for follow-up questions..."}
                    
                    follow_up_questions = self.synthesizer.generate_follow_up_questions(refinements, questions)
                    if follow_up_questions:
                        questions = follow_up_questions  # Update questions for next round
                        yield {"type": "synth_commentary", "content": follow_up_questions.overall_observations or "Follow-up questions generated."}

                    if follow_up_questions:
                        self._apply_architect_update(
                            "follow_up_questions",
                            {
                                "round": loop + 1,
                                "questions": follow_up_questions.to_dict()
                            },
                            {"stage": "synth_follow_up_questions"}
                        )
                    
                    yield {
                        "type": "awaiting_round_feedback",
                        "round": loop + 1,
                        "total_rounds": total_rounds,
                        "worker_outputs": {
                            wid: {
                                "display_id": w.display_id,
                                "summary": w.current_draft.summary if w.current_draft else None,
                                "refinement": self._build_refinement_payload(refinements.get(wid))
                            }
                            for wid, w in self.workers.items()
                        },
                        "follow_up_questions": follow_up_questions.to_dict() if follow_up_questions else None,
                        "context_patch": self._emit_context_patch()
                    }
                    return
        
        # Continue with synthesis and remaining stages
        for event in self._run_synthesis_and_voting():
            yield event
    
    def _run_synthesis_and_voting(self) -> Generator[Dict[str, Any], None, None]:
        """
        Run synthesis, argumentation, collaboration, and voting stages.
        
        Pipeline order:
        1. Candidate Synthesis - Create candidates from refined proposals
        2. Argumentation - Workers argue for their proposals
        3. Compatibility Check - Check if proposals can be merged
        4. Collaboration (if compatible) - Workers collaborate on compatible ideas
        5. Voting - AI and user vote on candidates
        6. Axiom Analysis - Analyze underlying axioms (in finalize)
        """
        # Gather refined proposals
        refined_proposals = {}
        for worker_id, worker in self.workers.items():
            if not worker.current_draft:
                continue
            latest_refinement = worker.refinements[-1] if worker.refinements else None
            refined_proposals[worker_id] = {
                "summary": worker.current_draft.summary,
                "answers_to_questions": latest_refinement.answers_to_questions if latest_refinement else {},
                "patch_notes": latest_refinement.patch_notes if latest_refinement else [],
                "new_risks": latest_refinement.new_risks if latest_refinement else [],
                "new_tradeoffs": latest_refinement.new_tradeoffs if latest_refinement else []
            }
        
        # Stage 1: Candidate Synthesis
        self.current_stage = PipelineStage.CANDIDATE_SYNTHESIS
        yield {"type": "stage_start", "stage": "candidate_synthesis"}
        
        candidates = self.architect.synthesize_candidates(refined_proposals)
        self._candidates = candidates
        
        architect_tokens = self.architect.get_last_token_usage()
        yield {
            "type": "tokens_update",
            "source": "architect",
            "tokens": architect_tokens,
            "context_limit": self.architect_context_window
        }
        
        self.logger.log(
            stage="candidate_synthesis",
            agent_id="architect",
            input_text=str(refined_proposals),
            output_text=str([c.to_dict() for c in candidates]),
            memory_usage_mb=self.memory_monitor.get_memory_mb()
        )
        
        self._stage_outputs["candidates"] = [c.to_dict() for c in candidates]
        self.voter.set_candidates([c.id for c in candidates])

        self._apply_architect_update(
            "candidate_synthesis",
            {
                "candidates": [c.to_dict() for c in candidates],
                "refined_proposals": refined_proposals
            },
            {"stage": "candidate_synthesis"}
        )
        
        yield {
            "type": "stage_complete",
            "stage": "candidate_synthesis",
            "candidates": [c.to_dict() for c in candidates],
            "context_patch": self._emit_context_patch()
        }
        
        # Stage 2: Multi-round Argumentation
        all_arguments = []  # Accumulate argument history for multi-round
        
        # Build and inject shared context BEFORE first argumentation round
        shared_context = self._build_shared_context_for_argumentation()
        for worker_id, worker in self.workers.items():
            worker.inject_shared_context(shared_context)
        
        for arg_round in range(self.argument_rounds):
            self.current_stage = PipelineStage.ARGUMENTATION
            round_label = f"argumentation_round_{arg_round + 1}"  # Always use indexed format
            yield {"type": "stage_start", "stage": round_label}
            
            round_arguments = {}
            
            for worker_id, worker in self.workers.items():
                # Build context: alternatives + previous arguments from other workers
                alternatives = [
                    w.current_draft.summary
                    for wid, w in self.workers.items()
                    if wid != worker_id and w.current_draft
                ]
                
                # Include previous round arguments from other workers for context
                previous_args = []
                if arg_round > 0 and all_arguments:
                    prev_round_args = all_arguments[-1]
                    for wid, arg in prev_round_args.items():
                        if wid != worker_id:
                            worker_display = self.workers[wid].display_id
                            previous_args.append({
                                "worker": worker_display,
                                "argument": arg.get("main_argument", "")
                            })
                
                yield {"type": "worker_start", "worker_id": worker_id, "stage": "argumentation"}
                
                # Get user guidance from previous argument round feedback (if any)
                user_guidance = None
                prev_arg_feedback = self._arg_round_feedback.get(arg_round, {})
                if prev_arg_feedback:
                    user_guidance = prev_arg_feedback.get("worker_feedback", {}).get(worker_id)
                
                # Pass previous arguments context for counter-arguments and user guidance
                argument = worker.argue(alternatives, self.rubric, counter_arguments=previous_args, user_guidance=user_guidance)
                round_arguments[worker_id] = argument.to_dict()
                
                self.logger.log(
                    stage=round_label,
                    agent_id=worker_id,
                    input_text=str(alternatives),
                    output_text=argument.raw_text,
                    persona_id=worker.persona.id if worker.persona else None,
                    persona_name=worker.persona.name if worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
                
                yield {
                    "type": "worker_complete",
                    "worker_id": worker_id,
                    "argument": argument.to_dict(),
                    "tokens": worker.get_last_token_usage(),
                    "context_patch": self._emit_context_patch()
                }
            
            all_arguments.append(round_arguments)
            self._stage_outputs[f"arguments_round_{arg_round + 1}"] = round_arguments
            self._apply_architect_update(
                "argumentation",
                {
                    "round": arg_round + 1,
                    "arguments": round_arguments
                },
                {"stage": "argumentation"}
            )
            yield {
                "type": "stage_complete",
                "stage": round_label,
                "context_patch": self._emit_context_patch()
            }
            
            # Synthesizer commentary after each argumentation round (except the last)
            if arg_round < self.argument_rounds - 1:
                commentary = self._get_architect_commentary(round_arguments, round_num=arg_round + 1)
                if commentary:
                    yield {
                        "type": "synth_commentary",
                        "round": arg_round + 1,
                        "content": commentary
                    }
                
                # Pause for user feedback between argumentation rounds
                self._awaiting_argument_feedback = True
                self._current_arg_round = arg_round + 1
                yield {
                    "type": "awaiting_argument_feedback",
                    "round": arg_round + 1,
                    "total_rounds": self.argument_rounds,
                    "worker_arguments": {
                        wid: {
                            "display_id": w.display_id,
                            "main_argument": round_arguments.get(wid, {}).get("main_argument", ""),
                            "key_strengths": round_arguments.get(wid, {}).get("key_strengths") or [],
                            "critique_of_alternatives": round_arguments.get(wid, {}).get("critique_of_alternatives") or "",
                            "rubric_alignment": round_arguments.get(wid, {}).get("rubric_alignment") or ""
                        }
                        for wid, w in self.workers.items()
                    },
                    "context_patch": self._emit_context_patch()
                }
                return  # Pipeline will resume when continue_pipeline is called
        
        # Store final round arguments for voting
        self._stage_outputs["arguments"] = all_arguments[-1] if all_arguments else {}
        
        # Stage 3: Compatibility Check (after argumentation, before collaboration)
        self.current_stage = PipelineStage.COMPATIBILITY_CHECK
        yield {"type": "stage_start", "stage": "compatibility_check"}
        
        # Re-gather proposals for compatibility check
        refined_proposals = {
            worker_id: {"summary": worker.current_draft.summary}
            for worker_id, worker in self.workers.items()
            if worker.current_draft
        }
        
        compatibility = self.synthesizer.check_compatibility(refined_proposals)
        self._compatibility_result = compatibility
        
        # Emit synthesizer token usage
        synth_tokens = self.synthesizer.get_last_token_usage()
        yield {
            "type": "tokens_update",
            "source": "synthesizer",
            "tokens": synth_tokens,
            "context_limit": self.synth_context_window
        }
        
        self.logger.log(
            stage="compatibility_check",
            agent_id="synthesizer",
            input_text=str(refined_proposals),
            output_text=str(compatibility),
            memory_usage_mb=self.memory_monitor.get_memory_mb()
        )

        self._apply_architect_update(
            "compatibility_check",
            {
                "compatibility": compatibility,
                "proposals": refined_proposals
            },
            {"stage": "compatibility_check"}
        )

        yield {
            "type": "stage_complete",
            "stage": "compatibility_check",
            "compatibility": compatibility,
            "context_patch": self._emit_context_patch()
        }
        
        # Stage 4: Collaboration (run for feedback even when proposals diverge)
        if self.collaboration_rounds > 0:
            for event in self._run_collaboration(compatibility):
                yield event
            
            # Check if we paused for collaboration feedback - if so, stop here
            # Voting will be triggered by continue_pipeline after feedback
            if self._awaiting_collab_feedback:
                return
        
        # Continue to voting stage
        for event in self._run_voting():
            yield event

    def _run_collaboration(self, compatibility: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """Run collaboration rounds for cross-proposal feedback."""
        overlap_areas = compatibility.get("overlap_areas", [])
        merge_strategy = compatibility.get("merge_strategy", "")
        compatible_pairs = compatibility.get("compatible_pairs", [])
        
        for collab_round in range(self.collaboration_rounds):
            self._current_collab_round = collab_round + 1
            self.current_stage = PipelineStage.COLLABORATION
            round_label = f"collaboration_round_{collab_round + 1}"  # Always use indexed format
            yield {"type": "stage_start", "stage": round_label}
            
            collab_outputs = {}
            
            for worker_id, worker in self.workers.items():
                if not worker.current_draft:
                    continue
                
                # Build compatible proposals for this worker
                compatible_proposals = []
                for wid, w in self.workers.items():
                    if wid != worker_id and w.current_draft:
                        # Check if these workers are in a compatible pair
                        is_pair = any(
                            (worker_id in pair and wid in pair)
                            for pair in compatible_pairs
                        ) if compatible_pairs else True  # If no pairs specified, all are compatible
                        
                        if is_pair or not compatible_pairs:
                            compatible_proposals.append({
                                "worker_id": wid,
                                "summary": w.current_draft.summary,
                                "display_id": w.display_id
                            })
                
                if not compatible_proposals:
                    continue
                
                yield {"type": "worker_start", "worker_id": worker_id, "stage": "collaboration"}
                
                # Get user guidance from previous collab round feedback (if any)
                user_guidance = None
                prev_collab_feedback = self._collab_feedback.get(collab_round, {})
                if prev_collab_feedback:
                    user_guidance = prev_collab_feedback.get("worker_feedback", {}).get(worker_id)
                
                collab_output = worker.collaborate(
                    compatible_proposals=compatible_proposals,
                    overlap_areas=overlap_areas,
                    merge_strategy=merge_strategy,
                    user_guidance=user_guidance
                )
                collab_outputs[worker_id] = collab_output
                
                self.logger.log(
                    stage=round_label,
                    agent_id=worker_id,
                    input_text=str(compatible_proposals),
                    output_text=str(collab_output),
                    persona_id=worker.persona.id if worker.persona else None,
                    persona_name=worker.persona.name if worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
                
                yield {
                    "type": "worker_complete",
                    "worker_id": worker_id,
                    "collaboration": collab_output,
                    "tokens": worker.get_last_token_usage(),
                    "context_patch": self._emit_context_patch()
                }
            
            self._stage_outputs[f"collaboration_round_{collab_round + 1}"] = collab_outputs
            self._apply_architect_update(
                "collaboration",
                {
                    "round": collab_round + 1,
                    "outputs": collab_outputs,
                    "overlap_areas": overlap_areas,
                    "merge_strategy": merge_strategy,
                    "compatible_pairs": compatible_pairs
                },
                {"stage": "collaboration"}
            )
            yield {
                "type": "stage_complete",
                "stage": round_label,
                "context_patch": self._emit_context_patch()
            }
            
            # Pause for feedback between collaboration rounds (except the last)
            if collab_round < self.collaboration_rounds - 1:
                self._awaiting_collab_feedback = True
                self.current_stage = PipelineStage.AWAITING_COLLAB_FEEDBACK
                yield {
                    "type": "awaiting_collab_feedback",
                    "round": collab_round + 1,
                    "total_rounds": self.collaboration_rounds,
                    "worker_outputs": {
                        wid: {
                            "display_id": w.display_id,
                            "summary": w.current_draft.summary if w.current_draft else None,
                            "collaboration": collab_outputs.get(wid)
                        }
                        for wid, w in self.workers.items()
                    },
                    "context_patch": self._emit_context_patch()
                }
                return  # Pipeline will resume when continue_pipeline is called
    
    def _continue_collaboration(self) -> Generator[Dict[str, Any], None, None]:
        """Continue collaboration rounds after feedback, then proceed to voting."""
        current_collab_round = self._current_collab_round
        compatibility = self._compatibility_result
        overlap_areas = compatibility.get("overlap_areas", [])
        merge_strategy = compatibility.get("merge_strategy", "")
        compatible_pairs = compatibility.get("compatible_pairs", [])
        
        # If user chose to skip - proceed directly to voting
        if self._skip_to_synthesis:
            yield {"type": "info", "message": "Skipping remaining collaboration rounds, proceeding to voting"}
            for event in self._run_voting():
                yield event
            return
        
        # Continue with remaining collaboration rounds
        for collab_round in range(current_collab_round, self.collaboration_rounds):
            self._current_collab_round = collab_round + 1
            self.current_stage = PipelineStage.COLLABORATION
            round_label = f"collaboration_round_{collab_round + 1}"  # Always use indexed format
            yield {"type": "stage_start", "stage": round_label}
            
            collab_outputs = {}
            
            for worker_id, worker in self.workers.items():
                if not worker.current_draft:
                    continue
                
                compatible_proposals = []
                for wid, w in self.workers.items():
                    if wid != worker_id and w.current_draft:
                        is_pair = any(
                            (worker_id in pair and wid in pair)
                            for pair in compatible_pairs
                        ) if compatible_pairs else True
                        
                        if is_pair or not compatible_pairs:
                            compatible_proposals.append({
                                "worker_id": wid,
                                "summary": w.current_draft.summary,
                                "display_id": w.display_id
                            })
                
                if not compatible_proposals:
                    continue
                
                yield {"type": "worker_start", "worker_id": worker_id, "stage": "collaboration"}
                
                user_guidance = None
                prev_collab_feedback = self._collab_feedback.get(collab_round, {})
                if prev_collab_feedback:
                    user_guidance = prev_collab_feedback.get("worker_feedback", {}).get(worker_id)
                
                collab_output = worker.collaborate(
                    compatible_proposals=compatible_proposals,
                    overlap_areas=overlap_areas,
                    merge_strategy=merge_strategy,
                    user_guidance=user_guidance
                )
                collab_outputs[worker_id] = collab_output
                
                self.logger.log(
                    stage=round_label,
                    agent_id=worker_id,
                    input_text=str(compatible_proposals),
                    output_text=str(collab_output),
                    persona_id=worker.persona.id if worker.persona else None,
                    persona_name=worker.persona.name if worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
                
                yield {
                    "type": "worker_complete",
                    "worker_id": worker_id,
                    "collaboration": collab_output,
                    "tokens": worker.get_last_token_usage(),
                    "context_patch": self._emit_context_patch()
                }
            
            self._stage_outputs[f"collaboration_round_{collab_round + 1}"] = collab_outputs
            self._apply_architect_update(
                "collaboration",
                {
                    "round": collab_round + 1,
                    "outputs": collab_outputs,
                    "overlap_areas": overlap_areas,
                    "merge_strategy": merge_strategy,
                    "compatible_pairs": compatible_pairs
                },
                {"stage": "collaboration"}
            )
            yield {
                "type": "stage_complete",
                "stage": round_label,
                "context_patch": self._emit_context_patch()
            }
            
            if collab_round < self.collaboration_rounds - 1:
                self._awaiting_collab_feedback = True
                self.current_stage = PipelineStage.AWAITING_COLLAB_FEEDBACK
                yield {
                    "type": "awaiting_collab_feedback",
                    "round": collab_round + 1,
                    "total_rounds": self.collaboration_rounds,
                    "worker_outputs": {
                        wid: {
                            "display_id": w.display_id,
                            "summary": w.current_draft.summary if w.current_draft else None,
                            "collaboration": collab_outputs.get(wid)
                        }
                        for wid, w in self.workers.items()
                    },
                    "context_patch": self._emit_context_patch()
                }
                return
        
        # All collaboration rounds complete - proceed to voting
        for event in self._run_voting():
            yield event
    
    def _continue_argumentation(self) -> Generator[Dict[str, Any], None, None]:
        """Continue argumentation rounds after feedback."""
        current_arg_round = self._current_arg_round
        
        # If user chose to skip to voting
        if self._skip_to_voting:
            yield {"type": "info", "message": f"Skipping remaining argument rounds, proceeding to voting"}
            # Proceed directly to voting stage
        else:
            # Get previous arguments from stage outputs
            all_arguments = []
            for i in range(1, current_arg_round + 1):
                if f"arguments_round_{i}" in self._stage_outputs:
                    all_arguments.append(self._stage_outputs[f"arguments_round_{i}"])
            
            # Continue with remaining argumentation rounds
            for arg_round in range(current_arg_round, self.argument_rounds):
                self._current_arg_round = arg_round + 1
                round_label = f"argumentation_round_{arg_round + 1}"  # Always use indexed format
                yield {"type": "stage_start", "stage": round_label}
                
                round_arguments = {}
                
                for worker_id, worker in self.workers.items():
                    alternatives = [
                        w.current_draft.summary
                        for wid, w in self.workers.items()
                        if wid != worker_id and w.current_draft
                    ]
                    
                    # Include previous round arguments from other workers for context
                    previous_args = []
                    if all_arguments:
                        prev_round_args = all_arguments[-1]
                        for wid, arg in prev_round_args.items():
                            if wid != worker_id:
                                worker_display = self.workers[wid].display_id
                                previous_args.append({
                                    "worker": worker_display,
                                    "argument": arg.get("main_argument", "")
                                })
                    
                    yield {"type": "worker_start", "worker_id": worker_id, "stage": "argumentation"}
                    
                    # Get user guidance from previous argument round feedback
                    user_guidance = None
                    prev_arg_feedback = self._arg_round_feedback.get(arg_round, {})
                    if prev_arg_feedback:
                        user_guidance = prev_arg_feedback.get("worker_feedback", {}).get(worker_id)
                    
                    argument = worker.argue(alternatives, self.rubric, counter_arguments=previous_args, user_guidance=user_guidance)
                    round_arguments[worker_id] = argument.to_dict()
                    
                    self.logger.log(
                        stage=round_label,
                        agent_id=worker_id,
                        input_text=str(alternatives),
                        output_text=argument.raw_text,
                        persona_id=worker.persona.id if worker.persona else None,
                        persona_name=worker.persona.name if worker.persona else None,
                        memory_usage_mb=self.memory_monitor.get_memory_mb()
                    )
                    
                    yield {
                        "type": "worker_complete",
                        "worker_id": worker_id,
                        "argument": argument.to_dict(),
                        "tokens": worker.get_last_token_usage(),
                        "context_patch": self._emit_context_patch()
                    }
                
                all_arguments.append(round_arguments)
                self._stage_outputs[f"arguments_round_{arg_round + 1}"] = round_arguments
                self._apply_architect_update(
                    "argumentation",
                    {
                        "round": arg_round + 1,
                        "arguments": round_arguments
                    },
                    {"stage": "argumentation"}
                )
                yield {
                    "type": "stage_complete",
                    "stage": round_label,
                    "context_patch": self._emit_context_patch()
                }
                
                # Synthesizer commentary after each round (except the last)
                if arg_round < self.argument_rounds - 1:
                    commentary = self._get_architect_commentary(round_arguments, round_num=arg_round + 1)
                    if commentary:
                        yield {
                            "type": "synth_commentary",
                            "round": arg_round + 1,
                            "content": commentary
                        }
                    
                    # Pause for user feedback between rounds
                    self._awaiting_argument_feedback = True
                    self._current_arg_round = arg_round + 1
                    yield {
                        "type": "awaiting_argument_feedback",
                        "round": arg_round + 1,
                        "total_rounds": self.argument_rounds,
                        "worker_arguments": {
                            wid: {
                                "display_id": w.display_id,
                                "main_argument": round_arguments.get(wid, {}).get("main_argument", ""),
                                "key_strengths": round_arguments.get(wid, {}).get("key_strengths") or [],
                                "critique_of_alternatives": round_arguments.get(wid, {}).get("critique_of_alternatives") or "",
                                "rubric_alignment": round_arguments.get(wid, {}).get("rubric_alignment") or ""
                            }
                            for wid, w in self.workers.items()
                        },
                        "context_patch": self._emit_context_patch()
                    }
                    return
            
            # Store final round arguments for voting
            self._stage_outputs["arguments"] = all_arguments[-1] if all_arguments else {}
        
        for event in self._run_post_argumentation():
            yield event

    def _run_post_argumentation(self) -> Generator[Dict[str, Any], None, None]:
        """Run compatibility check, collaboration, and voting after argumentation."""
        # Stage 3: Compatibility Check (after argumentation, before collaboration)
        self.current_stage = PipelineStage.COMPATIBILITY_CHECK
        yield {"type": "stage_start", "stage": "compatibility_check"}

        refined_proposals = {
            worker_id: {"summary": worker.current_draft.summary}
            for worker_id, worker in self.workers.items()
            if worker.current_draft
        }

        compatibility = self.synthesizer.check_compatibility(refined_proposals)
        self._compatibility_result = compatibility

        synth_tokens = self.synthesizer.get_last_token_usage()
        yield {
            "type": "tokens_update",
            "source": "synthesizer",
            "tokens": synth_tokens,
            "context_limit": self.synth_context_window
        }

        self.logger.log(
            stage="compatibility_check",
            agent_id="synthesizer",
            input_text=str(refined_proposals),
            output_text=str(compatibility),
            memory_usage_mb=self.memory_monitor.get_memory_mb()
        )

        self._apply_architect_update(
            "compatibility_check",
            {
                "compatibility": compatibility,
                "proposals": refined_proposals
            },
            {"stage": "compatibility_check"}
        )

        yield {
            "type": "stage_complete",
            "stage": "compatibility_check",
            "compatibility": compatibility,
            "context_patch": self._emit_context_patch()
        }

        # Stage 4: Collaboration (run for feedback even when proposals diverge)
        if self.collaboration_rounds > 0:
            for event in self._run_collaboration(compatibility):
                yield event

            if self._awaiting_collab_feedback:
                return

        for event in self._run_voting():
            yield event
    
    def _run_voting(self) -> Generator[Dict[str, Any], None, None]:
        """Run the AI and user voting stages."""
        # Stage 6: AI Voting
        self.current_stage = PipelineStage.AI_VOTING
        yield {"type": "stage_start", "stage": "ai_voting"}
        
        # Get candidates
        candidates = self._candidates
        arguments = self._stage_outputs.get("arguments", {})
        
        candidate_arguments = {}
        for candidate in candidates:
            if candidate.source_workers:
                source_worker = candidate.source_workers[0]
                if source_worker in arguments:
                    candidate_arguments[candidate.id] = arguments[source_worker].get("main_argument", "")
            if candidate.id not in candidate_arguments:
                candidate_arguments[candidate.id] = candidate.summary
        
        scores = self.architect.score_all_candidates(candidate_arguments, self.rubric)

        architect_tokens = self.architect.get_last_token_usage()
        yield {
            "type": "tokens_update",
            "source": "architect",
            "tokens": architect_tokens,
            "context_limit": self.architect_context_window
        }
        
        ai_scores = {cid: score.score for cid, score in scores.items()}
        self.voter.set_ai_scores(ai_scores)
        
        self._stage_outputs["ai_scores"] = {cid: s.to_dict() for cid, s in scores.items()}

        self._apply_architect_update(
            "ai_voting",
            {
                "ai_scores": ai_scores,
                "scores": {cid: s.to_dict() for cid, s in scores.items()},
                "candidate_arguments": candidate_arguments,
                "rubric": self.rubric
            },
            {"stage": "ai_voting"}
        )
        
        yield {
            "type": "stage_complete",
            "stage": "ai_voting",
            "scores": {cid: s.to_dict() for cid, s in scores.items()},
            "context_patch": self._emit_context_patch()
        }
        
        # Stage 7: Wait for User Voting
        self.current_stage = PipelineStage.USER_VOTING
        yield {
            "type": "awaiting_user_input",
            "stage": "user_voting",
            "candidates": [c.to_dict() for c in candidates],
            "ai_scores": ai_scores,
            "arguments": arguments,
            "worker_info": self.get_worker_info(),
            "context_patch": self._emit_context_patch()
        }
    
    def run_axiom_analysis(self) -> Generator[Dict[str, Any], None, None]:
        """
        Run axiom analysis - the LAST stage of the pipeline.
        Collects axioms from user feedback, workers, and architect.
        
        Yields:
            Event dicts with axiom collection progress.
        """
        self.current_stage = PipelineStage.AXIOM_ANALYSIS
        yield {"type": "stage_start", "stage": "axiom_analysis"}
        
        # Build conversation summary for context
        conversation_summary = self._build_conversation_summary()
        
        # Step 1: Extract user axioms from feedback history
        yield {"type": "info", "message": "Extracting user axioms from feedback..."}
        
        if self._user_feedback_history:
            user_axiom_result = self.architect.extract_user_axioms(
                feedback_history=self._user_feedback_history,
                context=conversation_summary
            )
            self._user_axioms = user_axiom_result.get("axioms", [])

            architect_tokens = self.architect.get_last_token_usage()
            yield {
                "type": "tokens_update",
                "source": "architect",
                "tokens": architect_tokens,
                "context_limit": self.architect_context_window
            }
            
            self.logger.log(
                stage="user_axiom_extraction",
                agent_id="architect",
                input_text=str(self._user_feedback_history),
                output_text=str(user_axiom_result),
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )
            
            yield {
                "type": "axiom_extracted",
                "source": "user",
                "axioms": self._user_axioms,
                "context_patch": self._emit_context_patch()
            }
        
        # Step 2: Collect worker axioms
        yield {"type": "info", "message": "Collecting worker axioms..."}
        
        for worker_id, worker in self.workers.items():
            if not worker.current_draft:
                continue
            
            yield {"type": "worker_start", "worker_id": worker_id, "stage": "axiom_analysis"}
            
            try:
                worker_axiom_result = worker.analyze_axioms(conversation_summary)
                extracted_axioms = worker_axiom_result.get("axioms", [])
                self._worker_axioms[worker_id] = extracted_axioms
                
                # Log warning if no axioms extracted
                if not extracted_axioms or len(extracted_axioms) == 0:
                    import logging
                    logging.warning(
                        f"No axioms extracted from {worker_id}. "
                        f"Theory contribution present: {bool(worker_axiom_result.get('theory_contribution'))}. "
                        f"Raw text length: {len(worker_axiom_result.get('raw_text', ''))}"
                    )
                
                self.logger.log(
                    stage="worker_axiom_analysis",
                    agent_id=worker_id,
                    input_text=conversation_summary,  # Log full summary, not truncated
                    output_text=str(worker_axiom_result),
                    persona_id=worker.persona.id if worker.persona else None,
                    persona_name=worker.persona.name if worker.persona else None,
                    memory_usage_mb=self.memory_monitor.get_memory_mb()
                )
                
                yield {
                    "type": "axiom_extracted",
                    "source": worker_id,
                    "worker_display_id": worker.display_id,
                    "axioms": self._worker_axioms[worker_id],
                    "axiom_count": len(self._worker_axioms[worker_id]),
                    "theory_contribution": worker_axiom_result.get("theory_contribution", ""),
                    "parsing_successful": len(extracted_axioms) > 0,
                    "context_patch": self._emit_context_patch()
                }
            except Exception as e:
                import logging
                logging.error(f"Error extracting axioms from {worker_id}: {e}", exc_info=True)
                self._worker_axioms[worker_id] = []
                yield {
                    "type": "axiom_extraction_error",
                    "source": worker_id,
                    "worker_display_id": worker.display_id,
                    "error": str(e),
                    "axioms": [],
                    "context_patch": self._emit_context_patch()
                }
        
        # Step 3: Synthesizer builds axiom network
        yield {"type": "info", "message": "Building axiom network..."}
        
        network_result = self.architect.analyze_axiom_network(
            user_axioms=self._user_axioms,
            worker_axioms=self._worker_axioms,
            discussion_summary=conversation_summary
        )
        self._axiom_network = network_result

        architect_tokens = self.architect.get_last_token_usage()
        yield {
            "type": "tokens_update",
            "source": "architect",
            "tokens": architect_tokens,
            "context_limit": self.architect_context_window
        }
        
        self.logger.log(
            stage="axiom_network",
            agent_id="architect",
            input_text=f"user_axioms={len(self._user_axioms)}, worker_axioms={sum(len(a) for a in self._worker_axioms.values())}",
            output_text=str(network_result),
            memory_usage_mb=self.memory_monitor.get_memory_mb()
        )
        
        # Build and save the AxiomNetwork
        from .models.axiom import (
            AxiomNetwork, AxiomNode, AxiomSource, AxiomSourceType,
            SessionContext, generate_axiom_id
        )
        
        # Create session context
        personas_used = [
            {"id": w.persona.id, "name": w.persona.name}
            for w in self.workers.values() if w.persona
        ]
        
        session_context = SessionContext.create(
            session_id=self.session_id,
            prompt=self.prompt,
            ram_mode=self.config.mode.value,
            worker_count=len(self.workers),
            personas=personas_used
        )
        
        # Build network
        axiom_network = AxiomNetwork(session=session_context)
        axiom_counter = {"user": 0, "synth": 0}
        for wid in self.workers:
            axiom_counter[wid] = 0
        
        # Add user axioms
        for axiom_data in self._user_axioms:
            axiom_counter["user"] += 1
            source = AxiomSource.user()
            axiom = AxiomNode(
                axiom_id=generate_axiom_id(self.session_id, source, axiom_counter["user"]),
                statement=axiom_data.get("statement", str(axiom_data)),
                axiom_type=axiom_data.get("axiom_type", "assumption"),
                source=source,
                session=session_context,
                round_num=1,
                confidence=float(axiom_data.get("confidence", 0.8))
            )
            axiom_network.add_axiom(axiom)
        
        # Add worker axioms
        for worker_id, axioms in self._worker_axioms.items():
            worker = self.workers.get(worker_id)
            for axiom_data in axioms:
                axiom_counter[worker_id] += 1
                source = AxiomSource.worker(
                    worker_id=worker_id,
                    persona_id=worker.persona.id if worker and worker.persona else None,
                    persona_name=worker.persona.name if worker and worker.persona else None
                )
                axiom = AxiomNode(
                    axiom_id=generate_axiom_id(self.session_id, source, axiom_counter[worker_id]),
                    statement=axiom_data.get("statement", str(axiom_data)),
                    axiom_type=axiom_data.get("axiom_type", "derived"),
                    source=source,
                    session=session_context,
                    round_num=1,
                    confidence=float(axiom_data.get("confidence", 0.7)),
                    vulnerability=axiom_data.get("vulnerability", ""),
                    potential_biases=axiom_data.get("potential_biases", [])
                )
                axiom_network.add_axiom(axiom)
        
        # Add synthesizer meta-axioms
        for axiom_data in network_result.get("meta_axioms", []):
            axiom_counter["synth"] += 1
            source = AxiomSource.synthesizer()
            axiom = AxiomNode(
                axiom_id=generate_axiom_id(self.session_id, source, axiom_counter["synth"]),
                statement=axiom_data.get("statement", str(axiom_data)),
                axiom_type="meta",
                source=source,
                session=session_context,
                round_num=1,
                confidence=float(axiom_data.get("confidence", 0.6))
            )
            axiom_network.add_axiom(axiom)
        
        # Build edges from network analysis
        axiom_network.shared_axioms = network_result.get("shared_axioms", [])
        axiom_network.conflict_clusters = network_result.get("conflicts", [])
        
        # Save axiom network
        axioms_dir = self.base_path / "data" / "axioms"
        axioms_dir.mkdir(parents=True, exist_ok=True)
        axiom_file = axioms_dir / f"{self.session_id}.json"
        axiom_network.save(str(axiom_file))
        
        self._stage_outputs["axiom_network"] = axiom_network.to_mindmap_json()

        self._apply_architect_update(
            "axiom_analysis",
            {
                "user_axioms": self._user_axioms,
                "worker_axioms": self._worker_axioms,
                "meta_axioms": network_result.get("meta_axioms", []),
                "shared_axioms": network_result.get("shared_axioms", []),
                "conflicts": network_result.get("conflicts", []),
                "theories": network_result.get("theories", [])
            },
            {"stage": "axiom_analysis"}
        )
        
        yield {
            "type": "stage_complete",
            "stage": "axiom_analysis",
            "axiom_network": {
                "user_axioms": len(self._user_axioms),
                "worker_axioms": {wid: len(ax) for wid, ax in self._worker_axioms.items()},
                "meta_axioms": len(network_result.get("meta_axioms", [])),
                "shared_axioms": len(network_result.get("shared_axioms", [])),
                "conflicts": len(network_result.get("conflicts", [])),
                "theories": network_result.get("theories", []),
                "file_saved": str(axiom_file)
            },
            "context_patch": self._emit_context_patch()
        }
    
    def _build_shared_context_for_argumentation(self) -> str:
        """
        Build shared context from all workers' refined proposals.
        This is injected into workers before argumentation begins.
        """
        parts = []
        parts.append("=== SHARED REFINED PROPOSALS FROM ALL WORKERS ===\n")
        
        for wid, worker in self.workers.items():
            if not worker.current_draft:
                continue
            
            parts.append(f"\n[{worker.display_id.upper()} - REFINED PROPOSAL]")
            parts.append(worker.current_draft.summary)
            
            # Add key insights from refinement rounds
            if worker.refinements:
                key_changes = []
                for ref in worker.refinements[-2:]:  # Last 2 refinements
                    if getattr(ref, "patch_notes", None):
                        key_changes.extend(ref.patch_notes[:2])
                if key_changes:
                    parts.append(f"\nKey refinements: {'; '.join(key_changes[:3])}")
            
            parts.append("")  # Blank line between workers
        
        parts.append("=== END SHARED CONTEXT ===")
        return "\n".join(parts)
    
    def _build_conversation_summary(self) -> str:
        """Build a comprehensive summary of the conversation for axiom extraction."""
        summary_parts = [f"PROMPT: {self.prompt}"]
        
        # Add constraints and rubric if present
        if self.constraints:
            summary_parts.append(f"\nCONSTRAINTS: {self.constraints}")
        if self.rubric:
            summary_parts.append(f"\nRUBRIC: {self.rubric}")
        
        # Add worker final proposals (use full summaries, not truncated)
        summary_parts.append("\nWORKER PROPOSALS:")
        for wid, w in self.workers.items():
            if w.current_draft:
                # Use full summary - don't truncate! Workers need full context for axiom analysis
                summary_parts.append(f"- {w.display_id} ({wid}): {w.current_draft.summary}")
        
        # Add synthesizer questions and observations
        if "questions" in self._stage_outputs:
            q = self._stage_outputs["questions"]
            summary_parts.append(f"\nSYNTHESIZER OBSERVATIONS: {q.get('overall_observations', '')}")
            if "questions_by_worker" in q:
                summary_parts.append("\nKEY QUESTIONS RAISED:")
                for worker_id, questions in q["questions_by_worker"].items():
                    for q_text in questions[:3]:  # Top 3 questions per worker
                        summary_parts.append(f"  - {q_text}")
        
        # Add argumentation highlights
        if "arguments" in self._stage_outputs:
            args = self._stage_outputs["arguments"]
            summary_parts.append("\nARGUMENTATION HIGHLIGHTS:")
            for wid, arg_data in args.items():
                if isinstance(arg_data, dict) and "main_argument" in arg_data:
                    summary_parts.append(f"- {self.workers[wid].display_id}: {arg_data['main_argument'][:200]}")
        
        # Add collaboration outcomes
        if "collaborations" in self._stage_outputs:
            collabs = self._stage_outputs["collaborations"]
            summary_parts.append("\nCOLLABORATION OUTCOMES:")
            for wid, collab_data in collabs.items():
                if isinstance(collab_data, dict) and "collaborative_summary" in collab_data:
                    summary_parts.append(f"- {self.workers[wid].display_id}: {collab_data['collaborative_summary'][:300]}")
        
        # Add user feedback
        if self._user_feedback_history:
            summary_parts.append("\nUSER FEEDBACK:")
            for fb in self._user_feedback_history[:5]:
                summary_parts.append(f"- Round {fb.get('round')}: {fb.get('feedback', '')}")
        
        return "\n".join(summary_parts)
    
    def _build_full_conversation_context(self) -> str:
        """
        Build comprehensive conversation context for final synthesis.
        This maximizes the synthesizer's context window utilization.
        """
        context_parts = []
        
        # 1. Original prompt
        context_parts.append(f"ORIGINAL PROMPT:\n{self.prompt}")
        
        # 2. Worker proposals and their evolution
        context_parts.append("\n\n--- WORKER REFINEMENT JOURNEY ---")
        for wid, worker in self.workers.items():
            if not worker.current_draft:
                continue
            context_parts.append(f"\n[{worker.display_id}]")
            context_parts.append(f"Final Proposal: {worker.current_draft.summary}")
            
            # Include key refinement changes
            if worker.refinements:
                changes = []
                for ref in worker.refinements[-2:]:  # Last 2 refinements
                    if getattr(ref, "patch_notes", None):
                        changes.extend(ref.patch_notes[:2])
                if changes:
                    context_parts.append(f"Key Changes: {'; '.join(changes[:4])}")
        
        # 3. Argumentation highlights
        context_parts.append("\n\n--- ARGUMENTATION SUMMARY ---")
        for key, value in self._stage_outputs.items():
            if key.startswith("arguments"):
                for wid, arg in value.items():
                    worker = self.workers.get(wid)
                    display = worker.display_id if worker else wid
                    main_arg = arg.get("main_argument", "")[:250]
                    context_parts.append(f"{display}: {main_arg}")
        
        # 4. Collaboration outcomes
        context_parts.append("\n\n--- COLLABORATION OUTCOMES ---")
        for key, value in self._stage_outputs.items():
            if key.startswith("collaboration"):
                for wid, collab in value.items():
                    summary = collab.get("collaborative_summary", "")[:200]
                    if summary:
                        context_parts.append(f"Merged proposal: {summary}")
                        break  # One merged proposal is enough
        
        # 5. User feedback throughout
        context_parts.append("\n\n--- USER FEEDBACK THROUGHOUT ---")
        if self._user_feedback_history:
            for fb in self._user_feedback_history:
                stage = fb.get("stage", "unknown")
                feedback = fb.get("feedback", fb.get("overall", ""))[:200]
                if feedback:
                    context_parts.append(f"[{stage}] {feedback}")
        else:
            context_parts.append("(No user feedback provided)")
        
        # 6. Synthesizer observations
        if "questions" in self._stage_outputs:
            q = self._stage_outputs["questions"]
            obs = q.get("overall_observations", "")
            if obs:
                context_parts.append(f"\n\n--- SYNTHESIZER OBSERVATIONS ---\n{obs}")
        
        return "\n".join(context_parts)
    
    def _build_axiom_summary(self) -> str:
        """Build a summary of axiom analysis for final output."""
        if not self._worker_axioms and not self._user_axioms and not self._axiom_network:
            return "(Axiom analysis not performed)"
        
        summary_parts = []
        
        # Count axioms by source
        user_count = len(self._user_axioms)
        worker_counts = {wid: len(axioms) for wid, axioms in self._worker_axioms.items()}
        total_count = user_count + sum(worker_counts.values())
        
        summary_parts.append(f"Total axioms identified: {total_count}")
        summary_parts.append(f"- From user feedback: {user_count}")
        for wid, count in worker_counts.items():
            worker = self.workers.get(wid)
            display = worker.display_id if worker else wid
            summary_parts.append(f"- From {display}: {count}")
        
        # Key shared axioms from network
        if self._axiom_network:
            shared = self._axiom_network.get("shared_axioms", [])
            if shared:
                summary_parts.append("\nShared beliefs across workers:")
                for ax in shared[:3]:
                    stmt = ax.get("statement", str(ax))[:150]
                    summary_parts.append(f"  • {stmt}")
            
            # Conflicts
            conflicts = self._axiom_network.get("conflicts", [])
            if conflicts:
                summary_parts.append("\nAreas of disagreement:")
                for c in conflicts[:2]:
                    nature = c.get("nature", "unknown")
                    summary_parts.append(f"  • {nature} conflict identified")
            
            # Theory
            theories = self._axiom_network.get("theories", [])
            if theories:
                theory = theories[0]
                summary_parts.append(f"\nEmerging theory: {theory.get('name', 'Unnamed')}")
                summary_parts.append(f"  {theory.get('summary', '')[:200]}")
        
        return "\n".join(summary_parts)
    
    def _get_architect_commentary(self, round_arguments: Dict[str, Dict], round_num: int = 0) -> str:
        """
        Get synthesizer commentary on the argumentation round.
        
        Args:
            round_arguments: Dict of worker arguments from this round.
            round_num: Current round number for accessing user feedback.
        
        Returns:
            Commentary text summarizing key points and areas of disagreement.
        """
        if not round_arguments:
            return ""
        
        # Build summary of arguments for commentary
        arguments_summary = []
        for worker_id, arg in round_arguments.items():
            worker = self.workers.get(worker_id)
            display_id = worker.display_id if worker else worker_id
            main_arg = arg.get("main_argument", "")
            arguments_summary.append(f"**{display_id}**: {main_arg[:200]}...")
        
        # Collect recent user feedback to pass to synthesizer
        combined_user_feedback = None
        recent_feedback = self._arg_round_feedback.get(round_num, {}).get("worker_feedback", {})
        if recent_feedback:
            feedback_parts = [f"{wid}: {fb}" for wid, fb in recent_feedback.items() if fb]
            if feedback_parts:
                combined_user_feedback = "\n".join(feedback_parts)
        
        # Generate commentary using architect
        commentary = self.architect.generate_argumentation_commentary(
            arguments_summary="\n".join(arguments_summary),
            round_num=round_num or len(self._stage_outputs.get("arguments_rounds", [])) + 1,
            user_feedback=combined_user_feedback
        )
        
        # Log commentary
        self.logger.log(
            stage="synth_commentary",
            agent_id="architect",
            input_text=str(round_arguments),
            output_text=commentary,
            memory_usage_mb=self.memory_monitor.get_memory_mb()
        )
        
        return commentary
    
    def diversify_workers(self) -> Generator[Dict[str, Any], None, None]:
        """
        Run diversify action - workers see each other's proposals and differentiate.
        
        Yields:
            Event dicts with worker progress and outputs.
        """
        if not self.session_id:
            raise ValueError("No active session")
        
        # Check that workers have drafts
        workers_with_drafts = [
            (wid, w) for wid, w in self.workers.items() if w.current_draft
        ]
        
        if len(workers_with_drafts) < 2:
            yield {"type": "error", "message": "Need at least 2 workers with drafts to diversify"}
            return
        
        yield {"type": "stage_start", "stage": "diversify"}
        
        for worker_id, worker in self.workers.items():
            if not worker.current_draft:
                continue
            
            # Gather other workers' proposals
            other_proposals = [
                {
                    "worker_id": wid,
                    "persona_name": w.persona.name if w.persona else None,
                    "summary": w.current_draft.summary
                }
                for wid, w in self.workers.items()
                if wid != worker_id and w.current_draft
            ]
            
            yield {
                "type": "worker_start",
                "worker_id": worker_id,
                "persona": worker.persona.name if worker.persona else "Default",
                "stage": "diversify"
            }
            
            # Check memory
            if self.memory_monitor.should_unload_model():
                yield {"type": "memory_warning", "message": "High memory usage detected"}
            
            # Run diversify
            diversified_draft = worker.diversify(other_proposals)
            
            # Log
            self.logger.log(
                stage="diversify",
                agent_id=worker_id,
                input_text=str(other_proposals),
                output_text=diversified_draft.summary,
                persona_id=worker.persona.id if worker.persona else None,
                persona_name=worker.persona.name if worker.persona else None,
                memory_usage_mb=self.memory_monitor.get_memory_mb()
            )
            
            yield {
                "type": "worker_complete",
                "worker_id": worker_id,
                "diversified": diversified_draft.to_dict(),
                "tokens": worker.get_last_token_usage()
            }
        
        yield {"type": "stage_complete", "stage": "diversify"}
        yield {"type": "complete"}
    
    def get_worker_info(self) -> Dict[str, Dict[str, Any]]:
        """Get worker info with display IDs for voting."""
        return {
            wid: {
                "worker_id": wid,
                "persona_id": w.persona.id if w.persona else None,
                "persona_name": w.persona.name if w.persona else None,
                "display_id": w.display_id
            }
            for wid, w in self.workers.items()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current session status."""
        return {
            "session_id": self.session_id,
            "current_stage": self.current_stage.value,
            "mode": self.config.mode.value,
            "debate_rounds": self.debate_rounds,
            "workers": {
                wid: {
                    "persona_id": w.persona.id if w.persona else None,
                    "persona_name": w.persona.name if w.persona else None,
                    "display_id": w.display_id,
                    "has_draft": w.current_draft is not None,
                    "refinement_count": len(w.refinements),
                    "has_argument": w.argument is not None
                }
                for wid, w in self.workers.items()
            },
            "candidates_count": len(self._candidates),
            "memory": self.memory_monitor.get_status()
        }

    def _build_refinement_payload(self, refinement: Optional[Any]) -> Dict[str, Any]:
        if not refinement:
            return {
                "answers_to_questions": {},
                "patch_notes": [],
                "new_risks": [],
                "new_tradeoffs": []
            }

        refinement_data = refinement.to_dict() if hasattr(refinement, "to_dict") else dict(refinement)
        payload = {
            "answers_to_questions": refinement_data.get("answers_to_questions", {}),
            "patch_notes": refinement_data.get("patch_notes", []),
            "new_risks": refinement_data.get("new_risks", []),
            "new_tradeoffs": refinement_data.get("new_tradeoffs", [])
        }

        if refinement_data.get("updated_summary"):
            payload["updated_summary"] = refinement_data.get("updated_summary")

        return payload

    def _emit_context_patch(self) -> Dict[str, Any]:
        """Emit a JSON-style patch payload for the global context."""
        if not self.global_context:
            return {"patch": [], "context": None}

        current = self.global_context.to_dict()
        previous = self._last_global_snapshot or {}
        patch = list(difflib.ndiff(
            str(previous).splitlines(),
            str(current).splitlines()
        ))
        self._last_global_snapshot = current
        return {"patch": patch, "context": current}

    def _append_global_context(
        self,
        section: str,
        payload: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Append to global context and log the update."""
        if not self.global_context:
            return None

        entry = self.global_context.add_entry(section, payload, provenance)
        if self.logger:
            self.logger.log(
                stage="global_context_update",
                agent_id="system",
                input_text=str(provenance or {}),
                output_text=str(entry),
                memory_usage_mb=self.memory_monitor.get_memory_mb(),
                metadata={"section": section}
            )
        return entry

    def _apply_architect_update(
        self,
        stage: str,
        payload: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Call the architect to update global context entries."""
        if not self.global_context or not self.architect:
            return None

        allowed_sections = set(self.global_context.to_dict().keys())

        update = self.architect.update_global_context(
            stage=stage,
            stage_payload=payload,
            current_context=self.global_context.to_dict(),
            provenance=provenance
        )

        for entry in update.get("entries", []):
            section = entry.get("section")
            entry_payload = entry.get("payload", {})
            entry_provenance = entry.get("provenance", {"stage": stage, "source": "architect"})
            if not section or section not in allowed_sections:
                if self.logger:
                    self.logger.log(
                        stage="global_context_update_skipped",
                        agent_id="architect",
                        input_text=str({"stage": stage, "section": section}),
                        output_text="Skipped unknown global context section",
                        memory_usage_mb=self.memory_monitor.get_memory_mb()
                    )
                continue
            self._append_global_context(section, entry_payload, entry_provenance)

        patch_notes = update.get("patch_notes", [])
        if patch_notes:
            self._append_global_context(
                "patch_notes",
                {"stage": stage, "notes": patch_notes},
                {"stage": stage, "source": "architect"}
            )

        return update
    
    def get_full_state(self) -> Dict[str, Any]:
        """
        Get complete session state for restoring UI after page reload.
        
        Returns:
            Full session state including log entries, candidates, scores, etc.
        """
        # Get log entries from logger
        log_entries = []
        if self.logger:
            for entry in self.logger.get_entries():
                if entry.stage == "global_context_update":
                    continue
                log_entries.append({
                    "timestamp": entry.timestamp,
                    "stage": entry.stage,
                    "workerId": entry.agent_id if entry.agent_id != "user" and entry.agent_id != "synthesizer" else None,
                    "personaName": entry.persona_name,
                    "content": entry.output_text,
                    "type": "info"
                })
        
        # Build full state
        state = {
            "session_id": self.session_id,
            "prompt": self.prompt,
            "current_stage": self.current_stage.value,
            "current_round": self._current_round,
            "total_rounds": self.debate_rounds,
            "awaiting_round_feedback": self._awaiting_round_feedback,
            "mode": self.config.mode.value,
            "log_entries": log_entries,
            "worker_info": self.get_worker_info(),
            "workers": {
                wid: {
                    "id": wid,
                    "persona_id": w.persona.id if w.persona else None,
                    "persona_name": w.persona.name if w.persona else None,
                    "display_id": w.display_id,
                    "draft": w.current_draft.to_dict() if w.current_draft else None,
                    "argument": w.argument.to_dict() if w.argument else None
                }
                for wid, w in self.workers.items()
            }
        }

        if self.global_context:
            state["global_context"] = self.global_context.to_dict()
        
        # Add voting data if in user_voting stage
        if self.current_stage == PipelineStage.USER_VOTING:
            state["candidates"] = self._stage_outputs.get("candidates", [])
            state["ai_scores"] = {
                cid: score.get("score") if isinstance(score, dict) else score 
                for cid, score in self._stage_outputs.get("ai_scores", {}).items()
            }
            state["arguments"] = self._stage_outputs.get("arguments", {})
        
        # Add round feedback state if awaiting
        if self._awaiting_round_feedback:
            state["round_worker_outputs"] = {
                wid: {
                    "display_id": w.display_id,
                    "summary": w.current_draft.summary if w.current_draft else None,
                    "refinement": self._build_refinement_payload(w.refinements[-1] if w.refinements else None)
                }
                for wid, w in self.workers.items()
            }
        
        return state
