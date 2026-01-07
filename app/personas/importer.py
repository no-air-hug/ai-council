"""
AI Council - Raw Text Importer
Imports and categorizes raw text for persona extraction.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from ..models.runtime import OllamaRuntime
from ..config import OllamaConfig


@dataclass
class RawTextImport:
    """A raw text import for persona extraction."""
    id: str
    filename: str
    content: str
    imported_at: str
    status: str  # pending, analyzed, extracted, completed
    analysis: Optional[Dict[str, Any]] = None
    extracted_personas: Optional[List[Dict[str, Any]]] = None


class PersonaImporter:
    """
    Handles importing raw text and extracting personas using LLM analysis.
    
    Workflow:
    1. Import raw JSON text
    2. Analyze text to identify distinct personas/styles
    3. Extract characteristics per persona
    4. Generate system prompts
    5. User review and approval
    """
    
    ANALYSIS_PROMPT = """Analyze the following text and identify distinct personas, writing styles, or thinking patterns.

For each distinct persona you identify, provide:
1. A suggested name
2. Key characteristics (3-5 bullet points)
3. Reasoning style (structured, lateral, critical, or intuitive)
4. Tone (formal, casual, technical, or conversational)

Text to analyze:
{text}

Respond in JSON format:
{{
  "personas": [
    {{
      "name": "persona name",
      "characteristics": ["trait 1", "trait 2", ...],
      "reasoning_style": "structured|lateral|critical|intuitive",
      "tone": "formal|casual|technical|conversational",
      "evidence": "brief quote or example from text"
    }}
  ]
}}"""

    PROMPT_GENERATION_TEMPLATE = """Based on these characteristics, generate a system prompt for an AI assistant:

Name: {name}
Characteristics: {characteristics}
Reasoning Style: {reasoning_style}
Tone: {tone}

Generate a system prompt that will make the AI embody this persona consistently.
The prompt should be 2-4 paragraphs and include specific instructions about:
- How to approach problems
- What to prioritize
- How to communicate
- Any unique perspectives to bring

Respond with only the system prompt text, no other commentary."""

    def __init__(self, base_path: Path, ollama_config: OllamaConfig):
        """
        Initialize persona importer.
        
        Args:
            base_path: Base path for data storage.
            ollama_config: Ollama configuration.
        """
        self.base_path = Path(base_path)
        self.imports_dir = self.base_path / "data" / "personas" / "raw_imports"
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        
        self.runtime = OllamaRuntime(ollama_config)
        self._imports: Dict[str, RawTextImport] = {}
    
    def import_json_file(self, filepath: Path) -> RawTextImport:
        """
        Import a JSON file for persona extraction.
        
        Args:
            filepath: Path to JSON file.
        
        Returns:
            RawTextImport record.
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to parse as JSON and extract text
        try:
            data = json.loads(content)
            # Handle various JSON structures
            if isinstance(data, str):
                text_content = data
            elif isinstance(data, list):
                text_content = "\n\n".join(str(item) for item in data)
            elif isinstance(data, dict):
                # Try common keys
                for key in ['text', 'content', 'body', 'data']:
                    if key in data:
                        text_content = str(data[key])
                        break
                else:
                    text_content = json.dumps(data, indent=2)
            else:
                text_content = str(data)
        except json.JSONDecodeError:
            text_content = content
        
        import_record = RawTextImport(
            id=str(uuid.uuid4()),
            filename=filepath.name,
            content=text_content,
            imported_at=datetime.utcnow().isoformat() + "Z",
            status="pending"
        )
        
        # Save import record
        self._imports[import_record.id] = import_record
        self._save_import(import_record)
        
        return import_record
    
    def import_text(self, text: str, name: str = "manual_import") -> RawTextImport:
        """
        Import raw text directly.
        
        Args:
            text: Raw text content.
            name: Name for the import.
        
        Returns:
            RawTextImport record.
        """
        import_record = RawTextImport(
            id=str(uuid.uuid4()),
            filename=name,
            content=text,
            imported_at=datetime.utcnow().isoformat() + "Z",
            status="pending"
        )
        
        self._imports[import_record.id] = import_record
        self._save_import(import_record)
        
        return import_record
    
    def _save_import(self, import_record: RawTextImport):
        """Save an import record to disk."""
        filepath = self.imports_dir / f"{import_record.id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(import_record), f, indent=2, ensure_ascii=False)
    
    def analyze_text(self, import_id: str, model: str = "qwen2.5:7b") -> Dict[str, Any]:
        """
        Analyze imported text to identify personas.
        
        Args:
            import_id: ID of the import to analyze.
            model: Model to use for analysis.
        
        Returns:
            Analysis results.
        """
        import_record = self._imports.get(import_id)
        if not import_record:
            raise ValueError(f"Import not found: {import_id}")
        
        # Truncate text if too long
        text = import_record.content[:8000]  # Limit to ~2K tokens
        
        prompt = self.ANALYSIS_PROMPT.format(text=text)
        
        result = self.runtime.generate(
            model=model,
            prompt=prompt,
            max_tokens=1000,
            temperature=0.3,
            format_json=True
        )
        
        try:
            analysis = json.loads(result.text)
        except json.JSONDecodeError:
            analysis = {"personas": [], "raw_response": result.text}
        
        import_record.analysis = analysis
        import_record.status = "analyzed"
        self._save_import(import_record)
        
        return analysis
    
    def generate_system_prompts(
        self,
        import_id: str,
        model: str = "qwen2.5:7b"
    ) -> List[Dict[str, Any]]:
        """
        Generate system prompts for identified personas.
        
        Args:
            import_id: ID of the import.
            model: Model to use for generation.
        
        Returns:
            List of persona data with generated prompts.
        """
        import_record = self._imports.get(import_id)
        if not import_record or not import_record.analysis:
            raise ValueError("Import not found or not analyzed")
        
        personas = import_record.analysis.get("personas", [])
        extracted = []
        
        for persona_data in personas:
            prompt = self.PROMPT_GENERATION_TEMPLATE.format(
                name=persona_data.get("name", "Unknown"),
                characteristics=", ".join(persona_data.get("characteristics", [])),
                reasoning_style=persona_data.get("reasoning_style", "structured"),
                tone=persona_data.get("tone", "formal")
            )
            
            result = self.runtime.generate(
                model=model,
                prompt=prompt,
                max_tokens=500,
                temperature=0.5
            )
            
            extracted.append({
                "name": persona_data.get("name"),
                "system_prompt": result.text.strip(),
                "reasoning_style": persona_data.get("reasoning_style", "structured"),
                "tone": persona_data.get("tone", "formal"),
                "source_text_id": import_id,
                "characteristics": persona_data.get("characteristics", []),
                "evidence": persona_data.get("evidence", "")
            })
        
        import_record.extracted_personas = extracted
        import_record.status = "extracted"
        self._save_import(import_record)
        
        return extracted
    
    def get_import(self, import_id: str) -> Optional[RawTextImport]:
        """Get an import record by ID."""
        return self._imports.get(import_id)
    
    def list_imports(self) -> List[Dict[str, Any]]:
        """List all imports."""
        # Load from disk if not in cache
        for filepath in self.imports_dir.glob("*.json"):
            if filepath.stem not in self._imports:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self._imports[data["id"]] = RawTextImport(**data)
                except Exception:
                    pass
        
        return [
            {
                "id": imp.id,
                "filename": imp.filename,
                "imported_at": imp.imported_at,
                "status": imp.status,
                "persona_count": len(imp.extracted_personas or [])
            }
            for imp in self._imports.values()
        ]


