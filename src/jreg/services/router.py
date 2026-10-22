from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from jreg.adapters.base import (
    ProviderAdapter,
    ProviderError,
    ProviderTimeoutError,
    QuotaExhaustedError,
    RateLimitError,
)
from jreg.models.schemas import ModelInfo, ModelStatus, RoutingProfile


@dataclass
class RoutingAttempt:
    """A single adapter call or a candidate skipped before an adapter call."""

    model_id: str
    provider_id: str
    attempt_number: int
    status: str
    error_code: Optional[str] = None
    retryable: bool = False
    message: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Router:
    def __init__(self, models: List[ModelInfo], adapters: Dict[str, ProviderAdapter]):
        self.models = models
        self.adapters = adapters

    def get_candidates(self, profile: RoutingProfile) -> List[ModelInfo]:
        candidates = [
            model
            for model in self.models
            if model.status == ModelStatus.ENABLED
            and all(capability in model.capabilities
                    for capability in profile.preferred_capabilities)
        ]
        # Python's sort is stable, so equal-priority candidates retain registry order.
        return sorted(candidates, key=lambda model: model.priority)

    @staticmethod
    def _classify_error(error: Exception) -> Tuple[str, bool]:
        if isinstance(error, QuotaExhaustedError):
            return "QUOTA_EXHAUSTED", False
        if isinstance(error, RateLimitError):
            return "RATE_LIMIT", True
        if isinstance(error, (ProviderTimeoutError, TimeoutError)):
            return "TIMEOUT", True
        if isinstance(error, ProviderError):
            return error.code, error.retryable
        return "UNEXPECTED_PROVIDER_ERROR", False

    async def route_with_attempts(
        self,
        profile: RoutingProfile,
        messages: List[Dict[str, str]],
    ) -> Tuple[Dict[str, Any], List[RoutingAttempt]]:
        candidates = self.get_candidates(profile)
        attempts: List[RoutingAttempt] = []
        if not candidates:
            error = ProviderError(
                "No eligible models found", code="NO_MODELS", retryable=False
            )
            error.attempts = attempts
            raise error

        last_error: Optional[Exception] = None
        for candidate_index, model in enumerate(candidates):
            adapter = self.adapters.get(model.provider_id)
            if adapter is None:
                attempts.append(
                    RoutingAttempt(
                        model_id=model.id,
                        provider_id=model.provider_id,
                        attempt_number=0,
                        status="skipped",
                        error_code="MISSING_ADAPTER",
                        message=f"No adapter registered for provider {model.provider_id}",
                    )
                )
                last_error = ProviderError(
                    f"No adapter registered for provider {model.provider_id}",
                    code="MISSING_ADAPTER",
                    retryable=False,
                )
            else:
                for attempt_number in range(profile.max_retries + 1):
                    try:
                        response = await adapter.chat(model, messages)
                    except Exception as error:  # Adapter boundaries classify all failures.
                        code, retryable = self._classify_error(error)
                        attempts.append(
                            RoutingAttempt(
                                model_id=model.id,
                                provider_id=model.provider_id,
                                attempt_number=attempt_number + 1,
                                status="failure",
                                error_code=code,
                                retryable=retryable,
                                message=str(error),
                            )
                        )
                        last_error = error if isinstance(error, ProviderError) else ProviderError(
                            str(error), code=code, retryable=retryable
                        )
                        if retryable and attempt_number < profile.max_retries:
                            continue
                        break
                    else:
                        attempts.append(
                            RoutingAttempt(
                                model_id=model.id,
                                provider_id=model.provider_id,
                                attempt_number=attempt_number + 1,
                                status="success",
                            )
                        )
                        return response, attempts

            # Fallback controls moving to a different candidate. A retry remains
            # bounded by max_retries and only occurs for errors classified retryable.
            if not profile.fallback_enabled:
                break
            if candidate_index + 1 < len(candidates):
                continue

        if last_error is None:
            last_error = ProviderError(
                "No model attempt completed", code="ALL_FAILED", retryable=False
            )
        # Expose the trace to task persistence and callers that need diagnostics.
        last_error.attempts = attempts
        raise last_error

    async def route(
        self, profile: RoutingProfile, messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        response, _attempts = await self.route_with_attempts(profile, messages)
        return response
