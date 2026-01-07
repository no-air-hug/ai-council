"""
AI Council - Ollama Runtime Interface
Handles model loading, unloading, and inference via Ollama.
"""

import json
import time
import requests
from typing import Dict, Any, Optional, Generator, List
from dataclasses import dataclass

from ..config import OllamaConfig


@dataclass
class GenerationResult:
    """Result from a generation request."""
    text: str
    tokens: int                    # Output tokens
    duration_ms: float
    model: str
    prompt_tokens: int = 0         # Input/prompt tokens
    total_tokens: int = 0          # Total tokens used
    context_size: int = 0          # Context window size used


class OllamaRuntime:
    """
    Interface to Ollama for model management and inference.
    
    Handles:
    - Model loading/unloading
    - Chat completions
    - Streaming responses
    - Health checks
    """
    
    def __init__(self, config: OllamaConfig):
        """
        Initialize Ollama runtime.
        
        Args:
            config: Ollama configuration.
        """
        self.base_url = config.base_url.rstrip('/')
        self.timeout = config.timeout
        self.retry_attempts = config.retry_attempts
        self.retry_delay = config.retry_delay
        self._current_model: Optional[str] = None
    
    def check_health(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def list_models(self) -> List[str]:
        """List available models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []
    
    def is_model_available(self, model_name: str) -> bool:
        """Check if a specific model is available."""
        models = self.list_models()
        # Handle both exact match and partial match (e.g., "qwen2.5:3b" matches "qwen2.5:3b-instruct")
        return any(model_name in m or m.startswith(model_name.split(':')[0]) for m in models)
    
    def load_model(self, model_name: str) -> bool:
        """
        Preload a model into memory.
        
        Args:
            model_name: Name of the model to load.
        
        Returns:
            True if successful.
        """
        try:
            # Ollama loads models on first use, but we can warm it up
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "Hello",
                    "options": {"num_predict": 1}
                },
                timeout=self.timeout
            )
            if response.status_code == 200:
                self._current_model = model_name
                return True
        except Exception:
            pass
        return False
    
    def unload_model(self, model_name: Optional[str] = None) -> bool:
        """
        Unload a model from memory.
        
        Args:
            model_name: Model to unload. If None, unloads current model.
        
        Returns:
            True if successful.
        """
        target = model_name or self._current_model
        if not target:
            return True
        
        try:
            # Ollama doesn't have explicit unload, but we can set keep_alive to 0
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": target,
                    "prompt": "",
                    "keep_alive": 0
                },
                timeout=10
            )
            if response.status_code == 200:
                if target == self._current_model:
                    self._current_model = None
                return True
        except Exception:
            pass
        return False
    
    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 300,
        temperature: float = 0.7,
        format_json: bool = False
    ) -> GenerationResult:
        """
        Generate a completion.
        
        Args:
            model: Model name.
            prompt: User prompt.
            system: Optional system prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            format_json: Whether to request JSON output.
        
        Returns:
            GenerationResult with the response.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        return self.chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            format_json=format_json
        )
    
    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.7,
        format_json: bool = False
    ) -> GenerationResult:
        """
        Send a chat completion request.
        
        Args:
            model: Model name.
            messages: List of message dicts with 'role' and 'content'.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            format_json: Whether to request JSON output.
        
        Returns:
            GenerationResult with the response.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature
            }
        }
        
        if format_json:
            payload["format"] = "json"
        
        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout
                )
                duration_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    self._current_model = model
                    
                    # Extract token counts from Ollama response
                    output_tokens = data.get("eval_count", 0)
                    prompt_tokens = data.get("prompt_eval_count", 0)
                    total_tokens = output_tokens + prompt_tokens
                    
                    return GenerationResult(
                        text=data.get("message", {}).get("content", ""),
                        tokens=output_tokens,
                        duration_ms=duration_ms,
                        model=model,
                        prompt_tokens=prompt_tokens,
                        total_tokens=total_tokens,
                        context_size=prompt_tokens + output_tokens
                    )
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    
            except requests.exceptions.Timeout:
                last_error = "Request timeout"
            except requests.exceptions.ConnectionError:
                last_error = "Connection error - is Ollama running?"
            except Exception as e:
                last_error = str(e)
            
            if attempt < self.retry_attempts - 1:
                time.sleep(self.retry_delay)
        
        raise RuntimeError(f"Generation failed after {self.retry_attempts} attempts: {last_error}")
    
    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.7
    ) -> Generator[str, None, None]:
        """
        Send a streaming chat completion request.
        
        Args:
            model: Model name.
            messages: List of message dicts.
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
        
        Yields:
            Chunks of generated text.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                self._current_model = model
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done", False):
                            break
            else:
                raise RuntimeError(f"Streaming failed: HTTP {response.status_code}")
                
        except Exception as e:
            raise RuntimeError(f"Streaming error: {e}")
    
    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a model."""
        try:
            response = requests.post(
                f"{self.base_url}/api/show",
                json={"name": model_name},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None


