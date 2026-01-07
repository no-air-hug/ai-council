"""
AI Council - Model Registry
Maps personas and roles to appropriate models based on RAM mode.
"""

from typing import Dict, Optional, List
from dataclasses import dataclass

from ..config import AppConfig, RAMMode


@dataclass
class ModelSpec:
    """Specification for a model."""
    name: str
    context_window: int
    max_output_tokens: int
    quantization: str = "4-bit"


class ModelRegistry:
    """
    Registry for model selection based on role and RAM mode.
    
    Handles:
    - Mode-specific model selection
    - Fallback models
    - Model capability queries
    """
    
    # Recommended models by size category
    MODELS_BY_SIZE = {
        "small": [  # 2-3B, good for 16GB workers
            "qwen2.5:3b",
            "phi3:mini",
            "gemma2:2b",
            "llama3.2:3b"
        ],
        "medium": [  # 3-4B, good for 32GB workers
            "qwen2.5:3b",
            "phi3:mini",
            "llama3.2:3b",
            "mistral:7b"
        ],
        "large": [  # 7-8B, synthesizers
            "qwen2.5:7b",
            "llama3.1:8b",
            "mistral:7b",
            "gemma2:9b"
        ]
    }
    
    def __init__(self, config: AppConfig):
        """
        Initialize model registry.
        
        Args:
            config: Application configuration.
        """
        self.config = config
        self._available_models: Optional[List[str]] = None
    
    def set_available_models(self, models: List[str]):
        """Set the list of available models (from Ollama)."""
        self._available_models = models
    
    def get_worker_model(self) -> ModelSpec:
        """Get the model specification for workers."""
        mode_config = self.config.mode_config
        return ModelSpec(
            name=mode_config.workers.model,
            context_window=mode_config.workers.context_window,
            max_output_tokens=mode_config.workers.max_output_tokens
        )
    
    def get_synthesizer_model(self) -> ModelSpec:
        """Get the model specification for the synthesizer."""
        mode_config = self.config.mode_config
        return ModelSpec(
            name=mode_config.synthesizer.model,
            context_window=mode_config.synthesizer.context_window,
            max_output_tokens=mode_config.synthesizer.max_output_tokens
        )
    
    def get_model_for_role(self, role: str) -> ModelSpec:
        """
        Get model specification for a specific role.
        
        Args:
            role: Role name (worker, synthesizer).
        
        Returns:
            ModelSpec for the role.
        """
        if role == "synthesizer":
            return self.get_synthesizer_model()
        else:
            return self.get_worker_model()
    
    def find_fallback_model(self, target_size: str) -> Optional[str]:
        """
        Find a fallback model if the primary isn't available.
        
        Args:
            target_size: Size category (small, medium, large).
        
        Returns:
            Name of available fallback model, or None.
        """
        if not self._available_models:
            return None
        
        candidates = self.MODELS_BY_SIZE.get(target_size, [])
        for model in candidates:
            # Check for exact or partial match
            for available in self._available_models:
                if model in available or available.startswith(model.split(':')[0]):
                    return available
        
        return None
    
    def get_recommended_models(self) -> Dict[str, List[str]]:
        """Get recommended models for the current mode."""
        if self.config.mode == RAMMode.MODE_16GB:
            return {
                "workers": self.MODELS_BY_SIZE["small"],
                "synthesizer": self.MODELS_BY_SIZE["medium"]
            }
        else:
            return {
                "workers": self.MODELS_BY_SIZE["medium"],
                "synthesizer": self.MODELS_BY_SIZE["large"]
            }
    
    def validate_model_availability(self) -> Dict[str, bool]:
        """
        Validate that required models are available.
        
        Returns:
            Dict mapping role to availability status.
        """
        if not self._available_models:
            return {"workers": False, "synthesizer": False}
        
        worker_model = self.get_worker_model().name
        synth_model = self.get_synthesizer_model().name
        
        def is_available(model_name: str) -> bool:
            return any(
                model_name in m or m.startswith(model_name.split(':')[0])
                for m in self._available_models
            )
        
        return {
            "workers": is_available(worker_model),
            "synthesizer": is_available(synth_model)
        }
    
    def get_context_limit(self, role: str) -> int:
        """Get context window limit for a role."""
        spec = self.get_model_for_role(role)
        return spec.context_window
    
    def get_output_limit(self, role: str) -> int:
        """Get output token limit for a role."""
        spec = self.get_model_for_role(role)
        return spec.max_output_tokens


