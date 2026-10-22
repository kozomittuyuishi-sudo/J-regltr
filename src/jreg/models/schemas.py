from pydantic import BaseModel, Field
from typing import List, Dict, Any
from enum import Enum

class Capability(str, Enum):
    TEXT = "text"
    CODE = "code"
    VISION = "vision"
    TOOLS = "tools"

class ModelStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    QUARANTINED = "quarantined"

class ProviderInfo(BaseModel):
    id: str
    name: str
    is_mock: bool = True

class ModelInfo(BaseModel):
    id: str
    name: str
    provider_id: str
    capabilities: List[Capability]
    priority: int = 10  # Lower is higher priority
    status: ModelStatus = ModelStatus.ENABLED
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RoutingProfile(BaseModel):
    name: str
    preferred_capabilities: List[Capability]
    # Retries are per model, after the first attempt. Keep the total bounded.
    max_retries: int = Field(default=1, ge=0, le=10)
    fallback_enabled: bool = True
