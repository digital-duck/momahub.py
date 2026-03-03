"""Cluster / hub-to-hub peering schemas."""
from __future__ import annotations
from pydantic import BaseModel, Field
from igrid.schema.enums import ComputeTier

class PeerCapability(BaseModel):
    tier: ComputeTier
    count: int
    models: list[str] = Field(default_factory=list)

class PeerHandshake(BaseModel):
    hub_id: str
    hub_url: str
    operator_id: str
    capabilities: list[PeerCapability] = Field(default_factory=list)

class PeerHandshakeAck(BaseModel):
    accepted: bool
    hub_id: str
    hub_url: str
    capabilities: list[PeerCapability] = Field(default_factory=list)
    message: str = ""

class PeerCapabilityUpdate(BaseModel):
    hub_id: str
    capabilities: list[PeerCapability] = Field(default_factory=list)

class ClusterStatus(BaseModel):
    this_hub_id: str
    peers: list[dict] = Field(default_factory=list)
