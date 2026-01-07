"""
AI Council - Persona Manager
Handles persona storage, retrieval, and management.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


@dataclass
class Persona:
    """A worker persona definition."""
    id: str
    name: str
    system_prompt: str
    reasoning_style: str  # structured, lateral, critical, intuitive
    tone: str  # formal, casual, technical, conversational
    source_text_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    usage_count: int = 0
    win_rate: float = 0.0
    is_default: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Persona":
        return cls(**data)


class PersonaManager:
    """
    Manages persona storage and retrieval.
    
    Personas are stored in a JSON file and loaded on demand.
    Default personas from config are merged with user-created ones.
    """
    
    def __init__(self, base_path: Path):
        """
        Initialize persona manager.
        
        Args:
            base_path: Base path for data storage.
        """
        self.base_path = Path(base_path)
        self.personas_file = self.base_path / "data" / "personas" / "personas.json"
        self.raw_imports_dir = self.base_path / "data" / "personas" / "raw_imports"
        
        # Ensure directories exist
        self.personas_file.parent.mkdir(parents=True, exist_ok=True)
        self.raw_imports_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache
        self._personas: Optional[Dict[str, Persona]] = None
        self._default_personas: List[Dict[str, Any]] = []
    
    def set_default_personas(self, defaults: List[Dict[str, Any]]):
        """Set default personas from configuration."""
        self._default_personas = defaults
    
    def _load_personas(self) -> Dict[str, Persona]:
        """Load personas from storage."""
        personas = {}
        
        # Load defaults first
        for default in self._default_personas:
            persona = Persona(
                id=default["id"],
                name=default["name"],
                system_prompt=default["system_prompt"],
                reasoning_style=default.get("reasoning_style", "structured"),
                tone=default.get("tone", "formal"),
                is_default=True
            )
            personas[persona.id] = persona
        
        # Load user personas
        if self.personas_file.exists():
            try:
                with open(self.personas_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for p_data in data.get("personas", []):
                        persona = Persona.from_dict(p_data)
                        personas[persona.id] = persona
            except Exception as e:
                print(f"Warning: Could not load personas: {e}")
        
        return personas
    
    def _save_personas(self):
        """Save user personas to storage."""
        if self._personas is None:
            return
        
        # Only save non-default personas
        user_personas = [
            p.to_dict() for p in self._personas.values()
            if not p.is_default
        ]
        
        data = {
            "personas": user_personas,
            "version": "1.0",
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
        
        with open(self.personas_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @property
    def personas(self) -> Dict[str, Persona]:
        """Get all personas (cached)."""
        if self._personas is None:
            self._personas = self._load_personas()
        return self._personas
    
    def get_all_personas(self) -> List[Dict[str, Any]]:
        """Get all personas as a list of dicts."""
        return [p.to_dict() for p in self.personas.values()]
    
    def get_persona(self, persona_id: str) -> Optional[Persona]:
        """Get a specific persona by ID."""
        return self.personas.get(persona_id)
    
    def create_persona(
        self,
        name: str,
        system_prompt: str,
        reasoning_style: str = "structured",
        tone: str = "formal",
        source_text_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new persona.
        
        Args:
            name: Display name.
            system_prompt: System prompt text.
            reasoning_style: Reasoning style.
            tone: Communication tone.
            source_text_id: Optional link to source text.
        
        Returns:
            The created persona as a dict.
        """
        persona = Persona(
            id=str(uuid.uuid4()),
            name=name,
            system_prompt=system_prompt,
            reasoning_style=reasoning_style,
            tone=tone,
            source_text_id=source_text_id,
            is_default=False
        )
        
        self.personas[persona.id] = persona
        self._save_personas()
        
        return persona.to_dict()
    
    def update_persona(self, persona_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update an existing persona.
        
        Args:
            persona_id: ID of persona to update.
            updates: Dict of fields to update.
        
        Returns:
            Updated persona as dict, or None if not found.
        """
        persona = self.personas.get(persona_id)
        if not persona:
            return None
        
        # Don't allow modifying default personas
        if persona.is_default:
            raise ValueError("Cannot modify default personas")
        
        # Apply updates
        allowed_fields = {"name", "system_prompt", "reasoning_style", "tone"}
        for field, value in updates.items():
            if field in allowed_fields:
                setattr(persona, field, value)
        
        self._save_personas()
        return persona.to_dict()
    
    def delete_persona(self, persona_id: str) -> bool:
        """
        Delete a persona.
        
        Args:
            persona_id: ID of persona to delete.
        
        Returns:
            True if deleted, False if not found.
        """
        persona = self.personas.get(persona_id)
        if not persona:
            return False
        
        if persona.is_default:
            raise ValueError("Cannot delete default personas")
        
        del self.personas[persona_id]
        self._save_personas()
        return True
    
    def increment_usage(self, persona_id: str):
        """Increment usage count for a persona."""
        persona = self.personas.get(persona_id)
        if persona:
            persona.usage_count += 1
            self._save_personas()
    
    def update_win_rate(self, persona_id: str, won: bool):
        """
        Update win rate for a persona.
        
        Args:
            persona_id: Persona ID.
            won: Whether the persona won the vote.
        """
        persona = self.personas.get(persona_id)
        if persona:
            # Simple moving average
            total_sessions = persona.usage_count or 1
            current_wins = persona.win_rate * (total_sessions - 1)
            new_wins = current_wins + (1 if won else 0)
            persona.win_rate = new_wins / total_sessions
            self._save_personas()
    
    def get_personas_by_style(self, reasoning_style: str) -> List[Persona]:
        """Get all personas with a specific reasoning style."""
        return [p for p in self.personas.values() if p.reasoning_style == reasoning_style]
    
    def get_top_performers(self, limit: int = 5) -> List[Persona]:
        """Get top performing personas by win rate."""
        sorted_personas = sorted(
            [p for p in self.personas.values() if p.usage_count > 0],
            key=lambda p: p.win_rate,
            reverse=True
        )
        return sorted_personas[:limit]


