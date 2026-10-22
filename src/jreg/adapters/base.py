from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from jreg.models.schemas import ModelInfo

class ProviderError(Exception):
    def __init__(self, message: str, code: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderTimeoutError(ProviderError):
    def __init__(self, message: str = "Request timed out"):
        super().__init__(message, code="TIMEOUT", retryable=True)

class QuotaExhaustedError(ProviderError):
    def __init__(self, message: str = "Quota exhausted"):
        super().__init__(message, code="QUOTA_EXHAUSTED", retryable=False)

class RateLimitError(ProviderError):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, code="RATE_LIMIT", retryable=True)

class ProviderAdapter(ABC):
    @abstractmethod
    async def chat(self, model: ModelInfo, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        pass

class MockAdapter(ProviderAdapter):
    def __init__(self, behaviors: Optional[Dict[str, Any]] = None):
        self.behaviors = behaviors or {}

    async def chat(self, model: ModelInfo, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        behavior = self.behaviors.get(model.id, "success")
        
        if behavior == "success":
            pass
        elif behavior == "quota_exhausted":
            raise QuotaExhaustedError()
        elif behavior == "rate_limit":
            raise RateLimitError()
        elif behavior == "timeout":
            raise ProviderTimeoutError()
        elif behavior == "error":
            raise ProviderError("Unknown provider error", code="UNKNOWN", retryable=False)
        else:
            raise ProviderError(
                f"Unsupported mock behavior: {behavior}",
                code="INVALID_MOCK_BEHAVIOR",
                retryable=False,
            )

        return {
            "id": f"mock-{model.id}-resp",
            "model": model.id,
            "choices": [{"message": {"role": "assistant", "content": f"Mock response from {model.id}"}}],
            "usage": {"total_tokens": 100}
        }
