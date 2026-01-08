"""
AI Council - Configuration Management
Handles 16GB/32GB mode detection and configuration loading.
"""

import os
import yaml
import psutil
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class RAMMode(Enum):
    """Available RAM modes."""
    MODE_16GB = "16GB"
    MODE_32GB = "32GB"


@dataclass
class WorkerConfig:
    """Worker agent configuration."""
    count: int
    model: str
    context_window: int
    max_output_tokens: int


@dataclass
class SynthesizerConfig:
    """Synthesizer agent configuration."""
    model: str
    context_window: int
    max_output_tokens: int


@dataclass
class ArchitectConfig:
    """Architect agent configuration."""
    model: str
    context_window: int
    max_output_tokens: int


@dataclass
class EngineerConfig:
    """Engineer agent configuration."""
    model: str
    context_window: int
    max_output_tokens: int


@dataclass
class TokenLimits:
    """Token limits for various stages."""
    worker_draft: int
    synth_questions: int
    refinement: int
    candidate_synthesis: int
    argumentation: int


@dataclass
class MemoryConfig:
    """Memory management configuration."""
    system_reserved_gb: int
    model_unloading: str
    max_ram_usage_percent: int


@dataclass
class PipelineConfig:
    """Pipeline execution configuration."""
    refinement_loops: int
    argumentation_rounds: int = 1  # Number of argument/counter-argument rounds
    collaboration_rounds: int = 1  # Number of collaboration rounds when compatible
    axiom_rounds: int = 1  # Number of axiom analysis rounds (LAST stage)
    require_structured_output: bool = True
    refinement_similarity_threshold: float = 0.92


@dataclass
class OllamaConfig:
    """Ollama runtime configuration."""
    base_url: str
    timeout: int
    retry_attempts: int
    retry_delay: int


@dataclass
class ModeConfig:
    """Complete mode-specific configuration."""
    mode_name: str
    description: str
    workers: WorkerConfig
    synthesizer: SynthesizerConfig
    architect: ArchitectConfig
    engineer: EngineerConfig
    token_limits: TokenLimits
    memory: MemoryConfig
    pipeline: PipelineConfig


@dataclass 
class AppConfig:
    """Complete application configuration."""
    mode: RAMMode
    mode_config: ModeConfig
    ollama: OllamaConfig
    default_personas: list
    base_path: Path = field(default_factory=lambda: Path.cwd())
    
    @property
    def data_dir(self) -> Path:
        return self.base_path / "data"
    
    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"
    
    @property
    def personas_file(self) -> Path:
        return self.data_dir / "personas" / "personas.json"
    
    @property
    def raw_imports_dir(self) -> Path:
        return self.data_dir / "personas" / "raw_imports"


class ConfigManager:
    """
    Manages configuration loading and RAM mode detection.
    
    Priority for RAM mode:
    1. Command-line argument (--ram-mode)
    2. Environment variable (AI_COUNCIL_RAM_MODE)
    3. Auto-detection from system RAM
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.cwd()
        self.config_dir = self.base_path / "config"
        self._config: Optional[AppConfig] = None
    
    def detect_ram_mode(self) -> RAMMode:
        """
        Detect appropriate RAM mode based on priority:
        1. Environment variable
        2. Auto-detection from system RAM
        """
        # Check environment variable
        env_mode = os.environ.get("AI_COUNCIL_RAM_MODE", "").upper()
        if env_mode == "32GB":
            return RAMMode.MODE_32GB
        elif env_mode == "16GB":
            return RAMMode.MODE_16GB
        
        # Auto-detect from system RAM
        total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        if total_ram_gb >= 28:  # Allow some margin
            return RAMMode.MODE_32GB
        else:
            return RAMMode.MODE_16GB
    
    def load_yaml(self, filepath: Path) -> Dict[str, Any]:
        """Load a YAML configuration file."""
        if not filepath.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def load_mode_config(self, mode: RAMMode) -> ModeConfig:
        """Load mode-specific configuration."""
        mode_file = self.config_dir / "modes" / f"{mode.value.lower()}.yaml"
        data = self.load_yaml(mode_file)
        
        return ModeConfig(
            mode_name=data["mode_name"],
            description=data["description"],
            workers=WorkerConfig(**data["workers"]),
            synthesizer=SynthesizerConfig(**data["synthesizer"]),
            architect=ArchitectConfig(**data["architect"]),
            engineer=EngineerConfig(**data["engineer"]),
            token_limits=TokenLimits(**data["token_limits"]),
            memory=MemoryConfig(**data["memory"]),
            pipeline=PipelineConfig(**data["pipeline"])
        )
    
    def load_default_config(self) -> Dict[str, Any]:
        """Load default configuration."""
        default_file = self.config_dir / "default.yaml"
        return self.load_yaml(default_file)
    
    def load(self, mode: Optional[RAMMode] = None) -> AppConfig:
        """
        Load complete application configuration.
        
        Args:
            mode: Optional RAM mode override. If not provided, auto-detects.
        
        Returns:
            Complete AppConfig instance.
        """
        # Determine RAM mode
        if mode is None:
            mode = self.detect_ram_mode()
        
        # Load configurations
        default = self.load_default_config()
        mode_config = self.load_mode_config(mode)
        
        # Build OllamaConfig
        ollama_config = OllamaConfig(**default["ollama"])
        
        # Create AppConfig
        self._config = AppConfig(
            mode=mode,
            mode_config=mode_config,
            ollama=ollama_config,
            default_personas=default.get("default_personas", []),
            base_path=self.base_path
        )
        
        return self._config
    
    @property
    def config(self) -> AppConfig:
        """Get current configuration, loading if necessary."""
        if self._config is None:
            return self.load()
        return self._config
    
    def get_mode_summary(self) -> Dict[str, Any]:
        """Get a summary of current mode configuration for the UI."""
        config = self.config
        return {
            "mode": config.mode.value,
            "description": config.mode_config.description,
            "worker_count": config.mode_config.workers.count,
            "worker_model": config.mode_config.workers.model,
            "synthesizer_model": config.mode_config.synthesizer.model,
            "refinement_loops": config.mode_config.pipeline.refinement_loops,
            "system_ram_gb": round(psutil.virtual_memory().total / (1024 ** 3), 1)
        }
    
    def switch_mode(self, new_mode: RAMMode) -> AppConfig:
        """Switch to a different RAM mode."""
        return self.load(mode=new_mode)


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(base_path: Optional[Path] = None) -> ConfigManager:
    """Get or create the global config manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(base_path)
    return _config_manager


def get_config() -> AppConfig:
    """Get the current application configuration."""
    return get_config_manager().config
