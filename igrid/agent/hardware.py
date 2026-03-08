"""Real hardware detection: pynvml → nvidia-smi → CPU-only fallback."""
from __future__ import annotations
import logging
import os
import subprocess

_log = logging.getLogger("igrid.agent.hardware")

class GPUInfo:
    def __init__(self, index: int, model: str, vram_gb: float):
        self.index = index; self.model = model; self.vram_gb = vram_gb
    def to_dict(self): return {"index": self.index, "model": self.model, "vram_gb": self.vram_gb}

def detect_gpus() -> list[GPUInfo]:
    gpus = _detect_via_pynvml()
    if gpus is not None: return gpus
    gpus = _detect_via_nvidia_smi()
    if gpus is not None: return gpus
    _log.warning("No NVIDIA GPU detected. Running CPU-only.")
    return []

def _detect_via_pynvml() -> list[GPUInfo] | None:
    try:
        # nvidia-ml-py provides the pynvml module without the deprecation warning
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        result = []
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes): name = name.decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            result.append(GPUInfo(i, name, round(mem.total / (1024**3), 2)))
        pynvml.nvmlShutdown()
        return result
    except Exception: return None

def _detect_via_nvidia_smi() -> list[GPUInfo] | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            timeout=5, stderr=subprocess.DEVNULL).decode()
        result = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3: continue
            result.append(GPUInfo(int(parts[0]), parts[1], round(float(parts[2]) / 1024, 2)))
        return result if result else None
    except Exception: return None

def gpu_utilization() -> tuple[float, float]:
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        util_sum = vram_used = 0.0
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            util_sum += pynvml.nvmlDeviceGetUtilizationRates(h).gpu
            vram_used += pynvml.nvmlDeviceGetMemoryInfo(h).used / (1024**3)
        pynvml.nvmlShutdown()
        return round(util_sum / max(count, 1), 1), round(vram_used, 2)
    except Exception: return 0.0, 0.0

def cpu_info() -> tuple[int, float]:
    try:
        import psutil
        return os.cpu_count() or 1, round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception: return os.cpu_count() or 1, 0.0
