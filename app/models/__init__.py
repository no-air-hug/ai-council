"""
AI Council - Model Components
Ollama runtime interface and model registry.
"""

from .runtime import OllamaRuntime
from .registry import ModelRegistry

__all__ = ["OllamaRuntime", "ModelRegistry"]


