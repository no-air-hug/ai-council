"""
AI Council - Memory Monitoring
Tracks RAM and VRAM usage for mode enforcement.
"""

import psutil
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class MemoryStatus:
    """Current memory status."""
    ram_total_gb: float
    ram_used_gb: float
    ram_available_gb: float
    ram_percent: float
    vram_total_gb: Optional[float]
    vram_used_gb: Optional[float]
    vram_available_gb: Optional[float]
    vram_percent: Optional[float]


class MemoryMonitor:
    """
    Monitors system RAM and GPU VRAM usage.
    
    Provides real-time memory information for:
    - Deciding when to unload models
    - Enforcing mode-specific limits
    - Logging memory stats with sessions
    """
    
    def __init__(self, max_ram_percent: float = 85.0):
        """
        Initialize memory monitor.
        
        Args:
            max_ram_percent: Maximum RAM usage before warnings.
        """
        self.max_ram_percent = max_ram_percent
        self._has_nvidia = self._check_nvidia()
    
    def _check_nvidia(self) -> bool:
        """Check if NVIDIA GPU monitoring is available."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_ram_info(self) -> Dict[str, float]:
        """Get current RAM usage information."""
        mem = psutil.virtual_memory()
        return {
            "total_gb": mem.total / (1024 ** 3),
            "used_gb": mem.used / (1024 ** 3),
            "available_gb": mem.available / (1024 ** 3),
            "percent": mem.percent
        }
    
    def get_vram_info(self) -> Optional[Dict[str, float]]:
        """Get current VRAM usage information (if NVIDIA GPU available)."""
        if not self._has_nvidia:
            return None
        
        try:
            import subprocess
            
            # Get total VRAM
            total_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Get used VRAM
            used_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if total_result.returncode == 0 and used_result.returncode == 0:
                total_mb = float(total_result.stdout.strip())
                used_mb = float(used_result.stdout.strip())
                
                return {
                    "total_gb": total_mb / 1024,
                    "used_gb": used_mb / 1024,
                    "available_gb": (total_mb - used_mb) / 1024,
                    "percent": (used_mb / total_mb) * 100 if total_mb > 0 else 0
                }
        except Exception:
            pass
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get complete memory status."""
        ram = self.get_ram_info()
        vram = self.get_vram_info()
        
        status = {
            "ram": {
                "total_gb": round(ram["total_gb"], 2),
                "used_gb": round(ram["used_gb"], 2),
                "available_gb": round(ram["available_gb"], 2),
                "percent": round(ram["percent"], 1)
            },
            "vram": None,
            "warnings": []
        }
        
        if vram:
            status["vram"] = {
                "total_gb": round(vram["total_gb"], 2),
                "used_gb": round(vram["used_gb"], 2),
                "available_gb": round(vram["available_gb"], 2),
                "percent": round(vram["percent"], 1)
            }
        
        # Add warnings
        if ram["percent"] > self.max_ram_percent:
            status["warnings"].append(f"RAM usage ({ram['percent']:.1f}%) exceeds threshold ({self.max_ram_percent}%)")
        
        if vram and vram["percent"] > 90:
            status["warnings"].append(f"VRAM usage ({vram['percent']:.1f}%) is critically high")
        
        return status
    
    def get_memory_status(self) -> MemoryStatus:
        """Get memory status as a dataclass."""
        ram = self.get_ram_info()
        vram = self.get_vram_info()
        
        return MemoryStatus(
            ram_total_gb=ram["total_gb"],
            ram_used_gb=ram["used_gb"],
            ram_available_gb=ram["available_gb"],
            ram_percent=ram["percent"],
            vram_total_gb=vram["total_gb"] if vram else None,
            vram_used_gb=vram["used_gb"] if vram else None,
            vram_available_gb=vram["available_gb"] if vram else None,
            vram_percent=vram["percent"] if vram else None
        )
    
    def should_unload_model(self, threshold_percent: float = None) -> bool:
        """
        Check if models should be unloaded due to memory pressure.
        
        Args:
            threshold_percent: Optional override for threshold.
        
        Returns:
            True if memory pressure is high and models should be unloaded.
        """
        threshold = threshold_percent or self.max_ram_percent
        ram = self.get_ram_info()
        return ram["percent"] > threshold
    
    def wait_for_memory(self, target_available_gb: float, timeout: int = 30) -> bool:
        """
        Wait for memory to become available.
        
        Args:
            target_available_gb: Target available RAM in GB.
            timeout: Maximum seconds to wait.
        
        Returns:
            True if target reached, False if timeout.
        """
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            ram = self.get_ram_info()
            if ram["available_gb"] >= target_available_gb:
                return True
            time.sleep(0.5)
        
        return False
    
    def get_memory_mb(self) -> int:
        """Get current RAM usage in MB (for logging)."""
        return int(psutil.virtual_memory().used / (1024 ** 2))


