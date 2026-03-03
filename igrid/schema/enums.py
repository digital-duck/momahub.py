"""Shared enumerations for i-grid protocol."""
from enum import Enum

class ComputeTier(str, Enum):
    PLATINUM = "PLATINUM"   # >= 60 TPS
    GOLD     = "GOLD"       # >= 30 TPS
    SILVER   = "SILVER"     # >= 15 TPS
    BRONZE   = "BRONZE"     # <  15 TPS

class TaskState(str, Enum):
    PENDING    = "PENDING"
    DISPATCHED = "DISPATCHED"
    IN_FLIGHT  = "IN_FLIGHT"
    FORWARDED  = "FORWARDED"
    COMPLETE   = "COMPLETE"
    FAILED     = "FAILED"

class AgentStatus(str, Enum):
    ONLINE  = "ONLINE"
    BUSY    = "BUSY"
    OFFLINE = "OFFLINE"

def tier_from_tps(tps: float) -> ComputeTier:
    if tps >= 60: return ComputeTier.PLATINUM
    if tps >= 30: return ComputeTier.GOLD
    if tps >= 15: return ComputeTier.SILVER
    return ComputeTier.BRONZE
