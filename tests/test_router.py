import pytest
from pydantic import ValidationError

from jreg.adapters.base import MockAdapter, ProviderError
from jreg.models.schemas import Capability, ModelInfo, ModelStatus, RoutingProfile
from jreg.services.router import Router


@pytest.fixture
def mock_models():
    return [
        ModelInfo(
            id="gpt-4", name="GPT-4", provider_id="openai",
            capabilities=[Capability.TEXT, Capability.TOOLS], priority=1,
        ),
        ModelInfo(
            id="gpt-3.5", name="GPT-3.5", provider_id="openai",
            capabilities=[Capability.TEXT], priority=2,
        ),
        ModelInfo(
            id="claude-3", name="Claude 3", provider_id="anthropic",
            capabilities=[Capability.TEXT, Capability.TOOLS], priority=1,
        ),
    ]


def profile(**kwargs):
    return RoutingProfile(
        name="default", preferred_capabilities=[Capability.TEXT], **kwargs
    )


def adapters(behaviors=None):
    adapter = MockAdapter(behaviors=behaviors)
    return {"openai": adapter, "anthropic": adapter}


@pytest.mark.asyncio
async def test_router_success_and_attempt_record(mock_models):
    router = Router(mock_models, adapters())
    response, attempts = await router.route_with_attempts(
        profile(), [{"role": "user", "content": "hello"}]
    )
    assert response["model"] == "gpt-4"
    assert [(a.model_id, a.status, a.attempt_number) for a in attempts] == [
        ("gpt-4", "success", 1)
    ]


@pytest.mark.asyncio
async def test_quota_exhaustion_falls_back_and_records_each_model(mock_models):
    router = Router(mock_models, adapters({"gpt-4": "quota_exhausted"}))
    response, attempts = await router.route_with_attempts(
        profile(), [{"role": "user", "content": "hello"}]
    )
    assert response["model"] == "claude-3"
    assert [(a.model_id, a.error_code, a.status) for a in attempts] == [
        ("gpt-4", "QUOTA_EXHAUSTED", "failure"),
        ("claude-3", None, "success"),
    ]


@pytest.mark.asyncio
async def test_rate_limit_retries_up_to_configured_limit_then_falls_back(mock_models):
    router = Router(mock_models, adapters({"gpt-4": "rate_limit"}))
    response, attempts = await router.route_with_attempts(
        profile(max_retries=2), [{"role": "user", "content": "hello"}]
    )
    assert response["model"] == "claude-3"
    assert [(a.model_id, a.attempt_number, a.error_code) for a in attempts[:3]] == [
        ("gpt-4", 1, "RATE_LIMIT"),
        ("gpt-4", 2, "RATE_LIMIT"),
        ("gpt-4", 3, "RATE_LIMIT"),
    ]


@pytest.mark.asyncio
async def test_no_fallback_tries_first_model_only(mock_models):
    router = Router(mock_models, adapters({"gpt-4": "quota_exhausted"}))
    with pytest.raises(ProviderError) as raised:
        await router.route_with_attempts(
            profile(fallback_enabled=False), [{"role": "user", "content": "hello"}]
        )
    assert raised.value.code == "QUOTA_EXHAUSTED"
    assert [attempt.model_id for attempt in raised.value.attempts] == ["gpt-4"]


@pytest.mark.asyncio
async def test_max_retries_zero_makes_exactly_one_call(mock_models):
    router = Router(mock_models, adapters({"gpt-4": "timeout"}))
    _response, attempts = await router.route_with_attempts(
        profile(max_retries=0), [{"role": "user", "content": "hello"}]
    )
    assert [a.model_id for a in attempts] == ["gpt-4", "claude-3"]
    assert attempts[0].error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_capabilities_disabled_models_and_stable_priority(mock_models):
    mock_models.extend([
        ModelInfo(
            id="disabled", name="Disabled", provider_id="openai",
            capabilities=[Capability.TEXT], priority=0, status=ModelStatus.DISABLED,
        ),
        ModelInfo(
            id="code-only", name="Code", provider_id="openai",
            capabilities=[Capability.CODE], priority=0,
        ),
        ModelInfo(
            id="equal-priority", name="Equal", provider_id="openai",
            capabilities=[Capability.TEXT], priority=1,
        ),
    ])
    router = Router(mock_models, adapters())
    candidates = router.get_candidates(profile())
    assert [model.id for model in candidates] == [
        "gpt-4", "claude-3", "equal-priority", "gpt-3.5"
    ]
    assert "disabled" not in [model.id for model in candidates]
    assert "code-only" not in [model.id for model in candidates]


@pytest.mark.asyncio
async def test_missing_adapter_is_recorded_and_falls_back(mock_models):
    router = Router(mock_models, {"anthropic": MockAdapter()})
    response, attempts = await router.route_with_attempts(
        profile(), [{"role": "user", "content": "hello"}]
    )
    assert response["model"] == "claude-3"
    assert attempts[0].error_code == "MISSING_ADAPTER"
    assert attempts[0].status == "skipped"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("behavior", "code", "retryable"),
    [
        ("quota_exhausted", "QUOTA_EXHAUSTED", False),
        ("rate_limit", "RATE_LIMIT", True),
        ("timeout", "TIMEOUT", True),
        ("error", "UNKNOWN", False),
        ("not-a-real-mode", "INVALID_MOCK_BEHAVIOR", False),
    ],
)
async def test_mock_failure_scenarios(mock_models, behavior, code, retryable):
    router = Router(mock_models[:1], {"openai": MockAdapter({"gpt-4": behavior})})
    with pytest.raises(ProviderError) as raised:
        await router.route_with_attempts(
            profile(max_retries=1), [{"role": "user", "content": "hello"}]
        )
    assert raised.value.code == code
    assert raised.value.attempts[0].retryable is retryable
    expected_count = 2 if retryable else 1
    assert len(raised.value.attempts) == expected_count


@pytest.mark.asyncio
async def test_task_manager_persists_each_routing_outcome(mock_models):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from jreg.models.db import Base, ModelAttempt
    from jreg.services.task_manager import TaskManager

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        manager = TaskManager(
            session,
            Router(mock_models, adapters({"gpt-4": "quota_exhausted"})),
        )
        task = manager.create_task("test continuity record")
        await manager.run_task(task.id, profile())
        records = (
            session.query(ModelAttempt)
            .filter(ModelAttempt.task_id == task.id)
            .order_by(ModelAttempt.id)
            .all()
        )
        assert [(row.model_id, row.status, row.error_code) for row in records] == [
            ("gpt-4", "failure", "QUOTA_EXHAUSTED"),
            ("claude-3", "success", None),
        ]
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_task_manager_persists_all_retry_failures_without_placeholder_rows(mock_models):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from jreg.models.db import Base, ModelAttempt
    from jreg.services.task_manager import TaskManager

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        manager = TaskManager(
            session,
            Router(mock_models[:1], {"openai": MockAdapter({"gpt-4": "rate_limit"})}),
        )
        task = manager.create_task("test failed attempts")
        with pytest.raises(ProviderError):
            await manager.run_task(task.id, profile(max_retries=2))
        records = (
            session.query(ModelAttempt)
            .filter(ModelAttempt.task_id == task.id)
            .order_by(ModelAttempt.id)
            .all()
        )
        assert [(row.model_id, row.provider_id, row.status, row.error_code)
                for row in records] == [
            ("gpt-4", "openai", "failure", "RATE_LIMIT"),
            ("gpt-4", "openai", "failure", "RATE_LIMIT"),
            ("gpt-4", "openai", "failure", "RATE_LIMIT"),
        ]
        assert all(row.model_id != "N/A" for row in records)
    finally:
        session.close()
        engine.dispose()


def test_retry_count_is_bounded_by_profile_validation():
    with pytest.raises(ValidationError):
        profile(max_retries=11)
    with pytest.raises(ValidationError):
        profile(max_retries=-1)
