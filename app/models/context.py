"""
AI Council - Context Management System
Handles context accumulation and management for workers and synthesizer.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class ContextPhase(Enum):
    """Pipeline phases with different context requirements."""
    DRAFT = "draft"
    REFINEMENT = "refinement"      # Isolated per worker
    ARGUMENTATION = "argumentation"  # Shared context begins
    COLLABORATION = "collaboration"  # Shared context continues
    FINAL = "final"                 # Synthesizer compiles everything


@dataclass
class Message:
    """A single message in the context."""
    role: str  # "system", "user", "assistant"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ContextWindow:
    """Manages a context window with token tracking."""
    max_tokens: int
    messages: List[Message] = field(default_factory=list)
    system_prompt: Optional[str] = None
    total_tokens_used: int = 0
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Add a message to the context."""
        self.messages.append(Message(
            role=role,
            content=content,
            metadata=metadata or {}
        ))
    
    def get_messages(self, include_system: bool = True) -> List[Dict[str, str]]:
        """Get messages for API call."""
        result = []
        if include_system and self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        result.extend([m.to_dict() for m in self.messages])
        return result
    
    def get_summary(self, max_chars: int = 2000) -> str:
        """Get a summary of the context for handoff."""
        parts = []
        for msg in self.messages:
            if msg.role == "assistant":
                # Include assistant responses (our outputs)
                parts.append(f"[Response]: {msg.content[:500]}...")
            elif msg.role == "user" and "question" in msg.metadata.get("type", ""):
                parts.append(f"[Question]: {msg.content[:200]}...")
        
        summary = "\n".join(parts)
        return summary[:max_chars] if len(summary) > max_chars else summary
    
    def clear(self) -> None:
        """Clear all messages."""
        self.messages = []
        self.total_tokens_used = 0
    
    def update_tokens(self, prompt_tokens: int, output_tokens: int) -> None:
        """Update token tracking."""
        self.total_tokens_used = prompt_tokens + output_tokens


class ContextManager:
    """
    Manages context for all agents in a session.
    
    Context Flow:
    1. REFINEMENT: Each worker has isolated context (draft + synth questions + refinements)
    2. ARGUMENTATION: Workers see their proposal + shared argument context
    3. COLLABORATION: All workers share merged context
    4. FINAL: Synthesizer gets everything
    """
    
    def __init__(
        self,
        worker_context_limit: int = 4096,
        synth_context_limit: int = 8192
    ):
        self.worker_context_limit = worker_context_limit
        self.synth_context_limit = synth_context_limit
        
        # Per-worker contexts (isolated during refinement)
        self.worker_contexts: Dict[str, ContextWindow] = {}
        
        # Synthesizer context
        self.synth_context: ContextWindow = ContextWindow(max_tokens=synth_context_limit)
        
        # Shared context (used during argumentation/collaboration)
        self.shared_context: ContextWindow = ContextWindow(max_tokens=max(worker_context_limit, synth_context_limit))
        
        # Current phase
        self.current_phase: ContextPhase = ContextPhase.DRAFT
        
        # Token usage tracking
        self.worker_tokens: Dict[str, Dict[str, int]] = {}
        self.synth_tokens: Dict[str, int] = {"input": 0, "output": 0, "total": 0}
    
    def initialize_worker(self, worker_id: str, system_prompt: str) -> None:
        """Initialize context for a worker."""
        self.worker_contexts[worker_id] = ContextWindow(
            max_tokens=self.worker_context_limit,
            system_prompt=system_prompt
        )
        self.worker_tokens[worker_id] = {"input": 0, "output": 0, "total": 0}
    
    def set_synth_system(self, system_prompt: str) -> None:
        """Set synthesizer system prompt."""
        self.synth_context.system_prompt = system_prompt
    
    def get_worker_context(self, worker_id: str) -> ContextWindow:
        """Get a worker's context window."""
        if worker_id not in self.worker_contexts:
            raise ValueError(f"Worker {worker_id} not initialized")
        return self.worker_contexts[worker_id]
    
    def add_worker_message(
        self,
        worker_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """Add message to worker's context."""
        ctx = self.get_worker_context(worker_id)
        ctx.add_message(role, content, metadata)
    
    def add_synth_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """Add message to synthesizer's context."""
        self.synth_context.add_message(role, content, metadata)
    
    def add_shared_message(
        self,
        role: str,
        content: str,
        source: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """Add message to shared context (used during argumentation/collaboration)."""
        meta = metadata or {}
        meta["source"] = source
        self.shared_context.add_message(role, content, meta)
    
    def get_worker_messages_for_call(
        self,
        worker_id: str,
        include_shared: bool = False
    ) -> List[Dict[str, str]]:
        """Get messages for a worker API call."""
        ctx = self.get_worker_context(worker_id)
        messages = ctx.get_messages(include_system=True)
        
        if include_shared and self.shared_context.messages:
            # Inject shared context summary before the last message
            shared_summary = self.shared_context.get_summary()
            if shared_summary and len(messages) > 1:
                shared_msg = {
                    "role": "user",
                    "content": f"[SHARED CONTEXT FROM OTHER WORKERS]\n{shared_summary}\n[END SHARED CONTEXT]"
                }
                messages.insert(-1, shared_msg)
        
        return messages
    
    def get_synth_messages_for_call(self) -> List[Dict[str, str]]:
        """Get messages for synthesizer API call."""
        return self.synth_context.get_messages(include_system=True)
    
    def transition_to_phase(self, phase: ContextPhase) -> None:
        """Transition to a new pipeline phase."""
        self.current_phase = phase
        
        if phase == ContextPhase.ARGUMENTATION:
            # Build shared context from all worker refinements
            for worker_id, ctx in self.worker_contexts.items():
                summary = ctx.get_summary(max_chars=1000)
                if summary:
                    self.shared_context.add_message(
                        "user",
                        f"[{worker_id.upper()} REFINED PROPOSAL]\n{summary}",
                        {"source": worker_id, "type": "refinement_summary"}
                    )
    
    def update_worker_tokens(
        self,
        worker_id: str,
        prompt_tokens: int,
        output_tokens: int
    ) -> None:
        """Update token tracking for a worker."""
        if worker_id in self.worker_tokens:
            self.worker_tokens[worker_id]["input"] += prompt_tokens
            self.worker_tokens[worker_id]["output"] += output_tokens
            self.worker_tokens[worker_id]["total"] += prompt_tokens + output_tokens
        
        if worker_id in self.worker_contexts:
            self.worker_contexts[worker_id].update_tokens(prompt_tokens, output_tokens)
    
    def update_synth_tokens(self, prompt_tokens: int, output_tokens: int) -> None:
        """Update token tracking for synthesizer."""
        self.synth_tokens["input"] += prompt_tokens
        self.synth_tokens["output"] += output_tokens
        self.synth_tokens["total"] += prompt_tokens + output_tokens
        self.synth_context.update_tokens(prompt_tokens, output_tokens)
    
    def get_worker_token_stats(self, worker_id: str) -> Dict[str, int]:
        """Get token stats for a worker."""
        ctx = self.get_worker_context(worker_id)
        return {
            "input_tokens": self.worker_tokens.get(worker_id, {}).get("input", 0),
            "output_tokens": self.worker_tokens.get(worker_id, {}).get("output", 0),
            "total_tokens": self.worker_tokens.get(worker_id, {}).get("total", 0),
            "context_used": ctx.total_tokens_used,
            "context_limit": self.worker_context_limit
        }
    
    def get_synth_token_stats(self) -> Dict[str, int]:
        """Get token stats for synthesizer."""
        return {
            "input_tokens": self.synth_tokens["input"],
            "output_tokens": self.synth_tokens["output"],
            "total_tokens": self.synth_tokens["total"],
            "context_used": self.synth_context.total_tokens_used,
            "context_limit": self.synth_context_limit
        }
    
    def build_final_context_for_synth(self) -> str:
        """Build complete context for final synthesis."""
        parts = []
        
        # Add each worker's full refinement journey
        for worker_id, ctx in self.worker_contexts.items():
            parts.append(f"=== {worker_id.upper()} REFINEMENT HISTORY ===")
            parts.append(ctx.get_summary(max_chars=1500))
            parts.append("")
        
        # Add shared argumentation/collaboration context
        if self.shared_context.messages:
            parts.append("=== ARGUMENTATION & COLLABORATION ===")
            parts.append(self.shared_context.get_summary(max_chars=2000))
        
        return "\n".join(parts)

